"""Build ac: Fotos ohne Standort anhand der Aufnahmezeit auf dem GPX-Track platzieren,
Hinweise beim Upload, Herkunft der Position (gps_source), EXIF-Aufnahmezeit aus dem Exif-IFD.

Fixtures aus tests/base.py: t_done hat eine Aufzeichnung mit Zeitstempeln (make_gpx(): Start
14.06.2025 08:00 UTC = 10:00 Ortszeit, 120 Punkte je 22 s nach Norden, 10-min-Pause bei Punkt 60),
t_plan eine geplante Route ohne Zeiten, t_open gar kein GPX."""
import datetime as dt
import io
import unittest

from tests.base import AppTestCase, appmod, app, db, M

try:
    from PIL import Image as _PILImage
    import piexif as _piexif
    HAVE_IMG = True
except Exception:          # pragma: no cover – ohne Pillow/piexif werden die Bild-Tests übersprungen
    HAVE_IMG = False

LOCAL = dt.datetime(2025, 6, 14, 10, 0, 0)          # = Start der Aufzeichnung in Ortszeit (CEST)


def _dms(value):
    value = abs(value)
    deg = int(value)
    minutes = int((value - deg) * 60)
    seconds = round(((value - deg) * 60 - minutes) * 60 * 100)
    return ((deg, 1), (minutes, 1), (seconds, 100))


_SEQ = [0]


def make_jpeg(taken=None, modified=None, gps=None):
    """Kleines JPEG; taken → DateTimeOriginal im Exif-IFD, modified → DateTime im IFD0,
    gps → GPS-IFD. Ohne Angaben ein JPEG ganz ohne EXIF. Jede Datei bekommt eine andere Farbe,
    sonst greift der Duplikat-Schutz (gleicher SHA-256 innerhalb einer Tour)."""
    _SEQ[0] += 1
    img = _PILImage.new('RGB', (8, 8), (200, (_SEQ[0] * 37) % 256, (_SEQ[0] * 91) % 256))
    zeroth, exif_ifd, gps_ifd = {}, {}, {}
    if modified:
        zeroth[_piexif.ImageIFD.DateTime] = modified.strftime('%Y:%m:%d %H:%M:%S').encode()
    if taken:
        exif_ifd[_piexif.ExifIFD.DateTimeOriginal] = taken.strftime('%Y:%m:%d %H:%M:%S').encode()
    if gps:
        lat, lng = gps
        gps_ifd = {_piexif.GPSIFD.GPSLatitudeRef: b'N' if lat >= 0 else b'S',
                   _piexif.GPSIFD.GPSLatitude: _dms(lat),
                   _piexif.GPSIFD.GPSLongitudeRef: b'E' if lng >= 0 else b'W',
                   _piexif.GPSIFD.GPSLongitude: _dms(lng)}
    buf = io.BytesIO()
    if zeroth or exif_ifd or gps_ifd:
        img.save(buf, 'JPEG', exif=_piexif.dump({'0th': zeroth, 'Exif': exif_ifd, 'GPS': gps_ifd}))
    else:
        img.save(buf, 'JPEG')
    return buf.getvalue()


class TrackPositionTest(AppTestCase):
    """Reine Rechenhelfer: Zeitstempel lesen, Position zur Uhrzeit interpolieren."""

    def _timed(self):
        return appmod._tour_timed_points(self.tour(self.t_done_id))

    def test_timed_points_read_and_sorted(self):
        pts = self._timed()
        self.assertEqual(len(pts), 120)
        self.assertEqual(pts[0][0], dt.datetime(2025, 6, 14, 8, 0, tzinfo=dt.timezone.utc).timestamp())
        self.assertEqual([p[0] for p in pts], sorted(p[0] for p in pts))
        self.assertEqual(appmod._tour_timed_points(self.tour(self.t_plan_id)), [])   # Route ohne Zeiten
        self.assertEqual(appmod._tour_timed_points(self.tour(self.t_open_id)), [])   # kein GPX

    def test_position_interpolated_between_points(self):
        pts = self._timed()
        self.assertEqual(appmod._track_position_at(pts, LOCAL), (53.4, 9.8))               # exakt Start
        lat, lng = appmod._track_position_at(pts, LOCAL + dt.timedelta(seconds=11))      # Mitte Punkt 0→1
        self.assertAlmostEqual(lat, 53.4005, places=4)
        self.assertAlmostEqual(lng, 9.80015, places=4)
        lat, _ = appmod._track_position_at(pts, LOCAL + dt.timedelta(minutes=10))        # 600 s → Punkt 27,27
        self.assertAlmostEqual(lat, 53.42727, places=4)

    def test_tolerance_before_start_and_after_end(self):
        pts = self._timed()
        self.assertEqual(appmod._track_position_at(pts, LOCAL - dt.timedelta(minutes=10)), (53.4, 9.8))
        self.assertIsNone(appmod._track_position_at(pts, LOCAL - dt.timedelta(minutes=20)))
        end_local = LOCAL + dt.timedelta(seconds=119 * 22 + 600)                          # 10:53:38
        self.assertEqual(appmod._track_position_at(pts, end_local + dt.timedelta(minutes=10)),
                         (round(53.4 + 119 * 0.001, 6), round(9.8 + (119 % 7) * 0.0003, 6)))
        self.assertIsNone(appmod._track_position_at(pts, end_local + dt.timedelta(minutes=20)))
        self.assertIsNone(appmod._track_position_at([], LOCAL))
        self.assertIsNone(appmod._track_position_at(pts, None))

    def test_gap_uses_nearest_point_instead_of_interpolating(self):
        pts = self._timed()
        t59 = LOCAL + dt.timedelta(seconds=59 * 22)            # letzter Punkt vor der 10-min-Pause
        near59 = appmod._track_position_at(pts, t59 + dt.timedelta(seconds=82))
        self.assertEqual(near59, (53.459, round(9.8 + 3 * 0.0003, 6)))
        near60 = appmod._track_position_at(pts, t59 + dt.timedelta(seconds=22 + 600 - 60))
        self.assertEqual(near60, (53.46, round(9.8 + 4 * 0.0003, 6)))

    def test_offset_corrects_camera_clock(self):
        pts = self._timed()
        ref = appmod._track_position_at(pts, LOCAL + dt.timedelta(minutes=10))
        self.assertEqual(appmod._track_position_at(pts, LOCAL + dt.timedelta(minutes=70), offset_min=60), ref)
        self.assertEqual(appmod._track_position_at(pts, LOCAL + dt.timedelta(minutes=5), offset_min=-5), ref)

    def test_place_helper_skips_real_positions(self):
        pts = self._timed()
        p_track = M.TourPhoto(tour_id=self.t_done_id, user_id=self.mem_id, filename='x1.jpg',
                              taken_at=LOCAL + dt.timedelta(minutes=5))
        p_manual = M.TourPhoto(tour_id=self.t_done_id, user_id=self.mem_id, filename='x2.jpg',
                               taken_at=LOCAL + dt.timedelta(minutes=5), lat=1.0, lng=2.0, gps_source='manual')
        p_notime = M.TourPhoto(tour_id=self.t_done_id, user_id=self.mem_id, filename='x3.jpg')
        p_outside = M.TourPhoto(tour_id=self.t_done_id, user_id=self.mem_id, filename='x4.jpg',
                                taken_at=LOCAL + dt.timedelta(hours=3))
        placed, no_time, outside = appmod._place_photos_on_track([p_track, p_manual, p_notime, p_outside], pts)
        self.assertEqual((placed, no_time, outside), (1, 1, 1))
        self.assertEqual(p_track.gps_source, 'track')
        self.assertTrue(p_track.has_gps)
        self.assertEqual((p_manual.lat, p_manual.lng, p_manual.gps_source), (1.0, 2.0, 'manual'))
        self.assertFalse(p_notime.has_gps)
        self.assertFalse(p_outside.has_gps)


@unittest.skipUnless(HAVE_IMG, 'Pillow/piexif nicht installiert')
class ExifDateTest(AppTestCase):
    def _write(self, data):
        import os
        path = os.path.join(app.config['UPLOAD_FOLDER_PHOTOS'], f'exif_{len(data)}_{id(data)}.jpg')
        with open(path, 'wb') as fh:
            fh.write(data)
        return path

    def test_prefers_datetimeoriginal_over_modification_date(self):
        taken, modified = dt.datetime(2025, 6, 14, 8, 30, 0), dt.datetime(2025, 6, 14, 12, 0, 0)
        self.assertEqual(appmod.extract_datetime_from_exif(self._write(make_jpeg(taken=taken, modified=modified))), taken)
        self.assertEqual(appmod.extract_datetime_from_exif(self._write(make_jpeg(modified=modified))), modified)
        self.assertIsNone(appmod.extract_datetime_from_exif(self._write(make_jpeg())))

    def test_tiff_parser_handles_garbage(self):
        self.assertIsNone(appmod._exif_datetime_from_tiff(b'XX\x00\x00'))
        self.assertIsNone(appmod._exif_datetime_from_tiff(b'II*\x00\x08\x00\x00\x00\x00\x00'))


@unittest.skipUnless(HAVE_IMG, 'Pillow/piexif nicht installiert')
class UploadPlacementTest(AppTestCase):
    """Upload: Position aus EXIF, vom Handy (device), per Uhrzeit vom Track – und die Hinweise."""

    def _upload(self, tour_id, files, extra=None, xhr=False, follow=True):
        appmod._rl_store.clear()                         # 5 Uploads/min je Nutzer
        data = {'photos': [(io.BytesIO(b), name) for b, name in files]}
        data.update(extra or {})
        headers = {'X-Requested-With': 'XMLHttpRequest'} if xhr else {}
        return self.client.post(f'/touren/{tour_id}/fotos', data=data, content_type='multipart/form-data',
                                headers=headers, follow_redirects=follow)

    def _last_photo(self):
        return M.TourPhoto.query.order_by(M.TourPhoto.id.desc()).first()

    def test_photo_with_time_lands_on_track(self):
        self.login_member()
        r = self._upload(self.t_done_id, [(make_jpeg(taken=LOCAL + dt.timedelta(minutes=10)), 'a.jpg')])
        html = r.get_data(as_text=True)
        self.assertIn('1 anhand der Aufnahmezeit auf der Strecke platziert', html)
        self.assertNotIn('ohne Standort.', html)
        p = self._last_photo()
        self.assertEqual(p.gps_source, 'track')
        self.assertAlmostEqual(p.lat, 53.42727, places=4)
        self.assertEqual(p.taken_at, LOCAL + dt.timedelta(minutes=10))

    def test_photo_without_time_gets_hint(self):
        self.login_member()
        html = self._upload(self.t_done_id, [(make_jpeg(), 'b.jpg')]).get_data(as_text=True)
        p = self._last_photo()
        self.assertFalse(p.has_gps)
        self.assertIsNone(p.gps_source)
        self.assertIn('1 Foto(s) ohne Standort', html)
        self.assertIn('„Dateien“', html)
        self.assertIn('keine Aufnahmezeit oder liegen außerhalb', html)

    def test_photo_outside_recording_window(self):
        self.login_member()
        html = self._upload(self.t_done_id, [(make_jpeg(taken=LOCAL + dt.timedelta(hours=5)), 'c.jpg')]).get_data(as_text=True)
        self.assertFalse(self._last_photo().has_gps)
        self.assertIn('ohne Standort', html)

    def test_exif_gps_wins_over_track(self):
        self.login_member()
        html = self._upload(self.t_done_id, [(make_jpeg(taken=LOCAL + dt.timedelta(minutes=10),
                                                         gps=(53.55, 9.99)), 'd.jpg')]).get_data(as_text=True)
        p = self._last_photo()
        self.assertEqual(p.gps_source, 'exif')
        self.assertAlmostEqual(p.lat, 53.55, places=3)
        self.assertAlmostEqual(p.lng, 9.99, places=3)
        self.assertIn('1 mit GPS', html)
        self.assertNotIn('anhand der Aufnahmezeit auf der Strecke platziert', html)

    def test_device_location_from_client(self):
        self.login_member()
        self._upload(self.t_done_id, [(make_jpeg(taken=LOCAL + dt.timedelta(minutes=10)), 'e.jpg')],
                     extra={'gps_lat_0': '53.1', 'gps_lng_0': '9.1', 'gps_src_0': 'device'})
        p = self._last_photo()
        self.assertEqual((p.lat, p.lng, p.gps_source), (53.1, 9.1, 'device'))

    def test_client_exif_fallback_is_source_exif(self):
        self.login_member()
        self._upload(self.t_done_id, [(make_jpeg(), 'f.jpg')],
                     extra={'gps_lat_0': '53.2', 'gps_lng_0': '9.2', 'exif_dt_0': '2025:06:14 10:05:00'})
        p = self._last_photo()
        self.assertEqual(p.gps_source, 'exif')
        self.assertEqual(p.taken_at, dt.datetime(2025, 6, 14, 10, 5))

    def test_client_time_fallback_enables_placement(self):
        self.login_member()
        self._upload(self.t_done_id, [(make_jpeg(), 'g.jpg')], extra={'exif_dt_0': '2025:06:14 10:10:00'})
        p = self._last_photo()
        self.assertEqual(p.gps_source, 'track')
        self.assertAlmostEqual(p.lat, 53.42727, places=4)

    def test_tour_without_timed_gpx_hints_route(self):
        self.login_member()
        html = self._upload(self.t_plan_id, [(make_jpeg(taken=LOCAL + dt.timedelta(minutes=10)), 'h.jpg')]).get_data(as_text=True)
        self.assertFalse(self._last_photo().has_gps)
        self.assertIn('keine Zeitstempel (geplante Route)', html)
        html = self._upload(self.t_open_id, [(make_jpeg(taken=LOCAL), 'i.jpg')]).get_data(as_text=True)
        self.assertIn('ohne Standort', html)
        self.assertNotIn('keine Zeitstempel (geplante Route)', html)

    def test_xhr_response_reports_placement(self):
        self.login_member()
        r = self._upload(self.t_done_id, [(make_jpeg(taken=LOCAL + dt.timedelta(minutes=20)), 'j.jpg'),
                                          (make_jpeg(), 'k.jpg')], xhr=True, follow=False)
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual((data['count'], data['placed'], data['no_gps']), (2, 1, 1))
        self.assertTrue(data['redirect'].endswith('#fotos'))


class PlaceRouteTest(AppTestCase):
    """POST /touren/<id>/fotos/platzieren – Rechte, Platzieren, Zeitkorrektur, Rückgängig; Anzeige."""

    @classmethod
    def _seed(cls):
        super()._seed()
        mk = lambda fn, **kw: M.TourPhoto(tour_id=cls.t_done.id, user_id=cls.mem.id, filename=fn, **kw)   # noqa: E731
        cls.p1 = mk('p1.jpg', taken_at=LOCAL + dt.timedelta(minutes=5))
        cls.p2 = mk('p2.jpg', taken_at=LOCAL + dt.timedelta(minutes=20))
        cls.p3 = mk('p3.jpg')
        cls.p4 = mk('p4.jpg', taken_at=LOCAL + dt.timedelta(minutes=30), lat=53.9, lng=9.9, gps_source='manual')
        cls.p5 = mk('p5.jpg', taken_at=LOCAL + dt.timedelta(hours=4))
        cls.q1 = M.TourPhoto(tour_id=cls.t_plan.id, user_id=cls.mem.id, filename='q1.jpg', taken_at=LOCAL)
        db.session.add_all([cls.p1, cls.p2, cls.p3, cls.p4, cls.p5, cls.q1])
        db.session.commit()
        for name in ('p1', 'p2', 'p3', 'p4', 'p5', 'q1'):
            setattr(cls, name + '_id', getattr(cls, name).id)

    def _photo(self, pid):
        return db.session.get(M.TourPhoto, pid)

    def _place(self, tour_id, **form):
        return self.client.post(f'/touren/{tour_id}/fotos/platzieren', data=form, follow_redirects=True)

    def test_member_forbidden(self):
        self.login_member()
        r = self.client.post(f'/touren/{self.t_done_id}/fotos/platzieren')
        self.assertEqual(r.status_code, 403)
        self.assertFalse(self._photo(self.p1_id).has_gps)

    def test_organizer_places_and_undoes(self):
        self.login_org()
        html = self._place(self.t_done_id).get_data(as_text=True)
        self.assertIn('2 Foto(s) auf der Strecke platziert', html)
        self.assertIn('1 ohne Aufnahmezeit', html)
        self.assertIn('1 außerhalb der Aufzeichnung (14.06.2025 10:00–10:53 Uhr)', html)
        p1, p2, p4 = self._photo(self.p1_id), self._photo(self.p2_id), self._photo(self.p4_id)
        self.assertEqual((p1.gps_source, p2.gps_source), ('track', 'track'))
        self.assertAlmostEqual(p1.lat, 53.4 + 300 / 22 * 0.001, places=4)
        self.assertEqual((p4.lat, p4.lng, p4.gps_source), (53.9, 9.9, 'manual'))
        self.assertFalse(self._photo(self.p3_id).has_gps)
        self.assertFalse(self._photo(self.p5_id).has_gps)

        # Anzeige: ≈-Badge, est-Flag im Karten-JSON, Rückgängig-Knopf
        html = self.get_html(f'/touren/{self.t_done_id}')
        self.assertIn('Position geschätzt', html)
        self.assertIn('bi-geo-alt-fill"></i>≈', html)
        self.assertIn('2 geschätzte Position(en) wieder entfernen', html)
        self.assertRegex(html, r'id: %d,[^}]*est: true' % self.p1_id)
        self.assertRegex(html, r'id: %d,[^}]*est: false' % self.p4_id)

        # Zeitkorrektur: Kamera geht 10 min vor → p1 (10:05) rückt auf 09:55 = Startpunkt
        html = self._place(self.t_done_id, offset_min='10').get_data(as_text=True)
        self.assertIn('Zeitkorrektur +10 min', html)
        self.assertEqual((self._photo(self.p1_id).lat, self._photo(self.p1_id).lng), (53.4, 9.8))
        self.assertEqual(self._photo(self.p4_id).lat, 53.9)

        # Rückgängig: nur geschätzte Positionen verschwinden
        html = self._place(self.t_done_id, action='undo').get_data(as_text=True)
        self.assertIn('2 geschätzte Position(en) entfernt', html)
        self.assertFalse(self._photo(self.p1_id).has_gps)
        self.assertIsNone(self._photo(self.p1_id).gps_source)
        self.assertEqual(self._photo(self.p4_id).gps_source, 'manual')

    def test_offset_is_clamped_and_tolerates_junk(self):
        self.login_admin()
        html = self._place(self.t_done_id, offset_min='abc').get_data(as_text=True)
        self.assertIn('auf der Strecke platziert', html)
        self.assertNotIn('Zeitkorrektur +', html)
        self.assertNotIn('Zeitkorrektur -', html)
        html = self._place(self.t_done_id, offset_min='99999').get_data(as_text=True)
        self.assertIn('Zeitkorrektur +720 min', html)
        self._place(self.t_done_id, action='undo')

    def test_untimed_or_missing_gpx(self):
        self.login_org()
        html = self._place(self.t_plan_id).get_data(as_text=True)
        self.assertIn('keine Zeitstempel', html)
        self.assertFalse(self._photo(self.q1_id).has_gps)
        html = self._place(self.t_open_id).get_data(as_text=True)
        self.assertIn('keine Zeitstempel', html)

    def test_detail_page_controls(self):
        self.login_org()
        html = self.get_html(f'/touren/{self.t_done_id}')
        self.assertIn('Foto(s) ohne Standort auf der Strecke platzieren', html)
        self.assertIn('name="offset_min"', html)
        self.assertIn('Aufzeichnung 10:00–10:53 Uhr', html)                 # Spanne der Aufzeichnung (Ortszeit)
        self.assertIn('window.GPX_TIMED = true', html)
        html = self.get_html(f'/touren/{self.t_plan_id}')                 # Route ohne Zeiten → Hinweis statt Knopf
        self.assertIn('keine Zeitstempel (geplante Route)', html)
        self.assertNotIn('name="offset_min"', html)
        self.assertIn('window.GPX_TIMED = false', html)
        self.login_member()
        html = self.get_html(f'/touren/{self.t_done_id}')
        self.assertNotIn('auf der Strecke platzieren', html)
        self.assertNotIn('id="place-on-track"', html)

    def test_manual_set_and_clear_update_source(self):
        self.login_member()
        r = self.client.post(f'/fotos/{self.p3_id}/gps', data={'lat': '53.5', 'lng': '9.5'})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self._photo(self.p3_id).gps_source, 'manual')
        r = self.client.post(f'/fotos/{self.p3_id}/gps-loeschen')
        self.assertEqual(r.status_code, 302)
        p3 = self._photo(self.p3_id)
        self.assertFalse(p3.has_gps)
        self.assertIsNone(p3.gps_source)

    def test_migration_adds_column(self):
        cols = {row[1] for row in db.session.execute(db.text('PRAGMA table_info(tour_photos)')).fetchall()}
        self.assertIn('gps_source', cols)

    def test_help_mentions_feature(self):
        self.login_member()
        html = self.get_html('/hilfe')
        self.assertIn('Automatisch per Aufnahmezeit platzieren', html)
        self.assertIn('In Dateien sichern', html)


class OffsetHintTest(AppTestCase):
    """Alle Fotos liegen 2 h vor der Aufzeichnung (App schreibt Ortszeit statt UTC) → Vorschlag."""

    @classmethod
    def _seed(cls):
        super()._seed()
        db.session.add_all([
            M.TourPhoto(tour_id=cls.t_done.id, user_id=cls.mem.id, filename='o1.jpg',
                        taken_at=LOCAL - dt.timedelta(minutes=115)),
            M.TourPhoto(tour_id=cls.t_done.id, user_id=cls.mem.id, filename='o2.jpg',
                        taken_at=LOCAL - dt.timedelta(minutes=100)),
            M.TourPhoto(tour_id=cls.t_done.id, user_id=cls.mem.id, filename='o3.jpg',
                        taken_at=LOCAL + dt.timedelta(minutes=20), lat=53.5, lng=9.5, gps_source='exif'),
        ])
        db.session.commit()

    def test_suggests_timezone_offset(self):
        self.login_org()
        r = self.client.post(f'/touren/{self.t_done_id}/fotos/platzieren', data={}, follow_redirects=True)
        html = r.get_data(as_text=True)
        self.assertIn('0 Foto(s) auf der Strecke platziert', html)
        self.assertIn('2 außerhalb der Aufzeichnung', html)
        self.assertIn('Mit Zeitkorrektur -120 min lägen 2 Foto(s) in der Aufzeichnung', html)
        r = self.client.post(f'/touren/{self.t_done_id}/fotos/platzieren', data={'offset_min': '-120'},
                             follow_redirects=True)
        html = r.get_data(as_text=True)
        self.assertIn('2 Foto(s) auf der Strecke platziert', html)
        self.assertIn('Zeitkorrektur -120 min', html)
        self.assertNotIn('lägen', html)
        placed = M.TourPhoto.query.filter_by(tour_id=self.t_done_id, gps_source='track').all()
        self.assertEqual(len(placed), 2)
        self.assertAlmostEqual(min(p.lat for p in placed), 53.4 + 300 / 22 * 0.001, places=4)   # 10:05 → Punkt 13,6

    def test_no_suggestion_without_candidates(self):
        self.assertIsNone(appmod._suggest_offset([], [(0, 1, 1)]))
        far = M.TourPhoto(tour_id=self.t_done_id, user_id=self.mem_id, filename='o9.jpg',
                          taken_at=LOCAL + dt.timedelta(hours=9))
        self.assertIsNone(appmod._suggest_offset([far], appmod._tour_timed_points(self.tour(self.t_done_id))))


class BuildMetaTest(AppTestCase):
    def test_build_marker(self):
        self.assertRegex(appmod.APP_BUILD, r'^\d{4}-\d{2}-\d{2} [a-z]{1,2}$')
        self.assertGreaterEqual(appmod.APP_BUILD, '2026-10-15 ac')
        self.login_member()
        self.assertIn(appmod.APP_BUILD, self.get_html('/'))


if __name__ == '__main__':
    unittest.main()
