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
        # Build aj: Die gruenen Selbsttest-Kaesten sind weg („Eingerichtet … 40 Sekunden",
        # „vom Gerät bestaetigt"). Geblieben ist die Rueckmeldung am Knopf und die Warnung.
        for text in ('🔆 wird eingeschaltet',
                     '⚠️ Geht auf diesem Gerät nicht: ',
                     '🌙 Bildschirm darf wieder ausgehen.'):
            self.assertIn(text, live, text)
        self.assertNotIn('🔆 Eingerichtet (', live)

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

    def test_beweis_erst_nach_40_sekunden_ohne_kasten(self):
        live = _live()
        # Der Nachweis nach 40 s bleibt die Grundlage – nur ohne gruene Box (Build aj).
        self.assertIn('jetzt - wachSeit >= 40000', live)
        self.assertIn('wachBeweis = {ok: true, geprueft: 40};', live)
        # und NICHT mehr „geprüft" direkt nach dem Einschalten
        self.assertNotIn("', geprüft.', 'gut')", live)
        # Build aj: keine Selbsttest-Meldungen mehr in der Leiste
        self.assertNotIn('✅ Bildschirm bleibt an – vom Gerät bestätigt (40 s ohne Unterbrechung).', live)
        self.assertNotIn('Ob der Bildschirm wirklich anbleibt, zeigt sich in den nächsten 40 Sekunden', live)
        self.assertNotIn('zeigt sich in den nächsten 40 Sekunden', live)

    def test_beweis_steht_weiter_im_knopf(self):
        live = _live()
        # Der Stand ist nicht verloren – er steckt im Symbol-Knopf (Farbe + title).
        self.assertIn('b.classList.toggle(\'on\', wakeWanted && wakeActive());', live)
        self.assertIn('vom Gerät bestätigt, ', live)
        self.assertIn('noch nicht bestätigt; das Gerät kann sich darüber hinwegsetzen', live)

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
        # Build ao (Audit 7): saverTap() war seit Build ai toter Code (nie aufgerufen) und
        # wurde entfernt. Geprueft wird die Stelle, die wirklich laeuft.
        self.assertNotIn('function saverTap()', live)
        self.assertIn('function saverBlick()', live)
        self.assertIn('function saverStufe(', live)
        # 4 s hell, dann wieder dunkel
        self.assertIn('}, 4000);', live)
        self.assertIn('d.classList.remove(\'saver-peek\')', live)

    def test_zweimal_tippen_bleibt_hell(self):
        live = _live()
        # Doppeltipp erkennt der zweite Tipp innerhalb der Wartezeit – Build ai: im
        # Dokument-Listener, der beide Zustaende gleich behandelt.
        block = live.split("document.addEventListener('click', e => {", 1)[1].split('}, true);', 1)[0]
        self.assertIn('const nah = _saverTippAt && (jetzt - _saverTippAt) < 400 &&', block)
        self.assertIn("saverStufe(!saverHell);", block)
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
        # Build ai: Die Erkennung sitzt am Dokument; das Aufhellen laeuft weiter ueber saverBlick().
        self.assertIn("if (!istKnopf && !saverHell) saverBlick();", live)
        # der alte Fehler: direktes Aufhellen ohne Timer darf nicht zurueckkommen
        self.assertNotIn("if (!saverHell && dim) dim.classList.add('saver-peek');", live)

    def test_doppeltipp_in_beiden_zustaenden(self):
        live = _live()
        block = live.split("document.addEventListener('click', e => {", 1)[1].split('}, true);', 1)[0]
        # im hellen wie im dunklen Zustand derselbe Weg: saverStufe umschalten
        self.assertIn('saverStufe(!saverHell);', block)
        self.assertIn('_saverTippAt = jetzt;', block)

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


class SaverDoppeltippMitKarteTest(unittest.TestCase):
    """Build ai: „Wenn die Karte auf groß gestellt ist, funktioniert zweimal tippen nicht mehr."

    Zwei Ursachen, beide von mir:
    1. Seit Build ah hat das Overlay im hellen Zustand `pointer-events: none` (damit die Karte
       bedienbar ist). Damit bekam der Tipp-Erkenner am Overlay keinen einzigen Tipp mehr –
       „zweimal tippen" zum Zurückschalten war tot. Aufgefallen im Vollbild, weil man dort
       die Karte wirklich bedient.
    2. Ein pauschales „es wurde bewegt"-Flag blockierte den Doppeltipp zusätzlich: Jede
       Mausbewegung und jedes Finger-Wackeln setzte es.
    """

    def test_erkennung_haengt_am_dokument_nicht_am_overlay(self):
        live = _live()
        # der alte Listener am Overlay darf nicht mehr existieren
        self.assertNotIn("document.getElementById('saver-dim').addEventListener('click'", live)
        block = live.split("document.addEventListener('click', e => {", 1)[1].split('}, true);', 1)[0]
        self.assertIn('saverStufe(!saverHell);', block)

    def test_kein_pauschales_bewegungsflag(self):
        live = _live()
        self.assertNotIn('_saverBewegt', live)
        # stattdessen: Kartenstand vergleichen
        self.assertIn('function _saverMapStand()', live)
        self.assertIn('_saverStandBeiTipp', live)

    def test_bedienelemente_zaehlen_nicht_als_tipp(self):
        live = _live()
        block = live.split("document.addEventListener('click', e => {", 1)[1].split('}, true);', 1)[0]
        self.assertIn("cls.indexOf('leaflet-control') >= 0", block)
        self.assertIn('if (istKnopf) { _saverTippAt = 0; return; }', block)
        # die Kartenflaeche selbst darf NICHT ausgeschlossen sein
        self.assertNotIn("cls.indexOf('leaflet-pane') >= 0", block)
        self.assertNotIn("el.id === 'live-map'", block)

    def test_heller_zustand_voll_bedienbar(self):
        css = _css()
        off = css.split('#saver-dim.saver-off {', 1)[1].split('}', 1)[0]
        self.assertIn('pointer-events: none', off)
        # kein Streifen, der im hellen Zustand etwas verdeckt
        self.assertIn('body.saver-hell #saver-dim .saver-chip { display: none; }', css)


class SaverDoppeltippOhneZoomTest(unittest.TestCase):
    """Build ak: „Blöd ist noch, dass die Karte gezoomt wird wenn man zweimal tippt und in
    Stromsparen geht."

    Im hellen Zustand ist die Karte bedienbar, also erreicht der Doppeltipp auch Leaflet –
    und Leaflet zoomt bei jedem dblclick eine Stufe hinein. Gemessen: Zoom 15 → 16 beim
    Zurückschalten in den Sparmodus. Der Doppeltipp-Zoom ist deshalb aus, solange der
    Sparmodus läuft; Zoomen per +/− und per zwei Fingern bleibt unberührt.
    """

    def test_doppeltipp_zoom_im_sparmodus_aus(self):
        live = _live()
        self.assertIn('if (saverOn) map.doubleClickZoom.disable();', live)
        self.assertIn('else map.doubleClickZoom.enable();', live)
        # und zwar an der Stelle, die beide Wege erreichen (Knopf und Doppeltipp)
        block = live.split('function saverStufe(hell) {', 1)[1].split('refreshSaverChip();', 1)[0]
        self.assertIn('doubleClickZoom', block)

    def test_zoom_knoepfe_bleiben_nutzbar(self):
        live = _live()
        # +/− nicht abschalten – nur den Doppeltipp
        self.assertNotIn('map.zoomControl.remove', live)
        self.assertNotIn('touchZoom.disable', live)
        self.assertIn("const map = L.map('live-map', {zoomControl: true, attributionControl: false});", live)


class SaverDoppeltippSchaltetNichtDasWachhaltenTest(unittest.TestCase):
    """Build ak: Derselbe Doppeltipp schaltete zusätzlich das Wachhalten um.

    Der Nutzer wollte nur zurück in den Stromsparmodus und bekam dabei ungefragt
    „Bildschirm an". Im Sparmodus gehört der Doppeltipp der Spar-Stufe; 🔆 bleibt
    für das Wachhalten zuständig.
    """

    def test_wachhalten_reagiert_im_sparmodus_nicht(self):
        live = _live()
        block = live.split("document.getElementById('live-wrap').addEventListener('touchend', function () {", 1)[1]
        kopf = block.split('const now = Date.now();', 1)[0]
        self.assertIn('if (saverOn) return;', kopf)

    def test_wachhalten_bleibt_ueber_den_knopf_erreichbar(self):
        live = _live()
        self.assertIn('id="btn-wake" onclick="toggleWake()"', live)
        self.assertIn('function toggleWake()', live)


class SaverSeitenZoomTest(unittest.TestCase):
    """Build al: „Im Stromsparmodus zoomt der ganze Screen und nicht nur die Karte."

    Gemessen mit echten Zwei-Finger-Touch-Events: Bei aktivem Sparmodus sprang
    `visualViewport.scale` von 1 auf 1.12 (die SEITE zoomte), während die Karte bei Zoom 12
    stehen blieb. Grund: `#saver-dim` hatte `touch-action: auto`; Leaflets `touch-action: none`
    liegt auf der Kartenfläche, die das Overlay verdeckt.

    Behoben: Das Overlay sperrt den Seiten-Zoom (`touch-action: none`) und das Script reicht
    die Zwei-Finger-Geste selbst an die Karte weiter (saverPinch).
    """

    def test_overlay_sperrt_den_seitenzoom(self):
        css = _css()
        block = css.split('#saver-dim { touch-action:', 1)
        self.assertEqual(len(block), 2, 'touch-action fuer #saver-dim fehlt')
        self.assertIn('none', block[1].split('}', 1)[0])
        # 'manipulation' allein reicht nicht – der Versuch ist dokumentiert
        self.assertIn('manipulation', css)

    def test_zweifinger_geht_an_die_karte(self):
        live = _live()
        self.assertIn('function saverPinchStart(', live)
        self.assertIn('function saverPinchMove(', live)
        self.assertIn('map.setZoom(z, {animate: false});', live)
        # passive:false, sonst greift preventDefault nicht und die Seite zoomt doch
        self.assertIn("dim.addEventListener('touchmove', saverPinchMove, {passive: false});", live)
        # die Geste zaehlt nicht als Tipp -> Sparstufe bleibt, wie sie ist
        self.assertIn('if (e.touches.length !== 2) { _saverPinch = null; return; }', live)

    def test_doppeltipp_zoom_bleibt_trotzdem_aus(self):
        live = _live()
        # Build ak darf durch Build al nicht verloren gehen
        self.assertIn('if (saverOn) map.doubleClickZoom.disable();', live)


class SperrenDerLiveKarteTest(unittest.TestCase):
    """Build am: „Bei der Live Karte kann man nicht so richtig scrollen, da man die Karte
    nicht sperren kann."

    Gemessen in acht Zuständen: Das 🔒 gab es nur, wenn weder Fahrt lief noch gefolgt wurde
    noch Vollbild an war. Wer während der Fahrt oder beim Folgen scrollen wollte, fand
    keinen Sperr-Knopf – die Karte blieb frei und fraß jedes Wischen (0 px Scroll).

    Neu: `guardLocked` ist eine eigene Sperre, die jeden anderen Zustand schlägt, und der
    🔒-Knopf wird immer angeboten, sobald die Karte frei ist.
    """

    def test_eigene_sperre_schlaegt_jeden_modus(self):
        live = _live()
        self.assertIn('let guardLocked = false;', live)
        block = live.split('function guardWanted() {', 1)[1].split('}', 1)[0]
        self.assertIn('return guardLocked ||', block)

    def test_sperrknopf_gibt_es_immer(self):
        live = _live()
        # die alte Bedingung, die den Knopf bei Fahrt/Folgen/Vollbild verschluckte
        self.assertNotIn('const lockBar = !sharing && !following && !_fsAn();', live)
        # der Knopf wird jetzt ohne Zustandspruefung angelegt
        self.assertIn("guardLock.title = 'Karte sperren – dann scrollt die Seite';", live)

    def test_sperren_setzt_die_karte_zurueck(self):
        live = _live()
        self.assertIn('let guardStartView = null;', live)
        self.assertIn('function guardViewMerken()', live)
        self.assertIn('if (guardStartView) map.setView(', live)

    def test_entsperren_loest_auch_die_eigene_sperre(self):
        live = _live()
        self.assertIn('guardPill.onclick = () => { guardUnlocked = true; guardLocked = false; setLiveGuard(); };', live)


class SperrknopfUeberDemInfoBlockTest(unittest.TestCase):
    """Build an: (1) „Beim Vollbild muss die Sperre nicht sein."
    (2) „Der Sperrknopf soll lieber unten über dem grünen/orangen InfoBlock erscheinen."

    Gemessen vorher: 🔒 bei y≈224 (oben links unter dem Zoom), der Info-Block unten bei
    y≈702–732. Jetzt sitzt der Knopf bei y≈664–694, also genau 8 px über dem Block.
    """

    def test_im_vollbild_wird_nicht_gesperrt(self):
        live = _live()
        block = live.split('function guardWanted() {', 1)[1].split('}', 1)[0]
        self.assertIn('if (_fsAn()) return false;', block)
        # auch kein Knopf im Vollbild
        else_teil = live.split('// Build an: NICHT im Vollbild – dort soll keine Sperre sein (Nutzerwunsch).', 1)
        self.assertEqual(len(else_teil), 2)
        self.assertIn("if (guardLock) guardLock.style.display = 'none';", else_teil[1].split('}', 1)[0])

    def test_vollbild_merkt_sich_die_sperre(self):
        live = _live()
        self.assertIn('let guardVorVollbild = false;', live)
        self.assertIn('guardVorVollbild = guardLocked;', live)
        self.assertIn('guardLocked = guardVorVollbild;', live)

    def test_knopf_und_pill_sitzen_ueber_dem_infoblock(self):
        live = _live()
        # mobil: dieselbe Kante wie der Status-Chip (58 + 64), plus dessen Hoehe und 8 px Luft
        # Build as: 34 px hoch (vorher 30) – gleiche Masse wie das Schloss auf allen Karten
        self.assertIn('#live-guard-pill, #live-guard-lock { position: fixed; bottom: calc(58px + 64px + 34px + 8px); }', live)
        # Desktop: der Status-Chip sitzt in der Karte bei bottom: 84px -> Knopf bei 122px
        self.assertIn('#live-guard-pill, #live-guard-lock { bottom: 126px; }', live)
        # die alte Lage oben links ist weg
        self.assertNotIn('#live-guard-pill { position: absolute; top: 80px; left: 10px;', live)
        self.assertNotIn('#live-guard-lock { position: absolute; top: 80px; left: 10px;', live)


class Audit7SperreUndVollbildTest(unittest.TestCase):
    """Audit 7 (Build ao): Zustandsfehler der Kartensperre nach dem Vollbild.

    Gefunden im Audit-Durchlauf: Wer im Vollbild den Stromsparmodus beendete, verlor den
    gemerkten Frei-Zustand. `saverStufe()` schrieb `guardUnlocked` auch dort, wo der
    Vollbild-Zustand gilt – nach dem Verlassen war die Karte gesperrt, obwohl sie vorher
    frei war (gemessen: `map.dragging` false statt true, Pill zurück).
    """

    def test_sparstufe_fasst_den_guard_im_vollbild_nicht_an(self):
        live = _live()
        block = live.split('function saverStufe(hell) {', 1)[1].split('const dim2', 1)[0]
        self.assertIn('if (_fsAn()) { /* Vollbild regelt den Guard selbst */ }', block)
        # die Guard-Zeilen haengen jetzt am else-Zweig
        self.assertIn('else if (saverHell) { guardUnlocked = true; setLiveGuard(); }', block)


class Audit7ToterCodeTest(unittest.TestCase):
    """Audit 7 (Build ao): saverTap() lief seit Build ai nie mehr (Tipp-Erkennung am
    Dokument) und war nur noch Ballast – dazu `const aufKarte`."""

    def test_saverTap_ist_weg(self):
        live = _live()
        self.assertNotIn('function saverTap()', live)
        # aufKarte darf nur noch im Grabstein-Kommentar stehen, nicht als Code
        for zeile in live.splitlines():
            if 'aufKarte' in zeile:
                self.assertTrue(zeile.strip().startswith('//'), f'Code statt Kommentar: {zeile!r}')

    def test_die_echte_stelle_bleibt(self):
        live = _live()
        self.assertIn("document.addEventListener('click', e => {", live)
        self.assertIn('function saverBlick()', live)


class VollbildSymbolTest(unittest.TestCase):
    """Build ap: „Das X irritiert. Man denkt hier beendet man was komplett."

    Im Vollbild ersetzte der Knopf sein Symbol durch ein großes ✕ – das liest sich wie
    „beenden/abbrechen". Jetzt ist es das übliche Gegenstück zum Auf-Symbol: vier Pfeile
    nach innen. Gleicher Platz, gleiche Größe – nur die Richtung zeigt die Bedeutung.
    """

    def test_vollbild_zeigt_pfeile_nach_innen_statt_x(self):
        live = _live()
        self.assertIn('const SVG_FS_AUS =', live)
        # das alte Kreuz darf nicht mehr als Vollbild-Symbol auftauchen
        self.assertNotIn('const SVG_X =', live)
        self.assertNotIn("M6 6l12 12M18 6L6 18", live)
        self.assertIn('if (fsIco) fsIco.innerHTML = on ? SVG_FS_AUS : SVG_FS;', live)

    def test_pfeile_zeigen_nach_innen(self):
        live = _live()
        block = live.split('const SVG_FS_AUS =', 1)[1].split(';', 2)[0] + \
                live.split('const SVG_FS_AUS =', 1)[1].split(';', 2)[1]
        # vier Ecken-Pfeile (ein Pfad mit vier "M"-Startpunkten)
        self.assertIn('M9 3v4.5', block)
        self.assertIn('M15 3v4.5', block)
        self.assertIn('M21 15h-4.5', block)
        self.assertIn('M3 15h4.5', block)

    def test_titel_bleibt_eindeutig(self):
        live = _live()
        self.assertIn("fsBtn.title = on ? 'Vollbild aus' : 'Vollbild';", live)
        self.assertIn("fsBtn.setAttribute('aria-label', on ? 'Vollbild aus' : 'Vollbild');", live)


class KartenHinweisUntenTest(unittest.TestCase):
    """Build aq: „Bei den anderen Karten stört mich das ‚Karte zum Verschieben antippen'
    in der Mitte. Sollte vielleicht weiter unten liegen?"

    Der Hinweis lag mittig (`align-items:center`) und verdeckte genau die Kartenmitte.
    Oben links ist der Zoom, oben rechts der Kartenstil-Knopf, unten rechts die
    Quellenangabe – frei bleibt nur unten in der Mitte. Gemessen nach dem Umbau:
    100-px-Karte: Hinweis 20 px hoch, 28 px Platz darunter; 624-px-Karte: 28 px hoch,
    30 px Platz; nie ein Konflikt mit Zoom, Stil, Schloss oder Quellenangabe.
    """

    def _js(self):
        return open(os.path.join(ROOT, 'static', 'js', 'map-touch.js'), encoding='utf-8').read()

    def test_hinweis_steht_unten_nicht_mittig(self):
        # Build as: naoch weiter nach links – der Hinweis sitzt jetzt unten LINKS, an derselben
        # Stelle, an der danach das Schloss erscheint (einheitlich mit der Live-Karte).
        js = self._js()
        self.assertIn("'align-items:flex-end;justify-content:flex-start;cursor:pointer;border-radius:inherit'", js)
        self.assertIn("overlay.style.paddingLeft = '8px';", js)
        # Der Hinweis-Overlay darf nicht mehr zentrieren (der Schloss-Knopf zentriert SEINEN
        # Inhalt per flex – das ist etwas anderes und bleibt).
        overlay_block = js.split("overlay.style.cssText =", 1)[1].split(';', 2)[0] + \
                        js.split("overlay.style.cssText =", 1)[1].split(';', 2)[1]
        self.assertNotIn('justify-content:center', overlay_block)

    def test_schrift_ist_einheitlich(self):
        # Build aq hatte die Schrift an die Kartenhöhe angepasst (100-px-Karten kleiner).
        # Build as nimmt das zurück: „Das sollte einheitlich sein" – eine feste Groesse,
        # zumal die Kante von 11 px über der Quellenangabe auf jeder Höhe passt.
        js = self._js()
        self.assertIn('font-size:.85rem;line-height:20px;', js)
        self.assertNotIn('var klein  = h < 140;', js)

    def test_kein_ueberlauf_auf_schmalen_karten(self):
        js = self._js()
        # Build as: Hinweis linksbuendig mit 8 px Rand – 16 px Abstand halten ihn im Bild
        self.assertIn('max-width:calc(100% - 16px)', js)


class LiveHinweisUntenLinksTest(unittest.TestCase):
    """Build ar: Der Nutzer widersprach meiner falschen Beschreibung –
    „Auf der Live Karte steht der Verschiebe-Hinweis unten links".

    Stimmt: `#live-guard-pill { left: 8px }` + `bottom:` = unten links. Seit Build an ist das
    die gewollte Lage („Der Sperrknopf soll lieber unten über dem grünen/orangen InfoBlock
    erscheinen"). Falsch war nur der Hilfetext, der noch „oben links" sagte.

    Im Browser nachgemessen (404 × 854): links 8 px, rechts 187 px, Unterkante 160 px über
    dem Fensterrand – also unten links, 38 px über der Statuszeile.
    """

    def test_hilfe_sagt_unten_links(self):
        h = open(os.path.join(ROOT, 'templates', 'hilfe.html'), encoding='utf-8').read()
        self.assertIn('Unten links über dem Info-Block steht', h)
        self.assertIn('„Zum Verschieben antippen“', h)
        self.assertNotIn('oben links', h)

    def test_pill_haengt_links_und_unten(self):
        live = _live()
        # links ist fest, unten kommt aus den beiden Media-Queries (mobil/desktop)
        self.assertIn('#live-guard-pill { position: absolute; left: 8px;', live)
        self.assertIn('#live-guard-pill, #live-guard-lock { position: fixed; '
                      'bottom: calc(58px + 64px + 34px + 8px); }', live)
        self.assertIn('#live-guard-pill, #live-guard-lock { bottom: 126px; }', live)

    def test_kommentare_behaupten_nicht_mehr_oben_links(self):
        live = _live()
        # „seit Build an unten links" muss im Kommentar stehen, damit der Irrtum nicht zurueckkommt
        self.assertIn('UNTEN LINKS (Build an:', live)
        self.assertIn('seit Build an ebenfalls unten links', live)


class EinheitlichesSchlossTest(unittest.TestCase):
    """Build as: „Das Schloss sollte auch jetzt im unteren Bereich erscheinen und nicht
    weiter oben rechts sein. Die Darstellung des Schlosses sind momentan unterschiedlich
    Live-Karte und andere Karten. Das sollte einheitlich sein."

    Vorher gab es ZWEI Darstellungen:

    | | Live-Karte | andere Karten |
    |---|---|---|
    | Ecke | unten links | **oben rechts** |
    | Symbol | 🔒 (Emoji) | Icon-Font `bi-lock-fill` (CDN!) |
    | Grund | dunkelblau rgba(20,30,60,.88) | **schwarz rgba(0,0,0,.5)** |
    | Form | Radius 20 px | **Radius 6 px, 32 × 32** |
    | Höhe | 30 px | 32 px |

    Jetzt eine Darstellung: unten links, Inline-SVG, 38 × 34, Radius 20 px, `display:flex`.
    Im Browser nachgemessen – alle fünf Karten liefern identische Werte.
    """

    def _js(self):
        return open(os.path.join(ROOT, 'static', 'js', 'map-touch.js'), encoding='utf-8').read()

    def test_schloss_steht_unten_links_nicht_oben_rechts(self):
        js = self._js()
        self.assertIn("lockBtn.style.cssText = 'position:absolute;left:8px;bottom:11px;z-index:1001;'", js)
        # die alte Lage oben rechts darf nicht zurückkommen
        self.assertNotIn("'position:absolute;top:8px;right:8px;z-index:1001;'", js)

    def test_schloss_hat_dieselben_masse_wie_die_live_karte(self):
        js = self._js()
        # 38 x 34, Radius 20, kein Innenabstand, dunkelblau - exakt wie #live-guard-lock
        self.assertIn("'padding:0;height:34px;width:38px;'", js)
        # Build ax: halbtransparent (.54) – vorher .88, „zu dunkel" (Nutzerwunsch)
        self.assertIn("background:rgba(20,30,60,.54)", js)
        live = _live()
        self.assertIn('#live-guard-lock { position: absolute; left: 8px; z-index: 1100;', live)
        self.assertIn('background: rgba(20, 30, 60, .54)', live)

    def test_kein_emoji_und_kein_icon_font_im_schloss(self):
        js = self._js()
        # Build as: Inline-SVG statt Emoji (sieht je nach Gerät anders aus) und statt Icon-Font
        # (kommt vom CDN - ohne Netz ein leerer Kasten)
        self.assertIn('var LOCK_SVG =', js)
        self.assertIn('lockBtn.innerHTML = LOCK_SVG;', js)
        self.assertNotIn("lockBtn.innerHTML = '<i class=\"bi bi-lock-fill\"></i>'", js)
        self.assertNotIn("lockBtn.textContent = '🔒'", js)

    def test_live_karte_und_karten_teilen_dasselbe_symbol(self):
        js = self._js()
        live = _live()
        # beide definieren dieselbe Zeichnung (Rechteck 4.5/10.5/15/10.5 r2.5 + Bogen)
        for quelle, name in ((js, 'map-touch.js'), (live, 'live.html')):
            self.assertIn('<rect x="4.5" y="10.5" width="15" height="10.5" rx="2.5"/>', quelle,
                          f'{name}: Rechteck fehlt')
            self.assertIn('<path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/>', quelle,
                          f'{name}: Buegel fehlt')
            self.assertIn('width="17" height="17"', quelle, f'{name}: Groesse fehlt')

    def test_hinweis_und_schloss_tauschen_sich_an_derselben_stelle(self):
        js = self._js()
        # beide left:8px, beide 34 px hoch, gleiche Unterkante -> beim Entsperren springt nichts
        self.assertIn("'align-items:flex-end;justify-content:flex-start;cursor:pointer;border-radius:inherit'", js)
        self.assertIn("overlay.style.paddingLeft = '8px';", js)
        self.assertIn('padding:.45rem .8rem;border-radius:20px;font-size:.85rem;line-height:20px;', js)
        # Hinweis: 6 px Rand + 2x6 Innenabstand + 20 Zeile = 34; Schloss: fest 34 + bottom 11
        self.assertIn('margin-bottom:11px', js)
        self.assertIn('bottom:11px', js)

    def test_stil_knopf_weicht_nur_bei_gleicher_zeile_aus(self):
        js = self._js()
        # alte Logik schob den Stil-Knopf immer nach links, sobald ein Lock existierte
        self.assertIn('var gleicheZeile = g.top < b.bottom && g.bottom > b.top;', js)
        self.assertIn("btn.style.right = '8px';", js)


class BlickZentriertAufMichTest(unittest.TestCase):
    """Build at: „Wenn man einmal tippt aus dem Stromspar kann man ja nichts bedienen, aber
    es sollte dann gezoomt werden auf einen selber um zu sehen wo man sich befindet, oder?"

    Ja – genau das war die Lücke: `saverBlick()` hellte nur auf, die Karte blieb stehen, wo
    sie war. Nach dem Folgen-Abbruch oder nach dem Wegscrollen zeigte der kurze Blick also
    irgendwo ins Leere, statt die eine Frage zu beantworten, für die man aufhellt.

    Im Browser gemessen (404 × 854): Ausgangslage Zoom 13, Mitte 53.4661/9.7995 –
    nach einem Tipp: **Zoom 16, Mitte 53.55/9.99** (die eigene Position).
    """

    def test_kurzer_blick_zentriert_auf_eigene_position(self):
        live = _live()
        self.assertIn('function saverAufMich()', live)
        self.assertIn('map.setView(ownLatLng, ziel, {animate: true});', live)
        # wird aus saverBlick() gerufen, nicht aus saverStufe()
        block = live.split('function saverBlick()', 1)[1].split('function ', 1)[0]
        self.assertIn('saverAufMich();', block)

    def test_zoom_ist_mindestens_16(self):
        live = _live()
        # wie beim Folgen: Strassen und Wege lesbar
        self.assertIn('const ziel = Math.max(map.getZoom(), 16);', live)

    def test_kein_zappeln_wenn_schon_dort(self):
        live = _live()
        # eigener Punkt im mittleren Bereich + Zoom schon ausreichend -> nicht eingreifen
        self.assertIn('const imBild = punkt.x > groesse.x * 0.15 && punkt.x < groesse.x * 0.85 &&', live)
        self.assertIn("if (imBild && map.getZoom() >= 16) return false;", live)

    def test_ohne_position_bleibt_die_karte(self):
        live = _live()
        block = live.split('function saverAufMich()', 1)[1].split('\n}\n', 1)[0]
        self.assertIn('if (typeof map === \'undefined\' || !map || !ownLatLng) return false;', block)
        # try/catch: eine kaputte Karten-API darf den Sparmodus nicht blockieren
        self.assertIn('catch (e) { return false; }', block)

    def test_dauerhaft_hell_zentriert_nicht(self):
        live = _live()
        # im dauerhaft hellen Zustand will man die Karte bedienen – kein Sprung
        stufe = live.split('function saverStufe(', 1)[1].split('\nfunction ', 1)[0]
        self.assertNotIn('saverAufMich', stufe)


class LiveStreckeTest(unittest.TestCase):
    """Build au: „kann man die zurückgelegte Route auch schon in der Live Karte anzeigen lassen?"

    Die Route wurde schon gezeichnet (`addTrails`, eigene Spur blau #1E88E5), aber niemand
    konnte sehen, WIE VIEL man geschafft hat – die Kilometerzahl stand erst nach der Fahrt
    auf der Tourseite. Jetzt rechnet die Live-Karte aus denselben Punkten mit.

    Im Browser gemessen: 10 Punkte → **1072 m = „1,2 km gefahren"**; zwei weitere Punkte →
    2156 m = „2,2 km", ohne Neuladen. Unter 50 m bleibt der Chip verborgen (kein „0,0 km").
    """

    def test_strecke_wird_aus_der_spur_gerechnet(self):
        live = _live()
        self.assertIn('function trailLaenge(uid)', live)
        self.assertIn('for (let i = 1; i < pts.length; i++) m += map.distance(pts[i - 1], pts[i]);', live)

    def test_chip_steht_auf_der_karte_nicht_in_der_liste(self):
        live = _live()
        # auf der Karte, oben links unter dem Zoom
        self.assertIn('<span id="live-km" class="d-none"', live)
        # Build ax: nicht mehr oben links (top: 82px), sondern unten links
        self.assertIn('#live-km { position: absolute; left: 8px; bottom: calc(', live)
        # der Chip im Card-Footer ist wieder weg (dort waere er auf dem Handy unsichtbar)
        self.assertNotIn('<span id="live-km" class="badge bg-secondary d-none"></span>', live)

    def test_unter_50_meter_keine_zahl(self):
        live = _live()
        # Build ax: km ODER Fahrzeit – „unter 50 m und unter einer Minute bleibt der Chip weg"
        self.assertIn('if (km >= 50 || sek >= 60) {', live)

    def test_kein_emoji_im_chip(self):
        live = _live()
        # Emoji fehlt auf manchen Geraeten -> leeres Kaestchen; daher Inline-SVG
        self.assertIn('const SVG_RAD =', live)
        # Build ax: km und Fahrzeit zusammen, gebaut aus Teilen
        self.assertIn('teile.push(SVG_RAD', live)
        self.assertNotIn("chip.innerHTML = '🚴 '", live)

    def test_waechst_bei_jedem_neuen_punkt(self):
        live = _live()
        # updateTrailKm() haengt am Ende von addTrails()
        block = live.split('function addTrails(obj)', 1)[1].split('\nfunction ', 1)[0]
        self.assertIn('updateTrailKm();', block)


class FahrtGesperrtSichtbarTest(unittest.TestCase):
    """Build av: „Jetzt kann ich bei Tour auf ‚Fahren' klicken, dann erscheint die Live Karte
    und dort ist der Button ‚Fahrt starten' weiter grün. Ein Draufklicken bringt keine Änderung."

    Der Knopf war tatsächlich `disabled` – aber er blieb **grün** und zeigte `cursor: pointer`.
    Im Browser gemessen: gesperrt `rgb(25,135,84)` (dasselbe Grün wie aktiv), nur Deckkraft
    0,65; der erklärende Hinweis stand klein über der Karte, nicht am Knopf.

    Jetzt: bernsteinfarben `#D98E04`, Schloss-Symbol, Text „Fahren", `cursor: not-allowed`,
    und der Grund steht sofort in der Statuszeile (dort, wo alle Live-Meldungen stehen).
    """

    def _js(self):
        live = _live()
        return live.split('<script>', 1)[1]

    def test_gesperrt_ist_nicht_mehr_gruen(self):
        live = _live()
        # der Knopf bekommt bei Sperre eine eigene Klasse statt btn-success
        self.assertIn("{% if can_share %}btn-success{% else %}btn-fahrt-gesperrt{% endif %}", live)
        # und die Klasse ist sichtbar anders: bernstein, kein Hand-Cursor
        self.assertIn('#live-bar .btn-fahrt-gesperrt,', live)
        self.assertIn('background: #D98E04 !important;', live)
        self.assertIn('cursor: not-allowed;', live)

    def test_text_sagt_dass_es_nicht_geht(self):
        live = _live()
        # „Fahren" statt „Fahrt starten" – man sieht schon am Wort, dass es nicht losgeht
        self.assertIn('{% if can_share %}▶ Fahrt starten{% else %}', live)
        self.assertIn('</svg> Fahren{% endif %}</button>', live)

    def test_grund_steht_in_der_statuszeile(self):
        live = _live()
        self.assertIn('const SHARE_HINT = {{ share_hint|tojson }};', live)
        self.assertIn("if (!CAN_SHARE && SHARE_HINT) setStatus('🔒 ' + SHARE_HINT + "
                      "' Zuschauen geht jederzeit.', 'warning');", live)

    def test_kein_hinweisblock_ueber_der_karte(self):
        live = _live()
        # der alte Block ueber der Karte ist weg (er verdeckte beim Fahren genau den Blick)
        self.assertNotIn('id="share-hint"', live)
        self.assertNotIn('hat-hinweis', live)


class FahrtStartFunktioniertTest(unittest.TestCase):
    """Zweite Hälfte der Meldung: „Ein Draufklicken bringt keine Änderung."

    Bei erlaubtem Fahren muss der Klick wirklich etwas tun – `toggleShare()` →
    `startShare()` setzt `sharing`, tauscht den Knopf auf „⏹ Fahrt beenden" (rot) und
    aktiviert die Standortabfrage. Diese Kette wird hier festgehalten, damit ein
    gesperrter Knopf nicht versehentlich der einzige Zustand bleibt.
    """

    def test_klick_startet_die_fahrt(self):
        live = _live()
        self.assertIn('id="btn-share" onclick="toggleShare()"', live)
        self.assertIn('function toggleShare() { if (sharing) stopShare(false); else startShare(); }', live)
        # startShare setzt den Zustand und tauscht die Beschriftung
        block = live.split('function startShare()', 1)[1].split('function ensureWatch', 1)[0]
        self.assertIn('sharing = true;', block)
        self.assertIn('updateShareBtn();', block)
        self.assertIn('ensureWatch();', block)

    def test_knopf_wird_rot_und_beschriftet_um(self):
        live = _live()
        self.assertIn("b.textContent = sharing ? '⏹ Fahrt beenden' : '▶ Fahrt starten';", live)
        self.assertIn("b.classList.toggle('btn-success', !sharing);", live)
        self.assertIn("b.classList.toggle('btn-danger', sharing);", live)

    def test_gesperrter_knopf_bleibt_wirklich_stumm(self):
        live = _live()
        # doppelte Absicherung: auch wenn das disabled-Attribut fehlte, bricht startShare ab
        self.assertIn('if (!CAN_SHARE) return;', live)


class SkriptReihenfolgeTest(unittest.TestCase):
    """Build aw: „Der grüne Button Fahrt starten bleibt weiterhin grün nach Drücken.
    Es passiert nichts. Eine Meldung sehe ich auch nicht."

    Das war ein Fehler aus Build au, den ich selbst eingebaut hatte: `addTrails(TRAILS)`
    stand VOR `const trailKm` / `const SVG_RAD`. `addTrails()` ruft `updateTrailKm()` auf,
    das beide benutzt – bei `const` gilt die Temporal Dead Zone:

        ReferenceError: Cannot access 'trailKm' before initialization

    Damit brach das **gesamte** Skript ab, sobald Spurpunkte vorhanden waren (also nach dem
    ersten Fahren oder wenn jemand anderes gefahren war). Alles danach – `toggleShare`,
    `startShare`, `setLiveGuard`, sämtliche Klick-Handler – wurde nie registriert.
    Deshalb blieb der Knopf grün und nichts geschah.

    Warum es durchgerutscht ist: mein Test rief `addTrails()` nur mit **leerer** Spur auf;
    die Schleife lief nie, `updateTrailKm()` wurde nie erreicht. Im Browser mit vorhandenen
    Punkten schlug es sofort zu. Diese Klasse prüft jetzt beide Fälle.
    """

    def _js(self):
        live = _live()
        return live.split('<script>', 1)[1].split('</script>', 1)[0]

    @staticmethod
    def _zeile(js, muster):
        """Erste Zeile mit dem Muster – Kommentare zählen nicht mit."""
        for i, z in enumerate(js.split('\n')):
            if muster in z.split('//')[0]:
                return i
        return -1

    def test_km_logik_steht_vor_dem_ersten_addtrails(self):
        js = self._js()
        aufruf = self._zeile(js, 'addTrails(TRAILS)')
        trail_km = self._zeile(js, 'const trailKm')
        svg_rad = self._zeile(js, 'const SVG_RAD')
        self.assertGreater(aufruf, 0, 'addTrails(TRAILS) fehlt')
        self.assertGreater(trail_km, 0)
        self.assertGreater(svg_rad, 0)
        self.assertLess(trail_km, aufruf,
                        'const trailKm muss VOR addTrails(TRAILS) stehen (Temporal Dead Zone)')
        self.assertLess(svg_rad, aufruf,
                        'const SVG_RAD muss VOR addTrails(TRAILS) stehen (Temporal Dead Zone)')

    def test_update_trail_km_nutzt_beide_konstanten(self):
        js = self._js()
        block = js.split('function updateTrailKm()', 1)[1].split('\n}', 1)[0]
        # updateTrailKm() greift ueber trailStand() auf trailKm zu und setzt SVG_RAD ein
        self.assertIn('trailStand(', block)
        self.assertIn('SVG_RAD', block)
        stand = js.split('function trailStand(uid)', 1)[1].split('\n}', 1)[0]
        self.assertIn('trailKm[uid]', stand)
        # und addTrails ruft updateTrailKm auf -> genau diese Kette brach
        add = js.split('function addTrails(obj)', 1)[1].split('\n}', 1)[0]
        self.assertIn('updateTrailKm();', add)

    def test_km_konstanten_werden_nirgends_vorher_benutzt(self):
        """Gezielter Waechter statt Parser: die beiden Konstanten, die den Fehler ausloesten,
        duerfen VOR ihrer Definition im Code nicht vorkommen. Ein allgemeiner Parser ueber
        das ganze Skript verwechselt lokale Variablen in Funktionen mit globalen consts
        (gemessen: 5 Fehlalarme) - hier zaehlt nur der reale Fehlerfall.
        """
        import re
        js = self._js()
        for name in ('trailKm', 'SVG_RAD'):
            defn = self._zeile(js, 'const ' + name)
            self.assertGreater(defn, 0, f'const {name} fehlt')
            davor = js.split('\n')[:defn]
            treffer = [f'Zeile {i+1}: {z.strip()[:60]}'
                       for i, z in enumerate(davor)
                       if re.search(r'(?<![\w.])' + re.escape(name) + r'(?![\w:])', z.split('//')[0])]
            self.assertEqual(treffer, [], f'{name} wird vor seiner Definition benutzt: {treffer[:3]}')


class HinweisHalbtransparentTest(unittest.TestCase):
    """Build ax: „die Meldungen ‚Zum verschieben tippen' sind mir zu dunkel, könnten irgendwie
    halbtransparent sein auf allen Karten."

    Vorher: `rgba(20,30,60,.88)` – fast deckend, die Karte war darunter nicht mehr zu sehen.
    Im Browser gemessen: überall `rgba(20, 30, 60, 0.54)` plus `blur(3px)`, auf allen vier
    Karten (Startseite, Tourseite, Karten-Seite, Gastro) und auf der Live-Karte.
    """

    def _js(self):
        return open(os.path.join(ROOT, 'static', 'js', 'map-touch.js'), encoding='utf-8').read()

    def test_hinweis_der_anderen_karten_ist_halbtransparent(self):
        js = self._js()
        self.assertIn('background:rgba(20,30,60,.54);color:#fff;', js)
        self.assertIn('backdrop-filter:blur(3px)', js)
        # das alte, fast deckende Dunkelblau darf fuer den Hinweis nicht mehr auftauchen
        self.assertNotIn('background:rgba(20,30,60,.88);color:#fff;\' +\n      \'padding:.45rem', js)

    def test_live_pill_und_schloss_sind_halbtransparent(self):
        live = _live()
        self.assertIn('background: rgba(20, 30, 60, .54)', live)
        self.assertIn('backdrop-filter: blur(3px)', live)
        # Pill, Lock und der km-/Zeit-Chip – alle drei mit demselben halbtransparenten Grund
        self.assertEqual(live.count('background: rgba(20, 30, 60, .54)'), 3)

    def test_schloss_der_anderen_karten_auch(self):
        js = self._js()
        self.assertIn("'background:rgba(20,30,60,.54);color:#fff;border:1px solid rgba(255,255,255,.22);border-radius:20px;'", js)


class FahrzeitOhnePausenTest(unittest.TestCase):
    """Build ax: „Zusätzlich dazu auch noch die reine Fahrzeit ohne Pausen."

    Die Spur liefert Zeitstempel; `addTrails()` verwarf sie bisher. Jetzt werden sie in
    `trailPunkte` mitgeschrieben und ausgewertet: eine Lücke von mehr als 2 Minuten gilt als
    Pause und zählt nicht (gesendet wird alle 10–30 s, also reißt die Reihe nur beim Stehen).

    Im Browser gemessen: 20 Punkte im 20-s-Takt mit EINER 20-Minuten-Pause dazwischen
    (Gesamtspanne 1580 s) → **360 s Fahrzeit** (19 Abstände à 20 s, die Pause komplett raus).
    """

    def test_zeitstempel_werden_mitgeschrieben(self):
        live = _live()
        self.assertIn('const trailPunkte = {};', live)
        block = live.split('function addTrails(obj)', 1)[1].split('\nfunction ', 1)[0]
        self.assertIn('(trailPunkte[uid] = trailPunkte[uid] || []).push([p[2], p[0], p[1]]);', block)

    def test_pausen_werden_erkannt(self):
        live = _live()
        self.assertIn('const PAUSE_LUECKE_S = 120;', live)
        block = live.split('function fahrzeitSek(uid)', 1)[1].split('\nfunction ', 1)[0]
        self.assertIn('if (d > PAUSE_LUECKE_S) continue;', block)

    def test_dauer_kurz_formatiert(self):
        live = _live()
        self.assertIn("if (sek < 60) return Math.round(sek) + ' s';", live)
        self.assertIn("if (min < 60) return min + ' min';", live)
        self.assertIn("return Math.floor(min / 60) + ':' + String(min % 60).padStart(2, '0') + ' h';", live)

    def test_km_und_zeit_stehen_zusammen_unten_links(self):
        live = _live()
        # Build au hatte den Chip oben links (top: 82px) – jetzt unten links
        self.assertIn('#live-km { position: absolute; left: 8px; bottom: calc(', live)
        self.assertNotIn('#live-km { position: absolute; left: 10px; top: 82px;', live)
        # km und Fahrzeit in einem Chip
        block = live.split('function updateTrailKm()', 1)[1].split('\n}', 1)[0]
        self.assertIn('if (km >= 50) teile.push(SVG_RAD', block)
        self.assertIn('if (sek >= 60) teile.push(SVG_UHR', block)

    def test_uhr_ist_ein_svg_kein_emoji(self):
        live = _live()
        self.assertIn('const SVG_UHR =', live)
        self.assertNotIn("teile.push('⏱", live)
