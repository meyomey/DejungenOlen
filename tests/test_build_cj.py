"""Build cj: „man kann den gefahrenen Track in blauer Farbe kaum erkennen"

Screenshot: Radkarte (CyclOSM) – die eigene Spur in #1E88E5, 3 px, 55 % Deckkraft, verschwand
zwischen den blauen Radrouten der Karte. Jetzt: Orangerot (#FF3D00, kommt auf keiner der drei
Kartenstile vor), 5 px, 95 %, plus weißer Saum (9 px) unter jeder Spur; Mitfahrer 4 px / 85 %.
"""
import os
import unittest

from tests.base import ROOT, appmod

LIVE = os.path.join(ROOT, 'templates', 'touren', 'live.html')


class SpurFarbeTest(unittest.TestCase):
    def setUp(self):
        with open(LIVE, encoding='utf-8') as f:
            self.js = f.read()

    def test_eigene_spur_nicht_mehr_blau(self):
        self.assertIn("const TRAIL_ME = '#FF3D00';", self.js)
        self.assertNotIn("'#1E88E5' : TRAIL_COLORS", self.js)
        self.assertIn("uid === ME.id ? TRAIL_ME : TRAIL_COLORS", self.js)

    def test_kraeftiger_und_mit_saum(self):
        self.assertIn("weight: mine ? 5 : 4, opacity: mine ? .95 : .85", self.js)
        self.assertIn("trailCasing[uid] = L.polyline([], {color: '#fff', weight: mine ? 9 : 7, opacity: .9", self.js)
        # Saum wird VOR der Spur angelegt (liegt darunter) und wächst mit
        a = self.js.index("trailCasing[uid] = L.polyline(")
        b = self.js.index("trails[uid] = L.polyline(", a)
        self.assertLess(a, b)
        self.assertIn("trailCasing[uid].addLatLng([p[0], p[1]]);\n      trails[uid].addLatLng([p[0], p[1]]);", self.js)

    def test_farbe_kollidiert_nicht(self):
        # nicht die Planstrecke (#2B3F6B), nicht in der Mitfahrer-Palette
        self.assertNotIn('#FF3D00', self.js.split('const TRAIL_COLORS')[1].split(';')[0])
        self.assertNotEqual('#FF3D00', '#2B3F6B')

    def test_build_stempel(self):
        self.assertGreaterEqual(appmod.APP_BUILD, '2026-11-12 cj')
