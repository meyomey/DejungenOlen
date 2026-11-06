"""Build z: Radkarte (CyclOSM) auf JEDER Karte der App.

Vorher hatte nur die Live-Karte einen Kachel-Umschalter (Build 11-06u, „🚵 Wege"),
die Tourseite einen eigenen Satz Knöpfe. Jetzt gibt es EINEN zentralen Umschalter in
static/js/map-touch.js (wird über base.html auf jeder Seite geladen) mit vier Stilen:
Standard (OSM) · Radkarte (CyclOSM) · Gelände (OpenTopoMap) · Luftbild (Esri).

Was hier geprüft wird (ohne Browser – reine HTML-/JS-Prüfung):
  * die zentrale Datei kennt CyclOSM und wird von base.html geladen,
  * jede Seite mit einer OSM-Karte bindet base.html ein (Ausnahmen: Druck, eigene Umschalter),
  * die Tourseite bietet CyclOSM über ihre eigenen Knöpfe an und teilt den Speicher,
  * die Druckansicht hat den Knopf ausdrücklich NICHT (data-map-style="off"),
  * kein zweiter Knopf auf Seiten mit eigenem Umschalter (data-map-style="own"),
  * Mini-Karten in Listen zeigen nur das Symbol (kein Text, der die Karte verdeckt).
"""
import re
import unittest

from tests.base import AppTestCase, app

# Dateien mit eigener OSM-Karte und die zugehörige URL, unter der sie im Test erreichbar ist.
# (touren/create.html und gastro/form.html decken „anlegen/bearbeiten" ab, orte/form.html
#  wird über /orte/neu geprüft; admin/settings.html nur als Administrator.)
MAP_PAGES = [
    ('/', 'index.html'),
    ('/karte', 'karte.html'),
    ('/karte/erkundung', 'karte_erkundung.html'),
    ('/touren', 'touren/list.html'),
    ('/touren/neu', 'touren/create.html'),
    ('/geplante-touren', 'touren/geplant.html'),
    ('/gastro', 'gastro/list.html'),
    ('/gastro/neu', 'gastro/form.html'),
    ('/orte', 'orte/list.html'),
    ('/orte/neu', 'orte/form.html'),
]


class CentralStyleSwitchTest(unittest.TestCase):
    """Die zentrale Lösung: eine Datei, vier Stile, CyclOSM enthalten."""

    @classmethod
    def setUpClass(cls):
        with open(f'{app.root_path}/static/js/map-touch.js', encoding='utf-8') as fh:
            cls.js = fh.read()

    def test_cyclosm_in_central_file(self):
        self.assertIn('tile-cyclosm.openstreetmap.fr/cyclosm/', self.js)
        self.assertIn("cyclosm:", self.js)

    def test_styles(self):
        """Drei Stile – Gelände ist bewusst NICHT dabei (Build f: auf Wunsch entfernt)."""
        for name in ("osm:", "cyclosm:", "sat:"):
            self.assertIn(name, self.js)
        self.assertNotIn('opentopomap', self.js)
        m = re.search(r'var ORDER = \[([^\]]+)\]', self.js)
        self.assertIsNotNone(m, 'ORDER fehlt')
        order = [x.strip().strip("'\"") for x in m.group(1).split(',')]
        self.assertEqual(order, ['osm', 'cyclosm', 'sat'])

    def test_public_api(self):
        for fn in ('djoMap', 'syncOthers', 'current:', 'styles:', 'order:'):
            self.assertIn(fn, self.js)

    def test_session_storage_key(self):
        self.assertIn("'djo_map_style'", self.js)

    def test_opt_out_markers(self):
        self.assertIn("mapStyle === 'off'", self.js)
        self.assertIn("mapStyle === 'own'", self.js)

    def test_tiny_maps_only_icon(self):
        """Mini-Karten (< 200 px) zeigen nur das Symbol – kein Text über dem Kartenbild."""
        self.assertIn('offsetHeight < 200', self.js)
        self.assertIn("(tiny ? '' :", self.js)

    def test_osm_max_zoom(self):
        self.assertIn('maxZoom: 19', self.js)


class BaseTemplateLoadsSwitchTest(AppTestCase):
    def test_base_loads_map_touch(self):
        self.login_member()
        html = self.get_html('/karte')
        self.assertIn('js/map-touch.js', html)

    def test_every_map_page_has_switch_script(self):
        """Alle Seiten mit OSM-Karte liefern den zentralen Umschalter mit aus."""
        self.login_admin()
        for url, name in MAP_PAGES:
            with self.subTest(name=name):
                html = self.get_html(url)
                self.assertIn('js/map-touch.js', html, f'{name}: map-touch.js fehlt')


class CyclOsmOnEveryMapPageTest(AppTestCase):
    """Die Karten selbst bleiben OSM-Kacheln – der Stil wird zur Laufzeit getauscht,
    deshalb steht in den Seiten weiter tile.openstreetmap.org (map-touch.js erkennt
    genau daran „das ist eine unserer Karten")."""

    def test_map_pages_keep_osm_base(self):
        self.login_admin()
        for url, name in MAP_PAGES:
            with self.subTest(name=name):
                html = self.get_html(url)
                self.assertIn('tile.openstreetmap.org', html, f'{name}: keine OSM-Basiskarte')


class TourDetailStyleButtonsTest(AppTestCase):
    """Die Tourseite hat einen eigenen Umschalter – er muss CyclOSM anbieten und
    denselben Speicher nutzen wie der zentrale Knopf."""

    def setUp(self):
        super().setUp()                     # AppTestCase.setUp legt den Test-Client an
        self.login_org()
        self.html = self.get_html('/touren/%d' % self.t_plan_id)

    def test_three_buttons(self):
        for bid in ('btn-osm', 'btn-cyc', 'btn-sat'):
            self.assertIn(f'id="{bid}"', self.html, f'{bid} fehlt')
        self.assertNotIn('id="btn-ter"', self.html)      # Build f: Gelände bewusst entfernt

    def test_cyclosm_layer_defined(self):
        self.assertIn('tile-cyclosm.openstreetmap.fr/cyclosm/', self.html)

    def test_switch_layer_uses_cycle(self):
        self.assertIn("switchLayer('cyclosm'", self.html)

    def test_no_second_central_button(self):
        """data-map-style="own" → map-touch.js hängt keinen zweiten Knopf an #tour-map."""
        self.assertIn('id="tour-map" data-map-style="own"', self.html)

    def test_shares_storage_with_central_switch(self):
        self.assertIn('djoMap.current', self.html)
        self.assertIn('djoMap.syncOthers', self.html)

    def test_track_stays_on_top(self):
        """Beim Stilwechsel muss die neue Kachel-Ebene nach hinten – sonst liegt sie über dem Track."""
        self.assertIn('bringToBack', self.html)

    def test_gps_modal_uses_style(self):
        """GPS-Modal übernimmt den Kartenstil, zeigt aber keinen zweiten Knopf."""
        self.assertIn("mapStyle: 'own'", self.html)
        self.assertIn('djoMap.layer', self.html)


class PrintViewWithoutSwitchTest(AppTestCase):
    def test_print_map_opts_out(self):
        self.login_org()
        html = self.get_html('/touren/%d/drucken' % self.t_plan_id)
        self.assertIn('data-map-style="off"', html)

    def test_print_has_no_switch_script(self):
        """Druckansicht erbt nicht von base.html – dort gibt es keinen Bedienknopf."""
        self.login_org()
        html = self.get_html('/touren/%d/drucken' % self.t_plan_id)
        self.assertNotIn('js/map-touch.js', html)


class LiveMapMigratesOldChoiceTest(AppTestCase):
    """Build u hatte einen eigenen Kachel-Schalter (localStorage djo_live_tiles).
    Die alte Wahl wird in den neuen Speicher übernommen, der Leistenknopf ist weg."""

    def test_old_key_migrated(self):
        self.assertIn('djo_live_tiles', self.html)
        self.assertIn('djo_map_style', self.html)

    def test_old_button_removed(self):
        self.assertNotIn('id="btn-tiles"', self.html)
        self.assertNotIn('toggleTiles', self.html)

    def setUp(self):                       # noqa: F811 – gleicher Name, bewusst überschrieben
        super().setUp()
        self.login_org()
        self.html = self.get_html('/touren/%d/live' % self.t_plan_id)

    def test_live_has_map(self):
        self.assertIn("L.map('live-map'", self.html)


if __name__ == '__main__':
    unittest.main()
