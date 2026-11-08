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
