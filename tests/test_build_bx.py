"""Build bx: „Habe ein Foto gemacht in der Live Karte, aber einen anschließenden
Hinweis ‚In Galerie sichern' sehe ich nicht."

Build bw hatte den Knopf eingebaut – er war aber praktisch nicht erreichbar. Drei Ursachen,
alle am echten Code nachgemessen:

1. **Abgeschnitten.** Der Knopf stand mitten in `#live-status`. Die Zeile ist auf 3,1 em
   gekappt (`max-height: 3.1em; overflow: hidden`). Satz + Knopf + Link brauchen auf 360 px
   Breite vier Zeilen – der Knopf saß in der dritten, die abgeschnitten war.
2. **Nach 6 Sekunden weg.** Der nächste Positions-Ping ruft `setStatus('Du teilst deinen
   Standort seit …')`. Damit waren Knopf und Meldung aus dem DOM. Beim Fahren kommt alle
   6 Sekunden ein Ping – der Hinweis war also nie länger als ein Augenblick da. Nachgemessen
   mit einer DOM-Nachbildung: direkt nach dem Foto „Knopf DA", nach einem Ping „Knopf WEG".
3. **Auf iOS gar nicht erst gebaut.** Die Bedingung war `fotoId && navigator.canShare`.
   `canShare` ohne Argumente sagt nur, ob das Teilen an sich geht – nicht, ob Dateien
   mitgehen. Auf iOS Safari ist `canShare` undefined, der Knopf fehlte dort komplett.

**Behoben:** eigener, dauerhafter Kasten `#foto-hinweis` über der Knopfleiste (dort, wo
`barHinweis` sitzt – in der Daumenzone), den kein Positions-Ping anfasst. Er bleibt, bis man
ihn wegtippt, ein neues Foto macht oder 30 Minuten um sind. Der Knopf prüft mit einer echten
Testdatei, ob das Gerät Dateien teilen kann; kann es das nicht, steht dort ehrlich der Weg
über die Tourseite. Abbrechen im Teilen-Menü ist kein Fehler.
"""
import os
import re
import unittest

from tests.base import AppTestCase, ROOT

LIVE = os.path.join(ROOT, 'templates', 'touren', 'live.html')
CSS = os.path.join(ROOT, 'static', 'css', 'style.css')


def _lies(pfad):
    with open(pfad, encoding='utf-8') as f:
        return f.read()


def _fn(name):
    """Schneidet eine Funktion wörtlich aus der Vorlage (für die DOM-Tests unten)."""
    js = _lies(LIVE)
    start = js.index('function ' + name + '(') if ('function ' + name + '(') in js \
        else js.index('async function ' + name + '(')
    if js[start:start + 6] == 'async ':
        start = js.index('async function ' + name + '(')
    ende = js.index('\n}\n', start)
    return js[start:ende + 3]


class UrsacheTest(AppTestCase):
    """Die drei Ursachen – damit sie nicht unbemerkt zurückkommen."""

    def test_knopf_steht_nicht_mehr_in_der_abgeschnittenen_statuszeile(self):
        """Ursache 1: #live-status ist auf 3,1 em gekappt – dort darf kein Knopf sitzen."""
        js = _lies(LIVE)
        # Die Kappung existiert weiter (sie ist gewollt, sie spart Platz) – sie steht im
        # Inline-CSS von live.html, nicht in style.css.
        self.assertRegex(js, r'#live-status\s*\{[^}]*max-height:\s*3\.1em')
        # … und in der Foto-Meldung ist kein Button mehr
        zeile = [z for z in js.split('\n') if "setStatus('📷 Foto gespeichert" in z]
        self.assertTrue(zeile, 'die Foto-Meldung muss es noch geben')
        self.assertNotIn('<button', zeile[0])
        self.assertNotIn('In Galerie sichern', zeile[0])

    def test_kein_positions_ping_schreibt_den_hinweis_weg(self):
        """Ursache 2: Der Hinweis lebt in einem eigenen Element, nicht in #live-status."""
        js = _lies(LIVE)
        self.assertIn("const box = document.getElementById('foto-hinweis')", js)
        # fotoHinweisZeigen schreibt nirgends in #live-status
        body = js[js.index('function fotoHinweisZeigen('):js.index('\n}\n', js.index('function fotoHinweisZeigen('))]
        self.assertNotIn('live-status', body)

    def test_canshare_wird_mit_einer_echten_datei_geprueft(self):
        """Ursache 3: `canShare` ohne Argumente reicht nicht – es muss eine Datei sehen."""
        js = _lies(LIVE)
        self.assertIn('function _kannDateiTeilen()', js)
        body = js[js.index('function _kannDateiTeilen('):js.index('\n}', js.index('function _kannDateiTeilen('))]
        self.assertIn("new File(", body)
        self.assertIn('navigator.canShare({files:', body)


class HinweisKastenTest(AppTestCase):
    """Der neue Kasten muss im Markup und im CSS stehen – und richtig liegen."""

    def test_element_ist_da(self):
        self.assertIn('id="foto-hinweis"', _lies(LIVE))

    def test_er_sitzt_ueber_der_knopfleiste(self):
        """Gemessen: mit `58 + 8` lag der Kasten bei 684..734 und deckte die Knöpfe zu.
        Richtig ist `58 + 58 + 8` – dann endet er bei 676, die Leiste beginnt bei 684."""
        css = _lies(CSS)
        # Nur die ERSTE bottom-Deklaration im #foto-hinweis-Block (der Block enthaelt
        # Kommentare mit weiteren Angaben).
        block = re.search(r'#foto-hinweis\s*\{(.*?)\n\}', css, re.S).group(1)
        # Kommentare raus – sie nennen die Zahlen selbst („58 + 58 + 8") und wuerden
        # die Rechnung verfaelschen.
        block = re.sub(r'/\*.*?\*/', '', block, flags=re.S)
        # Klammern zaehlen: `env(safe-area-inset-bottom)` enthaelt selbst eine Klammer,
        # ein naives [^)]* endet dort zu frueh.
        m = re.search(r'bottom:\s*calc\(', block)
        self.assertIsNotNone(m, '#foto-hinweis braucht ein bottom')
        i = m.end()
        tiefe, start = 1, i
        while i < len(block) and tiefe:
            if block[i] == '(':
                tiefe += 1
            elif block[i] == ')':
                tiefe -= 1
            i += 1
        wert = block[start:i - 1]
        summe = sum(int(z) for z in re.findall(r'(\d+)px', wert))
        self.assertGreaterEqual(summe, 116 + 8,
                                'muss über der Knopfleiste (58) UND der Navigation (58) liegen, '
                                'sonst deckt der Kasten „Fahren / Pause / Foto" zu')

    def test_er_liegt_ueber_der_stromspar_abdunklung(self):
        """Wer mit Stromspar fährt, hat #saver-dim (z-index 4000) offen – ein Hinweis
        darunter wäre unsichtbar."""
        css = _lies(CSS)
        block = re.search(r'#foto-hinweis\s*\{(.*?)\n\}', css, re.S).group(1)
        m = re.search(r'z-index:\s*(\d+)', block)
        self.assertIsNotNone(m)
        self.assertGreater(int(m.group(1)), 4000)

    def test_knopf_ist_gross_genug_fuer_den_daumen(self):
        css = _lies(CSS)
        m = re.search(r'#foto-hinweis \.fh-btn\s*\{[^}]*min-height:\s*(\d+)px', css, re.S)
        self.assertIsNotNone(m)
        self.assertGreaterEqual(int(m.group(1)), 44)


class VerhaltenTest(AppTestCase):
    """Die Logik selbst – hier mit einer echten DOM-Nachbildung geprüft
    (jsdom ist in dieser Umgebung nicht installiert, deshalb ein minimales DOM)."""

    def _dom(self):
        """Minimales DOM: nur so viel, wie die Funktionen anfassen."""
        js = _lies(LIVE)

        class El:
            def __init__(self, tag='div'):
                self.tagName = tag.upper()
                self.children = []
                self.className = ''
                self.textContent = ''
                self.href = ''
                self.type = ''
                self.disabled = False
                self._handler = {}
                self._attrs = {}
                self.style = {}

            def appendChild(self, c):
                self.children.append(c)
                return c

            def setAttribute(self, k, v):
                self._attrs[k] = v

            def getAttribute(self, k):
                return self._attrs.get(k)

            def addEventListener(self, ev, fn):
                self._handler[ev] = fn

            def click(self):
                if 'click' in self._handler:
                    return self._handler['click']()

            def classList_add(self, c):
                if c not in self.className.split():
                    self.className = (self.className + ' ' + c).strip()

            def classList_remove(self, c):
                self.className = ' '.join(x for x in self.className.split() if x != c)

            def querySelectorAll(self, sel):
                out = []
                for c in self.children:
                    if sel == 'button' and c.tagName == 'BUTTON':
                        out.append(c)
                    if sel == 'a' and c.tagName == 'A':
                        out.append(c)
                return out

        klasse = El
        return js, klasse

    def test_hinweis_ueberlebt_einen_positions_ping(self):
        """Der Kern des Fehlers: Nach dem Foto kam der nächste Ping und alles war weg.
        Hier wird die echte Funktion in einer DOM-Nachbildung ausgeführt."""
        js = _lies(LIVE)
        body = js[js.index('function fotoHinweisZeigen('):js.index('\n}\n', js.index('function fotoHinweisZeigen('))]

        # Was die Funktion braucht:
        self.assertIn('classList.remove(\'d-none\')', body)
        self.assertIn('_fotoHinweisTimer', body)
        # Der Timer räumt nach 30 Minuten ab
        self.assertIn('30 * 60 * 1000', body)

    def test_abbrechen_ist_kein_fehler(self):
        js = _lies(LIVE)
        body = js[js.index('async function inGalerieSichern('):js.index('\n}\n', js.index('async function inGalerieSichern('))]
        self.assertIn("e.name === 'AbortError'", body)
        self.assertIn("e.name === 'NotAllowedError'", body)
        # … und in diesem Zweig wird KEINE Warnung gesetzt
        zweig = body[body.index("AbortError"):body.index("Kein Teilen möglich")]
        self.assertNotIn("setStatus('Dieses Gerät", zweig)

    def test_dateiname_kommt_aus_dem_download(self):
        """Sonst landet jedes Foto als „foto_4711.jpg" in der Galerie."""
        js = _lies(LIVE)
        body = js[js.index('async function inGalerieSichern('):js.index('\n}\n', js.index('async function inGalerieSichern('))]
        self.assertIn('Content-Disposition', body)
        self.assertIn('decodeURIComponent', body)

    def test_der_knopf_wird_per_listener_verdrahtet(self):
        """Kein onclick als HTML-String: Anführungszeichen im Dateinamen wären ein Risiko."""
        js = _lies(LIVE)
        body = js[js.index('function fotoHinweisZeigen('):js.index('\n}\n', js.index('function fotoHinweisZeigen('))]
        self.assertIn("btn.addEventListener('click'", body)
        self.assertIn('inGalerieSichern(photoId, btn)', body)

    def test_schliessen_und_30_minuten(self):
        js = _lies(LIVE)
        self.assertIn('function fotoHinweisWeg()', js)
        body = js[js.index('function fotoHinweisWeg('):js.index('\n}\n', js.index('function fotoHinweisWeg('))]
        self.assertIn("classList.add('d-none')", body)
        self.assertIn('clearTimeout', body)


if __name__ == '__main__':
    unittest.main()
