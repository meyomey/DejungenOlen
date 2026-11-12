"""Build ca: zwei Meldungen zum Tour-Video.

**Meldung 1 – Einkehr doppelt:**
    „Im letzten Video sind wir nur einmal eingekehrt, im erzeugten Video stehen bei
    Einkehr zwei Positionen obwohl nur eine eingetragen ist."

**Meldung 2 – Namen statt Zähler im Einstiegsbild:**
    „Ich war dabei und zwei Leute waren als Gast dabei. Im Einstiegsbild des Videos
    sollen die Avatare mit Namen erscheinen auch für Gäste und nicht nur ‚3 dabei' stehen."

Beides ist am echten Code nachgemessen:

Ursache 1 – Der Zusammenbau der Folie filterte die Streckenfunde ausschließlich über
`id`. Derselbe Ort kann aber zweimal in `gastro_spots` stehen (einmal per
OpenStreetMap-Import, einmal von Hand angelegt) – dann hat der geplante Stopp eine
andere id als der Streckenfund und der zweite Datensatz rutschte durch.
Nachgestellt: geplant = [(1, 'Gasthof Adler')], Strecke = [(1, …), (2, …)],
Folie vorher = 2 Positionen, nachher = 1.

Ursache 2 – `tour_headcount` zählt Mitglieder UND Gäste (3), die Avatar-Liste enthielt
aber nur die Mitglieder (1). Das Einstiegsbild malte überhaupt keine Avatare, nur den
Text „3 dabei". Ohne Gäste hätte die Zeile selbst dann nur ein Gesicht gezeigt.
"""
import os

from tests.base import AppTestCase, appmod, db, M

EINKEHR_MERGE = '''def _einkehr_merge_dedup(planned_list, near_spots):'''


def _lies_app():
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app.py'),
              encoding='utf-8') as f:
        return f.read()


class EinkehrDubletteTest(AppTestCase):
    """Meldung 1: genau so viele Einkehr-Einträge wie eingetragen."""

    def _points(self):
        return [{'lat': 53.400, 'lng': 9.800},
                {'lat': 53.401, 'lng': 9.800},
                {'lat': 53.402, 'lng': 9.800}]

    def test_gleicher_ort_zwei_datensaetze_ergibt_einen_eintrag(self):
        """Der gemeldete Fall: ein Ort, zwei Datensätze (OSM-Import + Handanlage)."""
        from tests.base import app as flask_app
        with flask_app.app_context():
            # Denselben Namen, fast dieselbe Stelle – nur zwei Datensätze.
            sp_osm = M.GastroSpot(name='Gasthof Adler', spot_type='restaurant',
                                  lat=53.4010, lng=9.8000, osm_id='node/4242')
            sp_hand = M.GastroSpot(name='Gasthof Adler', spot_type='kneipe',
                                   lat=53.4011, lng=9.8001)
            db.session.add_all([sp_osm, sp_hand])
            db.session.commit()
            try:
                tour = M.Tour(title='Doppelte Einkehr', status='planned',
                              tour_date=None, created_by=self.org_id, group_id=self.g1_id)
                db.session.add(tour)
                db.session.commit()
                tour.gastro_spot_id = sp_osm.id
                db.session.commit()

                planned = appmod._planned_einkehr_entries(tour, self._points())
                near = appmod.gastro_near_track(self._points())

                # Vorbedingung: der Fehler wäre ohne die Entdopplung reproduzierbar.
                self.assertGreaterEqual(len(near), 1)
                ids_only = planned + [s for s in near if s.get('id') not in {e['id'] for e in planned}]
                self.assertEqual(len(ids_only), 2, 'ohne Entdopplung stünden hier zwei Positionen')

                merged = appmod._einkehr_merge_dedup(planned, near)
                self.assertEqual(len(merged), 1,
                                 f'erwartet 1 Einkehr, bekommen {len(merged)}: '
                                 f'{[e["name"] for e in merged]}')
                self.assertEqual(merged[0]['name'], 'Gasthof Adler')
            finally:
                M.Tour.query.filter_by(title='Doppelte Einkehr').delete()
                db.session.delete(sp_osm)
                db.session.delete(sp_hand)
                db.session.commit()

    def test_zwei_verschiedene_orte_bleiben_beide(self):
        """Gegenprobe: die Entdopplung darf echte Einkehren nicht verschlucken."""
        from tests.base import app as flask_app
        with flask_app.app_context():
            planned = [{'id': 1, 'name': 'Gasthof Adler', 'lat': 53.401, 'lng': 9.800}]
            near = [{'id': 1, 'name': 'Gasthof Adler', 'lat': 53.401, 'lng': 9.800},
                    {'id': 2, 'name': 'Bäckerei Kern', 'lat': 53.600, 'lng': 9.950}]
            merged = appmod._einkehr_merge_dedup(planned, near)
            self.assertEqual(len(merged), 2)
            self.assertEqual([e['name'] for e in merged], ['Gasthof Adler', 'Bäckerei Kern'])

    def test_gleicher_name_etwas_weiter_weg_ist_noch_derselbe_ort(self):
        """Bis 100 m gleicher Name = derselbe Ort (wie `_gastro_match_known`)."""
        from tests.base import app as flask_app
        with flask_app.app_context():
            planned = [{'id': 1, 'name': 'Gasthof Adler', 'lat': 53.4010, 'lng': 9.8000}]
            # ~78 m nördlich, gleicher Name
            near = [{'id': 2, 'name': 'gasthof  adler', 'lat': 53.4017, 'lng': 9.8000}]
            merged = appmod._einkehr_merge_dedup(planned, near)
            self.assertEqual(len(merged), 1)

    def test_zu_weit_weg_ist_ein_anderer_ort(self):
        """Gleicher Name, aber 300 m entfernt = eigener Eintrag."""
        from tests.base import app as flask_app
        with flask_app.app_context():
            planned = [{'id': 1, 'name': 'Gasthof Adler', 'lat': 53.4010, 'lng': 9.8000}]
            near = [{'id': 2, 'name': 'Gasthof Adler', 'lat': 53.4037, 'lng': 9.8000}]
            merged = appmod._einkehr_merge_dedup(planned, near)
            self.assertEqual(len(merged), 2)

    def test_drei_bewusst_eingetragene_stopps_bleiben_drei(self):
        """Build bh erlaubt drei Stopps – die dürfen sich nicht gegenseitig aufheben."""
        from tests.base import app as flask_app
        with flask_app.app_context():
            sp = []
            for i in range(3):
                s = M.GastroSpot(name=f'Stopp Nummer {i}', spot_type='cafe',
                                 lat=53.401 + i * 0.0001, lng=9.800, osm_id=f'node/77{i}')
                db.session.add(s)
                sp.append(s)
            db.session.commit()
            try:
                tour = M.Tour(title='Drei Stopps', status='planned', tour_date=None,
                              created_by=self.org_id, group_id=self.g1_id)
                db.session.add(tour)
                db.session.commit()
                tour.gastro_spot_id = sp[0].id
                tour.einkehr2_spot_id = sp[1].id
                tour.einkehr3_spot_id = sp[2].id
                db.session.commit()
                planned = appmod._planned_einkehr_entries(tour, self._points())
                self.assertEqual(len(planned), 3)
                merged = appmod._einkehr_merge_dedup(planned, [])
                self.assertEqual(len(merged), 3, 'bewusst gesetzte Stopps wurden zusammengelegt')
            finally:
                M.Tour.query.filter_by(title='Drei Stopps').delete()
                for s in sp:
                    db.session.delete(s)
                db.session.commit()

    def test_freitext_einkehr_erscheint_auf_der_folie(self):
        """Eine Einkehr ohne Gastro-Eintrag (nur Freitext) fehlte bisher ganz."""
        from tests.base import app as flask_app
        with flask_app.app_context():
            tour = M.Tour(title='Freitext-Einkehr', status='planned', tour_date=None,
                          created_by=self.org_id, group_id=self.g1_id)
            tour.einkehr_text = 'Almhütte Sonnenberg'
            db.session.add(tour)
            db.session.commit()
            try:
                entries = appmod._planned_einkehr_entries(tour, self._points())
                self.assertEqual(len(entries), 1)
                self.assertEqual(entries[0]['name'], 'Almhütte Sonnenberg')
                self.assertFalse(entries[0]['km_known'], 'ohne Position gibt es keinen km-Wert')
            finally:
                M.Tour.query.filter_by(title='Freitext-Einkehr').delete()
                db.session.commit()

    def test_ohne_einkehr_keine_erfundenen_eintraege(self):
        from tests.base import app as flask_app
        with flask_app.app_context():
            tour = M.Tour(title='Ohne Einkehr', status='planned', tour_date=None,
                          created_by=self.org_id, group_id=self.g1_id)
            db.session.add(tour)
            db.session.commit()
            try:
                self.assertEqual(appmod._planned_einkehr_entries(tour, self._points()), [])
            finally:
                M.Tour.query.filter_by(title='Ohne Einkehr').delete()
                db.session.commit()

    def test_video_route_nutzt_die_entdopplung(self):
        """Die Route darf nicht wieder auf den reinen id-Filter zurückfallen.
        Build cb: Die Route führt gar keine Streckenfunde mehr mit der Einkehr zusammen
        (nur eingetragene Einkehren) – der alte id-Filter darf trotzdem nicht zurückkommen."""
        src = _lies_app()
        self.assertIn('_near_spots = _planned_einkehr_entries(tour, _gpx_points)', src)
        self.assertNotIn("sp.get('id') not in _planned_ids", src)

    def test_osm_kennung_wird_mitgegeben(self):
        """Für die Entdopplung muss die OSM-Verknüpfung in beiden Quellen stehen."""
        src = _lies_app()
        block = src[src.index(EINKEHR_MERGE):]
        self.assertIn("a.get('osm_id')", block)
        # beide Erzeuger liefern das Feld
        self.assertRegex(src, r"found\.append\(\{'id': sp\.id, 'osm_id': getattr\(sp, 'osm_id', None\)")
        self.assertRegex(src, r"entry = \{'id': sp\.id, 'osm_id': getattr\(sp, 'osm_id', None\)")


class EinstiegsbildTest(AppTestCase):
    """Meldung 2: Avatare mit Namen für alle – auch für Gäste."""

    def _avatar_quelle(self, tour_id):
        """Genau die Logik aus der Video-Route (Teilnehmer + Gäste, deutsch sortiert)."""
        members = [(p.user.display_name, p.user.avatar) for p in
                   M.TourParticipant.query.filter_by(tour_id=tour_id, status='attending')
                   .join(M.User).all()]
        guests = [(g.name, None) for g in M.TourGuest.query.filter_by(tour_id=tour_id).all()]
        liste = members + guests
        liste.sort(key=lambda nv: appmod._de_name_key(nv[0]))
        return liste

    def test_gaeste_stehen_mit_namen_in_der_avatar_liste(self):
        """Der gemeldete Fall: 1 Mitglied + 2 Gäste = 3 Gesichter."""
        from tests.base import app as flask_app
        with flask_app.app_context():
            tour = M.Tour(title='Mit Gästen', status='planned', tour_date=None,
                          created_by=self.org_id, group_id=self.g1_id)
            db.session.add(tour)
            db.session.commit()
            try:
                db.session.add(M.TourParticipant(tour_id=tour.id, user_id=self.mem_id,
                                                 status='attending'))
                db.session.add(M.TourGuest(tour_id=tour.id, name='Ute Walser',
                                           created_by=self.org_id))
                db.session.add(M.TourGuest(tour_id=tour.id, name='Bernd Österle',
                                           created_by=self.org_id))
                db.session.commit()

                liste = self._avatar_quelle(tour.id)
                namen = [n for n, _ in liste]
                self.assertEqual(len(liste), 3, f'nur {namen} – Gäste fehlen')
                self.assertEqual(len(liste), appmod.tour_headcount(tour.id),
                                 'Avatar-Anzahl muss der Kopfzahl entsprechen')
                self.assertIn('Ute Walser', namen)
                self.assertIn('Bernd Österle', namen)
                # Gäste haben kein Konto und damit kein Bild -> Initialen-Kreis
                self.assertIsNone(dict(liste)['Ute Walser'])
            finally:
                M.Tour.query.filter_by(title='Mit Gästen').delete()
                M.TourParticipant.query.filter_by(tour_id=tour.id).delete()
                M.TourGuest.query.filter_by(tour_id=tour.id).delete()
                db.session.commit()

    def test_deutsche_sortierung(self):
        """Ä/Ö/Ü einsortiert wie im Telefonbuch – nicht hinten angehängt."""
        from tests.base import app as flask_app
        with flask_app.app_context():
            tour = M.Tour(title='Sortierung', status='planned', tour_date=None,
                          created_by=self.org_id, group_id=self.g1_id)
            db.session.add(tour)
            db.session.commit()
            try:
                for nm in ('Zoe', 'Ännchen', 'Anton', 'Ömer'):
                    db.session.add(M.TourGuest(tour_id=tour.id, name=nm, created_by=self.org_id))
                db.session.commit()
                namen = [n for n, _ in self._avatar_quelle(tour.id)]
                self.assertEqual(namen, ['Ännchen', 'Anton', 'Ömer', 'Zoe'])
            finally:
                M.TourGuest.query.filter_by(tour_id=tour.id).delete()
                M.Tour.query.filter_by(title='Sortierung').delete()
                db.session.commit()

    def test_einstiegsbild_malt_avatare_statt_zahl(self):
        src = _lies_app()
        block = src[src.index('def make_title_frame'):src.index('def _draw_weather_icon')]
        self.assertIn('_avatar_row_layer(_attending_users', block,
                      'das Einstiegsbild muss die Avatar-Zeile zeichnen')
        # Der Zähler darf nur noch der Ersatz sein, wenn keine Zeile baubar ist.
        self.assertIn('elif _attending_count:', block)
        self.assertNotIn("bits.append(f'{_attending_count} dabei')", block)

    def test_avatar_zeile_bricht_bei_vielen_gesichtern_um(self):
        """Viele Teilnehmer: umbrechen statt verkleinern (Namen bleiben lesbar)."""
        src = _lies_app()
        block = src[src.index('def _avatar_row_layer'):src.index('def _cover_photo_bg')]
        self.assertIn('max_shown=8', block, 'Standard bleibt 8 (Statistik-Folie unverändert)')
        self.assertIn('rows_of', block, 'Umbruch in mehrere Zeilen fehlt')

    def test_statistik_folie_bleibt_unveraendert(self):
        """Die Statistik-Folie ruft die Avatar-Zeile ohne neuen Parameter auf."""
        src = _lies_app()
        self.assertIn('_avatar_row_layer(users_info)', src)
        self.assertIn('_avatar_row_layer(users_info or [])', src)
