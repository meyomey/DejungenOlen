"""Build by: „Man klickt auf den Hinweis Bereich und nichts passiert, es bewegt sich nur
ein bisschen nach oben."

Gemeint war die Meldung nach dem Fahrtende (Screenshot 1080x2340 = 360x780 CSS):

  Gelber Kasten „Fahrt beendet – Aufzeichnung sichern…"   sichtbar 479..564 (85 px)
  Grüner Knopf „✓ Als Track übernehmen"                   bei 564 hart abgeschnitten
  Statuszeile darunter                                    endet mitten im Satz

**Ursachen (am Screenshot nachgemessen):**

1. **Der gelbe Kasten war auf zwei Zeilen geklemmt.** In Build bo stand hier
   `display: -webkit-box; -webkit-line-clamp: 2; overflow: hidden`. Ergebnis: Der Titel
   endet mit „…" (im Bild deutlich zu sehen: „sichern…"), und weil der Kasten nur zwei
   Zeilen hoch ist, wird die Knopfreihe mit abgeschnitten. Build bq hat die Regel
   entfernt – sie darf nie wieder hereinkommen.
2. **Ein Tipp auf den Kasten tat nichts.** Der Kasten hatte keinen Handler. Getroffen
   wurde die Statuszeile darunter – die klappt bei einem Tipp von 3,1 em auf 12 em auf.
   Genau das ist das „bewegt sich ein bisschen nach oben". Der Satz war vorher gekappt
   („…Die Aufzeichnung kannst du"), also war das Aufklappen auch noch sinnvoll – aber
   es sieht aus wie eine kaputte Schaltfläche.

**Behoben:**
- Der Kasten hat keine Klemmung mehr (Inline-Regel mit `!important` als Notaus, damit
  keine geerbte Regel aus einem älteren Build durchschlagen kann) und darf scrollen,
  statt abgeschnitten zu werden.
- Ein Tipp irgendwo auf die gelbe Fläche führt zur Tourseite in den Abschnitt
  „Live-Aufzeichnung". Knöpfe, Links und das ⓘ behalten ihre eigene Funktion.
- Bei beendeter Fahrt zeigt die Statuszeile ihren Text vollständig (`body.rec-hint-an`),
  und ein Tipp darauf führt ebenfalls zur Tourseite statt nur aufzuklappen.
"""
import os
import unittest

from tests.base import AppTestCase, ROOT

LIVE = os.path.join(ROOT, 'templates', 'touren', 'live.html')


def _lies(pfad=LIVE):
    with open(pfad, encoding='utf-8') as f:
        return f.read()


def _block(js, selektor):
    """Schneidet den CSS-Block zu einem Selektor aus dem Inline-Style."""
    i = js.find(selektor)
    if i < 0:
        return ''
    j = js.find('{', i)
    k = js.find('}', j)
    return js[j:k + 1]


class KlemmungTest(AppTestCase):
    """Ursache 1: Der Kasten war auf zwei Zeilen geklemmt."""

    def test_keine_klemmung_mehr_im_stylesheet(self):
        """Die Regel aus Build bo darf nicht zurückkommen – nur der Kommentar darf sie nennen."""
        js = _lies()
        # Alle Zeilen, die eine echte CSS-Anweisung sind (kein Kommentar):
        echte = []
        im_kommentar = False
        for z in js.split('\n'):
            if '/*' in z:
                im_kommentar = True
            if not im_kommentar:
                echte.append(z)
            if '*/' in z:
                im_kommentar = False
        treffer = [z for z in echte if 'line-clamp' in z and 'unset' not in z]
        self.assertEqual(treffer, [],
                         'line-clamp darf nur noch als Notaus (unset) vorkommen:\n' + '\n'.join(treffer))

    def test_notaus_steht_inline_am_kasten(self):
        """Inline schlägt jedes Stylesheet – so kann kein altes Build durchschlagen."""
        js = _lies()
        tag = js[js.index('id="rec-hint-fs"'):js.index('>', js.index('id="rec-hint-fs"'))]
        self.assertIn('-webkit-line-clamp: unset !important', tag)
        self.assertIn('-webkit-box-orient: initial !important', tag)

    def test_notaus_versteckt_den_kasten_nicht(self):
        """Ein `display: block !important` inline würde `d-none` aushebeln – der Kasten
        wäre dauerhaft sichtbar. Das darf nicht passieren."""
        js = _lies()
        tag = js[js.index('id="rec-hint-fs"'):js.index('>', js.index('id="rec-hint-fs"'))]
        self.assertNotIn('display:', tag)

    def test_kasten_darf_scrollen_statt_abzuschneiden(self):
        js = _lies()
        tag = js[js.index('id="rec-hint-fs"'):js.index('>', js.index('id="rec-hint-fs"'))]
        self.assertIn('overflow-y: auto', tag)
        self.assertIn('max-height:', tag)


class KlickTest(AppTestCase):
    """Ursache 2: Ein Tipp auf den Kasten tat nichts."""

    def test_es_gibt_einen_handler(self):
        js = _lies()
        self.assertIn('function recHintKlickFangen()', js)

    def test_handler_wird_beim_oeffnen_gesetzt(self):
        """Sowohl im Vollbild als auch im Normalbetrieb."""
        js = _lies()
        body = js[js.index('function showRecHint('):js.index('\n}\n', js.index('function showRecHint('))]
        self.assertEqual(body.count('recHintKlickFangen()'), 2,
                         'muss in BEIDEN Zweigen aufgerufen werden (Vollbild und normal)')

    def test_knopfe_behalten_ihre_funktion(self):
        """Der Handler darf Knöpfe, Links und das ⓘ nicht schlucken."""
        js = _lies()
        body = js[js.index('function recHintKlickFangen('):js.index('\n}\n', js.index('function recHintKlickFangen('))]
        self.assertIn("closest('button, a, input, form, .rec-info-btn, .rec-info')", body)
        self.assertIn('return;', body)

    def test_flaeche_fuehrt_zur_tourseite(self):
        js = _lies()
        body = js[js.index('function recHintKlickFangen('):js.index('\n}\n', js.index('function recHintKlickFangen('))]
        self.assertIn('#live-aufzeichnung', body)

    def test_handler_wird_nicht_doppelt_gehaengt(self):
        js = _lies()
        body = js[js.index('function recHintKlickFangen('):js.index('\n}\n', js.index('function recHintKlickFangen('))]
        self.assertIn('klickGefangen', body)

    def test_flaeche_ist_als_antippbar_erkennbar(self):
        js = _lies()
        body = js[js.index('function recHintKlickFangen('):js.index('\n}\n', js.index('function recHintKlickFangen('))]
        self.assertIn('cursor', body)
        self.assertIn('title =', body)


class StatuszeileTest(AppTestCase):
    """Das „bewegt sich ein bisschen nach oben" war das Aufklappen der Statuszeile."""

    def test_text_ist_bei_fahrtende_nicht_mehr_gekappt(self):
        js = _lies()
        self.assertIn('body.rec-hint-an #live-status', js)
        block = _block(js, 'body.rec-hint-an #live-status')
        self.assertIn('max-height: none', block)

    def test_tipp_fuehrt_zur_tourseite_statt_aufzuklappen(self):
        js = _lies()
        i = js.index("document.getElementById('live-status').addEventListener('click'")
        body = js[i:js.index('\n});', i)]
        self.assertIn('rec-hint-an', body)
        self.assertIn('#live-aufzeichnung', body)

    def test_waehrend_der_fahrt_klappt_sie_weiter_auf(self):
        """Das Verhalten dort ist gewollt und darf nicht verloren gehen."""
        js = _lies()
        i = js.index("document.getElementById('live-status').addEventListener('click'")
        body = js[i:js.index('\n});', i)]
        self.assertIn("classList.toggle('open')", body)


if __name__ == '__main__':
    unittest.main()
