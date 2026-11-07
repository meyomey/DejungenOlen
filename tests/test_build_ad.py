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
        # Build ae: „Bildschirm bleibt an" steht erst da, wenn der Selbsttest es bestätigt –
        # vorher nur „Eingerichtet … in 40 Sekunden weiß ich mehr".
        for text in ('🔆 wird eingeschaltet', '🔆 Eingerichtet (',
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
        """Build ae: Die Leiste wird NICHT mehr ueber die Abdunklung gehoben – der Nutzer
        meldete „es wird nicht der ganze Bildschirm abgedunkelt". Beendet wird ueber das ✕."""
        css = _css()
        self.assertNotIn('#live-bar { z-index: 4100 !important; }', css)
        self.assertNotIn('#saver-dim { bottom: var(--saver-frei, 0px); }', css)
        # alles andere dunkelt mit ab
        self.assertIn('body.saver-on:not(.saver-hell) #live-tools { visibility: hidden; }', _live())

    def test_spar_hinweis_sagt_die_wahrheit(self):
        live = _live()
        # Build af: Der grosse Kasten mitten im Bild ist ersetzt durch einen schmalen Streifen.
        self.assertIn('Einmal tippen = kurz schauen · zweimal tippen = dauerhaft hell', live)
        self.assertIn('🌙 Stromspar an – Display darf ausgehen, gesendet wird im 20-s-Takt.', live)
        self.assertIn('Einmal tippen = kurz schauen, zweimal = dauerhaft hell.', live)


if __name__ == '__main__':
    unittest.main()


class AbdunklungGanzflaechigTest(unittest.TestCase):
    """Build ae: „Es wird auch nicht der ganze Bildschirm abgedunkelt."

    Ursache: Build ad hob Knopfleiste und Symbolspalte über das Overlay, und das Overlay
    endete oberhalb der Leiste (`bottom: var(--saver-frei)`). Dadurch blieben unten helle
    Streifen – App-Navigation, Knopfleiste und Symbolspalte – und das Overlay war nicht
    bildschirmfüllend.
    """

    def test_overlay_deckt_das_ganze_fenster(self):
        css = _css()
        block = css.split('#saver-dim {', 1)[1].split('}', 1)[0]
        self.assertIn('position: fixed; inset: 0', block)
        # keine Verkürzung mehr nach unten
        self.assertNotIn('--saver-frei', css)
        self.assertNotIn('#live-bar { z-index: 4100', css)
        self.assertNotIn('bottom: var(--saver-frei', css)

    def test_nichts_steht_ueber_dem_overlay(self):
        css = _css()
        # Build ah: nur im DUNKLEN ausblenden – im hellen Zustand muss man bedienen koennen.
        self.assertIn('body.saver-on:not(.saver-hell) #live-tools { visibility: hidden; }', _live())
        self.assertIn('body.saver-on:not(.saver-hell) #live-status,', _live())


class SelbsttestWachhaltenTest(unittest.TestCase):
    """Build ae: „Es geht nicht, obwohl nur grüne Meldungen kommen."

    Der Konstruktionsfehler war, den technischen Zustand als Beweis auszugeben. Eine
    Web-Seite kann den Bildschirm nicht abfragen – aber sie kann messen, ob die Seite
    eingefroren wurde. Genau das macht wachTick().
    """

    def test_zeitmessung_existiert(self):
        live = _live()
        self.assertIn('function wachTick()', live)
        self.assertIn('letzteWachZeit', live)
        self.assertIn('setInterval(wachTick, 5000);', live)

    def test_stillstand_widerlegt_das_wachhalten(self):
        live = _live()
        self.assertIn('if (luecke > 20 && wakeWanted) {', live)
        self.assertIn("wachBeweis = {ok: false, luecke: luecke};", live)
        self.assertIn('Der Bildschirm ging trotz „an" aus', live)
        # der Gegenbeweis schlägt jede technische Freigabe
        self.assertIn('if (wachBeweis && wachBeweis.ok === false) f.ok = false;', live)

    def test_gruen_erst_nach_40_sekunden(self):
        live = _live()
        self.assertIn('jetzt - wachSeit >= 40000', live)
        self.assertIn('✅ Bildschirm bleibt an – vom Gerät bestätigt (40 s ohne Unterbrechung).', live)
        # und NICHT mehr „geprüft" direkt nach dem Einschalten
        self.assertNotIn("', geprüft.', 'gut')", live)
        self.assertIn('Ob der Bildschirm wirklich anbleibt, zeigt sich in den nächsten 40 Sekunden', live)

    def test_knopf_bleibt_an_nur_mit_beweis(self):
        live = _live()
        self.assertIn('const bewaehrt = !!(wachBeweis && wachBeweis.ok === true);', live)
        self.assertIn('noch nicht bestätigt; das Gerät kann sich darüber hinwegsetzen', live)


class StromsparZweiStufenTest(unittest.TestCase):
    """Build af: Einmal tippen = kurz schauen, zweimal = dauerhaft hell, nochmal = sparen.

    Der Nutzer: „Wenn der Stromsparen aktiv ist, soll bei einmal tippen das Display kurz
    angehen um kurz schauen zu können und bei zweimal tippen soll das Display anbleiben.
    Wenn man erneut zweimal tippt, wieder in Stromsparen gehen. Aktuell wird die Sicht auf
    die Karte versperrt mit dem großen Stromspar-an-Hinweis, auch wenn es hell ist."
    """

    def test_einmal_tippen_hellt_kurz_auf(self):
        live = _live()
        self.assertIn('function saverTap()', live)
        self.assertIn('function saverStufe(', live)
        # 4 s hell, dann wieder dunkel
        self.assertIn('}, 4000);', live)
        self.assertIn('d.classList.remove(\'saver-peek\')', live)

    def test_zweimal_tippen_bleibt_hell(self):
        live = _live()
        # Doppeltipp erkennt der zweite Tipp innerhalb der Wartezeit
        self.assertIn('if (saverTapTimer) {', live)
        self.assertIn("saverStufe(!saverHell);", live)
        css = _css()
        off = css.split('#saver-dim.saver-off {', 1)[1].split('}', 1)[0]
        self.assertIn('background: transparent', off)
        self.assertIn('pointer-events: none', off)

    def test_zurueck_in_den_sparmodus(self):
        live = _live()
        self.assertIn("dim.classList.toggle('saver-off', saverHell);", live)
        # Ausschalten räumt beide Stufen ab
        self.assertIn("dim.classList.remove('saver-off', 'saver-peek', 'saver-tipp')", live)

    def test_hinweis_versperrt_die_karte_nicht(self):
        live = _live()
        css = _css()
        # kein Kasten mehr mitten im Bild
        self.assertNotIn('Bildschirm bleibt an – das Display darf ausgehen', live)
        self.assertIn("id=\"saver-weg\"", live)
        # beim Aufwachen nach 2 s ausblenden
        self.assertIn('d.classList.add(\'saver-tipp\')', live)
        self.assertIn('}, 2000);', live)
        self.assertIn('#saver-dim.saver-tipp .saver-chip { opacity: 0; }', css)
        # Hinweis sitzt über der Leiste, nicht auf der Karte
        self.assertIn('padding-bottom: calc(122px + env(safe-area-inset-bottom));', css)


class StromsparBlickJedesMalTest(unittest.TestCase):
    """Build ag: „Einmal tippen funktioniert nur einmal. Wenn man erneut nach einer
    längeren Zeit auf den abgedunkelten Screen einmal tippt, bleibt er immer an."

    Ursache: saverTap() setzte die Aufhellung direkt (`classList.add('saver-peek')`), aber
    ohne Zeitgeber zum Zurückdunkeln. Der 4-s-Timer lebte nur in saverStufe() und lief
    einmal beim Einschalten. Danach blieb der Bildschirm dauerhaft hell.
    Jetzt gibt es genau eine Stelle, die den Blick steuert (saverBlick) – sie setzt BEIDE
    Timer bei jedem Tipp neu.
    """

    def test_blick_setzt_immer_beide_timer(self):
        live = _live()
        self.assertIn('function saverBlick()', live)
        block = live.split('function saverBlick()', 1)[1].split('\n}', 1)[0]
        self.assertIn('saverPeekTimer = setTimeout', block)     # zurückdunkeln nach 4 s
        self.assertIn('saverHintTimer = setTimeout', block)     # Hinweis weg nach 2 s
        self.assertIn('}, 4000);', block)
        self.assertIn('}, 2000);', block)

    def test_einzeltipp_nutzt_die_gemeinsame_stelle(self):
        live = _live()
        tap = live.split('function saverTap()', 1)[1].split('\n}', 1)[0]
        self.assertIn('saverBlick();', tap)
        # der alte Fehler: direktes Aufhellen ohne Timer darf nicht zurückkommen
        self.assertNotIn("if (!saverHell && dim) dim.classList.add('saver-peek');", live)

    def test_doppeltipp_in_beiden_zustaenden(self):
        live = _live()
        tap = live.split('function saverTap()', 1)[1].split('\n}', 1)[0]
        # die Wartezeit wird IMMER scharf gemacht – auch im hellen Zustand
        self.assertIn("saverTapTimer = setTimeout(() => { saverTapTimer = null; }, 300);", tap)
        self.assertIn('saverStufe(!saverHell);', tap)

    def test_zurueckdunkeln_nur_wenn_nicht_hell(self):
        live = _live()
        block = live.split('function saverBlick()', 1)[1].split('\n}', 1)[0]
        self.assertIn('if (d && !saverHell) d.classList.remove(\'saver-peek\');', block)


class StromsparHellBedienbarTest(unittest.TestCase):
    """Build ah: „man kann nur schauen und nicht bedienen oder zoomen nach einem Doppelklick
    aus dem Stromsparen?"

    Ursache: `background: transparent` machte das Overlay im dauerhaft hellen Zustand nur
    unsichtbar. Es lag weiterhin über allem und fing jeden Tipp ab – man konnte zusehen,
    aber nichts bedienen. Zusätzlich blendete `body.saver-on #live-tools` die Symbolspalte
    in JEDEM Sparzustand aus, und der Karten-Guard sperrte das Verschieben.
    """

    def test_overlay_laesst_tipps_durch(self):
        css = _css()
        block = css.split('#saver-dim.saver-off {', 1)[1].split('}', 1)[0]
        self.assertIn('pointer-events: none', block)
        # ✕ und Hinweis bleiben anklickbar – sonst käme man nicht mehr heraus
        self.assertIn('#saver-dim.saver-off #saver-off { pointer-events: auto; }', css)
        self.assertIn('#saver-dim.saver-off .saver-chip { pointer-events: auto; }', css)

    def test_symbolspalte_nur_im_dunklen_aus(self):
        live = _live()
        self.assertIn('body.saver-on:not(.saver-hell) #live-tools { visibility: hidden; }', live)
        self.assertIn('body.saver-on:not(.saver-hell) #live-status,', live)
        # die alte, zustandsunabhängige Regel darf nicht zurückkommen
        self.assertNotIn('body.saver-on #live-tools { visibility: hidden; }', live)

    def test_karte_im_hellen_zustand_verschiebbar(self):
        live = _live()
        block = live.split('function saverStufe(', 1)[1].split('\n}', 1)[0]
        self.assertIn('if (saverHell) { guardUnlocked = true; setLiveGuard(); }', block)
        self.assertIn("document.body.classList.toggle('saver-hell', saverHell && saverOn);", block)

    def test_zurueck_im_dunklen_wieder_geschuetzt(self):
        css = _css()
        # ohne saver-off gilt wieder die normale Overlay-Regel (pointer-events: auto)
        self.assertNotIn('#saver-dim { pointer-events: none;', css)
