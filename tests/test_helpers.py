"""Reine Hilfsfunktionen ohne Datenbank: GPX, Vorschau, ICS, Formularwerte, Filter."""
import datetime as dt
import os
import tempfile
import unittest

from tests.base import appmod, app, make_gpx


class HelpersTest(unittest.TestCase):

    def _gpx_file(self, xml):
        fd, path = tempfile.mkstemp(suffix='.gpx')
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            fh.write(xml)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return path

    def test_parse_gpx_with_timestamps(self):
        d = appmod.parse_gpx(self._gpx_file(make_gpx()))
        self.assertTrue(10 < d['km'] < 15, d['km'])
        self.assertGreaterEqual(d['ascent'], 0)
        self.assertEqual(len(d['points']), 120)
        self.assertTrue(2500 < d['moving_s'] < 2800, d['moving_s'])
        self.assertTrue(15 < d['avg_kmh'] < 21, d['avg_kmh'])

    def test_parse_gpx_without_timestamps(self):
        d = appmod.parse_gpx(self._gpx_file(make_gpx(with_time=False)))
        self.assertTrue(d['km'] > 10)
        self.assertFalse(d.get('moving_s'))
        self.assertFalse(d.get('avg_kmh'))

    def test_parse_gpx_broken_file(self):
        empty = appmod.parse_gpx(self._gpx_file('<gpx><trk><trkseg></trkseg></trk></gpx>'))
        self.assertFalse(empty and empty.get('points'))
        broken = appmod.parse_gpx(self._gpx_file('kein xml'))
        self.assertFalse(broken and broken.get('points'))

    def test_simplify_track(self):
        pts = appmod.parse_gpx(self._gpx_file(make_gpx(n=400)))['points']
        simple = appmod._simplify_track(pts, max_pts=50)
        self.assertLessEqual(len(simple), 50)
        self.assertGreaterEqual(len(simple), 2)
        self.assertEqual(simple[0], (pts[0]['lat'], pts[0]['lng']))
        self.assertEqual(simple[-1], (pts[-1]['lat'], pts[-1]['lng']))

    def test_track_preview_format(self):
        pts = appmod.parse_gpx(self._gpx_file(make_gpx()))['points']
        prev = appmod._track_preview(pts)
        head, body = prev.split('|')
        w, h = map(int, head.split(','))
        self.assertEqual(max(w, h), 1000)               # längere Seite ist immer 1000
        self.assertGreater(h, w)                        # Nord-Süd-Strecke → hochkant
        coords = body.split(' ')
        self.assertTrue(2 <= len(coords) <= 60)
        for c in coords:
            x, y = map(int, c.split(','))
            self.assertTrue(0 <= x <= w and 0 <= y <= h)
        self.assertFalse(appmod._track_preview([]))
        self.assertFalse(appmod._track_preview([{'lat': 53.0, 'lng': 9.0}]))

    def test_ics_helpers(self):
        self.assertEqual(appmod._ics_escape('a,b;c\\d\ne'), 'a\\,b\\;c\\\\d\\ne')
        long_line = 'DESCRIPTION:' + 'ä' * 200
        folded = appmod._ics_fold(long_line)
        parts = folded.split('\r\n')
        self.assertTrue(all(len(p.encode('utf-8')) <= 75 for p in parts))
        self.assertTrue(all(p.startswith(' ') for p in parts[1:]))
        self.assertEqual(''.join(p[1:] if i else p for i, p in enumerate(parts)), long_line)

    def test_form_value_parsers(self):
        self.assertEqual(appmod._parse_float('1,5'), 1.5)
        self.assertEqual(appmod._parse_float(''), None)
        self.assertEqual(appmod._parse_float('abc', 7), 7)
        self.assertEqual(appmod._parse_int('12'), 12)
        self.assertEqual(appmod._parse_int('x'), None)
        self.assertEqual(appmod._parse_date('2026-05-01'), dt.date(2026, 5, 1))
        self.assertEqual(appmod._parse_date('01.05.2026'), None)
        self.assertEqual(appmod._parse_date(''), None)

    def test_template_filters(self):
        f = app.jinja_env.filters
        self.assertEqual(f['hm'](3725), '1:02 h')
        self.assertEqual(f['hm'](None), '0:00 h')
        self.assertEqual(f['de1'](18.26), '18,3')
        self.assertEqual(f['de_date'](dt.date(2026, 10, 14)).split(',')[-1].strip(), '14.10.2026')

    def test_self_confirm_window(self):
        class T:                       # minimaler Tour-Ersatz
            is_date_open = False
            status = 'planned'

            def __init__(self, d):
                self.tour_date = d
        today = dt.date.today()
        self.assertTrue(appmod._self_confirm_window(T(today), today))
        self.assertTrue(appmod._self_confirm_window(T(today - dt.timedelta(days=3)), today))
        self.assertFalse(appmod._self_confirm_window(T(today - dt.timedelta(days=4)), today))
        self.assertFalse(appmod._self_confirm_window(T(today + dt.timedelta(days=1)), today))
        t = T(today)
        t.status = 'cancelled'
        self.assertFalse(appmod._self_confirm_window(t, today))

    def test_version_and_build(self):
        self.assertRegex(appmod.APP_VERSION, r'^\d+\.\d+\.\d+$')
        self.assertRegex(appmod.APP_BUILD, r'^\d{4}-\d{2}-\d{2} [a-z]{1,2}$')
