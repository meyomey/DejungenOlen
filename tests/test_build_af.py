"""Build af: Option C „Foto unterwegs“ (Kamera + aktueller Handy-Standort) und Option D
„Live-Karte als Aufzeichnung“ (LiveTrackPoint, Spuren auf der Live-Karte, GPX übernehmen/
herunterladen/löschen, Live-Aufzeichnung als Zeitquelle fürs Platzieren von Fotos).

Fixtures aus tests/base.py: t_plan hat eine geplante Route ohne Zeiten (→ Live-Aufzeichnung springt
ein), t_open gar kein GPX, t_done eine GPX-Aufzeichnung mit Zeiten (hat Vorrang)."""
import datetime as dt
import io
import unittest
from unittest import mock

from tests.base import AppTestCase, appmod, app, db, M
from tests.test_build_ac import HAVE_IMG, make_jpeg

UTC_START = dt.datetime(2025, 6, 14, 8, 0, 0)         # Aufzeichnung ab 10:00 Ortszeit (CEST)
LOCAL_START = dt.datetime(2025, 6, 14, 10, 0, 0)


def seed_track(tour_id, user_id, n=30, start=UTC_START, step_s=20, lat0=53.40, lng0=9.80, dlat=0.0005):
    """n Punkte Richtung Norden (~55 m je 20 s ≈ 10 km/h) ab start (UTC)."""
    for i in range(n):
        db.session.add(M.LiveTrackPoint(tour_id=tour_id, user_id=user_id, lat=lat0 + i * dlat, lng=lng0,
                                        accuracy=8.0, recorded_at=start + dt.timedelta(seconds=i * step_s)))
    db.session.commit()


class TrackHelpersTest(AppTestCase):
    """Reine Helfer: Punkte anhängen, Zusammenfassungen, Zeitquelle, GPX, Spuren, Aufräumen."""

    def setUp(self):
        super().setUp()
        M.LiveTrackPoint.query.delete()
        db.session.commit()

    def test_add_filters_bad_fixes(self):
        now = dt.datetime.utcnow()
        with app.test_request_context():
            self.assertFalse(appmod._live_track_add(self.t_plan_id, self.mem_id, 53.4, 9.8, 250.0, now))   # zu ungenau
            self.assertTrue(appmod._live_track_add(self.t_plan_id, self.mem_id, 53.4, 9.8, 10.0, now))
            self.assertFalse(appmod._live_track_add(self.t_plan_id, self.mem_id, 53.4001, 9.8, 10.0,
                                                    now + dt.timedelta(seconds=1)))                       # Doppelsendung
            self.assertFalse(appmod._live_track_add(self.t_plan_id, self.mem_id, 53.5, 9.8, 10.0,
                                                    now + dt.timedelta(seconds=20)))                      # 11 km in 20 s
            self.assertTrue(appmod._live_track_add(self.t_plan_id, self.mem_id, 53.4005, 9.8, None,
                                                   now + dt.timedelta(seconds=20)))                       # ohne Genauigkeit ok
            # nach langer Pause (Gerät aus) zählt der Sprung nicht als Ausreißer
            self.assertTrue(appmod._live_track_add(self.t_plan_id, self.mem_id, 53.9, 9.8, 10.0,
                                                   now + dt.timedelta(hours=7)))
        db.session.commit()
        self.assertEqual(M.LiveTrackPoint.query.filter_by(tour_id=self.t_plan_id).count(), 3)

    def test_summaries_sorted_and_min_points(self):
        seed_track(self.t_plan_id, self.mem_id, n=30)                       # ≈ 1,6 km
        seed_track(self.t_plan_id, self.org_id, n=60, lat0=53.50)           # ≈ 3,3 km → zuerst
        seed_track(self.t_plan_id, self.mem2_id, n=3)                       # zu kurz → fehlt
        with app.test_request_context():
            s = appmod._live_track_summaries(self.t_plan_id)
        self.assertEqual([d['user_id'] for d in s], [self.org_id, self.mem_id])
        self.assertEqual(s[1]['name'], 'Hein Mück')
        self.assertEqual(s[1]['n'], 30)
        self.assertAlmostEqual(s[1]['km'], 1.6, delta=0.15)
        self.assertEqual(s[1]['span'], '14.06.2025 10:00–10:09 Uhr')     # Ortszeit
        self.assertEqual(len(s[1]['points']), 30)
        self.assertEqual(appmod._live_track_summaries(self.t_open_id), [])

    def test_timed_points_prefer_own_recording(self):
        seed_track(self.t_plan_id, self.mem_id, n=30)
        seed_track(self.t_plan_id, self.org_id, n=60, lat0=53.50)
        with app.test_request_context():
            own = appmod._live_track_timed_points(self.t_plan_id, self.mem_id)
            best = appmod._live_track_timed_points(self.t_plan_id, self.mem2_id)   # Fiete hat keine → längste
            none = appmod._live_track_timed_points(self.t_plan_id, None)
            tour = self.tour(self.t_plan_id)
            pts, src = appmod._tour_timed_source(tour, self.mem_id)
            pts_done, src_done = appmod._tour_timed_source(self.tour(self.t_done_id), self.mem_id)
            pts_open, src_open = appmod._tour_timed_source(self.tour(self.t_open_id), self.mem_id)
        self.assertEqual(len(own), 30)
        self.assertAlmostEqual(own[0][1], 53.40, places=4)
        self.assertEqual(len(best), 60)
        self.assertEqual(len(none), 60)
        self.assertEqual((len(pts), src), (30, 'live'))                     # geplante Route ohne Zeiten → Live
        self.assertEqual(src_done, 'gpx')                                   # echte GPX-Aufzeichnung hat Vorrang
        self.assertEqual(len(pts_done), 120)
        self.assertEqual((pts_open, src_open), ([], None))
        # Position zur Uhrzeit: 10:05 Ortszeit = Punkt 15 → 53.4075
        pos = appmod._track_position_at(own, LOCAL_START + dt.timedelta(minutes=5))
        self.assertAlmostEqual(pos[0], 53.4075, places=4)

    def test_gpx_xml_roundtrip(self):
        seed_track(self.t_plan_id, self.mem_id, n=30)
        with app.test_request_context():
            summary = appmod._live_track_summaries(self.t_plan_id)[0]
            xml = appmod._live_track_gpx_xml(summary, self.tour(self.t_plan_id))
        self.assertIn('<trkpt lat="53.4', xml)
        self.assertIn('<time>2025-06-14T08:00:00Z</time>', xml)
        self.assertNotIn('Hein', xml)                                       # kein Personenbezug in der Datei
        import os
        path = os.path.join(app.config['UPLOAD_FOLDER_GPX'], 'live_roundtrip.gpx')
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(xml)
        parsed = appmod.parse_gpx(path)
        self.assertEqual(len(parsed['points']), 30)
        self.assertAlmostEqual(parsed['km'], 1.6, delta=0.15)
        self.assertTrue(parsed['moving_s'])                                 # Zeitstempel erkannt
        self.assertEqual((parsed['start_time'], parsed['end_time']), ('10:00', '10:09'))
        self.assertEqual(len(appmod._gpx_timed_points(path)), 30)

    def test_trails_payload_since_and_thinning(self):
        seed_track(self.t_plan_id, self.mem_id, n=900, start=dt.datetime.utcnow() - dt.timedelta(hours=1), step_s=4)
        with app.test_request_context():
            full = appmod._live_trails_payload(self.t_plan_id)
            key = str(self.mem_id)
            self.assertIn(key, full)
            self.assertLessEqual(len(full[key]), appmod.LIVE_TRACK_PAGE_PTS + 1)
            self.assertEqual(len(full[key][0]), 3)                           # [lat, lng, ts]
            last_ts = full[key][-1][2]
            delta = appmod._live_trails_payload(self.t_plan_id, dt.datetime.utcfromtimestamp(last_ts))
            self.assertLessEqual(len(delta.get(key, [])), 1)                 # höchstens der letzte Punkt nochmal (Sekundenbruchteil; Client filtert)
            older = appmod._live_trails_payload(self.t_plan_id, dt.datetime.utcfromtimestamp(last_ts - 100))
            self.assertTrue(0 < len(older[key]) <= 26)                       # nur die letzten 100 s
            # Älter als 12 h: nicht im Erstaufruf
            seed_track(self.t_open_id, self.mem_id, n=10, start=dt.datetime.utcnow() - dt.timedelta(hours=20))
            self.assertEqual(appmod._live_trails_payload(self.t_open_id), {})

    def test_cleanup_removes_old_recordings(self):
        now = dt.datetime.utcnow()
        seed_track(self.t_done_id, self.mem_id, n=10, start=now - dt.timedelta(days=40))
        seed_track(self.t_plan_id, self.mem_id, n=10, start=now - dt.timedelta(days=2))
        with app.test_request_context():
            appmod._live_cleanup(now)
        db.session.commit()
        self.assertEqual(M.LiveTrackPoint.query.filter_by(tour_id=self.t_done_id).count(), 0)
        self.assertEqual(M.LiveTrackPoint.query.filter_by(tour_id=self.t_plan_id).count(), 10)


class RecordingApiTest(AppTestCase):
    """Standort melden → Aufzeichnung; Spuren per Polling; Download, Übernahme als GPX, Löschen."""

    def setUp(self):
        super().setUp()
        M.LiveTrackPoint.query.delete()
        db.session.commit()

    def _post(self, tour_id, **extra):
        body = {'tour_id': tour_id, 'lat': 53.4, 'lng': 9.8, 'accuracy': 12}
        body.update(extra)
        return self.client.post('/api/location/update', json=body)

    def test_update_records_points_and_returns_trails(self):
        tour_day = self.tour(self.t_plan_id).tour_date
        self.login_member()
        with mock.patch.object(appmod, '_berlin_today', return_value=tour_day):
            r = self._post(self.t_plan_id, since=0)
            d = r.get_json()
            self.assertEqual(r.status_code, 200)
            self.assertTrue(d['recorded'])
            self.assertIn(str(self.mem_id), d['trails'])
            self.assertEqual(len(d['trails'][str(self.mem_id)]), 1)
            r = self._post(self.t_plan_id)                                   # gleiche Sekunde → Doppelsendung
            self.assertFalse(r.get_json()['recorded'])
            self.assertNotIn('trails', r.get_json())                         # ohne since keine Spuren
            r = self._post(self.t_plan_id, accuracy=500)                     # zu ungenau: Standort ja, Aufzeichnung nein
            self.assertFalse(r.get_json()['recorded'])
        self.assertEqual(M.LiveTrackPoint.query.filter_by(tour_id=self.t_plan_id, user_id=self.mem_id).count(), 1)
        self.assertEqual(M.LiveLocation.query.filter_by(tour_id=self.t_plan_id, user_id=self.mem_id).count(), 1)
        # Zuschauer: Spuren nur mit since-Parameter
        self.login('fiete@test.de')
        d = self.client.get(f'/api/location/tour/{self.t_plan_id}').get_json()
        self.assertNotIn('trails', d)
        d = self.client.get(f'/api/location/tour/{self.t_plan_id}?since=0').get_json()
        self.assertEqual(len(d['trails'][str(self.mem_id)]), 1)
        self.assertEqual(d['trails'][str(self.mem_id)][0][:2], [53.4, 9.8])
        # Teilen beenden löscht den Standort, nicht die Aufzeichnung
        self.login_member()
        self.client.post(f'/api/location/stop?tour_id={self.t_plan_id}', data='')
        self.assertEqual(M.LiveLocation.query.filter_by(tour_id=self.t_plan_id, user_id=self.mem_id).count(), 0)
        self.assertEqual(M.LiveTrackPoint.query.filter_by(tour_id=self.t_plan_id, user_id=self.mem_id).count(), 1)

    def test_download_permissions(self):
        seed_track(self.t_plan_id, self.mem_id, n=30)
        self.login_member()
        r = self.client.get(f'/touren/{self.t_plan_id}/live/aufzeichnung.gpx')          # eigene
        self.assertEqual(r.status_code, 200)
        self.assertIn('gpx', r.headers.get('Content-Type', ''))
        self.assertIn('attachment', r.headers.get('Content-Disposition', ''))
        self.assertIn(b'<trkpt', r.data)
        self.login('fiete@test.de')
        self.assertEqual(self.client.get(f'/touren/{self.t_plan_id}/live/aufzeichnung.gpx').status_code, 404)   # hat keine
        self.assertEqual(self.client.get(f'/touren/{self.t_plan_id}/live/aufzeichnung.gpx?user_id={self.mem_id}').status_code, 403)
        self.login_org()
        self.assertEqual(self.client.get(f'/touren/{self.t_plan_id}/live/aufzeichnung.gpx?user_id={self.mem_id}').status_code, 200)
        self.login('fremd@test.de')
        self.assertEqual(self.client.get(f'/touren/{self.t_plan_id}/live/aufzeichnung.gpx?user_id={self.mem_id}').status_code, 404)

    def test_adopt_as_gpx_and_place_photos(self):
        seed_track(self.t_open_id, self.mem_id, n=30)
        # Foto ohne Standort, aufgenommen 10:05 Ortszeit (Punkt 15 → 53.4075)
        db.session.add(M.TourPhoto(tour_id=self.t_open_id, user_id=self.mem2_id, filename='x.jpg',
                                   taken_at=LOCAL_START + dt.timedelta(minutes=5)))
        db.session.commit()
        self.login_member()
        r = self.client.post(f'/touren/{self.t_open_id}/live/aufzeichnung', data={'action': 'adopt', 'user_id': self.mem_id})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.client.post(f'/touren/{self.t_open_id}/live/aufzeichnung', data={'action': 'x'}).status_code, 400)
        self.login_org()
        r = self.client.post(f'/touren/{self.t_open_id}/live/aufzeichnung',
                             data={'action': 'adopt', 'user_id': self.mem_id}, follow_redirects=True)
        html = r.get_data(as_text=True)
        self.assertIn('Live-Aufzeichnung von Hein Mück als GPX-Track übernommen', html)
        self.assertIn('14.06.2025 10:00–10:09 Uhr, 30 Punkte', html)
        self.assertIn('1 Foto(s) anhand der Aufnahmezeit', html)
        self.assertNotIn('wurde ersetzt', html)
        t = self.tour(self.t_open_id)
        self.assertTrue(t.gpx_file and t.gpx_file.startswith(f'{self.t_open_id}_live_'))
        import os
        self.assertTrue(os.path.exists(os.path.join(app.config['UPLOAD_FOLDER_GPX'], t.gpx_file)))
        self.assertAlmostEqual(t.gpx_km, 1.6, delta=0.15)
        self.assertTrue(t.gpx_moving_s)
        p = M.TourPhoto.query.filter_by(tour_id=self.t_open_id).first()
        self.assertEqual(p.gps_source, 'track')
        self.assertAlmostEqual(p.lat, 53.4075, places=4)
        # Tour mit geplanter Route: Übernahme ersetzt den Track (Hinweis im Flash)
        seed_track(self.t_plan_id, self.org_id, n=30)
        r = self.client.post(f'/touren/{self.t_plan_id}/live/aufzeichnung', data={'action': 'adopt'}, follow_redirects=True)
        self.assertIn('wurde ersetzt', r.get_data(as_text=True))
        # ohne brauchbare Aufzeichnung: Hinweis statt Fehler
        r = self.client.post(f'/touren/{self.t_canc_id}/live/aufzeichnung', data={'action': 'adopt'}, follow_redirects=True)
        self.assertIn('Keine brauchbare Live-Aufzeichnung', r.get_data(as_text=True))

    def test_delete_own_and_all(self):
        seed_track(self.t_plan_id, self.mem_id, n=10)
        seed_track(self.t_plan_id, self.org_id, n=10, lat0=53.5)
        self.login_member()
        r = self.client.post(f'/touren/{self.t_plan_id}/live/aufzeichnung', data={'action': 'delete', 'user_id': 'all'})
        self.assertEqual(r.status_code, 403)
        r = self.client.post(f'/touren/{self.t_plan_id}/live/aufzeichnung', data={'action': 'delete'}, follow_redirects=True)
        self.assertIn('Deine Live-Aufzeichnung dieser Tour wurde gelöscht (10 Punkte)', r.get_data(as_text=True))
        self.assertEqual(M.LiveTrackPoint.query.filter_by(tour_id=self.t_plan_id).count(), 10)       # Orga bleibt
        self.login_org()
        r = self.client.post(f'/touren/{self.t_plan_id}/live/aufzeichnung', data={'action': 'delete', 'user_id': 'all'},
                             follow_redirects=True)
        self.assertIn('Alle Live-Aufzeichnungen dieser Tour gelöscht (10 Punkte)', r.get_data(as_text=True))
        self.assertEqual(M.LiveTrackPoint.query.filter_by(tour_id=self.t_plan_id).count(), 0)

    def test_tour_delete_removes_recording(self):
        t = M.Tour(title='Wegwerf-Tour', tour_date=dt.date(2025, 6, 14), status='completed',
                   created_by=self.org_id, group_id=self.g1_id)
        db.session.add(t)
        db.session.commit()
        seed_track(t.id, self.mem_id, n=10)
        with app.test_request_context():
            appmod._delete_tour_dependents(t.id)
        db.session.commit()
        self.assertEqual(M.LiveTrackPoint.query.filter_by(tour_id=t.id).count(), 0)


class PagesTest(AppTestCase):
    """Tourseite (Kamera-Knopf, Panel Live-Aufzeichnung, Platzieren-Block), Live-Karte, Hilfe, Datenschutz."""

    def setUp(self):
        super().setUp()
        M.LiveTrackPoint.query.delete()
        db.session.commit()

    def test_detail_has_camera_upload(self):
        self.login_member()
        html = self.get_html(f'/touren/{self.t_plan_id}')
        self.assertIn('id="photo-camera"', html)
        self.assertIn('capture="environment"', html)
        self.assertIn('Foto unterwegs aufnehmen', html)
        self.assertIn('async function photoFromCamera', html)
        self.assertIn("name=\"gps_src_0\" value=\"device\"", html)
        self.assertNotIn('id="live-aufzeichnung"', html)                     # keine Aufzeichnung → kein Panel

    def test_detail_recording_panel(self):
        seed_track(self.t_plan_id, self.mem_id, n=30)
        seed_track(self.t_plan_id, self.org_id, n=60, lat0=53.5)
        # Mitglied mit eigener Aufzeichnung: Download + eigene löschen, kein Übernehmen
        self.login_member()
        html = self.get_html(f'/touren/{self.t_plan_id}')
        self.assertIn('id="live-aufzeichnung"', html)
        self.assertIn('Hein Mück <span class="text-muted">(du)</span>', html)
        self.assertIn(f'/live/aufzeichnung.gpx?user_id={self.mem_id}', html)
        self.assertNotIn(f'/live/aufzeichnung.gpx?user_id={self.org_id}', html)   # fremde nicht
        self.assertIn('Meine Aufzeichnung löschen', html)
        self.assertNotIn('Als GPX-Track der Tour übernehmen', html)
        self.assertNotIn('>Alle löschen<', html)
        # Fiete ohne eigene Aufzeichnung: kein Panel
        self.login('fiete@test.de')
        self.assertNotIn('id="live-aufzeichnung"', self.get_html(f'/touren/{self.t_plan_id}'))
        # Orga: Auswahl + Übernehmen + Alle löschen
        self.login_org()
        html = self.get_html(f'/touren/{self.t_plan_id}')
        self.assertIn('Als GPX-Track der Tour übernehmen', html)
        self.assertIn(f'<option value="{self.org_id}">Orga (3,3 km)</option>', html)
        self.assertIn('>Alle löschen<', html)
        self.assertIn('Den vorhandenen GPX-Track dieser Tour durch die Live-Aufzeichnung ersetzen?', html)
        self.assertIn('nach 30 Tagen automatisch gelöscht', html)

    @unittest.skipUnless(HAVE_IMG, 'Pillow/piexif nicht installiert')
    def test_upload_places_photo_on_live_recording(self):
        seed_track(self.t_plan_id, self.mem_id, n=30)                                 # Heins Aufzeichnung
        seed_track(self.t_plan_id, self.org_id, n=30, lat0=53.50)                     # Orga woanders
        self.login_member()
        appmod._rl_store.clear()
        jpeg = make_jpeg(taken=LOCAL_START + dt.timedelta(minutes=5))                 # 10:05 → Punkt 15
        r = self.client.post(f'/touren/{self.t_plan_id}/fotos', data={'photos': [(io.BytesIO(jpeg), 'a.jpg')]},
                             content_type='multipart/form-data', follow_redirects=True)
        html = r.get_data(as_text=True)
        self.assertIn('1 anhand der Aufnahmezeit auf der Strecke platziert', html)
        p = M.TourPhoto.query.filter_by(tour_id=self.t_plan_id).order_by(M.TourPhoto.id.desc()).first()
        self.assertEqual(p.gps_source, 'track')
        self.assertAlmostEqual(p.lat, 53.4075, places=4)                              # auf Heins Spur, nicht Orgas
        # Platzieren-Block nennt die Live-Quelle; Zeitkorrektur-Knopf vorhanden
        self.login_org()
        html = self.get_html(f'/touren/{self.t_plan_id}')
        self.assertIn('Aufzeichnung Live-Karte, Orga: 14.06.2025 10:00–10:09 Uhr', html)   # Orga sieht die eigene
        self.assertIn('Geschätzte Positionen neu berechnen', html)
        self.assertIn('laut Live-Aufzeichnung', html)
        self.assertIn('window.GPX_TIMED = true', html)

    @unittest.skipUnless(HAVE_IMG, 'Pillow/piexif nicht installiert')
    def test_upload_with_device_location(self):
        self.login_member()
        appmod._rl_store.clear()
        r = self.client.post(f'/touren/{self.t_open_id}/fotos',
                             data={'photos': [(io.BytesIO(make_jpeg()), 'foto.jpg')],
                                   'gps_lat_0': '53.123456', 'gps_lng_0': '9.654321', 'gps_src_0': 'device',
                                   'exif_dt_0': '2025:06:14 10:05:00'},
                             content_type='multipart/form-data', headers={'X-Requested-With': 'XMLHttpRequest'})
        d = r.get_json()
        self.assertEqual((d['ok'], d['count'], d['no_gps']), (True, 1, 0))
        p = M.TourPhoto.query.filter_by(tour_id=self.t_open_id).order_by(M.TourPhoto.id.desc()).first()
        self.assertEqual(p.gps_source, 'device')
        self.assertEqual((p.lat, p.lng), (53.123456, 9.654321))
        self.assertEqual(p.taken_at, dt.datetime(2025, 6, 14, 10, 5))
        html = self.get_html(f'/touren/{self.t_open_id}')
        self.assertIn('📱 1 mit aktuellem Handy-Standort', html)

    def test_live_page_has_trails_and_camera(self):
        seed_track(self.t_plan_id, self.mem_id, n=10, start=dt.datetime.utcnow() - dt.timedelta(minutes=30))
        self.login_member()
        html = self.get_html(f'/touren/{self.t_plan_id}/live')
        self.assertIn('id="btn-photo"', html)
        self.assertIn('id="live-cam"', html)
        self.assertIn('function livePhoto', html)
        self.assertIn(f'const UPLOAD_URL = "/touren/{self.t_plan_id}/fotos"', html)
        self.assertRegex(html, r'const TRAILS\s*=\s*\{"%d": \[\[53\.4' % self.mem_id)
        self.assertIn('function addTrails', html)
        self.assertIn("'?since=' + trailSince", html)
        self.assertIn('id="live-rec-hint"', html)
        self.assertIn('nach 30 Tagen automatisch gelöscht', html)

    def test_help_and_privacy(self):
        self.login_member()
        html = self.get_html('/hilfe')
        self.assertIn('Foto unterwegs aufnehmen', html)
        self.assertIn('als GPX-Track der Tour übernehmen', html.replace('<strong>', '').replace('</strong>', ''))
        html = self.get_html('/datenschutz')
        self.assertIn('Live-Karte:', html)
        self.assertIn('Meine Aufzeichnung löschen', html)
