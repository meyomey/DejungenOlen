"""Build ag: Performance-Fix im Foto-Upload (Zeitquelle wird auch bei LEEREM Ergebnis gecacht –
vorher wurde der GPX je Foto ohne GPS neu geparst), pünktliche Erinnerung per Plesk-Cron
(/api/reminder/trigger, gleiche Token-Mechanik wie der Backup-Trigger), freundliche 413-Fehlerseite,
Größen-Caps für Foto-/Avatar-Uploads (vor dem Einlesen in den RAM), ZIP-Einträge einzeln aus dem
Upload-Tempfile gelesen und Aufräumen des Rate-Limiter-Speichers.

Fixtures aus tests/base.py: t_plan hat einen GPX OHNE Zeitstempel (geplante Route) und keine
Live-Aufzeichnung – genau der Fall, der vorher je Foto neu geparst hat."""
import datetime as dt
import io
import os
import unittest
import zipfile as _zipfile
from unittest import mock

from tests.base import AppTestCase, appmod, app, db, M, ROOT, make_gpx

try:
    from tests.test_build_ac import make_jpeg, HAVE_IMG
except Exception:                      # pragma: no cover – test_build_ac immer vorhanden
    HAVE_IMG = False


class TimedSourceCacheTest(AppTestCase):
    """Build ag: Die Zeitquelle (GPX sonst Live-Aufzeichnung) wird pro Upload nur EINMAL
    geladen – auch wenn es keine gibt (leeres Ergebnis)."""

    @unittest.skipUnless(HAVE_IMG, 'Pillow/piexif nicht installiert')
    def test_empty_timed_source_loaded_once(self):
        self.login_org()
        appmod._rl_store.clear()
        photos = [(make_jpeg(taken=dt.datetime(2025, 6, 14, 10, 10)), 'a.jpg'),
                  (make_jpeg(taken=dt.datetime(2025, 6, 14, 10, 20)), 'b.jpg')]
        data = {'photos': [(io.BytesIO(b), n) for b, n in photos]}
        # Vor dem Fix: je Foto ein kompletter GPX-Parse (+ Abfragen). XHR ohne Redirect-Follow,
        # damit die Detailseite (einmaliger Kennzahlen-Nachtrag) nicht mitzählt.
        with mock.patch.object(appmod, '_tour_gpx_timed_points',
                               wraps=appmod._tour_gpx_timed_points) as spy:
            r = self.client.post(f'/touren/{self.t_plan_id}/fotos', data=data,
                                 content_type='multipart/form-data', follow_redirects=False,
                                 headers={'X-Requested-With': 'XMLHttpRequest'})
        self.assertEqual(r.status_code, 200)
        js = r.get_json()
        self.assertTrue(js['ok'])
        self.assertEqual(js['count'], 2)
        self.assertEqual(js['no_gps'], 2)             # Hinweis-Logik unverändert
        self.assertEqual(spy.call_count, 1, 'GPX mit leerem Zeit-Ergebnis soll nur 1× geparst werden')

    @unittest.skipUnless(HAVE_IMG, 'Pillow/piexif nicht installiert')
    def test_photos_still_upload_after_cache_change(self):
        self.login_org()
        appmod._rl_store.clear()
        data = {'photos': [(io.BytesIO(make_jpeg()), 'nur_ein_bild.jpg')]}
        r = self.client.post(f'/touren/{self.t_done_id}/fotos', data=data,
                             content_type='multipart/form-data', follow_redirects=True)
        self.assertIn('1 Foto(s) hochgeladen', r.get_data(as_text=True))
        self.assertEqual(M.TourPhoto.query.filter_by(tour_id=self.t_done_id).count(), 1)


class ReminderCronTest(AppTestCase):
    """Build ag: /api/reminder/trigger – Plesk-Geplante-Aufgaben können die Tourtag-/Vorabend-
    Erinnerung pünktlich auslösen; Token wie beim Backup-Trigger (= erste 20 Zeichen SECRET_KEY)."""

    def _url(self, token='falsch'):
        return f'/api/reminder/trigger?token={token}'

    def test_wrong_token_rejected(self):
        r = self.client.get(self._url())
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.get_json(), {'error': 'invalid token'})
        r = self.client.post(self._url(''))
        self.assertEqual(r.status_code, 403)

    def test_correct_token_runs_reminders(self):
        with mock.patch.object(appmod, '_run_tour_reminders', return_value=2) as m:
            r = self.client.get(self._url(app.config['SECRET_KEY'][:20]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), {'ok': True, 'erinnert': 2})
        m.assert_called_once_with()

    def test_trigger_endpoint_skips_self_trigger(self):
        """Der Cron-Aufruf selbst darf den 3-%-Selbst-Trigger nicht zusätzlich auslösen
        (Tagesflags verhindern zwar Doppelsendung, aber der Aufruf soll schnell bleiben)."""
        with mock.patch.object(appmod, '_run_tour_reminders', return_value=0) as m, \
             mock.patch('random.random', return_value=0.0):     # Selbst-Trigger würde immer feuern
            r = self.client.get(self._url(app.config['SECRET_KEY'][:20]))
            self.assertEqual(r.status_code, 200)
            self.assertEqual(m.call_count, 1)                   # nur der Endpunkt selbst
            self.client.get('/')                                # normaler Aufruf → Selbst-Trigger
        self.assertEqual(m.call_count, 2)

    def test_admin_notifications_shows_trigger_url(self):
        self.login_admin()
        html = self.get_html('/admin/benachrichtigungen')
        self.assertIn('/api/reminder/trigger?token=', html)
        self.assertIn('Kopieren', html)

    def test_member_sees_no_cron_box(self):
        self.login_member()
        r = self.client.get('/admin/benachrichtigungen')
        self.assertEqual(r.status_code, 403)


class RequestTooLargeTest(AppTestCase):
    """Build ag: 413 (Upload über MAX_CONTENT_LENGTH) zeigt die freundliche Fehlerseite."""

    def test_413_friendly_page(self):
        self.login_org()
        appmod._rl_store.clear()
        old = app.config['MAX_CONTENT_LENGTH']
        app.config['MAX_CONTENT_LENGTH'] = 200      # künstlich klein – jeder Upload läuft über
        try:
            data = {'photos': (io.BytesIO(b'x' * 500), 'gross.jpg')}
            r = self.client.post(f'/touren/{self.t_done_id}/fotos', data=data,
                                 content_type='multipart/form-data')
            self.assertEqual(r.status_code, 413)
            html = r.get_data(as_text=True)
            self.assertIn('zu viel auf einmal', html)
            self.assertIn('Zurück', html)
        finally:
            app.config['MAX_CONTENT_LENGTH'] = old


@unittest.skipUnless(HAVE_IMG, 'Pillow/piexif nicht installiert')
class UploadSizeCapTest(AppTestCase):
    """Build ag: Größen-Caps werden geprüft, BEVOR die Datei in den RAM gelesen wird;
    ZIPs werden nicht mehr komplett geladen, sondern Eintrag für Eintrag."""

    def setUp(self):
        super().setUp()
        self.login_org()
        appmod._rl_store.clear()

    def _post(self, tour_id, files, extra=None):
        data = {'photos': [(io.BytesIO(b), n) for b, n in files]}
        data.update(extra or {})
        return self.client.post(f'/touren/{tour_id}/fotos', data=data,
                                content_type='multipart/form-data', follow_redirects=True)

    def test_normal_upload_unaffected(self):
        old = app.config['MAX_PHOTO_SIZE']
        app.config['MAX_PHOTO_SIZE'] = 60 * 1024 * 1024
        try:
            r = self._post(self.t_done_id, [(make_jpeg(), 'ok.jpg')])
        finally:
            app.config['MAX_PHOTO_SIZE'] = old
        self.assertIn('1 Foto(s) hochgeladen', r.get_data(as_text=True))

    def test_photo_over_cap_rejected_before_read(self):
        before = M.TourPhoto.query.filter_by(tour_id=self.t_done_id).count()
        old = app.config['MAX_PHOTO_SIZE']
        app.config['MAX_PHOTO_SIZE'] = 10            # absichtlich absurd klein
        try:
            r = self._post(self.t_done_id, [(make_jpeg(), 'riesig.jpg')])
        finally:
            app.config['MAX_PHOTO_SIZE'] = old
        html = r.get_data(as_text=True)
        self.assertIn('⚖️ 1 zu groß', html)
        self.assertIn('0 Foto(s) hochgeladen', html)
        after = M.TourPhoto.query.filter_by(tour_id=self.t_done_id).count()
        self.assertEqual(after, before)

    def test_zip_entries_individual_and_capped(self):
        """ZIP wird aus dem Upload-Tempfile gelesen (nicht komplett in den RAM);
        Einträge über dem Cap werden übersprungen und gezählt, kleine bleiben nutzbar."""
        big = b'\xff\xd8\xff' + b'0' * 3000          # größer als der Test-Cap
        small = make_jpeg()
        buf = io.BytesIO()
        with _zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('ordner/gross.jpg', big)
            zf.writestr('klein.jpg', small)
        before = M.TourPhoto.query.filter_by(tour_id=self.t_done_id).count()
        old = app.config['MAX_PHOTO_SIZE']
        app.config['MAX_PHOTO_SIZE'] = len(small) + 500    # klein passt, groß nicht
        try:
            r = self._post(self.t_done_id, [(buf.getvalue(), 'fotos.zip')])
        finally:
            app.config['MAX_PHOTO_SIZE'] = old
        html = r.get_data(as_text=True)
        self.assertIn('zu groß', html)
        self.assertIn('1 Foto(s) hochgeladen', html)
        self.assertIn('📦 davon 1 aus ZIP', html)
        after = M.TourPhoto.query.filter_by(tour_id=self.t_done_id).count()
        self.assertEqual(after, before + 1)

    def test_avatar_over_cap_rejected(self):
        old = app.config.get('MAX_AVATAR_SIZE')
        app.config['MAX_AVATAR_SIZE'] = 10
        try:
            buf = io.BytesIO()
            from PIL import Image as _PIL
            _PIL.new('RGB', (4, 4), (1, 2, 3)).save(buf, 'PNG')
            buf.seek(0)
            r = self.client.post('/profil/avatar', data={'avatar': (buf, 'ich.png')},
                                 content_type='multipart/form-data', follow_redirects=True)
        finally:
            app.config['MAX_AVATAR_SIZE'] = old
        self.assertIn('zu groß', r.get_data(as_text=True))
        self.assertIsNone(self.user(self.mem_id).avatar or None)   # mem ist eingeloggt …
        # … genauer: der aktuelle Nutzer ist 'hein@test.de' = self.mem
        self.assertIsNone(db.session.get(M.User, self.mem_id).avatar)


class RateLimitStoreCleanupTest(AppTestCase):
    """Build ag: veraltete Keys im Rate-Limiter-Speicher werden bei Gelegenheit entfernt."""

    def test_stale_keys_pruned_when_store_grows(self):
        appmod._rl_store.clear()
        now = appmod._time.time()
        for i in range(600):                       # > 512 → Aufräumen wird scharf geschaltet
            appmod._rl_store[f'alt:{i}'] = [now - 7200]     # 2 h alt (größtes Fenster: 1 h)
        appmod._rl_store['frisch:1'] = [now - 10]
        appmod._rate_limit('frisch:2')             # löst das Aufräumen aus
        self.assertFalse([k for k in appmod._rl_store if k.startswith('alt:')],
                         'veraltete Keys sollen entfernt werden')
        self.assertIn('frisch:1', appmod._rl_store)
        self.assertIn('frisch:2', appmod._rl_store)
        appmod._rl_store.clear()

    def test_recent_keys_survive(self):
        appmod._rl_store.clear()
        now = appmod._time.time()
        for i in range(600):
            appmod._rl_store[f'frisch:{i}'] = [now - 30]    # 30 s alt → behalten
        appmod._rate_limit('neu:1')
        self.assertEqual(len([k for k in appmod._rl_store if k.startswith('frisch:')]), 600)
        appmod._rl_store.clear()


class BuildMarkerTest(AppTestCase):

    def test_build_marker(self):
        self.assertEqual(appmod.APP_BUILD, '2026-11-04 o')


class PauseDetectionTest(AppTestCase):
    """Build aj: Pausen aus GPX-Zeitstempeln – Stehen/Lücken ab 3 min zählen, Bewegung unterbricht.
    make_gpx() hat eine 10-Minuten-Pause bei Punkt 60."""

    def test_helper_counts_single_pause(self):
        import io as _io
        gpx = make_gpx(with_time=True)
        path = os.path.join(app.config['UPLOAD_FOLDER_GPX'], 'pausen_test.gpx')
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(gpx)
        timed = appmod._gpx_timed_points(path)
        pauses = appmod._gpx_pauses(timed)
        self.assertEqual(len(pauses), 1)
        self.assertGreaterEqual(pauses[0][2], 600)          # ~10 min
        n, s = appmod._pauses_summary(pauses)
        self.assertEqual((n, s), (1, pauses[0][2]))

    def test_helper_empty_and_untimed(self):
        self.assertEqual(appmod._gpx_pauses([]), [])
        self.assertEqual(appmod._gpx_pauses([(100.0, 53.0, 9.0)]), [])

    def test_short_standing_is_no_pause(self):
        # 5 Punkte: 2 min stehen (unter 3 min) → keine Pause
        t0 = 1000.0
        pts = [(t0, 53.0, 9.0)]
        for i in range(1, 4):
            pts.append((t0 + i * 40, 53.0, 9.0))            # stehend, je 40 s
        pts.append((t0 + 160 + 30, 53.001, 9.0))            # Fahrt
        self.assertEqual(appmod._gpx_pauses(pts), [])

    @unittest.skipUnless(HAVE_IMG, 'Pillow/piexif nicht installiert')
    def test_upload_sets_pause_columns_and_tile(self):
        self.login_org()
        appmod._rl_store.clear()
        data = {'gpx_file': (io.BytesIO(make_gpx(with_time=True).encode('utf-8')), 'p.gpx')}
        r = self.client.post(f'/touren/{self.t_plan_id}/gpx', data=data,
                             content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        tour = self.tour(self.t_plan_id)
        self.assertIsNotNone(tour.gpx_moving_s)
        self.assertEqual(tour.gpx_pauses_n, 1)              # die 10-min-Pause aus make_gpx
        self.assertGreaterEqual(tour.gpx_pauses_s, 600)
        html = self.get_html(f'/touren/{self.t_plan_id}')
        self.assertIn('Pausen laut GPX-Zeitstempeln', html)   # Kachel vorhanden (Titel-Attribut)

    def test_untimed_gpx_no_pause_tile(self):
        self.login_org()
        appmod._rl_store.clear()
        data = {'gpx_file': (io.BytesIO(make_gpx(with_time=False).encode('utf-8')), 'pl.gpx')}
        self.client.post(f'/touren/{self.t_open_id}/gpx', data=data,
                         content_type='multipart/form-data', follow_redirects=True)
        tour = self.tour(self.t_open_id)
        self.assertIsNone(tour.gpx_moving_s)
        self.assertEqual(tour.gpx_pauses_n, 0)              # berechnet, keine Pausen möglich
        html = self.get_html(f'/touren/{self.t_open_id}')
        self.assertNotIn('Pausen laut GPX-Zeitstempeln', html)   # keine Kachel ohne Zeitstempel


class ReadAloudTest(AppTestCase):
    """Build aj: Vorlesen-Knopf – Text aus Serverdaten, global erreichbare Funktionen."""

    def test_detail_has_button_and_text(self):
        self.login_member()                                  # jeder Mitglied, nicht nur Tourleitung
        html = self.get_html(f'/touren/{self.t_plan_id}')
        self.assertIn('id="btn-read-aloud"', html)           # Build ak: in der Aktions-Reihe
        self.assertIn('toggleReadAloud()', html)
        self.assertIn('function stopReadAloud()', html)
        self.assertIn('TOUR_READ_TEXT', html)
        self.assertIn('Deichtour, mit Komma', html)          # Titel im Vorlesetext (gescapte Seite)
        self.assertIn('Treffpunkt: Bahnhof, Gleis 1', html)

    def test_read_aloud_text_building(self):
        tour = self.tour(self.t_plan_id)
        tour.gpx_km, tour.gpx_ascent, tour.gpx_moving_s, tour.gpx_avg_kmh = 62.1, 306, 13620, 16.8
        tour.gpx_pauses_n, tour.gpx_pauses_s = 3, 2520
        text = appmod._tour_read_aloud_text(tour, 3)
        self.assertIn('Tour Deichtour, mit Komma.', text)
        self.assertIn('62,1 Kilometer', text)
        self.assertIn('306 Höhenmeter', text)
        self.assertIn('3 Stunden 47 Minuten', text)          # 13 620 s
        self.assertIn('16,8 Stundenkilometer', text)
        self.assertIn('3 Pausen, insgesamt 42 Minuten', text)
        self.assertIn('Treffpunkt: Bahnhof, Gleis 1', text)
        self.assertIn('3 Fahrer angemeldet.', text)
        # Abgesagte Tour nennt Absage + Grund
        self.tour(self.t_canc_id).cancel_reason = 'Sturmwarnung'
        text2 = appmod._tour_read_aloud_text(self.tour(self.t_canc_id), 0)
        self.assertIn('abgesagt', text2)
        self.assertIn('Grund: Sturmwarnung', text2)


class ServiceWorkerPhotoPolicyTest(AppTestCase):
    """Audit 4 / Build ai: Fotos/Videos dürfen im Service-Worker nicht mehr cache-first
    serviert werden – sonst bekäme ein ausgeloggter Browser auf einem geteilten Gerät
    Bilder aus dem Cache. Jetzt network-first, Cache nur als Offline-Fallback."""

    def test_sw_photos_network_first(self):
        body = self.client.get('/sw.js').get_data(as_text=True)
        self.assertIn('Fotos/Videos network-first', body)
        # der alte cache-first-Block für Fotos/Videos muss weg
        self.assertNotIn('// Fotos/Videos: cache-first', body)
        # Offline-Fallback existiert weiter
        self.assertIn('caches.match(req).then(c => c || new Response', body)


class MobileCompactViewTest(AppTestCase):
    """Build ah: Tourseite auf dem Smartphone – Kennzahlen-Kacheln in einer Zeile statt
    2×2 große Kärtchen, Knöpfe kompakter (nur CSS unter 576 px + Markup-Anker;
    Großschrift-Modus und Desktop bleiben unangetastet)."""

    def test_detail_has_compact_anchors(self):
        self.login_org()
        html = self.get_html(f'/touren/{self.t_plan_id}')
        self.assertIn('stats-row', html)            # Kennzahlen-Raster (Grid auf dem Handy)
        self.assertIn('id="tour-actions"', html)    # Knopf-Leiste (inkl. Vorlesen, Build ak)
        self.assertIn('id="btn-read-aloud"', html)  # Vorlesen sitzt in der Aktions-Reihe
        self.assertIn('weather-past-tile', html)    # Wetter-Kachel (ganze Breite auf dem Handy)

    def test_short_labels_for_mobile(self):
        self.login_org()
        html = self.get_html(f'/touren/{self.t_done_id}')   # fertige Tour: alle Knöpfe sichtbar
        # volle Texte stehen im Markup, data-short trägt die Handy-Kurzfassung
        self.assertIn('data-short="Vorlage"', html)
        self.assertIn('data-short="Nochmal"', html)
        self.assertIn('data-short="Rückblick"', html)
        self.assertIn('data-short="Drucken"', html)
        self.assertIn('>Als Vorlage speichern</span>', html)
        self.assertIn('function applyShortLabels()', html)   # global (onclick-Regel)

    def test_stylesheet_has_mobile_rules_excluding_big_text(self):
        css = open(os.path.join(ROOT, 'static', 'css', 'style.css'), encoding='utf-8').read()
        self.assertIn('@media (max-width: 575.98px)', css)
        self.assertIn('.stats-row', css)
        self.assertIn('#tour-actions', css)
        self.assertIn('html:not(.big-text) .stats-row .stat-number', css)
        # Build ak: 3er-Raster statt gequetschter Reihe – kein Text-Überlauf mehr
        self.assertIn('grid-template-columns: repeat(3, 1fr)', css)
        self.assertIn('grid-column: 1 / -1', css)


class VideoButtonTest(AppTestCase):
    """Build al: „Rückblick & Video“ und „Video“ zeigten auf dieselbe Seite –
    jetzt gibt es nur noch einen Knopf."""

    def test_completed_with_photos_has_single_video_link(self):
        self.login_org()
        appmod._rl_store.clear()
        data = {'photos': [(io.BytesIO(make_jpeg()), 'rueckblick.jpg')]}
        self.client.post(f'/touren/{self.t_done_id}/fotos', data=data,
                         content_type='multipart/form-data', follow_redirects=True)
        html = self.get_html(f'/touren/{self.t_done_id}')
        # zählt nur den Knopf (href mit schließendem Anführungszeichen) – nicht
        # das Upload-Formular /touren/<id>/videos, das denselben Teilstring trägt
        self.assertEqual(html.count(f'/touren/{self.t_done_id}/video"'), 1,
                         'Rückblick- und Video-Knopf sind EIN Knopf')
        self.assertIn('>Rückblick & Video</span>', html)      # gelber Haupt-Knopf bleibt
        self.assertNotIn('Tour-Video erstellen', html)        # zweiter Knopf ist weg
        self.assertIn('data-short="Rückblick"', html)         # Handy-Kurzschrift unangetastet


class VideoCountTest(AppTestCase):
    """Build am: Video-Anzahlen neben den Foto-Anzahlen – Archiv (Tabelle + Karten),
    Archiv-Suche und Tourseite (Badge neben dem Fotos-Zähler)."""

    def _add_videos(self, tour_id, n=2):
        M.TourVideo.query.delete()          # Tests teilen sich eine DB – immer leer starten
        db.session.commit()
        db.session.add_all(
            M.TourVideo(tour_id=tour_id, user_id=self.org.id, filename=f'v{i}.mp4')
            for i in range(n)
        )
        db.session.commit()

    def test_archiv_shows_video_count_table_and_cards(self):
        self._add_videos(self.t_done_id, 2)
        self.login_org()
        html = self.get_html('/archiv')
        self.assertIn('📷 🎬', html)                       # Spaltenkopf
        self.assertIn('🎬 2', html)                        # Zelle + Karte
        self.assertIn('2 Videos', html)                    # Titel-Attribut (Mehrzahl)

    def test_archiv_search_shows_video_count(self):
        self._add_videos(self.t_done_id, 1)
        self.login_org()
        html = self.get_html('/archiv/suche?q=Alte')
        self.assertIn('🎬 1', html)
        self.assertIn('1 Video">', html)                   # Titel-Attribut (Einzahl)

    def test_detail_shows_video_badge_next_to_photos(self):
        self._add_videos(self.t_done_id, 3)
        self.login_org()
        html = self.get_html(f'/touren/{self.t_done_id}')
        self.assertIn('title="Videos zur Tour">🎬 3</span>', html)   # neben Fotos-Zähler
        self.assertIn('id="videos"', html)                 # Video-Karte weiterhin da

    def test_detail_without_videos_has_no_badge(self):
        M.TourVideo.query.delete()          # sicherstellen, dass wirklich kein Video existiert
        db.session.commit()
        self.login_org()
        html = self.get_html(f'/touren/{self.t_done_id}')
        self.assertNotIn('Videos zur Tour', html)


class VideoSmoothTest(AppTestCase):
    """Build an: Ruckeln in den Bewegungseffekten des Video-Renderers geglättet –
    Ken-Burns-Zoom subpixelgenau (Supersampling + Lanczos + Sanftanlauf),
    Karten-/Stats-/Profil-Animationen mit voller Video-Framerate."""

    @staticmethod
    def _app_src():
        return open(os.path.join(ROOT, 'app.py'), encoding='utf-8').read()

    def test_ken_burns_supersampled_and_eased(self):
        src = self._app_src()
        self.assertIn('scale={W*2}:{H*2}:flags=lanczos', src)     # Supersampling (Build ar: 2x, RAM-schonend)
        self.assertIn('scale={W}:{H}:flags=lanczos,', src)        # feines Downscaling
        self.assertIn('(1-cos(PI*on/', src)                       # Sanftanlauf
        self.assertNotIn('0.09*on/', src)                         # alte lineare Fahrt weg

    def test_card_animations_use_full_framerate(self):
        src = self._app_src()
        self.assertIn('N_STEPS = max(16, int(round(', src)        # Karte: 25 Bilder/s
        self.assertIn('per_frame_dur = round(1 / fps, 3)', src)   # exakte Bild-Taktung
        self.assertIn('step_fps = 4.0, 3.6, fps', src)            # Statistik
        self.assertIn('len(rows)), fps', src)                     # Einkehr
        self.assertIn('step_fps = 3.5, 2.6, fps', src)            # Höhenprofil
        self.assertNotIn('step_fps = 4.0, 3.6, 15', src)          # alte 15-Bilder/s-Taktung weg

    def test_segment_timeouts_raised(self):
        src = self._app_src()
        self.assertIn('capture_output=True, timeout=180', src)

    def test_photo_zoom_30fps_and_quality_segments(self):
        src = self._app_src()
        self.assertIn('fps        = 30', src)                 # ruhig auf 60-Hz-Displays
        self.assertNotIn('fps        = 25', src)              # alter Takt weg
        self.assertIn("seg_codec_opts = (['-c:v', 'libx264', '-preset', 'fast', '-crf', '18']", src)
        self.assertEqual(src.count('*seg_codec_opts,'), 4)    # alle 4 Segment-Encoder
        self.assertIn('(1-cos(PI*on/', src)                   # Sanftanlauf bleibt

    def test_server_has_effect_variety(self):
        src = self._app_src()
        self.assertIn("KB_LANDSCAPE = ['zoom_in', 'zoom_out', 'pan_lr', 'pan_rl', 'pan_ud', 'pan_du', 'diag', 'diag_back']", src)
        self.assertIn("KB_PORTRAIT  = ['zoom_in', 'zoom_out', 'pan_lr', 'pan_rl', 'drift_lr', 'drift_rl']", src)
        self.assertIn('def ken_burns_exprs(effect, n_frames):', src)   # Build aq: Modul-Ebene
        self.assertIn("effect='zoom_in', overlay_png=None", src)   # neue Signatur
        self.assertIn('effect=_kb_effect', src)                     # Aufrufstelle
        self.assertIn('_oh >= _ow', src)                            # Hochkant ohne Vertikal-Fahrten
        self.assertNotIn('zoom_in = (i % 2 == 0)', src)             # alt: nur rein/raus

    def test_as_minimap_lower_and_motion_smoothing(self):
        src = self._app_src()
        self.assertIn("' tmix ' in _flt.stdout", src)               # tmix-Verfügbarkeit wird geprüft
        self.assertIn("'tmix=frames=2,' if _tmix_ok else ''", src)  # Motion-Blur nur wenn verfügbar

    def test_h_live_status_endpoint_and_single_indicator(self):
        # Build h (2026-11-04): Live-Status ohne Seitenwechsel, EINE zentrale Anzeige,
        # „Fahren“ deaktiviert während der Fahrt.
        self.login_org()
        _grp = M.Tour.query.get(self.t_plan_id).group_id
        t = M.Tour(title='Fahrt-Läuft', tour_date=dt.date.today(), status='planned',
                   created_by=self.org_id, group_id=_grp)
        db.session.add(t)
        db.session.commit()
        self.client.post('/api/location/update',
                         json={'tour_id': t.id, 'lat': 53.10, 'lng': 9.20, 'accuracy': 10})
        # 1) Endpunkt liefert den Status fürs JS-Polling
        d = self.client.get('/api/live/now').get_json()
        self.assertTrue(d['live'])
        self.assertEqual(d['live']['tour_id'], t.id)
        self.assertEqual(d['live']['n'], 1)
        self.assertTrue(d['live']['recording'])
        # 2) Navbar: Host-Span + Polling-JS (Status erscheint ohne Menüwechsel)
        base = open(os.path.join(ROOT, 'templates', 'base.html'), encoding='utf-8').read()
        self.assertIn('id="live-now-host"', base)
        self.assertIn("fetch('/api/live/now'", base)
        self.assertIn('setInterval(pollLive, 30000)', base)
        # 3) Tour-Seite: „Fahren“ deaktiviert als „Fahrt läuft“, KEIN zweiter roter Badge
        det = self.client.get(f'/touren/{t.id}').get_data(as_text=True)
        self.assertIn('<span class="lbl">Fahrt läuft</span>', det)
        self.assertIn('id="fahren-running"', det)                        # Build o: laufende Fahrt sichtbar
        self.assertNotIn('id="fahren-running" class="d-none"', det)      # … und nicht versteckt
        self.assertIn('title="Auf dieser Tour läuft gerade eine Fahrt', det)
        self.assertNotIn('🔴 {{', det)
        self.assertNotIn('>🔴 ', det)
        self.assertNotIn('href="{{ url_for(\'tour_live\', tour_id=tour.id) }}" class="btn btn-sm btn-danger"', det)
        # 4) ohne laufende Fahrt: normaler Fahren-Knopf
        db.session.execute(db.text("UPDATE live_locations SET updated_at = datetime('now', '-10 minutes')"))
        db.session.commit()
        det = self.client.get(f'/touren/{t.id}').get_data(as_text=True)
        self.assertIn('<span class="lbl">Fahren</span>', det)
        self.assertIn('id="fahren-running" class="d-none"', det)     # Build o: Variante verborgen statt entfernt

    def test_o_fahren_button_updates_itself(self):
        # Build o (2026-11-04): „Fahren“/„Fahrt läuft“ auf der Tourseite hält sich selbst
        # aktuell – base.html pollt /api/live/now und ruft den Hook djoLiveNowUpdate, der
        # zwischen den beiden serverseitig gerenderten Varianten (eine d-none) umschaltet.
        base = open(os.path.join(ROOT, 'templates', 'base.html'), encoding='utf-8').read()
        self.assertIn('if (window.djoLiveNowUpdate)', base)
        det = open(os.path.join(ROOT, 'templates', 'touren', 'detail.html'), encoding='utf-8').read()
        self.assertIn('id="fahren-host"', det)
        self.assertIn('id="fahren-running"', det)
        self.assertIn('id="fahren-normal"', det)
        self.assertIn('window.djoLiveNowUpdate = function (lv)', det)
        self.assertIn("run.classList.toggle('d-none', !active)", det)
        self.assertIn("nor.classList.toggle('d-none', active)", det)

    def test_i_stop_button_clearly_named(self):
        # Build i (2026-11-04): Der Stopp-Knopf auf der Live-Karte heißt klar „⏹ Fahrt beenden“
        # (hieß „Teilen beenden“ und war in der Daumenleiste abgeschnitten); nach dem Beenden
        # verrät der Status, wie die Aufzeichnung gesichert wird.
        live = open(os.path.join(ROOT, 'templates', 'touren', 'live.html'), encoding='utf-8').read()
        self.assertIn("sharing ? '⏹ Fahrt beenden' : '▶ Fahrt starten'", live)
        self.assertNotIn('Teilen beenden', live)                       # alter, abgeschnittener Name weg
        self.assertIn('„⏹ Fahrt beenden“', live)                       # Hinweise-Block nennt den Knopf beim Namen
        self.assertIn('Als GPX übernehmen', live)                      # Status nach dem Beenden verrät das Sichern
        self.assertIn('#btn-share { flex: 2.2 1 0;', live)             # Knopf breit genug für das ganze Wort

    def test_m_stop_button_wraps_not_truncates(self):
        # Build m (2026-11-04): „⏹ Fahrt beenden“ wird in der Daumenleiste nicht mehr mit
        # „Fahrt bee…“ abgeschnitten – der Knopf darf zweizeilig werden; auf sehr schmalen
        # Displays wird die Schrift der Fahrt-Knöpfe leicht verkleinert.
        live = open(os.path.join(ROOT, 'templates', 'touren', 'live.html'), encoding='utf-8').read()
        self.assertIn('#live-bar #btn-share { flex: 2.2 1 0; white-space: normal; line-height: 1.15; text-overflow: clip; }', live)  # Build n: hoeher spezifisch – nowrap aus '#live-bar .btn' darf nicht gewinnen
        self.assertIn('@media (max-width: 374.98px) { #live-bar .lb-main .btn { font-size: .9rem; } }', live)

    def test_l_stop_status_links_to_recording(self):
        # Build l (2026-11-04): Auch die Meldung nach „⏹ Fahrt beenden“ verlinkt direkt –
        # „Als GPX übernehmen“ springt zum Aufzeichnungs-Bereich (#live-aufzeichnung) der
        # Tourseite. Nachzieher zu Build j: Auch der Aufzeichnungs-Kasten auf der Tourseite
        # sagt jetzt „Fahren“ statt „Standort teilen“.
        live = open(os.path.join(ROOT, 'templates', 'touren', 'live.html'), encoding='utf-8').read()
        self.assertIn("#live-aufzeichnung\">Als GPX übernehmen</a>", live)
        self.assertIn("mit <a href=\"/touren/' + TOUR_ID + '#live-aufzeichnung\"", live)
        self.assertNotIn('mit „Als GPX übernehmen“', live)             # alte reine-Text-Formulierung weg
        self.assertIn(", '', true)", live)                             # Meldung als HTML gerendert (neutral eingefärbt)
        det = open(os.path.join(ROOT, 'templates', 'touren', 'detail.html'), encoding='utf-8').read()
        self.assertIn('id="live-aufzeichnung"', det)                   # Anker existiert auf der Tourseite
        self.assertNotIn('„Standort teilen“', det)                     # alter Begriff auch hier vergangen

    def test_k_photo_status_links_to_photos(self):
        # Build k (2026-11-04): Nach „Foto gespeichert“ ist „Zur Tour → Fotos“ ein echter
        # Link, der direkt zum Fotos-Bereich der Tourseite springt (#fotos).
        live = open(os.path.join(ROOT, 'templates', 'touren', 'live.html'), encoding='utf-8').read()
        self.assertIn('function setStatus(text, cls, asHtml)', live)
        self.assertIn('''. <a href="/touren/' + TOUR_ID + '#fotos">Zur Tour → Fotos</a>''', live)
        self.assertIn(", 'sharing', true)", live)                      # Foto-Meldung als HTML gerendert
        self.assertIn('#fotos">Zur Tour → Fotos</a>', live)            # auch im Hinweise-Block verlinkt
        det = open(os.path.join(ROOT, 'templates', 'touren', 'detail.html'), encoding='utf-8').read()
        self.assertIn('id="fotos"', det)                               # Anker existiert auf der Tourseite

    def test_j_ride_terms_unified(self):
        # Build j (2026-11-04): Einheitliche Begriffe – „Fahren“ (Tourseite/Navigation) und der
        # grüne Live-Knopf sind dasselbe: der Knopf heißt jetzt „▶ Fahrt starten“ (statt
        # „Standort teilen“), der rote „⏹ Fahrt beenden“; auch die Zeitfenster-Hinweise in
        # app.py sagen „Fahren“ statt „Standort teilen“.
        live = open(os.path.join(ROOT, 'templates', 'touren', 'live.html'), encoding='utf-8').read()
        self.assertIn('>▶ Fahrt starten</button>', live)
        self.assertNotIn('Standort teilen', live)                  # alter Begriff auf der Live-Seite komplett weg
        self.assertIn('Wer die Fahrt startet („▶ Fahrt starten“)', live)   # Hinweise-Block gleicher Begriff
        self.assertIn('Fahrt nach 8 Stunden automatisch beendet', live)
        self.assertIn('Fahrt starten – dein Standort wird für alle geteilt', live)   # Tooltip erklärt das Teilen
        app_src = open(os.path.join(ROOT, 'app.py'), encoding='utf-8').read()
        self.assertIn('Fahren ist ab dem Vortag der Tour möglich', app_src)
        self.assertNotIn('Standort teilen geht', app_src)

    def test_g_ride_survives_page_change(self):
        # Build g (2026-11-04): „Fahren“ bleibt über Seitenwechsel aktiv –
        # kein Stop beim Verlassen der Live-Seite, globaler Tracker + Pill, Auto-Resume.
        live = open(os.path.join(ROOT, 'templates', 'touren', 'live.html'), encoding='utf-8').read()
        self.assertNotIn("addEventListener('pagehide'", live)          # Seitenwechsel beendet die Fahrt NICHT mehr
        self.assertIn('djoFahren.set({tour_id: TOUR_ID', live)         # Start merkt die Fahrt
        self.assertIn('djoFahren.clear()', live)                       # Beenden räumt auf
        self.assertIn('_fs.tour_id === TOUR_ID))) startShare();', live)  # Auto-Resume ohne ?share=1
        self.assertIn('während du in der App andere Seiten anschaust', live)
        base = open(os.path.join(ROOT, 'templates', 'base.html'), encoding='utf-8').read()
        self.assertIn("const KEY = 'djo_fahren'", base)                # globaler Tracker
        self.assertIn('/api/location/update', base)
        self.assertIn('/api/location/stop?tour_id=', base)
        self.assertIn("getElementById('btn-share')", base)             # Live-Seite hat Vorrang
        self.assertIn("8 * 3600 * 1000", base)                         # 8-h-Limit auch im Tracker
        css = open(os.path.join(ROOT, 'static', 'css', 'style.css'), encoding='utf-8').read()
        self.assertIn('.fahrt-pill', css)
        # Tracker-Skript nur für angemeldete Nutzer
        i_if = base.rfind('{% if current_user.is_authenticated %}', 0, base.find("const KEY = 'djo_fahren'"))
        self.assertGreater(i_if, -1)

    def test_f_live_now_badge_and_no_topo(self):
        # Build f (2026-11-04): zentraler Live-Punkt in der Navbar + Tour-Seite, Topo-Karte entfernt
        self.login_org()
        _grp = M.Tour.query.get(self.t_plan_id).group_id
        t = M.Tour(title='Live-Jetzt', tour_date=dt.date.today(), status='planned',
                   created_by=self.org_id, group_id=_grp)
        db.session.add(t)
        db.session.commit()
        # frische Position mit Aufzeichnung (ohne paused)
        d = self.client.post('/api/location/update',
                             json={'tour_id': t.id, 'lat': 53.10, 'lng': 9.20, 'accuracy': 10}).get_json()
        self.assertTrue(d['recorded'])
        # 1) Navbar: roter Live-Punkt mit Anzahl + Aufzeichnung, verlinkt auf die Live-Karte
        home = self.client.get('/').get_data(as_text=True)
        self.assertIn('live-now-badge', home)
        self.assertIn('1 unterwegs', home)
        self.assertIn('Aufzeichnung läuft', home)
        # 2) Tour-Seite: KEIN eigener roter Badge mehr (Build h: die Navbar-Anzeige ist DIE eine)
        det = self.client.get(f'/touren/{t.id}').get_data(as_text=True)
        self.assertNotIn('>🔴 ', det)
        # 3) nach 10 Minuten Funkstille: kein Live-Punkt mehr (rohes SQL – updated_at
        # hat einen onupdate-Hook, der jedes ORM-Update auf „jetzt“ zurücksetzt)
        db.session.execute(db.text(
            "UPDATE live_locations SET updated_at = datetime('now', '-10 minutes')"))   # ALLE Zeilen – frühere Tests haben evtl. eigene frische hinterlassen
        db.session.execute(db.text(
            "UPDATE live_track_points SET recorded_at = datetime('now', '-10 minutes')"))
        db.session.commit()
        home = self.client.get('/').get_data(as_text=True)
        self.assertIn('<span id="live-now-host"></span>', home)   # Host leer = keine Fahrt aktiv
        det = self.client.get(f'/touren/{t.id}').get_data(as_text=True)
        self.assertNotIn('unterwegs · Aufzeichnung läuft', det)
        # 4) Topo-Karte weg: weder Knopf noch Layer, OSM/Sat bleiben
        self.assertNotIn('btn-topo', det)
        self.assertNotIn('opentopomap', det)
        self.assertIn('btn-osm', det)
        self.assertIn('btn-sat', det)
        self.assertIn("#btn-osm,#btn-sat'", det)

    def test_d_live_infos_collapsed_status_clear_rides_folded(self):
        # Build c (2026-11-04): Live-Beschreibungen einklappbar, Status deutlich,
        # Fahrgemeinschaften auf der Tour-Seite eingeklappt.
        self.login_org()
        live = self.client.get(f'/touren/{self.t_plan_id}/live').get_data(as_text=True)
        # Genau EIN kombinierter Hinweis-Block, schön strukturiert
        self.assertEqual(live.count('details class="small text-muted live-info'), 1)
        self.assertIn('<i class="bi bi-info-circle me-1"></i>Hinweise', live)
        self.assertIn('live-info-grid', live)
        self.assertIn('👀 Zuschauen &amp; Fahren:</strong>', live)   # Build j: ein Begriff für Start/Stop
        self.assertIn('⏸ Pause:</strong>', live)
        self.assertIn('📝 Aufzeichnung:</strong>', live)
        self.assertIn('📷 Foto:</strong>', live)
        self.assertNotIn('id="live-rec-hint"', live)
        self.assertNotIn('id="live-hinweise"', live)
        # Lücke weg: kein Karten-Überstand, Laufraum am Seitenende
        self.assertNotIn('margin-bottom: 116px', live)
        self.assertNotIn('margin-bottom: 152px', live)
        self.assertIn('body { padding-bottom: calc(174px', live)
        # Status-Leiste mit klaren Zuständen (CSS) + setStatus nutzt sie
        self.assertIn('#live-status { padding:', live)
        self.assertIn('#live-status.warning { background:', live)
        self.assertIn("#live-status.danger  { background:", live)
        self.assertIn("el.className = 'mb-2 ' + (cls === 'danger' ? 'danger'", live)
        self.assertNotIn("el.className = 'small mb-2", live)
        # Fahrgemeinschaften: Header klappt, Body collapse ohne "show" (eingeklappt)
        html = self.client.get(f'/touren/{self.t_plan_id}').get_data(as_text=True)
        self.assertIn('data-bs-target="#rides-body"', html)
        self.assertLess(html.find('data-bs-target="#rides-body"'), html.find('id="rides-body"'))
        self.assertNotIn('class="collapse show" id="rides-body"', html)
        self.assertIn('class="collapse" id="rides-body"', html)

    def test_c_fahren_shortcut_and_thumb_bar(self):
        # Build b (2026-11-04): Blitzstart /fahren + mobil Daumenleiste + App-Verknüpfungen
        self.login_org()
        # 1) Fixture-Tour (t_plan, geplant) wird gefunden → Live-Karte mit Auto-Start
        r = self.client.get('/fahren')
        self.assertEqual(r.status_code, 302)
        self.assertIn(f'/touren/{self.t_plan_id}/live', r.headers['Location'])
        self.assertTrue(r.headers['Location'].endswith('?share=1'))
        # 2) „heute ohne Anmeldung“ schlägt „angemeldet, aber in der Zukunft“
        _grp = M.Tour.query.get(self.t_plan_id).group_id   # Tests laufen im Gruppen-Kontext
        t_heute = M.Tour(title='Heute-Fahrt', tour_date=dt.date.today(), status='planned',
                         created_by=self.org_id, group_id=_grp)
        t_später = M.Tour(title='Später-Fahrt', tour_date=dt.date.today() + dt.timedelta(days=9),
                          status='planned', created_by=self.org_id, group_id=_grp)
        db.session.add_all([t_heute, t_später])
        db.session.commit()
        db.session.add(M.TourParticipant(tour_id=t_später.id, user_id=self.org_id, status='attending'))
        db.session.commit()
        r = self.client.get('/fahren')
        self.assertIn(f'/touren/{t_heute.id}/live', r.headers['Location'])
        # 3) Anmeldung als Gleichstandskriterium: ohne heutige Tour gewinnt die früheste angemeldete
        db.session.delete(t_heute)
        db.session.commit()
        t_att = M.Tour(title='Angemeldet-Fahrt', tour_date=dt.date.today() + dt.timedelta(days=3),
                       status='planned', created_by=self.org_id, group_id=_grp)
        db.session.add(t_att)
        db.session.commit()
        db.session.add(M.TourParticipant(tour_id=t_att.id, user_id=self.org_id, status='attending'))
        db.session.commit()
        r = self.client.get('/fahren')
        self.assertIn(f'/touren/{t_att.id}/live', r.headers['Location'])
        # 4) Live-Seite via ?share=1 erreichbar, Daumenleiste-Struktur da
        html = self.client.get(f'/touren/{t_att.id}/live?share=1').get_data(as_text=True)
        self.assertIn('id="btn-pause"', html)
        self.assertIn('class="lb-main"', html)
        self.assertIn('class="lb-sec"', html)
        # 5) CSS (Inline in live.html – dort gewinnt es gegen die bestehenden Regeln)
        live_src = open(os.path.join(ROOT, 'templates', 'touren', 'live.html'), encoding='utf-8').read()
        self.assertIn('flex-direction: column-reverse', live_src)
        self.assertIn('bottom: calc(58px + env(safe-area-inset-bottom))', live_src)
        # 6) manifest: App-Verknüpfungen
        import json as _json
        man = _json.load(open(os.path.join(ROOT, 'static', 'manifest.json'), encoding='utf-8'))
        self.assertEqual([s['url'] for s in man['shortcuts']], ['/fahren', '/touren'])


    def test_b_ride_pause_and_fahren_start(self):
        # Build b: Fahrt starten ab der Tourseite, Auto-/Manuell-Pause stoppt die Aufzeichnung,
        # Standort bleibt für die anderen sichtbar.
        self.login_org()
        t_today = M.Tour(title='Heute-Tour', tour_date=dt.date.today(), status='planned',
                         created_by=self.org_id)
        db.session.add(t_today)
        db.session.commit()
        # 1) Tourseite: grüner „Fahren“-Knopf mit Deep-Link zur Live-Karte (Auto-Start)
        html = self.client.get(f'/touren/{t_today.id}').get_data(as_text=True)
        self.assertIn('<span class="lbl">Fahren</span>', html)
        self.assertIn('?share=1', html)
        # 2) Positions-Update ohne paused → Aufzeichnungspunkt
        pos = {'tour_id': t_today.id, 'lat': 53.10, 'lng': 9.20, 'accuracy': 10}
        d = self.client.post('/api/location/update', json=pos).get_json()
        self.assertTrue(d['ok'])
        self.assertTrue(d['recorded'])
        # 3) mit paused → LiveLocation bleibt aktualisiert, aber KEIN neuer Spurpunkt
        pt = M.LiveTrackPoint.query.filter_by(tour_id=t_today.id).order_by(M.LiveTrackPoint.id.desc()).first()
        pt.recorded_at = pt.recorded_at - dt.timedelta(seconds=10)
        db.session.commit()
        d = self.client.post('/api/location/update', json={**pos, 'lat': 53.1001, 'paused': True}).get_json()
        self.assertFalse(d['recorded'])
        self.assertEqual(M.LiveTrackPoint.query.filter_by(tour_id=t_today.id).count(), 1)
        self.assertIsNotNone(M.LiveLocation.query.filter_by(tour_id=t_today.id).first())
        # 4) paused wieder weg → Aufzeichnung läuft weiter (Auto-Fortsetzung)
        pt = M.LiveTrackPoint.query.filter_by(tour_id=t_today.id).order_by(M.LiveTrackPoint.id.desc()).first()
        pt.recorded_at = pt.recorded_at - dt.timedelta(seconds=10)
        db.session.commit()
        d = self.client.post('/api/location/update', json={**pos, 'lat': 53.1002}).get_json()
        self.assertTrue(d['recorded'])
        # 5) Live-Seite: Pause-Knopf, Auto-Pause-Logik, Auto-Start-Parameter
        live_src = open(os.path.join(ROOT, 'templates', 'touren', 'live.html'), encoding='utf-8').read()
        self.assertIn('id="btn-pause"', live_src)
        self.assertIn('togglePause', live_src)
        self.assertIn('PAUSE_AFTER_S', live_src)
        self.assertIn("paused: isPaused()", live_src)
        self.assertIn("get('share')", live_src)
        # 6) Server-Verzweigung vorhanden
        app_src = open(os.path.join(ROOT, 'app.py'), encoding='utf-8').read()
        self.assertIn('False if paused else _live_track_add', app_src)

    def test_bk_video_first_frame_not_black(self):
        # WhatsApp & Co. bauen die Chat-Vorschau aus den ersten Videobildern.
        # Build bk: Das ERSTE Segment startet ohne fade-in – Aufrufe nutzen fade_in=wrote_any
        # (bj hatte die Logik invertiert: "not wrote_any" = erstes Segment MIT Einblendung).
        import re as _re
        src = open(os.path.join(ROOT, 'app.py'), encoding='utf-8').read()
        # _fade_vf isoliert ausführen
        m = _re.search(r"def _fade_vf\(duration, fade_in=True\):\n(?:\s+.*\n)+?\s+return .+\.join\(parts\)", src)
        self.assertIsNotNone(m, '_fade_vf hat keinen fade_in-Parameter')
        ns = {'FADE_IN': 0.25, 'FADE_OUT': 0.35}
        exec(m.group(0).replace('        def', 'def'), ns)
        self.assertNotIn('fade=t=in', ns['_fade_vf'](3, fade_in=False))
        self.assertIn('fade=t=out', ns['_fade_vf'](3, fade_in=False))
        self.assertIn('fade=t=in', ns['_fade_vf'](3))
        # Polarität: ALLE 9 Aufruf-Stellen nutzen fade_in=wrote_any (NICHT die invertierte Variante)
        self.assertEqual(src.count('fade_in=wrote_any'), 9)
        self.assertNotIn('fade_in=not wrote_any', src)
        # Semantik der Aufruf-Logik nachgebaut
        wrote_any = False
        first_fade_in = wrote_any
        wrote_any = True
        second_fade_in = wrote_any
        self.assertFalse(first_fade_in, 'erstes Segment muss sichtbar starten')
        self.assertTrue(second_fade_in, 'folgende Segmente behalten den Dip')
        self.assertEqual(src.count('wrote_any = True'), 9)


    def test_bi_photo_delete_no_nested_forms(self):
        # Build bi: Das Bulk-Formular darf die Foto-Karten NICHT umschließen –
        # verschachtelte <form>-Tags verwirft der Browser, dann tut der Papierkorb nichts.
        from html.parser import HTMLParser

        class FormDepth(HTMLParser):
            def __init__(self):
                super().__init__()
                self.depth = 0
                self.max_depth = 0
            def handle_starttag(self, tag, attrs):
                if tag == 'form':
                    self.depth += 1
                    self.max_depth = max(self.max_depth, self.depth)
            def handle_endtag(self, tag):
                if tag == 'form':
                    self.depth -= 1

        self.login_org()
        import os as _os
        from PIL import Image as _Img
        t = M.Tour.query.get(self.t_done_id)
        fn = 'dbg_bi.jpg'
        _Img.new('RGB', (4, 4), 'blue').save(_os.path.join(app.config['UPLOAD_FOLDER_PHOTOS'], fn))
        db.session.add(M.TourPhoto(tour_id=t.id, user_id=self.org_id, filename=fn))
        db.session.commit()
        html = self.client.get(f'/touren/{self.t_done_id}').get_data(as_text=True)
        p = FormDepth()
        p.feed(html)
        self.assertEqual(p.max_depth, 1, 'Kein Formular darf in einem anderen liegen')
        self.assertEqual(p.depth, 0)
        # Lösch-Formular je Foto vorhanden und Checkbox an bulk-form angebunden
        self.assertIn("confirm('Foto löschen?')", html)
        self.assertIn('form="bulk-form"', html)
        self.assertIn('id="bulk-form"', html)

    def test_bh_multi_einkehr(self):
        self.login_org()
        spot = M.GastroSpot(name='Café Windbruch', spot_type='cafe', lat=53.5, lng=9.9, added_by=self.org_id)
        db.session.add(spot)
        db.session.commit()
        t = M.Tour.query.get(self.t_plan_id)
        base = {'title': t.title, 'tour_date': t.tour_date.isoformat()}
        # Stopps 1–3 setzen (1 = Gastro + Freitext, 2 = nur Freitext, 3 = nur Gastro)
        self.client.post(f'/touren/{self.t_plan_id}/bearbeiten',
                         data={**base, 'gastro_spot_id': str(spot.id), 'einkehr_text': 'Hauptstopp',
                               'einkehr2_text': 'Picknick am Deich',
                               'einkehr3_spot_id': str(spot.id)},
                         follow_redirects=True)
        t = M.Tour.query.get(self.t_plan_id)
        self.assertEqual(t.einkehr3_spot_id, spot.id)
        self.assertEqual(t.einkehr2_text, 'Picknick am Deich')
        # Tour-Seite: Kopfzeile zeigt alle drei in Reihenfolge
        html = self.client.get(f'/touren/{self.t_plan_id}').get_data(as_text=True)
        i1, i2, i3 = html.find('Einkehr:</strong>'), html.find('2. Stopp:'), html.find('3. Stopp:')
        self.assertTrue(0 < i1 < i2 < i3, 'Reihenfolge Einkehr → 2. Stopp → 3. Stopp')
        self.assertIn('Picknick am Deich', html)
        # Bearbeiten-Formular: Zeilen vorhanden, beide Stopps belegt → kein Hinzufügen-Knopf
        edit_html = self.client.get(f'/touren/{self.t_plan_id}/bearbeiten').get_data(as_text=True)
        self.assertIn('js-einkehr-extra', edit_html)
        self.assertIn('name="einkehr3_spot_id"', edit_html)
        self.assertNotIn('id="btn-einkehr-add"', edit_html)
        # Kurztext (Erinnerung/ICS/Kalender): alle Stopps, getrennt mit „ → “
        txt = appmod._tour_einkehr_text(M.Tour.query.get(self.t_plan_id))
        self.assertIn('Hauptstopp', txt)
        self.assertIn('Picknick am Deich', txt)
        self.assertIn(' → ', txt)
        self.assertLess(txt.find('Picknick'), txt.rfind('Café Windbruch'))
        # Video: Gastro-Stopps in Reihenfolge (Freitext ohne Position fehlt), ohne Track ohne km
        entries = appmod._planned_einkehr_entries(M.Tour.query.get(self.t_plan_id), [])
        self.assertEqual([e['name'] for e in entries], ['Café Windbruch', 'Café Windbruch'])
        self.assertFalse(entries[0]['km_known'])
        # Vorlesen: Haupt-Einkehr + weitere Stopps
        ra = appmod._tour_read_aloud_text(M.Tour.query.get(self.t_plan_id), 2)
        self.assertIn('Einkehr bei Café Windbruch', ra)
        self.assertIn('Später außerdem Einkehr bei', ra)
        # Druckansicht: alle Stopps
        pr = self.client.get(f'/touren/{self.t_plan_id}/drucken').get_data(as_text=True)
        self.assertIn('2. Stopp', pr)
        self.assertIn('Picknick am Deich', pr)
        # Aufräumen: Zeilen leer lassen → alle Stopps weg
        self.client.post(f'/touren/{self.t_plan_id}/bearbeiten', data=base, follow_redirects=True)
        t = M.Tour.query.get(self.t_plan_id)
        self.assertIsNone(t.einkehr2_spot_id)
        self.assertIsNone(t.einkehr3_text)
        self.assertEqual(appmod._tour_einkehr_text(t), '')
        # … und der Hinzufügen-Knopf ist wieder da
        edit_html = self.client.get(f'/touren/{self.t_plan_id}/bearbeiten').get_data(as_text=True)
        self.assertIn('id="btn-einkehr-add"', edit_html)

    def test_bf_gastro_sort_options(self):
        # Menschliche A–Z-Sortierung: Ä wie A, Ö wie O, Ü wie U
        self.assertEqual(appmod._de_name_key('Über den Deich'), 'uber den deich')
        self.assertLess(appmod._de_name_key('Altes Fischerhaus'), appmod._de_name_key('änder disse'))
        self.assertLess(appmod._de_name_key('Örtlicher Hof'), appmod._de_name_key('Zoo'))
        # Server-Listenreihenfolge: Umlaute nicht mehr hinten
        self.login_org()
        db.session.add_all([
            M.GastroSpot(name='Über den Deich', spot_type='restaurant', lat=53.5, lng=9.9, added_by=self.org_id),
            M.GastroSpot(name='Bistro Seefeld', spot_type='restaurant', lat=53.5, lng=9.9, added_by=self.org_id),
            M.GastroSpot(name='Altes Fischerhaus', spot_type='restaurant', lat=53.5, lng=9.9, added_by=self.org_id),
        ])
        db.session.commit()
        html = self.client.get('/gastro').get_data(as_text=True)
        self.assertLess(html.find('Altes Fischerhaus'), html.find('Bistro Seefeld'))
        self.assertLess(html.find('Bistro Seefeld'), html.find('Über den Deich'))
        # Sortierknöpfe vorhanden, A–Z ist Standard aktiv, Karten tragen Sortier-Daten
        self.assertIn('sortByRating', html)
        self.assertIn('sortByNewest', html)
        self.assertIn('id="btn-sort-name" class="js-sort btn btn-djo btn-sm"', html)
        self.assertIn('data-rating=', html)
        self.assertIn('data-created=', html)
        # bg: Einkehr-Dropdown im Tour-Formular ebenfalls menschlich sortiert
        choices = [name for _sid, name, _t in appmod.gastro_spot_choices()]
        self.assertLess(choices.index('Altes Fischerhaus'), choices.index('Bistro Seefeld'))
        self.assertLess(choices.index('Bistro Seefeld'), choices.index('Über den Deich'))
        create_html = self.client.get('/touren/neu').get_data(as_text=True)
        self.assertLess(create_html.find('Altes Fischerhaus'), create_html.find('Über den Deich'))

    def test_be_manual_moving_time(self):
        self.login_org()
        # Grunddaten mitschicken, damit die Tour unverändert bleibt (nur Fahrzeit)
        t = M.Tour.query.get(self.t_plan_id)
        base = {'title': t.title, 'tour_date': t.tour_date.isoformat()}
        # 1) manuell setzen (Touren-Bearbeiten) → Zeit + Ø erscheinen, Detail zeigt „3:30“
        r = self.client.post(f'/touren/{self.t_plan_id}/bearbeiten',
                             data={**base, 'moving_time': '3:30'}, follow_redirects=True)
        self.assertIn('Tour aktualisiert', r.get_data(as_text=True))
        t = M.Tour.query.get(self.t_plan_id)
        self.assertEqual(t.gpx_moving_s, 3 * 3600 + 30 * 60)
        self.assertTrue(t.time_manual)
        self.assertIn('3:30', self.client.get(f'/touren/{self.t_plan_id}').get_data(as_text=True))
        # 2) ungültiges Format → Meldung, kein 500
        r = self.client.post(f'/touren/{self.t_plan_id}/bearbeiten',
                             data={**base, 'moving_time': '3h30'}, follow_redirects=True)
        self.assertIn('Stunden:Minuten', r.get_data(as_text=True))
        # 3) Feld leeren → automatisch neu ermitteln (GPX ohne Zeitstempel → wieder „–“)
        self.client.post(f'/touren/{self.t_plan_id}/bearbeiten',
                         data={**base, 'moving_time': ''}, follow_redirects=True)
        t = M.Tour.query.get(self.t_plan_id)
        self.assertFalse(t.time_manual)
        self.assertIsNone(t.gpx_moving_s)

    def test_bd_orte_form_map_first_on_mobile(self):
        html = open(os.path.join(ROOT, 'templates', 'orte', 'form.html'), encoding='utf-8').read()
        self.assertIn('order-2 order-md-1', html)                 # Formular mobil danach
        self.assertIn('order-1 order-md-2', html)                 # Karte mobil zuerst

    def test_bb_unified_mobile_map_guard(self):
        js = open(os.path.join(ROOT, 'static', 'js', 'map-touch.js'), encoding='utf-8').read()
        self.assertIn('L.Map.addInitHook', js)                    # automatisch für jede Karte
        self.assertIn("mergeOptions({ mobileGuard: true })", js)
        self.assertIn('Tippen zum Aktivieren', js)
        self.assertIn("data-map-guard-hint", js)                  # eigener Text je Karte
        self.assertIn("mapGuard === 'off'", js)                   # Opt-out (data-map-guard="off")
        base = open(os.path.join(ROOT, 'templates', 'base.html'), encoding='utf-8').read()
        self.assertIn('js/map-touch.js', base)                    # zentral geladen (nach Leaflet)
        detail = open(os.path.join(ROOT, 'templates', 'touren', 'detail.html'), encoding='utf-8').read()
        self.assertNotIn('map-touch-overlay', detail)             # Inline-Duplikat entfernt
        self.assertNotIn('const isMobile', detail)
        karte = open(os.path.join(ROOT, 'templates', 'karte.html'), encoding='utf-8').read()
        self.assertNotIn('Tippen zum Aktivieren', karte)          # Inline-Duplikat entfernt
        gastro = open(os.path.join(ROOT, 'templates', 'gastro', 'form.html'), encoding='utf-8').read()
        self.assertIn('data-map-guard-hint', gastro)              # Picker-Hinweis
        printv = open(os.path.join(ROOT, 'templates', 'touren', 'print.html'), encoding='utf-8').read()
        self.assertIn('mobileGuard:false', printv)                # Druckansicht ohne Schutz

    def test_az_deploy_date_freshness(self):
        self.assertTrue(appmod.APP_BUILD.startswith('2026-'), 'Build trägt ein 2026er Datum')
        script = open(os.path.join(ROOT, 'make_deploy_zip.py'), encoding='utf-8').read()
        self.assertIn('heute ist', script)                       # Frischewarnung im Zip-Bau
        self.assertIn('APP_BUILD trägt Datum', script)
        readme = open(os.path.join(ROOT, 'README.md'), encoding='utf-8').read()
        self.assertIn('warnt, wenn das Build-Datum', readme)     # Doku-Hinweis

    def test_ay_gastro_form_umlaut_and_guidance(self):
        html = open(os.path.join(ROOT, 'templates', 'gastro', 'form.html'), encoding='utf-8').read()
        self.assertIn("'Eintrag suchen & importieren'", html)     # roh im Jinja-Ausdruck
        self.assertNotIn('suchen &amp;amp; importieren', html)   # doppelte Maskierung weg
        self.assertNotIn('&amp;amp;', html)                       # nirgends doppelt maskiert
        self.assertIn("So geht's:", html)                        # 3-Schritte-Hinweis
        self.assertIn('auf der Karte direkt darüber', html)      # ba: korrekte Weg-Beschreibung
        self.assertNotIn('links auf die Karte', html)            # ba: „links“ war falsch
        self.assertIn('bi-cloud-download', html)                 # ba: keine zweite Such-Lupe im Kopf
        self.assertIn('order-2 order-md-1', html)                # bc: mobil Karte+Suche zuerst
        self.assertIn('order-1 order-md-2', html)                # (Anzeige-Reihenfolge regeln die order-Klassen)
        self.assertIn('id="fill-note"', html)                    # Rückmelde-Stelle am Formular
        self.assertIn('function flashFormFilled()', html)        # global (onclick-Regel)
        self.assertIn('flashFormFilled();', html)                # Aufruf aus fillForm
        self.assertIn("matchMedia('(max-width: 767.98px)')", html)

    def test_ax_preview_no_tdz_and_visible_errors(self):
        html = open(os.path.join(ROOT, 'templates', 'touren', 'video.html'), encoding='utf-8').read()
        self.assertEqual(html.count('const mmSide = Math.round'), 1)   # genau EINE Deklaration
        self.assertLess(html.find('const mmSide = Math.round'),
                        html.find('(_hasMM2 ? mmSide : 0)'))           # Deklaration VOR der Nutzung
        self.assertIn("status.textContent = 'Vorschau-Fehler: ' + e.message;", html)  # Fehler sichtbar
        self.assertNotIn("if (e.message !== 'stopped') throw e;", html)  # stilles Weiterwerfen weg

    def test_aw_preview_shows_time_like_mp4(self):
        html = open(os.path.join(ROOT, 'templates', 'touren', 'video.html'), encoding='utf-8').read()
        self.assertIn("strftime('%H:%M Uhr') if p.taken_at", html)   # Zeit im Foto-JSON (nur taken_at)
        self.assertIn("const when = (photo && photo.time) ? photo.time : '';", html)
        self.assertIn('#ffd26e', html)                              # gelbe Uhrzeit wie im MP4
        self.assertIn('when && caption', html)                      # Zeit über Text

    def test_av_lock_keepalive_and_docs(self):
        src = self._app_src()
        self.assertIn('def _keep_lock():', src)                     # B1: Sperre frisch halten
        self.assertIn('os.utime(lock_path, None)', src)
        self.assertGreaterEqual(src.count('_keep_lock()'), 3)       # Start + Fotos + Final-Render
        hilfe = open(os.path.join(ROOT, 'templates', 'hilfe.html'), encoding='utf-8').read()
        self.assertIn('Videos zur Tour', hilfe)                     # B2: Doku-Lücke geschlossen
        readme = open(os.path.join(ROOT, 'README.md'), encoding='utf-8').read()
        self.assertIn('Ken-Burns-Effekte', readme)
        self.assertIn('eigene MP4s hochladen', readme)

    def test_at_minimap_aligned_with_caption_bar(self):
        src = self._app_src()
        self.assertIn('y1 = H - m', src)                            # Karte auf Leisten-Unterkante
        self.assertNotIn('y1 = (bar_top - 6)', src)                 # alte Höhe weg
        self.assertIn('_mm = int(min(W, H) * 0.22) if has_map else 0', src)
        self.assertIn('max_w = W - 2 * m - 2 * pad - (_mm + 12 if _mm else 0)', src)   # Text weicht aus
        self.assertIn('min(W - 2 * m - (_mm + 12 if _mm else 0)', src)                 # Leistenbreite ebenso
        html = open(os.path.join(ROOT, 'templates', 'touren', 'video.html'), encoding='utf-8').read()
        self.assertIn('H - 6, mmSide', html)                        # Vorschau: gleiche Unterkante

    def test_ar_lighter_zoompan_and_cleanup(self):
        src = self._app_src()
        self.assertIn('scale={W*2}:{H*2}:flags=lanczos', src)       # 2x statt 3x (RAM/CPU)
        self.assertNotIn('scale={W*3}:{H*3}:flags=lanczos', src)    # alte 3x-Stufe weg
        self.assertIn('int(W*1.5)//2*2', src)                       # 1,5x-Fenster (Build as wieder)
        self.assertIn('> 240:', src)                                # Sperre nach 4 min frei
        self.assertIn("startswith('djo_video_')", src)              # /tmp-Aufraeumen

    def test_preview_matches_server_effects(self):
        html = open(os.path.join(ROOT, 'templates', 'touren', 'video.html'), encoding='utf-8').read()
        for name in ('KB_FX', 'KB_EASE', 'KB_PORTRAIT', 'KB_LANDSCAPE', 'pan_ud', 'diag_back', 'TOUR_ID'):
            self.assertIn(name, html)
        self.assertNotIn('const zoomIn = (pi % 2 === 0);', html)    # alt: nur rein/raus

    def test_aq_stronger_effects_and_window_model(self):
        src = self._app_src()
        self.assertIn("\nKB_LANDSCAPE = ['zoom_in'", src)           # Modul-Ebene (Spalte 0)
        self.assertIn('def ken_burns_exprs(effect, n_frames):', src)
        self.assertNotIn('def _kb_exprs', src)                      # alter innerer Helfer weg
        self.assertIn("'pan_lr':    ('1.16', fx, cy),", src)        # kräftigere Fahrten
        self.assertIn("f'1+0.13*{p}'", src)                         # Zoom 13 %
        self.assertIn("f'1.20-0.14*{p}'", src)                      # Diagonale bis 20 %
        self.assertNotIn("f'1+0.09*{p}'", src)                      # alte dezente Stärke weg
        html = open(os.path.join(ROOT, 'templates', 'touren', 'video.html'), encoding='utf-8').read()
        self.assertIn('const cw = W/zoom', html)                    # Fenster-Modell in der Vorschau
        self.assertNotIn('dw > W + 1', html)                        # alte „tote Achse“-Bedingung weg
        self.assertIn('z: 1.06 + .14*t', html)                      # gleiche Amplituden wie MP4
