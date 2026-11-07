# -*- coding: utf-8 -*-
"""Build 2026-11-07 ad – Bildschirm wachhalten, Stromspar neu gedacht, Rückmeldung am Knopf.

Der Nutzer meldete nach Build ac: „es geht nicht. Wenn ich länger auf den Button tippe,
wird auch nichts angezeigt. Vielleicht sollte man den Stromsparmode nochmal neu denken."

Ursachen, die dieser Build behebt:
  1. Chromium gibt den Video-Wake-Lock nur, wenn das Video zu mindestens 20 % des Fensters
     zählt UND zu mindestens 75 % sichtbar ist (video_wake_lock.cc, kSizeThreshold = 0.2,
     kStrictVisibilityThreshold = 0.75) – oder wenn es hörbar ist. Das 2×2-px-Video aus
     Build ac erfüllte beides nie.
  2. Verweigert das Betriebssystem den Wake-Lock still (Akkusparmodus), sieht JavaScript das
     nicht. Die App schaltete daraufhin das Video ab („spart Akku") und hielt nichts mehr.
  3. Die Rückmeldung erschien nur als 2,5-s-Toast oben auf der Karte – beim Tippen auf einen
     Symbolknopf unten war sie nicht zu sehen.
  4. Stromspar verlangte „Display bleibt an" und war damit das Gegenteil von Stromsparen.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _live():
    return open(os.path.join(ROOT, 'templates', 'touren', 'live.html'), encoding='utf-8').read()


def _css():
    return open(os.path.join(ROOT, 'static', 'css', 'style.css'), encoding='utf-8').read()


class VideoWakeLockGroesseTest(unittest.TestCase):
    """Der Ersatz muss die Chromium-Bedingung erfüllen: Fläche und Sichtbarkeit."""

    def test_video_deckt_das_fenster(self):
        live = _live()
        self.assertIn('inset:0;width:100%;height:100%', live)
        self.assertIn('object-fit:cover', live)
        # unsichtbar, aber flächig – 1 % Deckkraft
        self.assertIn('opacity:.01', live)
        self.assertIn('pointer-events:none', live)
        # hinter dem Inhalt, damit nichts verdeckt wird
        self.assertIn('z-index:0', live)

    def test_nicht_wieder_winzig(self):
        live = _live()
        # Das 2×2-Video war der Fehler – es darf nicht zurückkommen.
        self.assertNotIn("width:2px;height:2px", live)

    def test_video_bleibt_an(self):
        live = _live()
        # Das Video darf NICHT abgeschaltet werden, nur weil die API „erteilt" hat:
        # ein vom System still verweigerter Lock ist von einem erteilten nicht zu trennen.
        self.assertNotIn('setFallback(false);              // API hält', live)
        self.assertIn('setFallback(true);\n      refreshWakeUi();\n      wakeVerify();', live)

    def test_nachpruefung_misst_die_regel(self):
        live = _live()
        self.assertIn('function wakeFacts()', live)
        self.assertIn('f.gross = f.flaeche >= 20 && f.sichtbar >= 75;', live)
        self.assertIn('function wakeVerify()', live)
        # ehrlich, wenn es nicht greift
        self.assertIn("wakeErr = f.laeuft ? 'video-zu-klein' : 'video-startet-nicht';", live)
        self.assertIn('video-zu-klein', live)
        self.assertIn('video-startet-nicht', live)


class RueckmeldungAmKnopfTest(unittest.TestCase):
    """Der Nutzer tippt unten – dort muss die Antwort erscheinen."""

    def test_barhinweis_existiert(self):
        live = _live()
        self.assertIn('function barHinweis(', live)
        self.assertIn("b.id = 'bar-hinweis';", live)
        # 4 s, nicht 2,5 s
        self.assertIn('}, 4000);', live)

    def test_alle_wake_rueckmeldungen_nutzen_die_leiste(self):
        live = _live()
        for text in ('🔆 wird eingeschaltet', '🔆 Bildschirm bleibt an – ',
                     '⚠️ Geht auf diesem Gerät nicht: ',
                     '🌙 Bildschirm darf wieder ausgehen.'):
            self.assertIn(text, live, text)

    def test_leiste_liegt_ueber_den_hauptknoepfen(self):
        css = _css()
        self.assertIn('.bar-hinweis {', css)
        self.assertIn('bottom: calc(58px + env(safe-area-inset-bottom) + 58px);', css)
        # Statuszeile weicht, solange der Hinweis steht (beide sitzen an derselben Stelle)
        self.assertIn('body.bar-hinweis-an #live-status { opacity: 0; }', _live())
        # Kein zweiter Toast oben auf der Karte – der Balken an der Leiste genuegt.
        self.assertNotIn("mapToast('⚠️ Bildschirm wachhalten greift hier nicht", _live())


class StromsparNeuTest(unittest.TestCase):
    """Stromspar heißt jetzt: das Display DARF ausgehen, kein Punkt geht verloren."""

    def test_sparmodus_verlangt_nicht_mehr_display_an(self):
        live = _live()
        self.assertNotIn('Sparmodus braucht das Display', live)
        self.assertIn('Display darf ausgehen', live)
        self.assertIn('if (!wakeWanted && !saverOn) setWakeWanted(true);', live)

    def test_jeder_punkt_wird_gesichert(self):
        live = _live()
        self.assertIn('function sicherSpeichern()', live)
        self.assertIn('function sicherLaden()', live)
        self.assertIn('function sicherNachsenden()', live)
        self.assertIn('gesichert.push(punkt);', live)
        self.assertIn("localStorage.setItem(SICHER_KEY", live)
        # gesichert wird VOR dem fetch – sonst wäre der Punkt bei Abbruch verloren
        pos_push = live.index('gesichert.push(punkt);')
        pos_fetch = live.index("fetch('/api/location/update', {", pos_push)
        self.assertLess(pos_push, pos_fetch)

    def test_nachsendung_bei_rueckkehr_und_start(self):
        live = _live()
        self.assertIn('sicherNachsenden();                          // Build ad: was während des Einfrierens offen blieb', live)
        self.assertIn('setTimeout(sicherNachsenden, 1500);', live)
        # bestätigte Punkte werden entfernt
        self.assertIn('gesichert.splice(ix, 1); sicherSpeichern();', live)

    def test_leiste_bleibt_im_sparmodus_bedienbar(self):
        """Vorher fing das dunkle Overlay jeden Tipp ab – Fahrt war nicht zu beenden."""
        css = _css()
        self.assertIn('#live-bar { z-index: 4100 !important; }', css)
        self.assertIn('#saver-dim { bottom: var(--saver-frei, 0px); }', css)
        self.assertIn('body.saver-on #live-tools { z-index: 4100; }', _live())

    def test_spar_hinweis_sagt_die_wahrheit(self):
        live = _live()
        self.assertIn('das Display darf ausgehen,<br>die Aufzeichnung läuft weiter', live)
        self.assertIn('🌙 Stromspar an – das Display darf jetzt ausgehen. Die Aufzeichnung läuft weiter.', live)


if __name__ == '__main__':
    unittest.main()
