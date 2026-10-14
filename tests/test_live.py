"""Build aa: Live-Karte (/touren/<id>/live + /api/location/*) und Gruppen-Karte (/karte)."""
import datetime as dt
from unittest import mock

from tests.base import AppTestCase, app, appmod, db, M


class LiveTest(AppTestCase):

    # ── Hilfsfunktionen ──
    def test_initials(self):
        f = appmod._initials
        self.assertEqual(f('Hein Mück'), 'HM')
        self.assertEqual(f('Fiete'), 'FI')
        self.assertEqual(f('Karl-Heinz Müller'), 'KM')
        self.assertEqual(f(''), '?')
        self.assertEqual(f(None), '?')

    def test_share_window(self):
        with app.test_request_context():
            t = self.tour(self.t_plan_id)
            mem, org = self.user(self.mem_id), self.user(self.org_id)
            d = t.tour_date
            self.assertFalse(appmod._live_share_window(t, mem, d - dt.timedelta(days=10))[0])
            self.assertTrue(appmod._live_share_window(t, mem, d - dt.timedelta(days=1))[0])
            self.assertTrue(appmod._live_share_window(t, mem, d)[0])
            self.assertTrue(appmod._live_share_window(t, mem, d + dt.timedelta(days=1))[0])
            ok, hint = appmod._live_share_window(t, mem, d + dt.timedelta(days=2))
            self.assertFalse(ok)
            self.assertIn('liegt zurück', hint)
            # Organisatoren dürfen immer (ausprobieren/vorführen), abgesagt nie
            self.assertTrue(appmod._live_share_window(t, org, d - dt.timedelta(days=10))[0])
            ok, hint = appmod._live_share_window(self.tour(self.t_canc_id), org, d)
            self.assertFalse(ok)
            self.assertIn('abgesagt', hint)
            ok, hint = appmod._live_share_window(self.tour(self.t_open_id), mem, d)
            self.assertFalse(ok)
            self.assertIn('Termin', hint)

    def test_open_now(self):
        f = appmod.open_now
        mon10 = dt.datetime(2026, 10, 12, 10, 0)      # Montag
        self.assertEqual(f('Mo-Fr 09:00-18:00; Sa,So 10:00-18:00', now=mon10), ('open', '18:00'))
        self.assertEqual(f('Mo-Fr 09:00-18:00', now=mon10.replace(hour=8)), ('closed', '09:00'))
        self.assertEqual(f('Mo-Fr 09:00-18:00', now=mon10.replace(hour=19)), ('closed', ''))
        self.assertEqual(f('Mo off; Di-So 11:00-22:00', now=mon10), ('closed', ''))
        self.assertEqual(f('Mo off; Di-So 11:00-22:00', now=mon10 + dt.timedelta(days=1, hours=2)), ('open', '22:00'))
        self.assertEqual(f('Fr 20:00-02:00', now=dt.datetime(2026, 10, 17, 1, 0)), ('open', '02:00'))   # Sa 01:00
        self.assertEqual(f('Di-So', now=mon10 + dt.timedelta(days=1)), ('open', ''))
        self.assertEqual(f('', now=mon10), (None, ''))
        self.assertEqual(f(None, '09:00', '17:00', now=mon10), ('open', '17:00'))   # nur Felder öffnet/schließt
        self.assertEqual(f('Mo-Fr 09:00-18:00', now=mon10.replace(hour=12, minute=0))[0], 'open')

    def test_migration_added_speed_heading(self):
        cols = {c['name'] for c in db.inspect(db.engine).get_columns('live_locations')}
        self.assertTrue({'speed', 'heading'} <= cols, cols)

    # ── API ──
    def _post(self, tour_id, **extra):
        body = {'tour_id': tour_id, 'lat': 53.4, 'lng': 9.8, 'accuracy': 12}
        body.update(extra)
        return self.client.post('/api/location/update', json=body)

    def test_member_cannot_share_ten_days_before(self):
        self.login_member()
        r = self._post(self.t_plan_id)
        self.assertEqual(r.status_code, 403)
        self.assertIn('Vortag', r.get_json()['error'])
        self.assertEqual(M.LiveLocation.query.filter_by(user_id=self.mem_id).count(), 0)
        # abgesagte Tour: auch für Organisatoren nicht
        self.login_org()
        self.assertEqual(self._post(self.t_canc_id).status_code, 403)

    def test_member_can_share_on_tour_day_and_watch_only_otherwise(self):
        tour_day = self.tour(self.t_plan_id).tour_date
        self.login_member()
        with mock.patch.object(appmod, '_berlin_today', return_value=tour_day):
            r = self._post(self.t_plan_id, speed=5.5, heading=90, foo='bar')
            self.assertEqual(r.status_code, 200)
            d = r.get_json()
            self.assertTrue(d['ok'])
            me = [x for x in d['locations'] if x['user_id'] == self.mem_id][0]
            self.assertEqual((me['name'], me['initials'], me['speed'], me['heading']), ('Hein Mück', 'HM', 5.5, 90.0))
            self.assertLessEqual(me['ago'], 2)
            # Unsinnige Werte werden verworfen, Koordinaten geprüft
            r = self._post(self.t_plan_id, speed=999, heading=-5)
            me = [x for x in r.get_json()['locations'] if x['user_id'] == self.mem_id][0]
            self.assertEqual((me['speed'], me['heading']), (None, None))
            self.assertEqual(self._post(self.t_plan_id, lat=95).status_code, 400)
            self.assertEqual(self.client.post('/api/location/update', json={'tour_id': self.t_plan_id}).status_code, 400)
            self.assertEqual(M.LiveLocation.query.filter_by(tour_id=self.t_plan_id, user_id=self.mem_id).count(), 1)
        # Zuschauen: anderes Mitglied sieht den Standort, ohne selbst zu teilen
        self.login('fiete@test.de')
        r = self.client.get(f'/api/location/tour/{self.t_plan_id}')
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertEqual(d['stale_s'], 900)
        self.assertIn(self.mem_id, [x['user_id'] for x in d['locations']])
        # Fremde Gruppe: 404
        self.login('fremd@test.de')
        self.assertEqual(self.client.get(f'/api/location/tour/{self.t_plan_id}').status_code, 404)
        # Stop per sendBeacon-URL (leerer Body)
        self.login_member()
        self.assertEqual(self.client.post('/api/location/stop').status_code, 400)
        r = self.client.post(f'/api/location/stop?tour_id={self.t_plan_id}', data='')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(M.LiveLocation.query.filter_by(tour_id=self.t_plan_id, user_id=self.mem_id).count(), 0)

    def test_stale_rows_hidden_and_cleanup(self):
        now = dt.datetime.utcnow()
        db.session.add_all([
            M.LiveLocation(tour_id=self.t_done_id, user_id=self.org_id, lat=53.0, lng=9.0, updated_at=now - dt.timedelta(minutes=2)),
            M.LiveLocation(tour_id=self.t_done_id, user_id=self.mem2_id, lat=53.0, lng=9.0, updated_at=now - dt.timedelta(minutes=20)),
            M.LiveLocation(tour_id=self.t_done_id, user_id=self.admin_id, lat=53.0, lng=9.0, updated_at=now - dt.timedelta(hours=30)),
        ])
        db.session.commit()
        with app.test_request_context():
            ids = [x['user_id'] for x in appmod._live_locations_payload(self.t_done_id, now)]
        self.assertEqual(ids, [self.org_id])                      # 20 min und 30 h alt: ausgeblendet
        self.assertEqual(appmod._live_cleanup(now), 1)            # nur die 30 h alte Zeile wird gelöscht
        db.session.commit()
        self.assertEqual(M.LiveLocation.query.filter_by(tour_id=self.t_done_id).count(), 2)

    # ── Seiten ──
    def test_live_page_member_watch_only(self):
        self.login_member()
        html = self.get_html(f'/touren/{self.t_plan_id}/live')
        self.assertIn('Live-Karte: Deichtour, mit Komma', html)
        self.assertIn('id="btn-share"', html)
        self.assertIn('disabled title="Standort teilen geht ab dem Vortag', html)
        self.assertIn('const CAN_SHARE = false', html)
        self.assertIn('"initials": "HM"', html)
        self.assertIn('Bahnhof, Gleis 1', html)                    # Treffpunkt
        self.assertRegex(html, r'const TRACK\s*=\s*\[\[\d')         # vereinfachter GPX-Track
        self.assertIn('Karte folgt mir', html)
        self.assertIn('Alle zeigen', html)
        # Fremde Tour
        self.assertEqual(self.client.get(f'/touren/{self.t_fremd_id}/live').status_code, 404)

    def test_live_page_organizer_can_share(self):
        self.login_org()
        html = self.get_html(f'/touren/{self.t_plan_id}/live')
        self.assertIn('const CAN_SHARE = true', html)
        self.assertNotIn('disabled title=', html)
        html = self.get_html(f'/touren/{self.t_open_id}/live')
        self.assertIn('Termin offen', html)
        self.assertIn('const TRACK     = []', html)

    def test_detail_links_to_live_page(self):
        self.login_member()
        html = self.get_html(f'/touren/{self.t_plan_id}')
        self.assertIn(f'/touren/{self.t_plan_id}/live', html)
        self.assertIn('id="live-hint"', html)
        self.assertNotIn('toggleLiveLocation', html)
        self.assertNotIn('_pollLiveLocations', html)
        html = self.get_html(f'/touren/{self.t_done_id}')           # 30 Tage her: keine Live-Leiste
        self.assertNotIn('id="live-hint"', html)
        self.assertNotIn(f'/touren/{self.t_done_id}/live', html)

    def test_gruppenkarte(self):
        t = self.tour(self.t_open_id)
        t.meeting_lat, t.meeting_lng, t.meeting_desc = 52.96, 9.09, 'Dörphus'
        db.session.commit()
        self.login_member()
        html = self.get_html('/karte')
        self.assertIn('Gruppen-Karte', html)
        self.assertIn('js/osm_gastro.js', html)
        for fid in ('f-q', 'f-type', 'f-morning', 'f-lunch', 'f-open'):
            self.assertIn(f'id="{fid}"', html)
        self.assertIn('option value="kneipe"', html)
        self.assertIn('"open_now"', html)
        self.assertIn('"lunch_status"', html)
        self.assertIn('"closed": ["Mo"]', html)                    # Zur alten Mühle: Ruhetag
        self.assertIn('"date": "offen"', html)                     # Termin-offen-Tour statt 31.12.9999
        self.assertNotIn('31.12.9999', html)
        self.assertIn('"upcoming": true', html)
        self.assertIn(f'"url": "/gastro/{self.spot_id}"', html)
        self.assertIn(f'"url": "/touren/{self.t_plan_id}"', html)
        self.assertIn('const HOME     = {"lat": 52.9637', html)    # Standard-Treffpunkt als Startansicht
        self.assertIn('markerClusterGroup', html)
        self.assertNotIn('tap:', html)
        # Menü und Hilfe
        self.assertIn('Gruppen-Karte</a>', html)
        self.assertNotIn('Live-Karte</a></li>', html)
        self.assertIn('Gruppen-Karte', self.get_html('/hilfe'))
