# -*- coding: utf-8 -*-
"""Build 2026-11-07 ay – „Als GPX speichern": bei Mitgliedern blieb die Tour ohne Track.

Der Nutzer: „Checke die Funktion ‚Als GPX speichern'. Irgendwie wird bei mir anschließend kein
Track angezeigt." Nachgefragt: Knopf auf der Live-Karte nach „Fahrt beenden", kurze Fahrt mit
dem Handy, Datei in Ordnung – aber auf der Tourseite kein Track.

Gemessen (Mitglied, 45 Punkte, 1,9 km):
  Ausgangslage                    gpx_file=None      → Tourseite GPX_DATA=null, 0 Linien
  Mitglied lädt GPX herunter      gpx_file=None      → Tour bleibt ohne Track
  Übernehmen-Knopf für Mitglied   nicht vorhanden
  Nach dem Fix: Mitglied klickt „Meine Aufzeichnung als Track übernehmen"
                                  gpx_file=…, 1,9 km → Tourseite 2 Linien, 45 Punkte, Zoom 14
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*pfad):
    with open(os.path.join(ROOT, *pfad), encoding='utf-8') as f:
        return f.read()


class MitgliedDarfUebernehmenTest(unittest.TestCase):
    """Die Route darf jetzt auch ein Mitglied – aber nur für die EIGENE Aufzeichnung."""

    def test_route_erlaubt_eigene_aufzeichnung(self):
        app_py = _read('app.py')
        block = app_py.split("def tour_live_recording(tour_id):", 1)[1].split('\n@app.route', 1)[0]
        # Der alte Pauschal-Riegel (jeder Nicht-Manager -> 403) ist weg
        self.assertNotIn("    if not _can_manage_tour(tour):\n        abort(403)\n    summaries", block)
        # … und durch die Prüfung auf die eigene Aufzeichnung ersetzt
        self.assertIn("if not summary or summary['user_id'] != current_user.id:", block)
        self.assertIn('abort(403)', block)

    def test_fremde_aufzeichnung_bleibt_gesperrt(self):
        app_py = _read('app.py')
        block = app_py.split("def tour_live_recording(tour_id):", 1)[1].split('\n@app.route', 1)[0]
        # fremde Aufzeichnung: uid != current_user -> 403
        self.assertIn("summary['user_id'] != current_user.id", block)

    def test_vorhandener_track_wird_nicht_von_mitgliedern_ersetzt(self):
        app_py = _read('app.py')
        block = app_py.split("def tour_live_recording(tour_id):", 1)[1].split('\n@app.route', 1)[0]
        self.assertIn('if tour.gpx_file:', block)
        self.assertIn('hat schon einen GPX-Track', block)


class KnopfAufDerTourseiteTest(unittest.TestCase):
    """Ein Mitglied sah auf der Tourseite GAR KEINEN Übernehmen-Knopf – nur die Orga."""

    def test_mitglied_sieht_uebernehmen_knopf(self):
        html = _read('templates', 'touren', 'detail.html')
        self.assertIn('{% if can_manage or (live_rec_mine and not tour.gpx_file) %}', html)
        self.assertIn('Meine Aufzeichnung als Track übernehmen', html)

    def test_mitglied_schickt_eigene_user_id(self):
        html = _read('templates', 'touren', 'detail.html')
        block = html.split('Meine Aufzeichnung als Track übernehmen', 1)[0]
        self.assertIn('<input type="hidden" name="user_id" value="{{ current_user.id }}">', block)

    def test_orga_sieht_weiter_die_auswahl(self):
        html = _read('templates', 'touren', 'detail.html')
        self.assertIn('Als GPX-Track der Tour übernehmen', html)
        self.assertIn('<select name="user_id"', html)


class LiveKarteUebernehmenTest(unittest.TestCase):
    """Auf der Live-Karte gab es für Mitglieder nur „⬇ GPX speichern" – die Datei landete auf
    dem Handy, die Tour blieb ohne Track. Jetzt steht dort „✓ Als Track übernehmen"."""

    def test_live_karte_hat_uebernehmen_knopf(self):
        html = _read('templates', 'touren', 'live.html')
        self.assertIn('✓ Als Track übernehmen', html)
        # das Formular um den Knopf herum (nicht der Kommentar davor)
        block = html.split('<form method="post" action="{{ url_for(\'tour_live_recording\'', 1)[1]
        block = block.split('</form>', 1)[0]
        self.assertIn('name="action" value="adopt"', block)
        self.assertIn('name="user_id" value="{{ current_user.id }}"', block)
        self.assertIn('✓ Als Track übernehmen', block)

    def test_download_daneben_bleibt(self):
        html = _read('templates', 'touren', 'live.html')
        # wer die Datei will, bekommt sie weiter – aber nicht mehr als einzige Möglichkeit
        self.assertIn('⬇ GPX speichern', html)

    def test_uebernehmen_ist_kein_link_sondern_ein_formular(self):
        html = _read('templates', 'touren', 'live.html')
        block = html.split('id="rec-hint"', 1)[1].split('</form>', 1)[0]
        # ein echtes POST-Formular – kein Link auf die Tourseite (dort landete man ohne Track)
        self.assertIn('method="post"', block)
        self.assertIn("url_for('tour_live_recording'", block)


class DownloadFehlerTest(unittest.TestCase):
    """Vorher: 404 lieferte die HTML-Fehlerseite – der Browser speicherte sie trotzdem als
    „…_live_….gpx". Der Nutzer hielt eine kaputte Datei in der Hand, ohne Hinweis."""

    def test_keine_html_datei_als_gpx(self):
        app_py = _read('app.py')
        block = app_py.split("def tour_live_recording_download(tour_id):", 1)[1].split('\n@app.route', 1)[0]
        self.assertNotIn('abort(404)', block)
        self.assertIn('keine brauchbare Aufzeichnung', block)
        self.assertIn('flash(', block)

    def test_meldung_nennt_die_ursache(self):
        app_py = _read('app.py')
        block = app_py.split("def tour_live_recording_download(tour_id):", 1)[1].split('\n@app.route', 1)[0]
        # die zwei echten Ursachen: zu wenige Punkte, zu ungenaues GPS
        self.assertIn('mindestens 8 Punkte', block)
        self.assertIn('WLAN-Ortung', block)


if __name__ == '__main__':
    unittest.main()

class AuchAdminBrauchtEinenEchtenKnopfTest(unittest.TestCase):
    """Build ay, Nachtrag: „Ich hatte das vorher als Admin gemacht, nicht als Mitglied."

    Damit war die erste Erklärung unvollständig. Der Knopf, den ein ADMIN in Build ax sah,
    war ein LINK auf die Tourseite („✓ Als GPX übernehmen" -> /touren/1#live-aufzeichnung).
    Er hat nichts übernommen – er hat nur die Seite gewechselt. Die Strecke blieb weg, weil
    man auf der Tourseite noch einmal „Als GPX-Track der Tour übernehmen" drücken musste.

    Gemessen in Build ax (Admin, 45 Punkte, 1,9 km): nach dem Klick 0 Linien, GPX_DATA=null.
    Jetzt: ein POST-Formular, das direkt übernimmt – 2 Linien, 45 Punkte, Meldung sichtbar.
    """

    def test_uebernehmen_postet_direkt_statt_zu_verlinken(self):
        html = _read('templates', 'touren', 'live.html')
        block = html.split('id="rec-hint"', 1)[1].split('</form>', 1)[0]
        self.assertIn('<form method="post"', block)
        self.assertIn('name="action" value="adopt"', block)
        # der alte, folgenlose Link darf dort nicht mehr stehen
        self.assertNotIn("href=\"{{ url_for('tour_detail', tour_id=tour.id) }}#live-aufzeichnung\"", block)

    def test_admin_und_mitglied_bekommen_denselben_knopf(self):
        """Kein Unterschied mehr zwischen den Rollen – beide uebernehmen mit einem Klick."""
        html = _read('templates', 'touren', 'live.html')
        block = html.split('id="rec-hint"', 1)[1].split('</form>', 1)[0]
        self.assertNotIn('{% if can_takeover %}', block)
        self.assertIn('✓ Als Track übernehmen', block)

    def test_kein_link_ohne_wirkung_mehr_im_status(self):
        """Auch die Statusmeldung nach dem Beenden schickte nur auf die Tourseite."""
        html = _read('templates', 'touren', 'live.html')
        # der Status darf weiter auf die Tourseite hinweisen (dort steht die Aufzeichnung),
        # aber der KNOPF im Hinweis muss uebernehmen
        block = html.split('id="rec-hint"', 1)[1].split('</form>', 1)[0]
        self.assertIn('type="submit"', block)


if __name__ == "__main__":
    unittest.main()

class HinweisAuchImVollbildTest(unittest.TestCase):
    """Build ba: „Wenn in der Live Karte die große Kartendarstellung aktiv ist und die Fahrt
    beendet sieht man keinen Hinweis auf Track/GPX speichern."

    Der Hinweis stand AUSSERHALB von #live-wrap. Im Vollbild ist das aber
    `position: fixed; inset: 0` mit z-index 2000 und deckte ihn komplett ab.
    Gemessen vorher: `elementFromPoint` an der Stelle des Hinweises ergab „live-map",
    beide Knoepfe „nicht sichtbar". Jetzt gibt es eine zweite Kopie INNERHALB der Karte.
    Gemessen nachher: im Vollbild sichtbar und klickbar, ausserhalb unsichtbar – nie beide.
    """

    def test_zweite_kopie_liegt_in_der_karte(self):
        html = _read('templates', 'touren', 'live.html')
        i_wrap = html.find('<div id="live-wrap">')
        i_hint = html.find('id="rec-hint-fs"')
        i_end = html.find('id="live-bar"')
        self.assertGreater(i_wrap, 0)
        self.assertGreater(i_hint, i_wrap, 'Vollbild-Hinweis liegt nicht in #live-wrap')
        self.assertLess(i_hint, i_end)

    def test_kopie_hat_track_und_gpx_knopf(self):
        html = _read('templates', 'touren', 'live.html')
        block = html.split('id="rec-hint-fs"', 1)[1].split('</div>\n      </div>', 1)[0]
        self.assertIn('✓ Als Track übernehmen', block)
        self.assertIn('⬇ GPX speichern', block)
        self.assertIn('name="action" value="adopt"', block)

    def test_beide_kopien_werden_zusammen_geschaltet(self):
        html = _read('templates', 'touren', 'live.html')
        show = html.split('function showRecHint()', 1)[1].split('\nfunction ', 1)[0]
        hide = html.split('function hideRecHint()', 1)[1].split('\nfunction ', 1)[0]
        self.assertIn("getElementById('rec-hint-fs')", show)
        self.assertIn("getElementById('rec-hint-fs')", hide)

    def test_kein_scrollen_im_vollbild(self):
        """Im Vollbild waere scrollIntoView sinnlos – die Karte deckt alles ab.

        Build bd: Der Vollbild-Zweig endet jetzt frueher (er zeigt nur die Kopie in der
        Karte und kehrt zurueck), das scrollIntoView steht nur noch im Normal-Zweig.
        """
        html = _read('templates', 'touren', 'live.html')
        show = html.split('function showRecHint()', 1)[1].split('\nfunction ', 1)[0]
        vor_return, nach_return = show.split('return;', 1)
        self.assertIn('if (_fsAn())', vor_return)
        self.assertNotIn('scrollIntoView', vor_return)     # im Vollbild kein Scrollen
        self.assertIn('scrollIntoView', nach_return)       # draussen schon

    def test_hinweis_weicht_der_symbolspalte_rechts(self):
        """Gemessen: mit right:8px lag die Symbolspalte auf dem dritten Knopf."""
        html = _read('templates', 'touren', 'live.html')
        block = html.split('id="rec-hint-fs"', 1)[1].split('>', 1)[0]
        self.assertIn('right: 56px', block)


if __name__ == "__main__":
    unittest.main()

class VollbildKnoepfeWeiterUntenTest(unittest.TestCase):
    """Build bb: „Könnte man die Symbole und Knöpfe bei der Vollkarte weiter nach unten bringen?"

    Im Vollbild liegt die Karte über der unteren App-Navigation. Gemessen: bottom-nav
    NICHT sichtbar, `navUnten = 0` – trotzdem hielten Knopfleiste, Statuszeile, Pill und 🔒
    die 58 px für sie frei. Unter der Leiste blieb ein leerer Streifen von 58 px.

    Nach dem Umbau gemessen (460×900, Vollbild):
      Leiste     unten 0    (vorher 58)
      Status     unten 64   (vorher 122)
      Symbolspalte über der Statuszeile, keine Überlappung (vorher stieß sie an die Leiste)
    """

    def test_leiste_geht_im_vollbild_an_den_rand(self):
        html = _read('templates', 'touren', 'live.html')
        self.assertIn('#live-wrap.live-fs #live-bar { bottom: 0;', html)

    def test_statuszeile_und_pill_ruecken_mit(self):
        html = _read('templates', 'touren', 'live.html')
        self.assertIn('#live-wrap.live-fs #live-status { bottom: 64px; }', html)
        self.assertIn('#live-wrap.live-fs #live-guard-pill,\n    #live-wrap.live-fs #live-guard-lock', html)

    def test_symbolspalte_ueber_der_statuszeile(self):
        """5 Knöpfe à 42 px = 234 px. Ganz unten traf sie die Knopfleiste (gemessen)."""
        html = _read('templates', 'touren', 'live.html')
        block = html.split('#live-wrap.live-fs #live-tools {', 1)[1].split('}', 1)[0]
        self.assertIn('bottom: calc(64px + 3.1em + 8px)', block)

    def test_vollbild_hinweis_rueckt_mit(self):
        # Build bc: nicht mehr auf 64 px (dort lag er auf dem km-Chip), sondern ueber ihm
        html = _read('templates', 'touren', 'live.html')
        i = html.find('#live-wrap.live-fs #rec-hint-fs { bottom:')
        self.assertGreater(i, 0)
        block = html[i:].split('}', 1)[0]
        self.assertIn('calc(64px + 3.1em + 8px + 31px + 8px)', block)

    def test_normalbetrieb_bleibt_unveraendert(self):
        """Ausserhalb des Vollbilds liegt die App-Navigation unten – dort bleiben die 58 px."""
        html = _read('templates', 'touren', 'live.html')
        self.assertIn('bottom: calc(58px + env(safe-area-inset-bottom));', html)
        self.assertIn('#live-status { position: fixed; left: 8px; bottom: calc(58px + 64px);', html)


if __name__ == "__main__":
    unittest.main()

class KmChipWandertMitTest(unittest.TestCase):
    """Build bc: „dann sollte die Zeit und km Anzeige auch mitwandern nach unten"

    Der km-/Zeit-Chip hing im Vollbild an der Pill-Reihe: seine Formel zählte Pill (34 px) und
    🔒 (34 px) mit, obwohl beide im Vollbild gar nicht erscheinen. Gemessen stand er dadurch
    155 px über der Statuszeile (unten 188 statt 64).

    Beim Nachmessen fiel ein zweiter Fehler auf: `bottom: 128px` stand als INLINE-STYLE am
    Hinweis. Ein Inline-Style schlägt jedes Stylesheet – der Hinweis blieb im Vollbild auf
    128 px und lag auf dem Chip (Ueberlappung km/hint bei 460x972, 390x844 und 360x740).
    """

    def test_chip_rechnet_nicht_mehr_mit_unsichtbaren_elementen(self):
        html = _read('templates', 'touren', 'live.html')
        block = html.split('#live-wrap.live-fs #live-km {', 1)[1].split('}', 1)[0]
        self.assertIn('calc(64px + 3.1em + 8px)', block)
        # die alten 34-px-Posten (Pill + Schloss) duerfen nicht mehr drin sein
        self.assertNotIn('34px', block)

    def test_chip_steht_ueber_der_statuszeile(self):
        """Gemessen 460x972: Status unten 64, Chip unten 113, Abstand 8 px."""
        html = _read('templates', 'touren', 'live.html')
        block = html.split('#live-wrap.live-fs #live-km {', 1)[1].split('}', 1)[0]
        self.assertIn('3.1em', block)      # Statuszeilen-Hoehe

    def test_hinweis_ueber_dem_chip(self):
        html = _read('templates', 'touren', 'live.html')
        i = html.find('#live-wrap.live-fs #rec-hint-fs { bottom:')
        self.assertGreater(i, 0)
        block = html[i:].split('}', 1)[0]
        self.assertIn('31px', block)       # Chip-Hoehe

    def test_kein_inline_bottom_mehr_am_hinweis(self):
        """Genau daran scheiterte die erste Korrektur: Inline-Style gewinnt immer."""
        html = _read('templates', 'touren', 'live.html')
        tag = html.split('id="rec-hint-fs"', 1)[1].split('>', 1)[0]
        self.assertNotIn('bottom:', tag)
        # die Basis-Lage kommt aus dem Stylesheet
        self.assertIn('bottom: 128px', html)   # Basis-Lage (seit Build bd mit display:none davor)


if __name__ == "__main__":
    unittest.main()

class HinweisNichtDoppeltTest(unittest.TestCase):
    """Build bd: „Die Abfrage 'Als Track übernehmen' erscheint doppelt in der normalen
    Kartenansicht in der Live Karte."

    Ursache: showRecHint() nahm `d-none` von BEIDEN Kopien. Die Kopie fuer das Vollbild
    steht in #live-wrap und war ausserhalb des Vollbilds ein normaler Block im Fluss –
    sie erschien unter der Karte ein zweites Mal. Am Bildschirm gemessen stand sie mit
    `un: -78` sogar unter dem Fensterrand.

    Gemessen nach dem Fix (460x972):
      Normalbetrieb: sichtbare „Als Track übernehmen"-Knoepfe = 1 (in #rec-hint)
      Vollbild:      = 1 (in #rec-hint-fs)
      nach „Später": = 0, und das bleibt auch beim Umschalten so
    """

    def test_kopie_ist_ausserhalb_des_vollbilds_ausgeblendet(self):
        html = _read('templates', 'touren', 'live.html')
        self.assertIn('#rec-hint-fs { display: none; bottom: 128px; }', html)
        self.assertIn('#live-wrap.live-fs #rec-hint-fs { display: block; }', html)

    def test_show_zeigt_nur_die_passende_kopie(self):
        html = _read('templates', 'touren', 'live.html')
        show = html.split('function showRecHint()', 1)[1].split('\nfunction ', 1)[0]
        fs_zweig, rest = show.split("if (_fsAn()) {", 1)
        fs_inhalt = rest.split('return;', 1)[0]
        # im Vollbild: aeussere Kopie zu, innere auf
        self.assertIn("el.classList.add('d-none')", fs_inhalt)
        self.assertIn("fs.classList.remove('d-none')", fs_inhalt)
        # draussen: innere Kopie zu, aeussere auf
        self.assertIn("fs.classList.add('d-none')", rest)
        self.assertIn("el.classList.remove('d-none')", rest)

    def test_umschalten_haengt_die_rueckfrage_mit_um(self):
        """Ohne das zeigte nach dem Moduswechsel KEINE Kopie mehr (gemessen)."""
        html = _read('templates', 'touren', 'live.html')
        fs_fn = html.split('function toggleFs()', 1)[1].split('\nfunction ', 1)[0]
        self.assertIn('if (recHintOffen) showRecHint();', fs_fn)

    def test_spaeter_raeumt_beide_und_bleibt_weg(self):
        html = _read('templates', 'touren', 'live.html')
        hide = html.split('function hideRecHint()', 1)[1].split('\nfunction ', 1)[0]
        self.assertIn('recHintOffen = false;', hide)
        self.assertIn("el.classList.add('d-none')", hide)
        self.assertIn("fs.classList.add('d-none')", hide)


if __name__ == "__main__":
    unittest.main()

class SpaeterErklaertTest(unittest.TestCase):
    """Build be: „Man weiß gar nicht genau was mit 'Später' gemeint ist. Und wie man das wie und
    wo aufruft."

    Gemessen vorher: der Knopf hiess nur „Später" (ohne title), und im Hinweis stand kein Wort
    darueber, dass die Aufzeichnung auf der Tourseite im Abschnitt „Live-Aufzeichnung" wartet.
    Den gibt es wirklich – gemessen auf /touren/1 mit den Knoepfen
    „Als GPX-Track der Tour übernehmen" / „⬇ GPX" / „Meine Aufzeichnung löschen".

    Gemessen nachher: Klick auf „Zur Tourseite" landet auf /touren/1#live-aufzeichnung,
    der Abschnitt steht bei top=0 im Bild.
    """

    def test_knopf_sagt_was_er_tut(self):
        html = _read('templates', 'touren', 'live.html')
        self.assertEqual(html.count('Später entscheiden'), 2)      # beide Kopien
        self.assertNotIn('onclick="hideRecHint()">Später<', html)

    def test_knopf_hat_erklaerung(self):
        html = _read('templates', 'touren', 'live.html')
        i = html.find('Später entscheiden')
        block = html[max(0, i-400):i]
        self.assertIn('title="Blendet diese Abfrage aus', block)

    @staticmethod
    def _block(html, marke, ende):
        i = html.find(marke)
        j = html.find(ende, i)
        assert i > 0 and j > i, f'Block {marke} nicht gefunden'
        return html[i:j]

    def test_erklaerung_nennt_den_ort(self):
        html = _read('templates', 'touren', 'live.html')
        aussen = self._block(html, 'id="rec-hint"', '<div class="row g-3">')
        innen = self._block(html, 'id="rec-hint-fs"', 'id="live-bar"')
        for name, block in (('aussen', aussen), ('Vollbild', innen)):
            self.assertIn('Tourseite', block, f'{name}: Ort fehlt')
            self.assertIn('Live-Aufzeichnung', block, f'{name}: Abschnitt fehlt')
        self.assertIn('nichts geht verloren', aussen)

    def test_link_springt_in_den_abschnitt(self):
        html = _read('templates', 'touren', 'live.html')
        aussen = self._block(html, 'id="rec-hint"', '<div class="row g-3">')
        self.assertIn("#live-aufzeichnung", aussen)
        self.assertIn('Zur Tourseite', aussen)

    def test_abschnitt_existiert_wirklich(self):
        """Der Ort, auf den verwiesen wird, muss es auch geben."""
        detail = _read('templates', 'touren', 'detail.html')
        self.assertIn('id="live-aufzeichnung"', detail)
        self.assertIn('Live-Aufzeichnung', detail)


if __name__ == "__main__":
    unittest.main()

class RecInfoAufklapperTest(unittest.TestCase):
    """Build bg: Erklärung hinter einem ⓘ, das erst auf Tippen aufklappt.

    Vorher stand die ganze Erklärung offen – gemessen war der Hinweis dadurch
    328–367 px hoch (normal) bzw. 286 px (Vollbild) und schob die Karte zusammen.

    Gemessen nachher (460x972 / 390x844 / 360x740):
      normal: 298 / 357 / 418 px zugeklappt, +85/+104/+123 px aufgeklappt
      Vollbild 460x972: 214 -> 279 px; 360x740: 224 -> 348 px
    """

    def test_beide_kopien_haben_den_aufklapper(self):
        html = _read('templates', 'touren', 'live.html')
        self.assertEqual(html.count('class="rec-info-btn"'), 2)
        self.assertIn("toggleRecInfo(this, 'rec-info-text')", html)
        self.assertIn("toggleRecInfo(this, 'rec-info-fs-text')", html)

    def test_startet_zugeklappt_und_sagt_es_an(self):
        html = _read('templates', 'touren', 'live.html')
        i = html.find('class="rec-info-btn"')
        block = html[i:i+400]
        self.assertIn('aria-expanded="false"', block)
        self.assertIn('aria-controls="rec-info-text"', block)
        self.assertIn('class="rec-info d-none"', html)

    def test_js_klappt_um_und_pflegt_aria(self):
        html = _read('templates', 'touren', 'live.html')
        fn = html.split('function toggleRecInfo(btn, id)', 1)[1].split('\n}', 1)[0]
        self.assertIn("classList.toggle('d-none')", fn)
        self.assertIn("setAttribute('aria-expanded'", fn)

    def test_kern_bleibt_offen_sichtbar(self):
        """Der Nutzer soll ohne Tippen sehen: nichts geht verloren."""
        html = _read('templates', 'touren', 'live.html')
        ausserhalb_des_aufklappers = html.split('class="rec-info d-none"')[0]
        self.assertIn('nichts geht verloren', ausserhalb_des_aufklappers)

    def test_erklaerung_nennt_die_tage(self):
        """Die Zahl „30 Tage" steht jetzt im Aufklapp-Text – sie muss bleiben."""
        html = _read('templates', 'touren', 'live.html')
        # die Tagesangabe steht im Fliesstext ueber dem Aufklapper (aussen)
        i, j = html.find('id="rec-hint"'), html.find('<div class="row g-3">')
        self.assertGreater(i, 0); self.assertGreater(j, i)
        self.assertIn('{{ keep_days }}', html[i:j])

    def test_symbolspalte_ueberlappt_den_hinweis_nicht(self):
        """Gemessen 360x740: Symbolspalte 310..352 lag auf dem Text des Hinweises (12..348).

        Behoben über den rechten Rand des Hinweises (`margin-right: 48px`), nicht über die
        Symbolspalte – ein Versuch mit zweispaltiger Spalte hat es im Vollbild schlimmer
        gemacht und wurde verworfen.
        """
        html = _read('templates', 'touren', 'live.html')
        i = html.find('#rec-hint { margin-right: 48px; }')
        self.assertGreater(i, 0, 'Breiten-Fix fehlt')
        block = html[max(0, i-200):i+100]
        self.assertIn('@media (max-width: 575px)', block)
        # nicht wieder die zweispaltige Spalte einbauen
        self.assertNotIn('body.rec-hint-an #live-tools', html)


if __name__ == "__main__":
    unittest.main()

class TourTitelIstLinkTest(unittest.TestCase):
    """Build bh: „Wenn man auf den Titel klickt, soll man auch in die Details kommen."

    Gemessen vorher (/touren, 460x972): Der Titel war ein `<span class="fw-semibold">`
    ohne Link, `cursor: auto`, ein Tipp änderte die URL nicht.
    Gemessen nachher: `a.tour-titel-link`, `cursor: pointer`, Klick führt auf /touren/<id>.

    Betroffen waren drei Stellen in der Liste (Karte mit Foto, Karte ohne Foto,
    Archiv-Karte) plus die Übersicht der geplanten Touren.
    """

    def test_liste_titel_ist_ein_link(self):
        html = _read('templates', 'touren', 'list.html')
        # drei Titel sind jetzt Links (Foto-Karte, Karte ohne Foto, Archiv-Karte)
        self.assertEqual(html.count('{{ t.title }}</a>'), 3)
        # kein alter, nicht klickbarer Titel mehr
        self.assertNotIn('<span class="fw-semibold" style="font-size:.92rem;color:var(--djo-navy)">{{ t.title }}</span>', html)
        self.assertNotIn('<span class="text-white fw-bold" style="font-size:.92rem;line-height:1.3">{{ t.title }}</span>', html)

    def test_geplante_titel_ist_ein_link(self):
        html = _read('templates', 'touren', 'geplant.html')
        self.assertIn('tour-titel-link', html)
        self.assertIn("url_for('tour_detail', tour_id=t.id)", html)

    def test_titel_link_sieht_nicht_wie_ein_blauer_link_aus(self):
        """Der Titel soll aussehen wie vorher – nur klickbar."""
        html = _read('templates', 'touren', 'list.html')
        i = html.find('class="fw-semibold text-decoration-none tour-titel-link"')
        self.assertGreater(i, 0, 'Titel-Link ohne text-decoration-none')
        block = html[i:i+200]
        self.assertIn('color:var(--djo-navy)', block)     # dieselbe Farbe wie vorher


if __name__ == "__main__":
    unittest.main()

class KartenhinweiseBleibenInDerKarteTest(unittest.TestCase):
    """Build bi: „Wenn ich scrolle, verschiebt sich die Karte, aber ‚Zum Verschieben antippen'
    bleibt unten. Die Zeitanzeige ist auch nicht optimal positioniert."

    Gemessen vorher (460x972): Karte wanderte beim Scrollen von oben 144 auf -56 (200 px),
    die Pill blieb bei 774 stehen (`position: fixed`) – sie hing am FENSTER, nicht an der Karte.
    Der km/Zeit-Chip hing an einer eigenen, fensterbezogenen Leiter (204 px) und riss dadurch
    von der Pill ab.

    Gemessen nachher: Pill `absolute` in #live-wrap, 164 px über der Kartenunterkante;
    Chip 206 px (= 164 + 34 Pill + 8) – Abstand exakt 8.00 px, Verschiebung beim Scrollen
    bei Karte UND Pill exakt 200 px.
    """

    def test_pill_haengt_an_der_karte_nicht_am_fenster(self):
        html = _read('templates', 'touren', 'live.html')
        i = html.find('#live-guard-pill, #live-guard-lock { position: absolute; bottom: 164px; }')
        self.assertGreater(i, 0, 'Pill sitzt nicht mehr an der Karte')
        # die alte, fensterfeste Lage darf nicht zurueckkommen
        self.assertNotIn('position: fixed; bottom: calc(58px + 64px + 34px + 8px)', html)

    def test_chip_steht_direkt_ueber_der_pill(self):
        """164 (Pill) + 34 (Pillhoehe) + 8 (Abstand) = 206."""
        html = _read('templates', 'touren', 'live.html')
        self.assertIn('#live-km { position: absolute; left: 8px; bottom: 206px;', html)

    def test_chip_haengt_nicht_mehr_an_der_fensterleiter(self):
        """Die alte Formel zaehlte Leiste (58), Status (64), Pill (34) und Abstaende mit."""
        html = _read('templates', 'touren', 'live.html')
        self.assertNotIn('bottom: calc(58px + 64px + 34px + 8px + 40px)', html)

    def test_vollbild_lage_unveraendert(self):
        """Im Vollbild gilt weiter die eigene Kante (ueber Statuszeile + Chip)."""
        html = _read('templates', 'touren', 'live.html')
        self.assertIn('#live-wrap.live-fs #live-km { bottom: calc(64px + 3.1em + 8px); }', html)


if __name__ == "__main__":
    unittest.main()
