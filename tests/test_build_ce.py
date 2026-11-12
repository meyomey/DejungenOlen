"""Build ce: Wetter am Tourtag erscheint in Vorschau und MP4 – auch ohne Treffpunkt.

**Meldung:** „Die Wetterinfo am Tourtag vermisse ich bei beiden, Vorschau und Video.“

**Nachgemessen:** Die Detailseite (Build q) holt das Wetter mit Ersatz-Ort – ohne
Treffpunkt nimmt sie den GPX-Start (`?lat=&lng=` an `tour_weather_day`). Video-Seite und
Renderer riefen dagegen `_tour_day_weather(tour)` **ohne** Ersatz auf; die Funktion bricht
ohne `meeting_lat/lng` sofort mit `None` ab. Nachgestellt (Open-Meteo-Attrappe: 9 °C,
bewölkt): Tour ohne Treffpunkt → Detailseite 9 °C ☁️, Video-Seite/MP4 **nichts**.

**Fix:** `_video_weather(tour, gpx_points, photos)` – gleiche Reihenfolge für Seite und
Renderer: Treffpunkt → GPX-Startpunkt → erstes Foto mit GPS → Standard-Treffpunkt der
Gruppe. Im Renderer wird das Wetter erst nach dem GPX-Parsen geholt.
"""
import datetime
import json
import os
import re
from unittest import mock

from tests.base import AppTestCase, appmod, db, M

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _fake_get(url, params=None, timeout=None):
    class R:
        def json(self):
            return {'daily': {'weathercode': [3], 'temperature_2m_max': [9.4], 'temperature_2m_min': [4.1]}}
    _fake_get.calls.append(dict(params or {}))
    return R()


_fake_get.calls = []


class WetterErsatzOrtTest(AppTestCase):
    def _tour(self, **kw):
        t = M.Tour(title='Ohne Treffpunkt', status='done', tour_date=datetime.date(2026, 11, 11),
                   created_by=self.org_id, group_id=self.g1_id, **kw)
        db.session.add(t)
        db.session.commit()
        return t

    def test_vorbedingung_ohne_treffpunkt_kein_wetter_im_alten_aufruf(self):
        from tests.base import app as flask_app
        with flask_app.app_context(), mock.patch.object(appmod.http_requests, 'get', side_effect=_fake_get):
            t = self._tour()
            self.assertIsNone(t.meeting_lat)
            self.assertIsNone(appmod._tour_day_weather(t), 'so sahen Video-Seite und MP4 das Wetter: gar nicht')

    def test_gpx_start_als_ersatz(self):
        from tests.base import app as flask_app
        with flask_app.app_context(), mock.patch.object(appmod.http_requests, 'get', side_effect=_fake_get):
            t = self._tour()
            _fake_get.calls.clear()
            w = appmod._video_weather(t, [{'lat': 52.95, 'lng': 9.10}, {'lat': 52.96, 'lng': 9.11}])
            self.assertEqual((w['temp_max'], w['kind']), (9, 'cloud'))
            self.assertEqual((_fake_get.calls[0]['latitude'], _fake_get.calls[0]['longitude']), (52.95, 9.10))

    def test_foto_gps_als_zweiter_ersatz(self):
        from tests.base import app as flask_app
        with flask_app.app_context(), mock.patch.object(appmod.http_requests, 'get', side_effect=_fake_get):
            t = self._tour()
            ph = M.TourPhoto(tour_id=t.id, user_id=self.org_id, filename='f.jpg', lat=53.1, lng=9.4)
            db.session.add(ph)
            db.session.commit()
            _fake_get.calls.clear()
            w = appmod._video_weather(t, [], [ph])
            self.assertIsNotNone(w)
            self.assertEqual((_fake_get.calls[0]['latitude'], _fake_get.calls[0]['longitude']), (53.1, 9.4))

    def test_treffpunkt_hat_vorrang(self):
        from tests.base import app as flask_app
        with flask_app.app_context(), mock.patch.object(appmod.http_requests, 'get', side_effect=_fake_get):
            t = self._tour(meeting_lat=52.5, meeting_lng=9.9)
            _fake_get.calls.clear()
            appmod._video_weather(t, [{'lat': 52.95, 'lng': 9.10}])
            self.assertEqual((_fake_get.calls[0]['latitude'], _fake_get.calls[0]['longitude']), (52.5, 9.9))

    def test_offenes_datum_weiter_kein_wetter(self):
        from tests.base import app as flask_app
        with flask_app.app_context(), mock.patch.object(appmod.http_requests, 'get', side_effect=_fake_get):
            t = M.Tour(title='Offen', status='planned', tour_date=None, created_by=self.org_id, group_id=self.g1_id)
            db.session.add(t)
            db.session.commit()
            self.assertIsNone(appmod._video_weather(t, [{'lat': 52.95, 'lng': 9.10}]))


class VideoSeiteTest(AppTestCase):
    def test_seite_liefert_wetter_ohne_treffpunkt(self):
        from tests.base import app as flask_app
        with flask_app.app_context():
            t = M.Tour(title='Ohne Treffpunkt', status='done', tour_date=datetime.date(2026, 11, 11),
                       created_by=self.org_id, group_id=self.g1_id)
            db.session.add(t)
            db.session.commit()
            db.session.add(M.TourPhoto(tour_id=t.id, user_id=self.org_id, filename='f.jpg', lat=53.1, lng=9.4))
            db.session.commit()
            tid = t.id
        self.login_org()
        with mock.patch.object(appmod.http_requests, 'get', side_effect=_fake_get):
            html = self.client.get(f'/touren/{tid}/video').get_data(as_text=True)
        w = json.loads(re.search(r'const WEATHER = (.*?);\n', html).group(1))
        self.assertIsNotNone(w, 'vorher: const WEATHER = null')
        self.assertEqual(w['temp_max'], 9)

    def test_renderer_nutzt_denselben_helfer(self):
        src = open(os.path.join(_ROOT, 'app.py'), encoding='utf-8').read()
        self.assertIn('_weather = _video_weather(tour, _gpx_points, photos)', src)
        self.assertIn("weather = _video_weather(tour, (gpx_data or {}).get('points'), photos)", src)
        # Der alte Aufruf ohne Ersatz-Ort darf in Seite/Renderer nicht zurückkommen.
        self.assertNotIn('_weather = _tour_day_weather(tour)', src)
        self.assertNotIn('weather = _tour_day_weather(tour)   # Build j', src)
        # Reihenfolge: Wetter erst NACH dem GPX-Parsen holen
        self.assertLess(src.index("_ride = {k: _parsed.get(k)"), src.index('_weather = _video_weather(tour, _gpx_points, photos)'))

    def test_build_stempel(self):
        self.assertGreaterEqual(appmod.APP_BUILD, '2026-11-12 ce')
