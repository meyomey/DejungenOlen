"""Build ck: „in der live Karte ist er immer noch blau"

Build cj hatte die LIVE-SPUR orangerot gemacht – gemeint war aber die TOURSTRECKE (GPX), die als
dicke dunkelblaue Linie (#2B3F6B, 5 px, 80 %) auf der Radkarte zwischen den blauen Radrouten
unterging (Screenshot 2: der Chip zeigt „2 min" ohne km, es gab noch keine Live-Spur – die sichtbare
Linie war die Planstrecke). Jetzt: Magenta #C2185B mit weißem Saum (9 px), 5 px / 95 %.
"""
import os
import unittest

from tests.base import ROOT, appmod

LIVE = os.path.join(ROOT, 'templates', 'touren', 'live.html')


class TourstreckeFarbeTest(unittest.TestCase):
    def setUp(self):
        with open(LIVE, encoding='utf-8') as f:
            self.js = f.read()

    def test_tourstrecke_nicht_mehr_dunkelblau(self):
        self.assertNotIn("L.polyline(TRACK, {color: '#2B3F6B'", self.js)
        self.assertIn("const TRACK_COLOR = '#C2185B';", self.js)
        self.assertIn("trackLine = L.polyline(TRACK, {color: TRACK_COLOR, weight: 5, opacity: .95})", self.js)

    def test_weisser_saum_unter_der_strecke(self):
        a = self.js.index("L.polyline(TRACK, {color: '#fff', weight: 9, opacity: .9, interactive: false})")
        b = self.js.index("trackLine = L.polyline(TRACK, {color: TRACK_COLOR")
        self.assertLess(a, b, 'Saum zuerst – liegt unter der Strecke')

    def test_drei_farben_unterscheidbar(self):
        # Tourstrecke, eigene Live-Spur, Mitfahrer-Palette: keine Dopplung
        palette = self.js.split('const TRAIL_COLORS = ')[1].split(';')[0]
        self.assertNotIn('#C2185B', palette)
        self.assertNotIn('#FF3D00', palette)
        self.assertNotEqual('#C2185B', '#FF3D00')

    def test_build_stempel(self):
        self.assertGreaterEqual(appmod.APP_BUILD, '2026-11-12 ck')
