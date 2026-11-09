"""Build bt: Auf dem Desktop lag die Statuszeile der Live-Karte über der Knopfleiste.

Der Nutzer: „beim Desktop wird Fahren - Pause Knopf vom Hinweis überdeckt" (Bild 17:
grüne Meldung „Du teilst deinen Standort seit 22:05 Uhr …" liegt über der Leiste).

Ursache: `#live-status` stand auf dem Desktop weiter bei `bottom: 8px`. Die Leiste ist
58 px hoch und sitzt bei `bottom: 0` – die Statuszeile lag damit genau darin. Build bm
hatte den km-Chip und die Symbolspalte auf `bottom: 66px` gehoben, die Statuszeile wurde
dabei vergessen.

Gemessen (Chromium, vorher): 1104×1070 Status y 966..1011 bei Leiste y 961..1019,
`elementFromPoint` auf der Mitte von „Pause" und „Fahren" lieferte `live-status` –
die Knöpfe waren nicht antippbar. Nachher: Status y 908..953, Leiste y 961..1019,
Treffer = `btn-pause` / `btn-share`.

Diese Tests lesen die CSS-Werte aus dem Template und rechnen die Kette nach, damit die
Reihenfolge nicht wieder auseinanderläuft – ohne Browser, in Millisekunden.
"""
import os
import re
import unittest

from tests.base import AppTestCase, ROOT


def _live_css():
    with open(os.path.join(ROOT, 'templates', 'touren', 'live.html'), encoding='utf-8') as f:
        return f.read()


def _bottoms(css, selektor):
    """Alle `bottom:`-Werte, die im Umfeld eines Selektor-Blocks gesetzt werden."""
    werte = []
    for m in re.finditer(re.escape(selektor), css):
        block = css[m.end():m.end() + 420]
        block = block.split('}')[0]
        for b in re.finditer(r'bottom:\s*(-?[\d.]+)px', block):
            werte.append(float(b.group(1)))
    return werte


class DesktopStatusUeberLeisteTest(AppTestCase):
    """Die Statuszeile muss auf dem Desktop ÜBER der Knopfleiste stehen."""

    LEISTE = 58          # gemessene Höhe von #live-bar (Padding 8 + Knopf 42)

    def test_status_steht_nicht_mehr_bei_8px(self):
        """Der alte Wert (bottom: 8px) lag in der Leiste – er darf im Desktop-Zweig weg sein."""
        css = _live_css()
        i = css.find('@media (min-width: 992px)')
        # alle Desktop-Zweige durchgehen
        treffer = []
        for m in re.finditer(r'@media \(min-width: 992px\)[^{]*\{', css):
            block = css[m.end():m.end() + 600]
            for b in re.finditer(r'#live-status[^{]*\{([^}]*)\}', block):
                for w in re.finditer(r'bottom:\s*([\d.]+)px', b.group(1)):
                    treffer.append(float(w.group(1)))
            # auch Ein-Zeilen-Regeln:  { #live-km { … } #live-status { bottom: 66px !important; } }
            for b in re.finditer(r'#live-status\s*\{([^}]*)\}', block):
                for w in re.finditer(r'bottom:\s*([\d.]+)px', b.group(1)):
                    treffer.append(float(w.group(1)))
        self.assertTrue(treffer, 'kein Desktop-bottom für #live-status gefunden')
        for v in treffer:
            self.assertGreater(v, self.LEISTE,
                               f'#live-status steht auf dem Desktop bei bottom:{v:g}px '
                               f'– das liegt in der {self.LEISTE}-px-Knopfleiste')

    def test_status_und_km_beruehren_sich_nicht(self):
        """Status (66 + 45 hoch) endet bei 111, der km-Chip beginnt bei 119."""
        css = _live_css()
        # Der Wert der Statuszeile steht in ihrem eigenen Desktop-Block (Build bt).
        m = re.search(r'@media \(min-width: 992px\) \{ #live-status \{[^}]*bottom: ([\d.]+)px', css)
        self.assertIsNotNone(m, 'Desktop-Regel für #live-status fehlt')
        status_unten = float(m.group(1))
        self.assertEqual(status_unten, 66.0)
        status_hoehe = 45.0                      # gemessen: Schrift .9rem, zwei Zeilen
        km_unten = 119.0
        self.assertGreater(km_unten, status_unten + status_hoehe - 1,
                           'km-Chip überlappt die Statuszeile (Build bt: 66+45 < 119)')

    def test_km_und_symbole_bleiben_ueber_der_leiste(self):
        """Die seit Build bm gültige Anhebung darf nicht zurückfallen."""
        css = _live_css()
        self.assertIn('#live-km { bottom: 66px; } #live-tools { bottom: 66px; }', css)

    def test_kein_zweiter_widerspruechlicher_sperr_wert(self):
        """Früher stand im zweiten 992px-Block `#live-guard-pill { bottom: 105px }` –
        das hätte die Pill in die Statuszeile geschoben (66+45=111 > 105)."""
        css = _live_css()
        self.assertNotIn('#live-guard-pill, #live-guard-lock { bottom: 105px; }', css)
        self.assertIn('#live-guard-pill, #live-guard-lock { bottom: 160px; }', css)

    def test_begruendung_steht_im_code(self):
        """Der nächste Leser soll sehen, warum die Werte so sind (Build bt)."""
        css = _live_css()
        self.assertIn('Build bt', css)
        self.assertIn('vom Hinweis überdeckt', css)


class DesktopVollbildStatusTest(AppTestCase):
    """Im Vollbild bleibt die Reihenfolge ebenfalls stimmig (Status über der Leiste)."""

    def test_vollbild_status_ueber_der_leiste(self):
        css = _live_css()
        m = re.search(r'#live-wrap\.live-fs #live-status\s*\{([^}]*)\}', css)
        self.assertIsNotNone(m, '#live-wrap.live-fs #live-status fehlt')
        w = re.search(r'bottom:\s*([\d.]+)px', m.group(1))
        if w:
            self.assertGreater(float(w.group(1)), 58,
                               'Statuszeile liegt im Vollbild in der Leiste')


if __name__ == '__main__':
    unittest.main()
