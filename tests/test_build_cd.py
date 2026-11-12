"""Build cd: Die Browser-Vorschau sieht aus wie das erzeugte MP4.

**Meldung:** „Die Vorschau sollte auch so aussehen wie das erzeugte Video.“

**Nachgemessen (templates/touren/video.html gegen tour_video_render in app.py):**

| Folie      | MP4 (Server)                                              | Vorschau (vorher)                      |
|------------|-----------------------------------------------------------|----------------------------------------|
| Titel      | Logo, Datum, „km · Hm“, Wetter, Avatar-Zeile (inkl. Gäste) | 🚴, „👥 3 dabei“ – keine Avatare        |
| Track      | lila Einkehr-Marker mit Namensschild                      | keine Marker                           |
| Einkehr    | eigene Folie nach dem Track                               | fehlte („nur MP4“)                     |
| Statistik  | Avatar-Zeile mit Profilbildern (Mitglieder + Gäste), Logo | Namens-Textzeile, nur Mitglieder       |
| Outro      | Logo über dem Dank                                        | kein Logo                              |

**Fix:** Die Seite bekommt dieselben Daten wie der Renderer (`_video_attending_users` – ein
Helfer für beide, `_video_page_einkehr`, `logo_url`); das JS zeichnet Avatar-Zeile
(`drawAvatarRow`), Logo (`drawLogoCentered`/`drawWatermark`), Einkehr-Folie
(`drawGastroFrame`, gleiche Dauer wie `build_gastro_frames`) und Einkehr-Marker.
Nachgestellt mit einem Stub-Canvas in Node: Titel zeichnet „AH Axel · JK Jörg · O Orga“,
Einkehr-Folie „Badener Asia Bistro · Geplante Einkehr · Imbiss“.
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from tests.base import AppTestCase, appmod, db, M

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _lies(rel):
    with open(os.path.join(_ROOT, rel), encoding='utf-8') as f:
        return f.read()


class _MitTour(AppTestCase):
    """Tour mit einem Mitglied, zwei Gästen und einer eingetragenen Einkehr."""

    def _tour(self):
        from tests.base import app as flask_app
        with flask_app.app_context():
            sp = M.GastroSpot(name='Badener Asia Bistro', spot_type='imbiss', lat=53.4022, lng=9.8004)
            db.session.add(sp)
            db.session.commit()
            t = M.Tour(title='Cluvenhagen - Wulmstorf', status='done', tour_date=datetime.date(2026, 11, 11),
                       created_by=self.org_id, group_id=self.g1_id, gpx_km=42.3, gpx_ascent=120)
            db.session.add(t)
            db.session.commit()
            t.gastro_spot_id = sp.id
            db.session.add(M.TourParticipant(tour_id=t.id, user_id=self.org_id, status='attending'))
            db.session.add(M.TourGuest(tour_id=t.id, name='Axel Hübner', created_by=self.org_id))
            db.session.add(M.TourGuest(tour_id=t.id, name='Jörg Krüger', created_by=self.org_id))
            db.session.commit()
            return t.id

    def _seite(self):
        tid = self._tour()
        self.login_org()
        r = self.client.get(f'/touren/{tid}/video')
        self.assertEqual(r.status_code, 200)
        return r.get_data(as_text=True)

    @staticmethod
    def _const(html, name):
        return json.loads(re.search(name + r' = (.*?);\n', html).group(1))


class SeitenDatenTest(_MitTour):
    def test_teilnehmer_mit_gaesten_und_avatarfeld(self):
        html = self._seite()
        users = self._const(html, 'ATTENDING_USERS')
        self.assertEqual([u['name'] for u in users], ['Axel Hübner', 'Jörg Krüger', 'Orga'],
                         'Mitglieder + Gäste, deutsch sortiert – wie _attending_users im MP4')
        self.assertTrue(all('avatar' in u for u in users))
        self.assertEqual(self._const(html, 'ATTENDING_COUNT'), 3)

    def test_einkehr_fuer_folie_und_marker(self):
        html = self._seite()
        eink = self._const(html, 'EINKEHR')
        self.assertEqual([e['name'] for e in eink], ['Badener Asia Bistro'])
        self.assertEqual(eink[0]['type_label'], 'Imbiss')
        self.assertFalse(eink[0]['km_known'], 'ohne GPX kein km-Wert – Folie zeigt „Geplante Einkehr“')
        self.assertAlmostEqual(eink[0]['lat'], 53.4022)

    def test_logo_konstante_und_label(self):
        html = self._seite()
        self.assertIn('const LOGO_URL = ', html)
        self.assertNotIn('(nur MP4)', html, 'Einkehr-Folie läuft jetzt auch in der Vorschau')

    def test_gemeinsamer_helfer_fuer_seite_und_mp4(self):
        src = _lies('app.py')
        self.assertIn('def _video_attending_users(tour_id):', src)
        self.assertIn('_attending_users = _video_attending_users(tour_id)', src, 'Renderer nutzt denselben Helfer')
        self.assertIn('_att = _video_attending_users(tour_id)', src, 'Seite nutzt denselben Helfer')
        from tests.base import app as flask_app
        tid = self._tour()
        with flask_app.app_context():
            self.assertEqual([n for n, _ in appmod._video_attending_users(tid)],
                             ['Axel Hübner', 'Jörg Krüger', 'Orga'])


class VorschauSkriptTest(_MitTour):
    def test_js_bausteine_vorhanden(self):
        tpl = _lies('templates/touren/video.html')
        for frag in ('function drawAvatarRow(', 'function drawGastroFrame(', 'function gastroSlideSecs(',
                     'function drawWatermark(', 'function drawLogoCentered(',
                     "'Unsere Einkehr auf dieser Tour'", 'EINKEHR.forEach(sp =>',
                     "status.textContent = 'Einkehr…'"):
            self.assertIn(frag, tpl, frag)
        self.assertNotIn("'👥 ' + ATTENDING_COUNT + ' dabei'", tpl)
        self.assertNotIn("'📊 Die Tour in Zahlen'", tpl)
        # Dauer der Einkehr-Folie wie im MP4 (build_gastro_frames): min(6, 2.5 + 0.5 n)
        self.assertIn('Math.min(6.0, 2.5 + 0.5 * n)', tpl)
        self.assertIn('Math.min(total - 0.4, 1.2 + 0.4 * n)', tpl)
        self.assertIn("if (showGastro && EINKEHR.length) secs += gastroSlideSecs().total", tpl)

    def test_folien_zeichnen_mit_stub_canvas(self):
        """Echte Seite, echtes Skript, Stub-2D-Kontext: Was steht auf Titel/Einkehr/Statistik?"""
        node = shutil.which('node')
        if not node:
            raise unittest.SkipTest('node nicht gefunden')
        html = self._seite()
        m = re.search(r'<script>\s*(const GPX_DATA[\s\S]*?)</script>', html)
        self.assertIsNotNone(m)
        js = re.sub(r'// Draw initial frame[\s\S]*$', '', m.group(1))
        harness = r'''
const vm = require('vm');
const texts = [];
const ctx = new Proxy({}, {get(t, k) {
  if (k === 'measureText') return s => ({width: String(s || '').length * 10});
  if (k === 'fillText') return s => { texts.push(String(s)); };
  if (k === 'createLinearGradient' || k === 'createRadialGradient') return () => ({addColorStop() {}});
  if (k === 'roundRect') return undefined;
  if (typeof k === 'string') return () => {};
  return undefined; }, set() { return true; }});
const el = () => ({checked: true, value: '5', textContent: '', style: {}, classList: {add() {}, remove() {}},
                   addEventListener() {}, getContext: () => ctx, width: 1280, height: 720});
const sandbox = {console, setTimeout, clearTimeout, performance: {now: () => Date.now()},
  document: {getElementById: el, querySelectorAll: () => [], querySelector: el, addEventListener() {}},
  Image: class { set src(v) { setTimeout(() => this.onerror && this.onerror(), 0); } },
  navigator: {userAgent: 'node'}};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(require('fs').readFileSync(process.argv[2], 'utf8') + `
;globalThis._p = {drawTitle, drawGastroFrame, drawStatsFrame, drawOutroFrame, gastroSlideSecs, calcTotalSecs};`, sandbox);
const P = sandbox._p, out = {};
function run(name, fn) { texts.length = 0; fn(); out[name] = texts.slice(); }
run('titel', () => P.drawTitle(1, null));
run('einkehr', () => P.drawGastroFrame(1));
run('stats', () => P.drawStatsFrame(1));
run('outro', () => P.drawOutroFrame(1, null));
out.gastro = P.gastroSlideSecs(); out.total = P.calcTotalSecs();
console.log(JSON.stringify(out));
'''
        with tempfile.TemporaryDirectory() as td:
            jsf, hf = os.path.join(td, 'page.js'), os.path.join(td, 'h.js')
            open(jsf, 'w', encoding='utf-8').write(js)
            open(hf, 'w', encoding='utf-8').write(harness)
            r = subprocess.run([node, hf, jsf], capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, f'Harness-Fehler: {r.stderr[:600]}')
        out = json.loads(r.stdout.strip().splitlines()[-1])
        # Titel: Avatar-Zeile mit Initialen + Vornamen, auch für Gäste – kein „3 dabei“
        for s in ('AH', 'Axel', 'JK', 'Jörg', 'O', 'Orga', '42.3 km  ·  120 Hm'):
            self.assertIn(s, out['titel'], f'{s!r} fehlt auf dem Titel: {out["titel"]}')
        self.assertFalse(any('dabei' in s for s in out['titel']))
        # Einkehr-Folie wie im MP4
        self.assertEqual(out['einkehr'][:4], ['Einkehr unterwegs', 'Unsere Einkehr auf dieser Tour',
                                              'Badener Asia Bistro', 'Geplante Einkehr · Imbiss'])
        # Statistik: Avatar-Zeile statt Namens-Textzeile
        self.assertIn('Jörg', out['stats'])
        self.assertFalse(any(' · ' in s and 'Orga' in s for s in out['stats']), 'alte Namenszeile ist weg')
        self.assertIn('42.3 km', out['stats'])
        self.assertEqual(out['gastro'], {'total': 3, 'anim': 1.6})     # 1 Einkehr: 2.5 + 0.5
        self.assertEqual(out['total'], 3 + 3 + 4 + 6)                  # Titel + Einkehr + Statistik + Outro


class BuildTest(AppTestCase):
    def test_build_stempel(self):
        self.assertEqual(appmod.APP_BUILD, '2026-11-12 cd')
