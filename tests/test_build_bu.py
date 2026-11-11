"""Build bu: Stromspar-Modus zeichnete fast nur Geraden.

Der Nutzer: „Das tracken im Stromsparmodus ist nicht brauchbar. Es sind fast nur Geraden
sichtbar" (Bild 18: die Spur auf der Tourseite besteht aus langen geraden Strichen, die
Bögen fehlen).

**Ursache 1 – invertierter Richtungs-Trigger (Client).** Build 11-06o hatte einen
Richtungs-Trigger eingebaut, der laut Kommentar „Kurven sofort sichern" sollte (wie die
Akku-Modi von Strava & Co.). Der Code war aber genau umgekehrt:

    if (turn < 25) return;        // bei Kursänderung UNTER 25° verwerfen

Damit flogen die Punkte **in den Kurven** raus und nur die **Geraden** blieben übrig –
das gemeldete Bild. Dazu kam die Reihenfolge: Der 20-s-Takt prüfte **zuerst** und warf
den Punkt weg, bevor die Richtung überhaupt gefragt wurde. Der Trigger konnte deshalb
nie etwas behalten, nur zusätzlich verwerfen.

**Ursache 2 – zu kleine Punktgrenze auf der Karte (Server).** `LIVE_TRACK_PAGE_PTS = 400`
dünnte beim Erstaufruf der Live-Karte gleichmäßig aus. Bei einer 4-h-Tour wurde daraus
jeder 7. Punkt – die Verbindung dazwischen ist wieder eine Gerade. Jetzt 2000.

**Ursache 3 – kein Nachschub bei stehender Seite.** Fehlt ein Punkt, muss die Lücke
später gefüllt werden. Das erledigt der „Nachsenden"-Pfad (gesichert/sicherNachsenden).

Die Tests hier prüfen den **echten Code aus dem Template**: Der Drossel-Block wird aus
`templates/touren/live.html` gelesen und in Node gegen eine simulierte Tour aus Geraden
und 90°-Bögen laufen gelassen. Kein Nachbau – wenn jemand die Regel wieder umdreht,
fällt es hier auf.
"""
import os
import shutil
import subprocess
import tempfile
import unittest

from tests.base import AppTestCase, ROOT

LIVE = os.path.join(ROOT, 'templates', 'touren', 'live.html')

HARNESS = r"""
// Prueft den Drossel-Block aus live.html gegen eine simulierte Tour.
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');

const bm = src.match(/function _bearing\(a, b\) \{[\s\S]*?\n\}/);
if (!bm) { console.error('KEIN _bearing'); process.exit(1); }
eval(bm[0]);

const start = src.indexOf('const moved = lastPos ? map.distance(lastPos, ownLatLng) : Infinity;');
const ende  = src.indexOf('lastSent = now; lastPos = ownLatLng;', start);
if (start < 0 || ende < 0) { console.error('KEIN Drossel-Block'); process.exit(1); }
const block = src.slice(start, ende + 'lastSent = now; lastPos = ownLatLng;'.length);

const map = { distance: (a, b) => Math.hypot((b[0]-a[0])*111320,
                                             (b[1]-a[1])*111320*Math.cos(a[0]*Math.PI/180)) };

// Realistische Runde: 400-m-Geraden im Wechsel mit 90-Grad-Boegen (r = 60 m).
function tour(dauerS, tempoKmh, radiusM) {
  const pts = []; let x = 0, y = 0, kurs = 0, phase = 0, phaseStart = 0;
  const v = tempoKmh / 3.6, dt = 3;
  for (let t = 0; t <= dauerS; t += dt) {
    pts.push({t: t*1000, lat: 53.55 + y/111320,
              lng: 9.98 + x/(111320*Math.cos(53.55*Math.PI/180))});
    const dauer = t - phaseStart;
    let kr = 0;
    if (phase % 2 === 0) { if (dauer > 400/v) { phase++; phaseStart = t; } }
    else { kr = (v/radiusM)*(180/Math.PI);
           if (dauer > (Math.PI/2*radiusM/v)) { phase++; phaseStart = t; } }
    kurs += kr*dt;
    x += Math.cos(kurs*Math.PI/180)*v*dt;
    y += Math.sin(kurs*Math.PI/180)*v*dt;
  }
  return pts;
}

function lauf(pts, saver) {
  const f = new Function('saverOn','lastPos','prevSentPos','lastSent','now','ownLatLng',
                         '_bearing','DIST', `
     const map = {distance:(a,b)=>DIST(a,b)};
     (function(){
       ${block}
     })();
     return {lastPos, prevSentPos, lastSent};`);
  let lastPos = null, prevSentPos = null, lastSent = 0, out = [];
  for (const p of pts) {
    const vor = lastSent;
    const r = f(saver, lastPos, prevSentPos, lastSent, p.t, [p.lat, p.lng], _bearing, map.distance);
    if (r.lastSent !== vor) out.push(p);          // der Block lief durch -> gesendet
    lastPos = r.lastPos; prevSentPos = r.prevSentPos; lastSent = r.lastSent;
  }
  return out;
}

function maxLuecke(a) {
  let m = 0;
  for (let i = 1; i < a.length; i++) {
    const d = map.distance([a[i-1].lat, a[i-1].lng], [a[i].lat, a[i].lng]);
    if (d > m) m = d;
  }
  return m;
}

const dauer = parseInt(process.argv[3] || '1800', 10);
const pts = tour(dauer, 18, 60);
const spar = lauf(pts, true);
const normal = lauf(pts, false);
console.log(JSON.stringify({
  fixes: pts.length,
  spar: spar.length,  spar_luecke: Math.round(maxLuecke(spar)),
  normal: normal.length, normal_luecke: Math.round(maxLuecke(normal)),
}));
"""


def _node():
    return shutil.which('node')


class SparmodusKurvenTest(AppTestCase):
    """Der echte Drossel-Block muss in Kurven verdichten, nicht ausdünnen."""

    @classmethod
    def setUpClass(cls):
        cls.node = _node()
        if not cls.node:
            raise unittest.SkipTest('node nicht gefunden')

    def _lauf(self, dauer=1800, datei=LIVE):
        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as f:
            f.write(HARNESS)
            js = f.name
        try:
            r = subprocess.run([self.node, js, str(datei), str(dauer)],
                               capture_output=True, text=True, timeout=120)
        finally:
            os.unlink(js)
        self.assertEqual(r.returncode, 0, f'Harness-Fehler: {r.stderr[:400]}')
        import json
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_kurven_werden_verdichtet(self):
        """Vorher 36 von 601 Punkten, jetzt > 250 – die Kurvenpunkte kommen durch."""
        d = self._lauf()
        self.assertGreater(d['spar'], 250,
                           f"nur {d['spar']} von {d['fixes']} Punkten gesendet – "
                           f'die Kurven fallen wieder weg (alte Regel: 36)')

    def test_luecke_bleibt_klein(self):
        """Die größte Lücke zwischen zwei Punkten darf nicht zur Geraden werden."""
        d = self._lauf()
        self.assertLess(d['spar_luecke'], 80,
                        f"groesste Luecke {d['spar_luecke']} m – das ist eine Gerade "
                        f"(alte Regel: 329 m, ungedrosselt: 60 m)")

    def test_luecke_nicht_schlechter_als_ohne_sparmodus(self):
        """Der Sparmodus darf die Spur nur groeber machen, nicht kaputt."""
        d = self._lauf()
        self.assertLessEqual(d['spar_luecke'], d['normal_luecke'] * 1.5,
                             f"Spur im Sparmodus ({d['spar_luecke']} m) ist deutlich "
                             f"grober als ohne ({d['normal_luecke']} m)")

    def test_lange_tour_bleibt_brauchbar(self):
        """4 h Tour: auch da darf die Luecke nicht in die Hunderte Meter laufen."""
        d = self._lauf(dauer=4 * 3600)
        self.assertLess(d['spar_luecke'], 120,
                        f"4-h-Tour: groesste Luecke {d['spar_luecke']} m")

    def test_alte_invertierte_regel_ist_weg(self):
        """Der Test aus Build ag hielt `if (turn < 25) return;` fest – das war der Fehler."""
        with open(LIVE, encoding='utf-8') as f:
            js = f.read()
        self.assertNotIn('if (turn < 25) return;', js)
        self.assertIn('} else if (dreht >= 20) {', js)
        # Takt und Stand-Takt im Sparmodus
        self.assertIn('sendEvery = saverOn ? 6000 : 10000', js)
        self.assertIn('stillEvery = saverOn ? 20000 : 30000', js)


class KartenPunktgrenzeTest(AppTestCase):
    """Ursache 2: Die Karten-Nutzlast dünnte bei langen Touren jede 7. Position weg."""

    def test_grenze_deutlich_erhoeht(self):
        from tests.base import appmod
        self.assertGreaterEqual(appmod.LIVE_TRACK_PAGE_PTS, 1500,
                                '400 Punkte reichen fuer eine Tagestour nicht '
                                '(4 h Fahrt -> 2 500 Punkte, jeder 7. blieb uebrig)')

    def test_grenze_bleibt_endlich(self):
        """Sie ist eine Notbremse gegen Riesen-Nutzlasten – nicht abschaffen, nur anheben."""
        from tests.base import appmod
        self.assertLessEqual(appmod.LIVE_TRACK_PAGE_PTS, 5000,
                             'zu gross: die Nutzlast waechst linear damit')

    def test_douglas_peucker_statt_jeder_n_te(self):
        """Gegenprobe an der echten Ausduenn-Funktion: Bei einer Geraden darf fast alles
        wegfallen, in einer Kurve fast nichts. Blindes `pts[::step]` kann das nicht."""
        from tests.base import appmod

        class P:
            __slots__ = ('lat', 'lng')

            def __init__(self, lat, lng):
                self.lat, self.lng = lat, lng

        # 1000 Punkte auf einer Geraden -> wenige bleiben uebrig
        gerade = [P(53.0 + i * 0.0001, 9.9) for i in range(1000)]
        aus_g = appmod._thinned_track(gerade, 100)
        self.assertLessEqual(len(aus_g), 100)
        self.assertLessEqual(len(aus_g), 20, 'Geraden muessen stark ausgeduennt werden')
        self.assertEqual(aus_g[0].lat, gerade[0].lat)
        self.assertEqual(aus_g[-1].lat, gerade[-1].lat)

        # 1000 Punkte auf einem Kreis -> die Form muss erhalten bleiben
        import math
        kreis = [P(53.55 + 0.0006 * math.sin(2 * math.pi * i / 1000),
                   9.98 + 0.0006 * math.cos(2 * math.pi * i / 1000) * 1.6) for i in range(1000)]
        aus_k = appmod._thinned_track(kreis, 100)
        self.assertLessEqual(len(aus_k), 100)
        # Entscheidend ist die FORM: Jeder ausgeduennte Punkt muss auf der Originalkurve
        # liegen. (Nicht „Radius = 65 m" pruefen – die Testkurve ist eine Ellipse mit
        # 63.5..66.8 m, und ein Kreis mit 65 m Radius waere in x/y verschieden lang.)
        m_lat, m_lng = 111320.0, 111320.0 * math.cos(math.radians(53.55))
        orig = [(p.lng * m_lng, p.lat * m_lat) for p in kreis]
        for p in aus_k:
            px, py = p.lng * m_lng, p.lat * m_lat
            dmin = 1e18
            for a, b in zip(orig, orig[1:]):
                dx, dy = b[0] - a[0], b[1] - a[1]
                seg = dx * dx + dy * dy
                tt = max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / seg)) if seg else 0.0
                dmin = min(dmin, math.hypot(px - (a[0] + tt * dx), py - (a[1] + tt * dy)))
            self.assertLess(dmin, 2.0, 'ausgeduennte Punkte muessen auf der Kurve liegen')

    def test_spur_bleibt_nah_an_der_echten_fahrt(self):
        """Die gezeichnete Spur darf nicht querfeldein abkuerzen (alt: bis 541 m daneben)."""
        from tests.base import appmod

        class P:
            __slots__ = ('lat', 'lng')

            def __init__(self, lat, lng):
                self.lat, self.lng = lat, lng

        import math
        # 4-h-Runde: 400-m-Geraden und 90-Grad-Boegen (r = 60 m), Punkt alle 3 s
        pts, x, y, kurs, phase, ps, tempo = [], 0.0, 0.0, 0.0, 0, 0, 5.0
        for t in range(0, 4 * 3600 + 1, 3):
            pts.append(P(53.55 + y / 111320.0,
                         9.98 + x / (111320.0 * math.cos(math.radians(53.55)))))
            dauer, kr = t - ps, 0.0
            if phase % 2 == 0:
                if dauer > 400 / tempo:
                    phase += 1
                    ps = t
            else:
                kr = math.degrees(tempo / 60.0)
                if dauer > (math.pi / 2 * 60 / tempo):
                    phase += 1
                    ps = t
            kurs += kr * 3
            x += math.cos(math.radians(kurs)) * tempo * 3
            y += math.sin(math.radians(kurs)) * tempo * 3

        aus = appmod._thinned_track(pts, appmod.LIVE_TRACK_PAGE_PTS)
        self.assertLessEqual(len(aus), appmod.LIVE_TRACK_PAGE_PTS)
        # Groesster Abstand Original -> gezeichnete Linie
        m_lat, m_lng = 111320.0, 111320.0 * math.cos(math.radians(53.55))
        T = [(p.lng * m_lng, p.lat * m_lat) for p in aus]
        schlimmster, j = 0.0, 0
        for p in pts:
            px, py = p.lng * m_lng, p.lat * m_lat
            dmin = 1e18
            for k in range(max(0, j - 2), min(len(T) - 2, j + 60) + 1):
                ax, ay = T[k]
                dx, dy = T[k + 1][0] - ax, T[k + 1][1] - ay
                seg = dx * dx + dy * dy
                tt = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg)) if seg else 0.0
                d = math.hypot(px - (ax + tt * dx), py - (ay + tt * dy))
                if d < dmin:
                    dmin, j = d, k
            schlimmster = max(schlimmster, dmin)
        self.assertLess(schlimmster, 15,
                        f'Spur weicht {schlimmster:.0f} m von der Fahrt ab '
                        f'(alte blinde Ausduennung: 541 m)')


class MeldungUndDokuTest(AppTestCase):
    """Die Anzeige darf keinen alten Takt behaupten."""

    def test_meldung_nennt_den_neuen_takt(self):
        with open(LIVE, encoding='utf-8') as f:
            js = f.read()
        self.assertIn('gesendet wird alle 6 s (in Kurven sofort)', js)
        self.assertNotIn('gesendet wird im 20-s-Takt', js)

    def test_begruendung_steht_im_code(self):
        with open(LIVE, encoding='utf-8') as f:
            js = f.read()
        self.assertIn('Build bu', js)
        # Die Meldung des Nutzers steht woertlich im Kommentar (ueber zwei Zeilen umbrochen)
        self.assertIn('nur Geraden sichtbar', js)
        self.assertIn('INVERTIERT', js)


if __name__ == '__main__':
    unittest.main()
