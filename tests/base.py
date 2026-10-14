"""Gemeinsame Basis für die Smoke-Tests von „De jungen Olen“ (Build y).

Nur Standardbibliothek + die App selbst, keine zusätzlichen Pakete.

Start im Projektordner (Windows, macOS, Linux):

    python -m unittest                 # alle Tests
    python -m unittest -v tests.test_touren
    python -m unittest tests.test_routes.RoutesTest.test_all_get_routes_member

Was die Tests NICHT tun:
- Sie fassen die echte Datenbank und static/uploads nicht an. Vor dem Import der App werden
  DATABASE_URL und die Upload-Ordner auf einen Temp-Ordner umgebogen (eine .env im Projekt
  überschreibt diese Werte nicht, python-dotenv lässt gesetzte Variablen in Ruhe).
- Sie bauen keine Netzverbindungen auf: Push, Telegram, E-Mail, Overpass, Wetter/Nominatim
  sind durch Attrappen ersetzt (siehe AppTestCase.setUp). Die zufälligen Hintergrund-
  Trigger (Backup, Morgen-/Abend-Erinnerung) sind während der Tests abgeschaltet.
"""
import atexit
import datetime as dt
import io
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix='djo-tests-'))

# ── Umgebung VOR dem Import der App setzen ────────────────────────────────────────────────
os.environ['SECRET_KEY'] = 'test-secret-key-' + 'x' * 32
os.environ['DATABASE_URL'] = 'sqlite:///' + (TMP / 'test.db').as_posix()
os.environ['BASE_URL'] = 'http://localhost'
os.environ['TELEGRAM_BOT_TOKEN'] = ''
os.environ['TELEGRAM_CHAT_ID'] = ''
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import app as appmod            # noqa: E402  (erst nach den Umgebungsvariablen!)
from app import app, db         # noqa: E402
import models as M              # noqa: E402

app.config.update(TESTING=True, SERVER_NAME='localhost', BASE_URL='http://localhost',
                  PREFERRED_URL_SCHEME='http')
for _key in ('UPLOAD_FOLDER_GPX', 'UPLOAD_FOLDER_PHOTOS', 'UPLOAD_FOLDER_VIDEOS', 'UPLOAD_FOLDER_AVATARS'):
    app.config[_key] = str(TMP / _key.split('_')[-1].lower())
    os.makedirs(app.config[_key], exist_ok=True)


def _cleanup():
    try:
        db.engine.dispose()
    except Exception:
        pass
    shutil.rmtree(TMP, ignore_errors=True)


atexit.register(_cleanup)

PASSWORD = 'geheim123'
FAR_FUTURE = dt.date(9999, 12, 31)   # „Datum offen“


# ── Attrappen für Netz-Zugriffe ───────────────────────────────────────────────────────────
class FakeResponse:
    """Minimaler Ersatz für requests.Response."""

    def __init__(self, status_code=200, json_data=None, text='', headers=None):
        self.status_code = status_code
        self._json = json_data
        self.text = text if text or json_data is None else __import__('json').dumps(json_data)
        self.content = self.text.encode('utf-8')
        self.headers = headers or {'Content-Type': 'application/json'}
        self.ok = 200 <= status_code < 300

    def json(self):
        if self._json is None:
            raise ValueError('kein JSON')
        return self._json

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f'HTTP {self.status_code}')


class NetworkBlocked(Exception):
    """Wird von den Attrappen geworfen, wenn ein Test unerwartet ins Netz will."""


def _blocked(*args, **kwargs):
    raise NetworkBlocked(f'Netzzugriff in Tests gesperrt: {args[:1]}')


def make_gpx(n=120, with_time=True, pause_at=60, lat0=53.40, lng0=9.80, start=dt.datetime(2025, 6, 14, 8, 0)):
    """GPX-Track Richtung Norden (~111 m je Punkt). Mit Zeitstempeln ≈ 18 km/h und einer
    10-Minuten-Pause bei Punkt `pause_at`, damit Fahrzeit ≠ Gesamtzeit."""
    t = start
    pts = []
    for i in range(n):
        if with_time and i == pause_at:
            t += dt.timedelta(minutes=10)
        time_tag = f'<time>{t.strftime("%Y-%m-%dT%H:%M:%SZ")}</time>' if with_time else ''
        pts.append(f'<trkpt lat="{lat0 + i * 0.001:.4f}" lon="{lng0 + (i % 7) * 0.0003:.4f}">'
                   f'<ele>{10 + (i % 9)}</ele>{time_tag}</trkpt>')
        t += dt.timedelta(seconds=22)
    return ('<?xml version="1.0" encoding="UTF-8"?><gpx version="1.1" creator="tests">'
            '<trk><name>Test</name><trkseg>' + ''.join(pts) + '</trkseg></trk></gpx>')


class AppTestCase(unittest.TestCase):
    """Frische Datenbank je Testklasse, Standard-Daten (Gruppe, Nutzer, Touren, Gastro)."""

    @classmethod
    def setUpClass(cls):
        with app.app_context():
            db.session.remove()
            db.drop_all()
            db.create_all()
            appmod.migrate_db()
            try:
                appmod.init_site_config()
            except Exception:
                pass
            cls._seed()
        try:
            appmod._overpass_cache.clear()
        except Exception:
            pass

    @classmethod
    def _seed(cls):
        today = dt.date.today()
        g1 = M.Group(name='Olen', slug='olen')
        g2 = M.Group(name='Andere Gruppe', slug='andere')
        db.session.add_all([g1, g2])
        db.session.flush()

        def user(name, email, group, role='member'):
            u = M.User(name=name, email=email, role=role, group_id=group.id)
            u.set_password(PASSWORD)
            db.session.add(u)
            db.session.flush()
            return u

        cls.admin = user('Admin', 'admin@test.de', g1, 'admin')
        cls.org = user('Orga', 'orga@test.de', g1, 'organizer')
        cls.mem = user('Hein Mück', 'hein@test.de', g1)
        cls.mem2 = user('Fiete', 'fiete@test.de', g1)
        cls.fremd = user('Fremd', 'fremd@test.de', g2, 'organizer')

        def tour(title, d, status='planned', creator=None, group=g1, **kw):
            t = M.Tour(title=title, tour_date=d, status=status, group_id=group.id,
                       created_by=(creator or cls.org).id, **kw)
            db.session.add(t)
            db.session.flush()
            return t

        cls.t_plan = tour('Deichtour, mit Komma', today + dt.timedelta(days=10), start_time='10:00',
                          meeting_desc='Bahnhof, Gleis 1', meeting_lat=53.4661, meeting_lng=9.7995,
                          description='Zeile 1\nZeile 2')
        cls.t_open = tour('Idee ohne Termin', FAR_FUTURE)
        cls.t_done = tour('Alte Marschtour', today - dt.timedelta(days=30), status='completed')
        cls.t_canc = tour('Abgesagte Tour', today + dt.timedelta(days=3), status='cancelled')
        cls.t_fremd = tour('Fremde Tour', today + dt.timedelta(days=5), creator=cls.fremd, group=g2)
        cls.write_gpx(cls.t_done, make_gpx())
        cls.write_gpx(cls.t_plan, make_gpx(with_time=False))

        cls.spot = M.GastroSpot(name='Café Deichblick', spot_type='cafe', lat=53.42, lng=9.80,
                                hours_text='Mo-Fr 09:00-18:00; Sa,So 10:00-18:00', added_by=cls.org.id)
        cls.spot2 = M.GastroSpot(name='Zur alten Mühle', spot_type='kneipe', lat=53.60, lng=9.95,
                                 hours_text='Mo off; Di-So 11:00-22:00', added_by=cls.org.id)
        db.session.add_all([cls.spot, cls.spot2])
        db.session.add(M.TourParticipant(tour_id=cls.t_done.id, user_id=cls.mem.id, status='attending',
                                         confirmed_present=True))
        db.session.commit()
        # IDs merken – die Objekte selbst sind nach dem Context nicht mehr an die Session gebunden
        for name in ('admin', 'org', 'mem', 'mem2', 'fremd', 't_plan', 't_open', 't_done', 't_canc',
                     't_fremd', 'spot', 'spot2'):
            setattr(cls, name + '_id', getattr(cls, name).id)
        cls.g1_id, cls.g2_id = g1.id, g2.id

    @classmethod
    def write_gpx(cls, tour, xml):
        fn = f'tour_{tour.id}_test.gpx'
        with open(os.path.join(app.config['UPLOAD_FOLDER_GPX'], fn), 'w', encoding='utf-8') as fh:
            fh.write(xml)
        tour.gpx_file = fn
        parsed = appmod.parse_gpx(os.path.join(app.config['UPLOAD_FOLDER_GPX'], fn)) or {}
        tour.gpx_km = parsed.get('km')
        tour.gpx_ascent = parsed.get('ascent')
        return fn

    # ── je Test ──
    def setUp(self):
        self.client = app.test_client()
        self.pushes, self.mails, self.telegrams = [], [], []
        self._patches = [
            mock.patch('random.random', return_value=1.0),                       # Hintergrund-Trigger aus
            mock.patch.object(appmod, 'send_push_to_user',
                              side_effect=lambda u, title, body, url=None:
                              (self.pushes.append((u.email, title, body, url)) or (1, 0))),
            mock.patch.object(appmod, 'send_push_to_group',
                              side_effect=lambda *a, **k: (0, 0)),
            mock.patch.object(appmod, 'send_telegram',
                              side_effect=lambda msg, *a, **k: self.telegrams.append(msg)),
            mock.patch.object(appmod, 'send_mail',
                              side_effect=lambda to, subject, body: (self.mails.append((to, subject, body)) or True)),
            mock.patch.object(appmod.http_requests, 'get', side_effect=_blocked),
            mock.patch.object(appmod.http_requests, 'post', side_effect=_blocked),
        ]
        for p in self._patches:
            p.start()
        self.ctx = app.app_context()
        self.ctx.push()

    def tearDown(self):
        db.session.rollback()
        db.session.remove()
        self.ctx.pop()
        for p in reversed(self._patches):
            p.stop()

    # ── Helfer ──
    def login(self, email):
        self.client.get('/logout')
        appmod._rl_store.clear()          # Login-Limit (10/min je IP) für Tests zurücksetzen
        r = self.client.post('/login', data={'email': email, 'password': PASSWORD})
        self.assertIn(r.status_code, (302, 303), f'Login von {email} fehlgeschlagen')
        return r

    def login_member(self):
        return self.login('hein@test.de')

    def login_org(self):
        return self.login('orga@test.de')

    def login_admin(self):
        return self.login('admin@test.de')

    def get_html(self, path, status=200):
        r = self.client.get(path)
        self.assertEqual(r.status_code, status, f'{path} → {r.status_code}')
        return r.get_data(as_text=True)

    def tour(self, tour_id):
        return db.session.get(M.Tour, tour_id)

    def user(self, user_id):
        return db.session.get(M.User, user_id)

    def ensure_participant(self, tour_id, user_id, status='attending', confirmed=False):
        p = M.TourParticipant.query.filter_by(tour_id=tour_id, user_id=user_id).first()
        if not p:
            p = M.TourParticipant(tour_id=tour_id, user_id=user_id, status=status)
            db.session.add(p)
        p.status = status
        p.confirmed_present = confirmed
        return p

    def upload_gpx(self, tour_id, xml, filename='track.gpx'):
        return self.client.post(f'/touren/{tour_id}/gpx',
                                data={'gpx_file': (io.BytesIO(xml.encode('utf-8')), filename)},
                                content_type='multipart/form-data')

    @staticmethod
    def inline_scripts(html):
        return '\n'.join(m.group(1) for m in re.finditer(r'<script(?![^>]*src=)[^>]*>(.*?)</script>', html, re.S))
