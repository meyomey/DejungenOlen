"""Gastronomie: Liste/Detail, Schnell-Übernahme (Duplikat-Schutz), Overpass-Suche mit Attrappe,
Öffnungszeiten-Helfer, geplante Einkehr."""
from unittest import mock

from tests.base import AppTestCase, appmod, db, M, FakeResponse

OVERPASS_ELEMENTS = {
    'elements': [
        {'type': 'node', 'id': 101, 'lat': 53.405, 'lon': 9.8005,
         'tags': {'amenity': 'cafe', 'name': 'Café Deichkrone', 'opening_hours': 'Mo-Fr 09:00-18:00; Sa,Su 10:00-18:00',
                  'addr:street': 'Deichstraße', 'addr:housenumber': '1', 'addr:city': 'Hollern'}},
        {'type': 'way', 'id': 202, 'center': {'lat': 53.45, 'lon': 9.801},
         'tags': {'amenity': 'restaurant', 'name': 'Zum Anker'}},
        {'type': 'node', 'id': 303, 'lat': 53.47, 'lon': 9.802, 'tags': {'shop': 'bakery', 'name': 'Bäcker Meyer'}},
        {'type': 'node', 'id': 404, 'lat': 53.48, 'lon': 9.803, 'tags': {'amenity': 'cafe'}},   # ohne Namen
    ]
}


class GastroTest(AppTestCase):

    def test_list_and_detail(self):
        self.login_member()
        html = self.get_html('/gastro')
        self.assertIn('Café Deichblick', html)
        html = self.get_html(f'/gastro/{self.spot_id}')
        self.assertIn('Café Deichblick', html)
        self.assertEqual(self.client.get('/gastro/999999').status_code, 404)

    def test_quick_add_and_duplicate_protection(self):
        self.login_org()
        payload = {'name': 'Neues Café', 'type': 'cafe', 'lat': 53.50, 'lng': 9.90,
                   'address': 'Dorfstraße 2', 'hours_text': 'Mo-So 08:00-18:00', 'osm_id': 'n555'}
        r = self.client.post('/api/gastro/quick-add', json=payload)
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        d = r.get_json()
        self.assertTrue(d['ok'] and not d['existing'] and d['id'])
        spot = db.session.get(M.GastroSpot, d['id'])
        self.assertEqual((spot.name, spot.spot_type, spot.osm_id), ('Neues Café', 'cafe', 'n555'))
        # gleicher OSM-Eintrag noch einmal → vorhandener Eintrag, kein Duplikat
        r = self.client.post('/api/gastro/quick-add', json=payload)
        self.assertTrue(r.get_json()['existing'])
        self.assertEqual(r.get_json()['id'], d['id'])
        # Pflichtfelder
        self.assertEqual(self.client.post('/api/gastro/quick-add', json={'name': 'X'}).status_code, 400)

    def _fake_post(self, responses):
        """Reihum-Antworten je Overpass-Server; merkt sich die aufgerufenen Endpunkte."""
        calls = []

        def _post(url, data=None, headers=None, timeout=None, **kw):
            calls.append((url, headers or {}, data or {}))
            resp = responses[min(len(calls) - 1, len(responses) - 1)]
            if isinstance(resp, Exception):
                raise resp
            return resp
        return _post, calls

    def test_overpass_bbox_search_mocked(self):
        self.login_member()
        appmod._overpass_cache.clear()
        post, calls = self._fake_post([FakeResponse(200, OVERPASS_ELEMENTS)])
        with mock.patch.object(appmod.http_requests, 'post', side_effect=post):
            r = self.client.get('/api/overpass-gastro?s=53.40&w=9.79&n=53.49&e=9.81')
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        d = r.get_json()
        names = [x['name'] for x in d['results']]
        self.assertIn('Café Deichkrone', names)
        self.assertIn('Zum Anker', names)               # way mit center
        self.assertIn('Bäcker Meyer', names)            # shop=bakery
        self.assertEqual(len(calls), 1)
        ua = calls[0][1].get('User-Agent', '')
        self.assertTrue(ua and 'python-requests' not in ua.lower(), f'eigener User-Agent nötig (406): {ua!r}')
        # zweiter Aufruf kommt aus dem Cache – kein weiterer Netzzugriff
        with mock.patch.object(appmod.http_requests, 'post', side_effect=post):
            r2 = self.client.get('/api/overpass-gastro?s=53.40&w=9.79&n=53.49&e=9.81')
        self.assertTrue(r2.get_json()['cached'])
        self.assertEqual(len(calls), 1)

    def test_overpass_fallback_and_failure(self):
        self.login_member()
        appmod._overpass_cache.clear()
        # 1. Server 406, 2. Server liefert
        post, calls = self._fake_post([FakeResponse(406, text='Not Acceptable'), FakeResponse(200, OVERPASS_ELEMENTS)])
        with mock.patch.object(appmod.http_requests, 'post', side_effect=post):
            r = self.client.get('/api/overpass-gastro?s=53.10&w=9.70&n=53.19&e=9.75')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(calls), 2)
        self.assertEqual(r.get_json()['source'], calls[1][0].split('/')[2])
        # alle Server weg → 502 mit Abfrage für den Browser-Fallback
        appmod._overpass_cache.clear()
        post, calls = self._fake_post([appmod.http_requests.exceptions.Timeout()])
        with mock.patch.object(appmod.http_requests, 'post', side_effect=post):
            r = self.client.get('/api/overpass-gastro?s=53.20&w=9.70&n=53.29&e=9.75')
        self.assertEqual(r.status_code, 502)
        self.assertIn('query', r.get_json())
        self.assertEqual(len(calls), len(appmod.OVERPASS_ENDPOINTS))
        # zu großer Ausschnitt
        self.assertEqual(self.client.get('/api/overpass-gastro?s=53&w=9&n=54&e=10').status_code, 400)

    def test_osm_search_along_track(self):
        self.login_org()
        appmod._overpass_cache.clear()
        post, calls = self._fake_post([FakeResponse(200, OVERPASS_ELEMENTS)])
        with mock.patch.object(appmod.http_requests, 'post', side_effect=post):
            r = self.client.get(f'/api/touren/{self.t_done_id}/osm-gastro?radius=250')
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        d = r.get_json()
        self.assertTrue(d['results'])
        first = d['results'][0]
        for key in ('name', 'km', 'dist_m', 'lat', 'lng', 'type_label'):
            self.assertIn(key, first)
        self.assertIn('around:', calls[0][2].get('data', ''), 'Streckensuche nutzt eine around-Polyline')
        kms = [x['km'] for x in d['results']]
        self.assertEqual(kms, sorted(kms), 'Treffer sind nach Streckenkilometer sortiert')
        # Tour ohne GPX → 400
        self.assertEqual(self.client.get(f'/api/touren/{self.t_open_id}/osm-gastro').status_code, 400)

    def test_hours_helpers(self):
        self.assertEqual(appmod.hours_de('Mo-Fr 08:00-18:00; Su off'), 'Mo–Fr 08:00–18:00 · So geschlossen')
        self.assertEqual(appmod.hours_de(''), '')
        self.assertEqual(appmod.closed_days('Mo off; Tu-Su 11:00-22:00'), ['Mo'])
        self.assertEqual(appmod.closed_days('Montag Ruhetag'), ['Mo'])
        self.assertEqual(appmod.closed_days('Mo-We off'), ['Mo', 'Di', 'Mi'])
        self.assertEqual(appmod.closed_days(None), [])

    def test_einkehr_from_map(self):
        self.login_org()
        r = self.client.post(f'/touren/{self.t_plan_id}/einkehr', json={'spot_id': self.spot_id})
        d = r.get_json()
        self.assertEqual((r.status_code, d['ok'], d['spot_id']), (200, True, self.spot_id))
        self.assertTrue(d['text'].startswith('Café Deichblick'))
        html = self.get_html(f'/touren/{self.t_plan_id}')
        self.assertIn('CAN_SET_EINKEHR = true', html)
        self.assertIn('"name": "Caf', html.replace('&#34;', '"'))
        # unbekannter Eintrag → Einkehr leer
        self.assertIsNone(self.client.post(f'/touren/{self.t_plan_id}/einkehr', json={'spot_id': 999999}).get_json()['spot_id'])
        info = appmod._einkehr_info(self.tour(self.t_plan_id))
        self.assertIsNone(info)

    def test_einkehr_in_morning_reminder(self):
        t = self.tour(self.t_plan_id)
        t.gastro_spot_id = self.spot_id
        db.session.add(M.TourParticipant(tour_id=t.id, user_id=self.mem_id, status='attending'))
        db.session.commit()
        appmod._send_morning_reminder_for_tour(self.tour(self.t_plan_id))
        self.assertTrue(self.telegrams and 'Einkehr: Café Deichblick' in self.telegrams[0])
        self.assertTrue(self.pushes and 'Einkehr: Café Deichblick' in self.pushes[0][2])


class MittagstischTest(AppTestCase):
    """Build z: Mittagstisch – Öffnungszeiten-Auswertung, OSM-Tags, Filter, Formular, Einkehr-Hinweis."""

    EN = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']

    def test_noon_parser(self):
        nd = appmod.noon_days
        self.assertEqual(nd('Mo-Fr 11:30-14:00,17:00-22:00'), ['Mo', 'Tu', 'We', 'Th', 'Fr'])
        self.assertEqual(nd('Mo-Th 17:00-23:00; Fr-Su 11:30-23:00'), ['Fr', 'Sa', 'Su'])
        self.assertEqual(nd('Mo off; Tu-Su 11:00-22:00'), ['Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'])
        self.assertEqual(nd('Mo-Sa 09:00-18:00; PH off'), ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'])
        self.assertEqual(nd('24/7'), self.EN)
        self.assertEqual(nd('Mo-Su 11:00+'), self.EN)
        self.assertEqual(nd('Mo-Su 13:00-18:00'), [], 'erst ab 13 Uhr offen zählt nicht als Mittagszeit')
        self.assertEqual(nd('Mo-Fr 11:00-12:45'), [])
        # deutscher Freitext
        self.assertEqual(nd('Di–So 9–18 Uhr'), ['Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'])
        self.assertEqual(nd('Montag Ruhetag, Di–So 11.30–14 Uhr und 17–22 Uhr'), ['Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'])
        self.assertEqual(nd('Dienstag bis Sonntag 11:30 bis 21:00 Uhr, Montag Ruhetag'), ['Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'])
        self.assertEqual(nd('täglich 10-22 Uhr'), self.EN)
        # nichts Verwertbares → None (keine Aussage), nicht „geschlossen“
        for txt in ('', None, 'nach Vereinbarung', 'Mo Ruhetag', 'Ruhetag: Montag'):
            self.assertIsNone(nd(txt), txt)
        # Küchenzeiten gehen vor
        self.assertEqual(nd('Mo-Su 10:00-24:00', 'Mo-Su 17:00-21:00'), [])
        self.assertEqual(nd('Mo-Su 10:00-24:00', 'Mo-Fr 12:00-14:00,17:00-21:00'), ['Mo', 'Tu', 'We', 'Th', 'Fr'])
        self.assertEqual(appmod.days_de(['Mo', 'Tu', 'We', 'Th', 'Fr']), 'Mo–Fr')
        self.assertEqual(appmod.days_de(['Tu', 'Th', 'Sa']), 'Di, Do, Sa')
        self.assertEqual(appmod.days_de(self.EN), 'täglich')

    def test_lunch_info(self):
        sp = M.GastroSpot(name='x', spot_type='restaurant', lat=1, lng=1, hours_text='Mo off; Tu-Su 11:00-22:00')
        info = appmod.lunch_info(sp)
        self.assertEqual((info['status'], info['days_de']), ('noon', 'Di–So'))
        self.assertIn('mittags geöffnet Di–So', info['label'])
        sp.lunch, sp.lunch_text = 'yes', 'Wochenkarte 9,50 €'
        self.assertEqual(appmod.lunch_info(sp)['label'], '🍽️ Mittagstisch: Wochenkarte 9,50 €')
        sp.lunch = 'no'
        self.assertEqual(appmod.lunch_info(sp)['status'], 'no')
        sp.lunch, sp.hours_text, sp.opens_at, sp.closes_at = None, None, '14:00', '22:00'
        self.assertEqual(appmod.lunch_info(sp)['status'], 'noon_closed')
        sp.opens_at = None
        self.assertIsNone(appmod.lunch_info(sp)['status'])

    def test_osm_tags_mapping(self):
        elements = [
            {'type': 'node', 'id': 1, 'lat': 53.4, 'lon': 9.8,
             'tags': {'amenity': 'restaurant', 'name': 'Landgasthof', 'opening_hours': 'Mo-Su 10:00-23:00',
                      'opening_hours:kitchen': 'Mo-Fr 11:30-14:00,17:30-21:00', 'cuisine': 'german;regional'}},
            {'type': 'node', 'id': 2, 'lat': 53.4, 'lon': 9.8,
             'tags': {'amenity': 'restaurant', 'name': 'Trattoria', 'lunch': 'yes', 'lunch:menu': 'Mo-Fr 12:00-14:30'}},
            {'type': 'node', 'id': 3, 'lat': 53.4, 'lon': 9.8,
             'tags': {'amenity': 'pub', 'name': 'Abendkneipe', 'lunch': 'no', 'opening_hours': 'Mo-Su 17:00-01:00'}},
            {'type': 'node', 'id': 4, 'lat': 53.4, 'lon': 9.8, 'tags': {'amenity': 'cafe', 'name': 'Ohne Zeiten'}},
        ]
        res = {r['name']: r for r in appmod._overpass_elements_to_results(elements)}
        lg = res['Landgasthof']
        self.assertEqual((lg['lunch_status'], lg['noon_days']), ('noon', ['Mo', 'Di', 'Mi', 'Do', 'Fr']),
                         'Küchenzeiten entscheiden, nicht die Öffnungszeiten der Gaststube')
        self.assertEqual((lg['cuisine'], lg['kitchen_hours']), ('deutsch, regional', 'Mo-Fr 11:30-14:00,17:30-21:00'))
        tr = res['Trattoria']
        self.assertEqual((tr['lunch'], tr['lunch_status']), ('yes', 'yes'))
        self.assertIn('Mittagsmenü Mo–Fr 12:00–14:30', tr['lunch_text'])
        self.assertEqual(res['Abendkneipe']['lunch_status'], 'no')
        oz = res['Ohne Zeiten']
        self.assertEqual((oz['lunch_status'], oz['noon_known'], oz['noon_days']), (None, False, []))
        # Felder kommen auch über die Streckensuche beim Browser an
        self.login_org()
        appmod._overpass_cache.clear()
        with mock.patch.object(appmod.http_requests, 'post',
                               return_value=FakeResponse(200, {'elements': elements})):
            d = self.client.get(f'/api/touren/{self.t_done_id}/osm-gastro?radius=1000').get_json()
        self.assertTrue(d['results'])
        for key in ('lunch_status', 'lunch_label', 'noon_days', 'cuisine', 'kitchen_hours'):
            self.assertIn(key, d['results'][0])

    def _spots(self):
        """Vier Einträge mit unterschiedlicher Mittagstisch-Lage anlegen (einmal je Klasse)."""
        if getattr(self.__class__, '_lunch_ids', None):
            return self.__class__._lunch_ids
        mk = lambda name, **kw: M.GastroSpot(name=name, spot_type='restaurant', lat=53.5, lng=9.9, added_by=self.org_id, **kw)
        a = mk('Gasthof Mittagstisch', lunch='yes', lunch_text='Mo–Fr 11:30–14:00 Wochenkarte')
        b = mk('Deichkrug', hours_text='Mo-Fr 11:30-14:00,17:00-22:00; Sa,Su 17:00-22:00')
        c = mk('Abendrestaurant', hours_text='Mo-Su 17:00-23:00')
        d = mk('Unbekanntes Café')
        db.session.add_all([a, b, c, d])
        db.session.commit()
        self.__class__._lunch_ids = {'yes': a.id, 'noon': b.id, 'closed': c.id, 'none': d.id}
        return self.__class__._lunch_ids

    def test_list_filter_and_badges(self):
        ids = self._spots()
        self.login_member()
        html = self.get_html('/gastro')
        self.assertIn('id="f-mittag"', html)
        self.assertIn('osm_gastro.js', html)
        self.assertIn('🍽️ Mittagstisch', html)
        self.assertIn('mittags geöffnet Mo–Fr', html)
        self.assertIn('mittags geschlossen', html)
        self.assertIn('data-lunch="noon" data-noon="Mo,Di,Mi,Do,Fr"', html)
        # Filter „ja / mittags offen“
        html = self.get_html('/gastro?mittag=1')
        self.assertIn('Gasthof Mittagstisch', html)
        self.assertIn('Deichkrug', html)
        self.assertNotIn('Abendrestaurant', html)
        self.assertNotIn('Unbekanntes Café', html)
        # Filter nach Wochentag: Samstag → nur der bestätigte Mittagstisch (Deichkrug hat Sa zu)
        html = self.get_html('/gastro?mittag=Sa')
        self.assertIn('Gasthof Mittagstisch', html)
        self.assertNotIn('Deichkrug', html)
        html = self.get_html('/gastro?mittag=Mi')
        self.assertIn('Deichkrug', html)
        # ungültiger Wert → ignoriert
        html = self.get_html('/gastro?mittag=xx')
        self.assertIn('Abendrestaurant', html)
        # Detailseite
        html = self.get_html(f"/gastro/{ids['yes']}")
        self.assertIn('id="mittagstisch"', html)
        self.assertIn('Wochenkarte', html)
        html = self.get_html(f"/gastro/{ids['closed']}")
        self.assertIn('mittags geschlossen', html)

    def test_form_and_quick_add_save_lunch(self):
        self.login_org()
        r = self.client.post('/gastro/neu', data={
            'name': 'Formular-Gasthaus', 'spot_type': 'restaurant', 'lat': '53.70', 'lng': '9.70',
            'hours_text': 'Di–So 11–22 Uhr', 'lunch': 'yes', 'lunch_text': 'Mo–Fr Mittagskarte'}, follow_redirects=False)
        self.assertEqual(r.status_code, 302, r.get_data(as_text=True)[:300])
        sp = M.GastroSpot.query.filter_by(name='Formular-Gasthaus').first()
        self.assertEqual((sp.lunch, sp.lunch_text), ('yes', 'Mo–Fr Mittagskarte'))
        html = self.get_html(f'/gastro/{sp.id}/bearbeiten')
        self.assertIn('id="flunch1" value="yes" checked', html)
        self.assertIn('value="Mo–Fr Mittagskarte"', html)
        # ungültiger Wert → keine Angabe
        r = self.client.post(f'/gastro/{sp.id}/bearbeiten', data={
            'name': 'Formular-Gasthaus', 'spot_type': 'restaurant', 'lat': '53.70', 'lng': '9.70',
            'hours_text': 'Di–So 11–22 Uhr', 'lunch': 'vielleicht', 'lunch_text': ''})
        self.assertIn(r.status_code, (200, 302))
        db.session.expire_all()
        sp = db.session.get(M.GastroSpot, sp.id)
        self.assertIsNone(sp.lunch)
        self.assertEqual(appmod.lunch_info(sp)['status'], 'noon', 'ohne Angabe aus den Öffnungszeiten abgeleitet')
        # Schnell-Übernahme aus der OSM-Suche
        r = self.client.post('/api/gastro/quick-add', json={
            'name': 'OSM-Gasthof', 'type': 'restaurant', 'lat': 53.71, 'lng': 9.71, 'osm_id': 'node/777',
            'hours_text': 'Mo-Su 10:00-23:00', 'lunch': 'yes', 'lunch_text': 'Mittagsmenü Mo–Fr 12:00–14:30'})
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        sp2 = db.session.get(M.GastroSpot, r.get_json()['id'])
        self.assertEqual((sp2.lunch, sp2.lunch_text), ('yes', 'Mittagsmenü Mo–Fr 12:00–14:30'))

    def test_einkehr_lunch_hint(self):
        import datetime as dt
        ids = self._spots()
        t = self.tour(self.t_plan_id)
        t.gastro_spot_id = ids['noon']                       # Deichkrug: mittags nur Mo–Fr, Sa/So erst ab 17 Uhr
        t.tour_date = dt.date(2026, 10, 17)                  # Samstag
        db.session.commit()
        info = appmod._einkehr_info(self.tour(self.t_plan_id))
        self.assertEqual(info['lunch'], 'noon')
        self.assertTrue(info['noon_warn'], 'Samstag: laut Öffnungszeiten mittags zu')
        self.assertIn('mittags geschlossen?', appmod._tour_einkehr_text(self.tour(self.t_plan_id)))
        self.login_org()
        html = self.get_html(f'/touren/{self.t_plan_id}')
        self.assertIn('mittags geschlossen am Tourtag?', html)
        self.assertIn('id="osm-gastro-lunch"', html)
        t = self.tour(self.t_plan_id)
        t.tour_date = dt.date(2026, 10, 16)                  # Freitag
        db.session.commit()
        info = appmod._einkehr_info(self.tour(self.t_plan_id))
        self.assertFalse(info['noon_warn'])
        t = self.tour(self.t_plan_id)
        t.gastro_spot_id = ids['yes']
        db.session.commit()
        txt = appmod._tour_einkehr_text(self.tour(self.t_plan_id))
        self.assertIn('Mittagstisch: Mo–Fr 11:30–14:00 Wochenkarte', txt)
        html = self.get_html(f'/touren/{self.t_plan_id}')
        self.assertIn('🍽️ Mittagstisch', html)

    def test_static_js_served(self):
        r = self.client.get('/static/js/osm_gastro.js')
        self.assertEqual(r.status_code, 200)
        body = r.get_data(as_text=True)
        for fn in ('function osmNoonDays', 'function lunchMatches', 'function lunchBadgeHtml', 'function osmLunchEnrich'):
            self.assertIn(fn, body)
        self.assertNotIn('(?<', body, 'kein Lookbehind – ältere Safari-Versionen')
