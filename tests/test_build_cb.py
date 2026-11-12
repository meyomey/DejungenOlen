"""Build cb: Einkehr-Folie im Tour-Video zeigt nur noch die eingetragene Einkehr.

**Meldung:**
    „Im Video erscheinen zwei Einkehrpunkte, wir waren aber nur im Asia Bistro. Bei der
    zweiten Stelle waren wir nicht. Das darf im Video nicht erscheinen, es ist auch nur
    die eine Einkehrstelle in der Tour eingetragen.“

**Nachgemessen:** Die Folie „Einkehr unterwegs“ bekam seit Build j zwei Quellen – die in
der Tour eingetragene Einkehr (`_planned_einkehr_entries`) und *alle* Gastro-Einträge
≤ 150 m neben dem Track (`gastro_near_track`). Darum stand „Bootshaus · 81 m neben der
Route“ mit auf der Folie, obwohl niemand dort war. Nachgestellt: eingetragen = 1 (Asia
Bistro), Streckenfunde = 2 (Asia Bistro 35 m, Bootshaus 80 m), Folie vorher = 2 Zeilen.

**Fix:** Die Video-Route nimmt nur noch `_planned_einkehr_entries`. Die Streckenfunde
bleiben auf der Tour-Seite („Einkehr entlang der Strecke“, Build u), kommen aber nicht
mehr ins Video – weder auf die Folie noch als Kartenmarker. Folie nachher = 1 Zeile,
ohne eingetragene Einkehr = keine Folie.
"""
import os
import re

from tests.base import AppTestCase, appmod, db, M

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _lies(rel):
    with open(os.path.join(_ROOT, rel), encoding='utf-8') as f:
        return f.read()


def _video_route_src():
    """Nur der Ausschnitt der Video-Route zwischen GPX-Parsen und Titelfolie."""
    src = _lies('app.py')
    a = src.index('_gpx_points, _ride, _near_spots, _mini_track = [], {}, [], None')
    b = src.index('# 1. Titelfolie (3s)', a)
    return src[a:b]


class EinkehrNurEingetrageneTest(AppTestCase):
    """Der gemeldete Fall mit echten Datensätzen."""

    def _points(self):
        return [{'lat': 53.400 + i * 0.001, 'lng': 9.800} for i in range(8)]

    def _mit_tour(self, fn, *, gastro_spot_id=None):
        from tests.base import app as flask_app
        with flask_app.app_context():
            bistro = M.GastroSpot(name='Badener Asia Bistro', spot_type='imbiss', lat=53.4022, lng=9.8004)
            boot = M.GastroSpot(name='Bootshaus', spot_type='restaurant', lat=53.4060, lng=9.8012)
            db.session.add_all([bistro, boot])
            db.session.commit()
            tour = M.Tour(title='cb-Tour', status='planned', tour_date=None,
                          created_by=self.org_id, group_id=self.g1_id)
            db.session.add(tour)
            db.session.commit()
            try:
                if gastro_spot_id == 'bistro':
                    tour.gastro_spot_id = bistro.id
                    db.session.commit()
                fn(tour, bistro, boot)
            finally:
                M.Tour.query.filter_by(title='cb-Tour').delete()
                db.session.delete(bistro)
                db.session.delete(boot)
                db.session.commit()

    def test_vorbedingung_zwei_streckenfunde_eine_einkehr(self):
        """So entstand die Meldung: Bootshaus liegt < 150 m neben dem Track, ist aber nicht eingetragen."""
        def check(tour, bistro, boot):
            near = appmod.gastro_near_track(self._points())
            self.assertEqual(sorted(s['name'] for s in near), ['Badener Asia Bistro', 'Bootshaus'])
            planned = appmod._planned_einkehr_entries(tour, self._points())
            self.assertEqual([e['name'] for e in planned], ['Badener Asia Bistro'])
            # Vorher (Build ca): beide zusammengeführt → 2 Zeilen auf der Folie.
            self.assertEqual(len(appmod._einkehr_merge_dedup(planned, near)), 2)
        self._mit_tour(check, gastro_spot_id='bistro')

    def test_folie_bekommt_nur_die_eingetragene_einkehr(self):
        """Nachher: die Route nimmt nur _planned_einkehr_entries – genau eine Zeile."""
        def check(tour, bistro, boot):
            entries = appmod._planned_einkehr_entries(tour, self._points())
            self.assertEqual([e['name'] for e in entries], ['Badener Asia Bistro'])
            self.assertTrue(entries[0]['km_known'])
            self.assertNotIn('Bootshaus', [e['name'] for e in entries])
        self._mit_tour(check, gastro_spot_id='bistro')

    def test_ohne_eingetragene_einkehr_keine_folie(self):
        """Keine Einkehr eingetragen → leere Liste → `if show_gastro and _near_spots` überspringt die Folie."""
        def check(tour, bistro, boot):
            self.assertEqual(appmod._planned_einkehr_entries(tour, self._points()), [])
            # … obwohl zwei Lokale an der Strecke liegen.
            self.assertEqual(len(appmod.gastro_near_track(self._points())), 2)
        self._mit_tour(check)

    def test_drei_eingetragene_bleiben_drei(self):
        """Gegenprobe Build bh: bis zu drei Stopps erscheinen weiterhin alle."""
        def check(tour, bistro, boot):
            tour.einkehr2_spot_id = boot.id
            tour.einkehr3_text = 'Eisdiele am Markt'
            db.session.commit()
            entries = appmod._planned_einkehr_entries(tour, self._points())
            self.assertEqual([e['name'] for e in entries],
                             ['Badener Asia Bistro', 'Bootshaus', 'Eisdiele am Markt'])
        self._mit_tour(check, gastro_spot_id='bistro')


class VideoRouteQuelltextTest(AppTestCase):
    """Die Route darf die Streckenfunde nicht wieder ins Video holen."""

    def test_route_ruft_gastro_near_track_nicht_mehr(self):
        seg = _video_route_src()
        code = '\n'.join(l for l in seg.splitlines() if not l.strip().startswith('#'))
        self.assertNotIn('gastro_near_track(', code)
        self.assertNotIn('_einkehr_merge_dedup(', code)
        self.assertIn('_near_spots = _planned_einkehr_entries(tour, _gpx_points)', seg)

    def test_kartenmarker_kommen_aus_derselben_liste(self):
        """Die Track-Folie bekommt _near_spots – also ebenfalls nur eingetragene Einkehren."""
        src = _lies('app.py')
        self.assertIn('build_track_frames(_gpx_points, _photos_with_gps, _near_spots)', src)
        self.assertIn('build_gastro_frames(_near_spots)', src)

    def test_tour_seite_behaelt_die_streckenfunde(self):
        """Nur das Video ändert sich – die Planungsansicht (Build u) nutzt gastro_near_track weiter."""
        src = _lies('app.py')
        self.assertIn('gastro_near = gastro_near_track(', src)


class FolienTextTest(AppTestCase):
    def test_unterzeile_und_geplant_zusatz(self):
        src = _lies('app.py')
        a = src.index('def build_gastro_frames(spots):')
        b = src.index('def build_profile_frames', a)
        seg = src[a:b]
        self.assertIn("'Unsere Einkehr auf dieser Tour'", seg)
        self.assertNotIn('Gastronomie direkt an der Strecke', seg)
        self.assertNotIn("' · geplant'", seg)
        self.assertIn('Geplante Einkehr', seg, 'Freitext ohne Position (Build ca) bleibt')

    def test_gerenderte_folie_hat_eine_zeile(self):
        """Folie wirklich zeichnen (Closure per AST herausgeschnitten) – eine Kachel, kein ‚· geplant‘."""
        import ast
        import tempfile
        import textwrap
        try:
            import PIL.Image as _PIL
            import PIL.ImageDraw as _ID_MOD
        except ImportError:
            self.skipTest('Pillow fehlt')
        from tests.base import app as flask_app
        src = _lies('app.py')
        lines = src.splitlines(keepends=True)
        tree = ast.parse(src)
        want = ['_pil_font', '_centered_text', '_logo_scaled', 'paste_watermark', 'build_gastro_frames']
        found = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in want}
        body = '\n\n'.join(''.join(lines[found[w].lineno - 1:found[w].end_lineno]) for w in want)
        tmp = tempfile.mkdtemp()
        ns = dict(os=os, _PIL=_PIL, _ID_MOD=_ID_MOD, app=flask_app, W=1920, H=1080, SAFE=40, PIL_OK=True,
                  _IFO=__import__('PIL.ImageFont', fromlist=['x']),
                  _ILF=__import__('PIL.ImageFilter', fromlist=['x']),
                  photos=[], logo_rgba=None, _group_name='x', fps=25, tmpdir=tmp, GASTRO_NEAR_M=150,
                  __file__=os.path.join(_ROOT, 'app.py'))
        exec(compile('def _inner():\n' + textwrap.indent(textwrap.dedent(body), '    ')
                     + '\n    return locals()\n', '<f>', 'exec'), ns)
        loc = ns['_inner']()
        frames = loc['build_gastro_frames']([{'name': 'Badener Asia Bistro', 'type_label': 'Imbiss',
                                              'km': 26.3, 'dist_m': 27, 'planned': True, 'km_known': True}])
        self.assertTrue(frames)
        img = _PIL.open(frames[-1][0]).convert('RGB')
        # Kachelfarbe (58, 74, 108) nur in der ersten Zeile – dort, wo bisher die zweite
        # Zeile (Bootshaus) stand, muss Hintergrund (30, 45, 80) sein.
        row_h, gap, y0 = max(96, int(1080 * 0.085)), 18, int(1080 * 0.22)
        x = 1920 // 2
        def nah(px, soll):      # JPEG rundet um ±3
            return all(abs(a - b) <= 3 for a, b in zip(px, soll))
        self.assertTrue(nah(img.getpixel((x, y0 + 10)), (58, 74, 108)))
        self.assertTrue(nah(img.getpixel((x, y0 + row_h + gap + 10)), (30, 45, 80)))


class FormularTest(AppTestCase):
    def test_haekchen_text(self):
        html = _lies('templates/touren/video.html')
        self.assertNotIn('Einkehr nahe der Route', html)
        self.assertRegex(html, r'for="show-gastro">🍴 Einkehr')

    def test_build_stempel(self):
        self.assertEqual(appmod.APP_BUILD, '2026-11-12 cb')
        self.assertRegex(appmod.APP_BUILD, r'^\d{4}-\d{2}-\d{2} [a-z]{2}$')
        self.assertTrue(re.match(r'^1\.5\.', appmod.APP_VERSION))
