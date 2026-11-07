"""Build aa: Live-Karte – die Karte bekommt den Bildschirm.

Aus dem Screenshot vom 2026-11-07: „Vom Wichtigsten, der Karte, kann man fast nichts mehr
sehen. Die Knöpfe nehmen viel zu viel Platz ein."

Drei Ursachen, drei Änderungen:
  1. Über der Karte standen vier Blöcke (Zurück-Link, Titel, Datum, Hinweise, Status) – über
     300 px. Jetzt EINE Titelzeile (Zurück · Titel · ℹ️); Datum und Hinweise stecken im ℹ️,
     der Status ist ein Chip AUF der Karte.
  2. Unter der Karte lagen fünf Reihen Knöpfe (≈ 200 px). Jetzt nur noch die drei wichtigen
     groß (Fahrt/Weiter · Pause · Foto, 58 px hoch); Folgen/Alle/Vollbild/Bildschirm/Stromspar
     sind kleine Symbole auf der Karte.
  3. Symbole als Inline-SVG statt Bootstrap-Icons: unterwegs (kein Netz zum CDN) bleiben die
     Schrift-Icons sonst leere Kästchen.
"""
import os
import re
import unittest

from tests.base import AppTestCase, ROOT


class LiveKopfUndLeisteTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.login_org()
        self.html = self.get_html('/touren/%d/live' % self.t_plan_id)

    # ── 1. Kopf: eine Zeile ──────────────────────────────────────────────────────────────
    def test_kopf_ist_eine_zeile(self):
        h = self.html
        self.assertIn('id="live-head"', h)
        self.assertIn('class="lh-back"', h)                     # Zurück als Symbol
        self.assertIn('class="lh-title"', h)                    # Titel, einzeilig mit Ellipse
        self.assertIn('id="live-info-btn"', h)                  # ℹ️ öffnet Details
        # Datum/Treffpunkt und Hinweise stecken im selben Aufklapper
        self.assertIn('id="live-details"', h)
        self.assertIn('class="lh-when"', h)
        self.assertNotIn('📍 Live-Karte: {{ tour.title }}</h2>', h)   # kein h2-Block mehr

    def test_hinweise_weiterhin_vorhanden(self):
        """Die Hinweise dürfen nicht verschwinden – nur woanders liegen (Build e bleibt)."""
        for text in ('👀 Zuschauen &amp; Fahren:', '⏸ Pause:', '📝 Aufzeichnung:', '📷 Foto:'):
            self.assertIn(text, self.html)

    def test_status_liegt_auf_der_karte(self):
        h = self.html
        self.assertIn('id="live-status"', h)
        self.assertIn('max-height: 3.1em', h)                   # zwei Zeilen, antippbar
        self.assertIn('#live-status.open { max-height: 12em;', h)
        # Auf dem Handy hängt der Chip am Fenster (die Leiste ist dort fixed)
        self.assertIn('@media (max-width: 991.98px) {\n    #live-status { position: fixed;', h)

    # ── 2. Leiste: drei große Knöpfe, Rest als Symbole auf der Karte ─────────────────────
    def test_drei_grosse_hauptknoepfe(self):
        h = self.html
        self.assertIn('id="btn-share"', h)
        self.assertIn('id="btn-pause"', h)
        self.assertIn('id="btn-photo"', h)
        self.assertIn('min-height: 46px', h)                    # Build ab: kleiner, aber daumenfreundlich
        self.assertIn('#live-bar #btn-share { flex: 2.2 1 0; }', h)

    def test_sekundaere_sind_symbole_auf_der_karte(self):
        h = self.html
        self.assertIn('id="live-tools"', h)
        for bid in ('btn-follow', 'btn-all', 'btn-fs', 'btn-wake', 'btn-saver'):
            self.assertIn('class="lt-btn" id="%s"' % bid, h, f'{bid} fehlt')
        self.assertIn('#live-bar .lb-sec  { display: none; }', h)   # keine zweite Knopfreihe
        self.assertIn('#live-tools .lt-btn { width: 42px; height: 42px;', h)

    def test_symbole_ohne_icon_font(self):
        """Unterwegs ohne Netz lädt Bootstrap Icons nicht – die Symbole müssen trotzdem da sein."""
        h = self.html
        self.assertIn('<svg viewBox="0 0 24 24"', h)
        self.assertNotIn('<i class="bi bi-crosshair"></i>', h)
        self.assertNotIn('<i class="bi bi-people-fill"></i>', h)
        self.assertNotIn('<i class="bi bi-brightness-high"></i>', h)

    def test_symbole_nennen_ihren_namen(self):
        h = self.html
        self.assertIn("const TOOL_NAMES = { 'btn-follow': 'Folgen'", h)   # Einblendung beim Tippen
        for aria in ('aria-label="Folgen"', 'aria-label="Alle anzeigen"',
                     'aria-label="Vollbild"', 'aria-label="Bildschirm an"', 'aria-label="Stromspar"'):
            self.assertIn(aria, h)

    def test_karte_bekommt_den_platz(self):
        h = self.html
        self.assertIn('#live-map  { height: calc(100vh - 205px); min-height: 330px; }', h)
        self.assertIn('#live-map { height: calc(100vh - 168px); }', h)      # sehr schmal
        self.assertIn('html body { padding-bottom: calc(106px', h)          # flache Leiste

    def test_zustaende_der_symbole(self):
        h = self.html
        self.assertIn("b.classList.toggle('on', following);", h)
        self.assertIn("b.classList.toggle('on', wakeWanted && wakeActive());", h)
        self.assertIn("b.classList.toggle('warn', wakeWanted && !wakeActive());", h)
        # Build ap: Im Vollbild keine ✕ mehr (sah nach „beenden" aus), sondern Pfeile nach innen.
        self.assertIn("fsIco.innerHTML = on ? SVG_FS_AUS : SVG_FS;", h)


class WakeLockMitVideoErsatzTest(AppTestCase):
    """Build ab: „Bildschirm bleibt an funktioniert nicht" – auf dem S23 und im Browser.

    Ursache: Der Wake-Lock ist eine *Berechtigung* des Browsers. Verweigert er sie
    (Energiesparmodus, Akku schwach, Richtlinie, http statt https), blieb nur die ehrliche
    Fehlermeldung. Jetzt gibt es einen zweiten Weg: ein stilles Endlos-Video (641 Byte,
    im HTML eingebettet) hält den Bildschirm genauso wach – das ist der klassische
    Ausweg, den auch NoSleep.js geht.
    """

    def setUp(self):
        super().setUp()
        self.login_org()
        self.html = self.get_html('/touren/%d/live' % self.t_plan_id)

    def test_video_eingebettet_ohne_netz(self):
        h = self.html
        self.assertIn('const NOSLEEP_WEBM = \'data:video/webm;base64,', h)
        self.assertIn('wakeVideo', h)
        # kein Nachladen von außen
        self.assertNotIn('nosleep.js', h.lower())

    def test_zwei_wege_und_ehrlicher_zustand(self):
        h = self.html
        # Build ac: nur ein WIRKLICH laufendes Video zählt (nicht bloß ein Flag)
        self.assertIn('function videoRunning() { return !!(wakeVideo && wakeVideoOn && !wakeVideo.paused', h)
        self.assertIn('function wakeActive() { return wakeHeld() || videoRunning(); }', h)
        self.assertIn('function setFallback(on)', h)
        self.assertIn('function tryVideoAgain()', h)

    def test_api_fehler_faellt_auf_video_zurueck(self):
        h = self.html
        # nach dem catch der API wird der Video-Weg versucht
        self.assertIn('const ok2 = setFallback(true);', h)
        self.assertIn('wakeErr = wakeSupported() ? (wakeErr + \'-video\') : \'video\';', h)

    def test_ausserten_ausschalten_stoppt_beide(self):
        self.assertIn("""function releaseWakeLock() {
  if (wakeLock) { wakeLock.release().catch(() => {}); wakeLock = null; }
  setFallback(false);
}""", self.html)

    def test_video_wird_beim_wechsel_erneuert(self):
        h = self.html
        self.assertIn('if (wakeVideoOn && wakeVideo && wakeVideo.paused) tryVideoAgain();', h)
        self.assertIn('if (wakeWanted && wakeVideoOn && wakeVideo && wakeVideo.paused) tryVideoAgain();', h)

    def test_waechter_prueft_beide_wege(self):
        self.assertIn('if (wakeWanted && !wakeActive()) requestWakeLock();', self.html)

    def test_kartenstil_knopf_ist_auf_der_live_karte_ein_symbol(self):
        """Build ab: oben rechts sitzt der Stil-Knopf als 42-px-Quadrat, damit er nicht
        mit Lizenzhinweis/Symbolspalte kollidiert – der Hinweis rückt ein Stück nach links."""
        h = self.html
        self.assertIn('data-map-style-compact="1"', h)
        self.assertIn('#live-map .leaflet-control-attribution { margin-right: 50px !important; }', h)


class WakeLockTonspurTest(AppTestCase):
    """Build ac: „Bildschirm bleibt an funktioniert immer noch nicht."

    Zwei Fehler gefunden und behoben:
      1. Das Ersatz-Video aus Build ab war STUMM (kein `muted`-Attribut nötig, aber auch keine
         Tonspur). Ein stummes Video hält den Bildschirm NICHT wach – das ist die Regel, die
         auch NoSleep.js befolgt: dort steckt eine Vorbis-/AAC-Tonspur drin.
      2. `wakeActive()` prüfte nur ein Flag. Stand das Video (Autoplay-Sperre), behauptete die
         Seite trotzdem „Bildschirm bleibt an". Jetzt zählt nur, was nachweislich läuft.
    """

    def setUp(self):
        super().setUp()
        self.login_org()
        self.html = self.get_html('/touren/%d/live' % self.t_plan_id)

    def test_video_hat_tonspur(self):
        """Das eingebettete WebM ist nicht stumm – sonst hält es den Bildschirm nicht wach."""
        h = self.html
        self.assertIn("base64,", h)
        self.assertNotIn("wakeVideo.muted = true", h)
        self.assertNotIn("wakeVideo.setAttribute('muted'", h)
        self.assertIn("wakeVideo.volume = 0.02;", h)      # unhörbar, aber nicht stumm
        # das Video ist deutlich größer als das stumme aus Build ab (641 Byte)
        import re
        m = re.search(r"const NOSLEEP_WEBM = 'data:video/webm;base64,([^']+)'", h)
        self.assertIsNotNone(m)
        self.assertGreater(len(m.group(1)), 3000)

    def test_kein_falsches_versprechen(self):
        h = self.html
        self.assertIn('function videoRunning()', h)
        self.assertIn('wakeVideo.readyState >= 2', h)
        # Build ad: Die Warnung nennt jetzt den konkreten Grund und steht auch an der Knopfleiste.
        self.assertIn("barHinweis('⚠️ Bildschirm wachhalten greift hier nicht", h)
        self.assertIn('Bildschirm wachhalten greift hier nicht', h)

    def test_fehlertext_nennt_video_probleme(self):
        h = self.html
        self.assertIn("das Ersatz-Video wird blockiert (Code ' + wakeVideo.error.code", h)
        self.assertIn("das Ersatz-Video startet nicht (Autoplay gesperrt)", h)


class LiveKarteImBrowserTest(AppTestCase):
    """Platzverhältnisse im gerenderten HTML (ohne Browser messbar: Höhen stehen im CSS)."""

    def test_kopf_und_leiste_klein(self):
        self.login_org()
        html = self.get_html('/touren/%d/live' % self.t_plan_id)
        css = re.search(r'<style>(.*?)</style>', html, re.S).group(1)
        # Kopfzeile: feste 38-px-Knöpfe, eine Zeile
        self.assertIn('#live-head { display: flex; align-items: center; gap: .5rem;', css)
        self.assertIn('width: 38px; height: 38px;', css)
        # Leiste auf dem Handy: nur eine Reihe
        self.assertIn('#live-bar .lb-main { display: flex; gap: 6px; }', css)
        self.assertIn('#live-bar .lb-sec  { display: none; }', css)


class DruckUndDesktopUnveraendertTest(AppTestCase):
    def test_desktop_zeigt_weiterhin_die_leiste(self):
        """Ab 992 px ist die Leiste nicht fixed – dort bleibt alles wie vorher (volle Breite)."""
        self.login_org()
        html = self.get_html('/touren/%d/live' % self.t_plan_id)
        self.assertIn('#live-bar .lb-main, #live-bar .lb-sec { display: contents; }', html)

    def test_vollbild_bleibt(self):
        self.login_org()
        html = self.get_html('/touren/%d/live' % self.t_plan_id)
        self.assertIn('#live-wrap.live-fs { position: fixed; inset: 0;', html)
        self.assertIn('id="btn-fs"', html)


if __name__ == '__main__':
    unittest.main()
