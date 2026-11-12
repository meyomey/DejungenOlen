"""Build bz: „Der Text läuft über die Begrenzungen." (Format-Auswahl beim Tour-Video)

Screenshot (500 px breit): Die fünf Kacheln der Format-Auswahl sind 118 px breit, innen
bleiben nach dem Padding ~102 px. Die Beschriftungen brauchen aber deutlich mehr:

    „Insta · TikTok · WhatsApp"   ~143 px
    „Insta · Facebook 4:5"        ~112 px
    „Facebook · Insta 1:1"        ~112 px

**Ursache:** `static/css/style.css` setzt global `.btn { white-space: nowrap; }` (aus
Build 11-06i, damit „Anwenden" nicht mitten im Wort bricht). Die Format-Kacheln tragen
`btn` aber nur als Optik. Der Text konnte deshalb nirgends umbrechen und lief in die
Nachbarkachel – im Bild sichtbar: „Quadratisch" ragte in „Feed-Post", und
„Insta · Facebook 4:5" überlappte mit „Facebook · Insta 1:1".

**Behoben:**
- `.format-btn` (und alles darin) darf umbrechen. Die Regel greift bewusst nur dort –
  das globale Einzeilig-Gebot für echte Knöpfe bleibt unangetastet.
- Lange Wörter dürfen zusätzlich getrennt werden (`overflow-wrap: anywhere`), statt
  aus der Kachel zu laufen.
- Die Kacheln bleiben in einer Reihe gleich hoch (`height: 100%` auf Label und Kachel).
- Unter 430 px nur noch zwei Spalten – dort wären drei Spalten so eng, dass selbst
  umbrochene Wörter kaum passen. Nachgerechnet: bei 430 px sind die Kacheln 195 px
  breit und ALLE Beschriftungen einzeilig.
- Alle Regeln hängen an `.format-wahl` – vorher hätte `.row .col-4` auch andere Seiten
  getroffen (das `<style>` steht global im Dokument).
"""
import os
import re
import unittest

from tests.base import AppTestCase, ROOT, appmod

VIDEO = os.path.join(ROOT, 'templates', 'touren', 'video.html')
CSS = os.path.join(ROOT, 'static', 'css', 'style.css')


def _lies(pfad):
    with open(pfad, encoding='utf-8') as f:
        return f.read()


def _style_block():
    """Der <style>-Block am Ende von video.html."""
    js = _lies(VIDEO)
    i = js.rindex('<style>')
    return js[i:js.index('</style>', i)]


class UmbruchTest(AppTestCase):
    """Der Kern: Die Kachel darf umbrechen."""

    def test_kacheln_duerfen_umbrechen(self):
        block = _style_block()
        self.assertRegex(block, r'\.format-btn[^{]*\{[^}]*white-space:\s*normal')

    def test_auch_die_kleine_zeile_bricht_um(self):
        """`small` erbt sonst das nowrap vom .btn-Elternteil."""
        block = _style_block()
        self.assertIn('.format-btn *', block)

    def test_lange_woerter_werden_getrennt(self):
        block = _style_block()
        self.assertIn('overflow-wrap: anywhere', block)

    def test_globales_einzeilig_gebot_bleibt(self):
        """Darf nicht angetastet werden – sonst bricht „Anwenden" wieder im Wort."""
        css = _lies(CSS)
        self.assertIn('.btn { white-space: nowrap; }', css)

    def test_kein_veraltetes_break_word(self):
        """`word-break: break-word` ist veraltet und tat hier nichts."""
        block = _style_block()
        self.assertNotIn('word-break: break-word', block)


class GeltungsbereichTest(AppTestCase):
    """Die Regeln müssen auf die Format-Auswahl begrenzt sein."""

    def test_container_klasse_existiert(self):
        js = _lies(VIDEO)
        self.assertIn('row g-2 format-wahl', js)

    def test_keine_globalen_col_regeln(self):
        """`.row .col-4` hätte auch jede andere Seite getroffen."""
        block = _style_block()
        treffer = re.findall(r'(?<![\w.-])\.row\s+\.col-4', block)
        self.assertEqual(treffer, [], 'Regeln müssen an .format-wahl hängen')

    def test_col_regeln_haengen_am_container(self):
        block = _style_block()
        self.assertIn('.format-wahl > [class*="col-"]', block)


class GleicheHoeheTest(AppTestCase):
    """Kacheln in einer Reihe sollen nicht „auf Lücke" stehen."""

    def test_label_bekommt_volle_hoehe(self):
        block = _style_block()
        self.assertRegex(block, r'\.format-wahl > \[class\*="col-"\] > label\s*\{[^}]*height:\s*100%')

    def test_kachel_bekommt_volle_hoehe(self):
        block = _style_block()
        self.assertRegex(block, r'\.format-btn\s*\{[^}]*height:\s*100%')

    def test_kein_eigenes_flex_layout(self):
        """Bootstrap-.btn ist inline-block mit zentriertem Text – flex würde die
        Zeilen anders verteilen als vorher."""
        block = _style_block()
        self.assertNotIn('flex-direction: column', block)


class SchmaleFensterTest(AppTestCase):
    """Unter 430 px drei Spalten wären zu eng."""

    def test_media_query_vorhanden(self):
        block = _style_block()
        m = re.search(r'@media\s*\(max-width:\s*(\d+)px\)\s*\{([^}]*)\}', block)
        self.assertIsNotNone(m, 'es muss eine Media-Query für schmale Fenster geben')
        self.assertLessEqual(int(m.group(1)), 430)
        self.assertIn('width: 50%', m.group(2))

    def test_zwei_spalten_passen_rechnerisch(self):
        """Bei 430 px: Kachel ~195 px, innen 179 px. Der längste Text braucht 143 px
        -> einzeilig. Bei drei Spalten wären es 102 px -> zwei Zeilen, aber die
        Nachbarkacheln überlappen nicht mehr (weil umbrochen wird)."""
        innen_zwei = 195 - 16
        self.assertGreater(innen_zwei, 143, 'längster Text (143 px) muss einzeilig passen')


class DatumTest(AppTestCase):
    """Build bz: Der Stempel trug noch das Datum vom 09.11., obwohl am 12.11. gebaut wurde.

    Das ist im Alltag leicht zu übersehen: Der Footer ist die einzige Stelle, an der man
    auf dem Server ablesen kann, welcher Stand läuft. Steht dort ein altes Datum, sucht
    man den Fehler im Code statt im Upload – genau das ist bei Build bx passiert.
    `make_deploy_zip.py` warnt beim ZIP-Bau schon davor; dieser Test prüft es zusätzlich
    bei jedem Testlauf.
    """

    def test_build_datum_ist_heute_oder_spaeter(self):
        import datetime as _dt
        build = appmod.APP_BUILD                       # z. B. '2026-11-12 bz'
        datum = build.split(' ')[0]
        gebaut = _dt.date.fromisoformat(datum)
        heute = _dt.date.today()
        self.assertLessEqual(
            gebaut, heute,
            f'APP_BUILD ({build}) liegt in der Zukunft – Tippfehler im Datum?')
        # Grosszuegig: das Datum darf hoechstens 2 Tage alt sein. Aelter heisst fast
        # immer, dass beim Ausliefern vergessen wurde, den Stempel zu setzen.
        self.assertGreaterEqual(
            gebaut, heute - _dt.timedelta(days=2),
            f'APP_BUILD traegt das Datum {datum}, heute ist {heute}. Bitte in app.py '
            f'auf das Auslieferungsdatum setzen (z. B. \'{heute} bz\').')

    def test_build_hat_die_form_datum_buchstabe(self):
        self.assertRegex(appmod.APP_BUILD, r'^\d{4}-\d{2}-\d{2} [a-z]{2}$')


class MarkupTest(AppTestCase):
    """Die fünf Kacheln sind unverändert vorhanden."""

    def test_alle_fuenf_formate(self):
        js = _lies(VIDEO)
        for wert in ('reels', 'feed', 'square', 'landscape', 'shorts'):
            self.assertIn(f'value="{wert}"', js)

    def test_beschriftungen_unveraendert(self):
        js = _lies(VIDEO)
        for text in ('Reels / Story', 'Feed-Post', 'Quadratisch', 'Quer / TV', 'Shorts'):
            self.assertIn(text, js)


if __name__ == '__main__':
    unittest.main()
