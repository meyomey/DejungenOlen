"""Build bv: Nachgesendete Punkte gingen verloren – die Spur war halb so lang wie die Fahrt.

Der Nutzer nach Build bu: „Eigentlich war die Strecke heute ungefähr 40 km lang" – aufgezeichnet
waren **19,3 km** bei 6:36 h. Dazu: „Größtenteils war der Stromsparmodus an und auch öfter
Display aus."

**Ursache.** Der Client sichert jeden Punkt lokal (`gesichert`), weil das Display ausgehen darf.
Beim Nachsenden schickte er aber **keinen Zeitstempel** mit:

    body: {tour_id, lat, lng, accuracy, speed, heading, paused, resume, since}

Der Server setzte die **Ankunftszeit** ein. Damit passierten drei Dinge auf einmal:

1. **Der 3-s-Filter warf fast alles weg.** 200 gesicherte Punkte kamen innerhalb von 2 s an –
   alle mit fast derselben Zeit. Nur der erste überlebte: gemessen **1 von 5**, bei 200 Punkten
   **1 von 200**.
2. **Die 90-km/h-Prüfung rechnete mit der falschen Zeit.** Ein Punkt von vor 3 Minuten wurde
   gegen „jetzt" geprüft: 5,5 km in 180 s = 110 km/h statt 5,5 km in 6 s = 3 300 km/h.
3. **Die Aufnahmezeiten waren verfälscht** – Zeitfenster, Fahrzeit und GPX-Zeitstempel.

Die verlorenen Punkte wurden auf der Karte mit **Geraden** überbrückt: Das Dreieck im
Screenshot 18 waren keine Kurven, sondern fehlende Abschnitte.

**Behoben (Build bv):**
1. Der Client schickt `at` (Aufnahmezeit in ms) mit – im Normalversand und beim Nachsenden.
   Der Server übernimmt sie, wenn sie plausibel ist (nicht aus der Zukunft, nicht älter als 6 h).
2. Nachsenden läuft nur noch einmal zur Zeit (`nachsendenLaeuft`), in 60er-Blöcken und nach
   Aufnahmezeit sortiert. Vorher konnte es doppelt starten (Wächter + Sichtbarwerden) und
   schickte denselben Punkt zweimal.
3. Der Puffer fasst 1 200 statt 200 Punkte (2 h Sparmodus statt 20 min).
4. Ein GPS-Aussetzer wird im Client **übersprungen**, ohne die nächste Sendung zu blockieren.
5. Die 8-Stunden-Grenze warnt jetzt 30 Minuten vorher und erklärt danach, wie es weitergeht.
"""
import datetime as dt
import os
import unittest

from tests.base import AppTestCase, ROOT, app, appmod, db
import models as M

LIVE = os.path.join(ROOT, 'templates', 'touren', 'live.html')
APP = os.path.join(ROOT, 'app.py')


def _live():
    with open(LIVE, encoding='utf-8') as f:
        return f.read()


def _app():
    with open(APP, encoding='utf-8') as f:
        return f.read()


class AufnahmezeitTest(AppTestCase):
    """Punkt 1: Der Zeitstempel der Aufnahme muss beim Server ankommen."""

    def test_client_schickt_at_im_normalversand(self):
        js = _live()
        self.assertIn('at: punkt.at', js, 'Normalversand muss die Aufnahmezeit mitschicken')

    def test_client_schickt_at_beim_nachsenden(self):
        js = _live()
        self.assertIn('at: g.at', js, 'Nachsenden muss die Aufnahmezeit mitschicken')

    def test_server_liest_at(self):
        py = _app()
        self.assertIn("at = data.get('at')", py)
        self.assertIn('Build bv: Aufnahmezeit', py)

    def test_server_prueft_die_zeit_auf_plausibilitaet(self):
        """Eine Zeit aus der Zukunft oder von vor drei Tagen darf nicht übernommen werden."""
        py = _app()
        self.assertIn('t_client <= now + timedelta(minutes=2)', py)
        self.assertIn('t_client >= now - timedelta(hours=6)', py)

    def test_nachsenden_setzt_echte_zeiten(self):
        """Gegenprobe am echten _live_track_add: 200 Punkte einer Stunde überleben."""
        with app.app_context():
            u = M.User(email='bv1@t.de', name='BV')
            u.set_password('x')
            db.session.add(u)
            db.session.commit()
            t = M.Tour(title='BV-Nachsenden', status='planned',
                       tour_date=dt.date(2026, 11, 9), created_by=u.id)
            db.session.add(t)
            db.session.commit()

            jetzt = dt.datetime.utcnow()
            start = jetzt - dt.timedelta(hours=1)
            n_ok = 0
            for i in range(200):
                at = start + dt.timedelta(seconds=i * 6)          # echte Aufnahmezeit
                if appmod._live_track_add(t.id, u.id, 53.55 + i * 30 / 111320.0, 9.98, 8.0, at):
                    n_ok += 1
            db.session.commit()
            self.assertEqual(n_ok, 200, 'nachgesendete Punkte muessen alle ankommen')

            rows = (M.LiveTrackPoint.query.filter_by(tour_id=t.id)
                    .order_by(M.LiveTrackPoint.id).all())
            dauer = (rows[-1].recorded_at - rows[0].recorded_at).total_seconds()
            self.assertAlmostEqual(dauer, 6 * 199, delta=2,
                                   msg='das Zeitfenster muss die echte Fahrt abbilden, nicht die Ankunft')

    def test_ohne_at_bleibt_alles_wie_vorher(self):
        """Alte Clients (ohne `at`) dürfen nicht kaputtgehen."""
        with app.app_context():
            u = M.User(email='bv2@t.de', name='BV2')
            u.set_password('x')
            db.session.add(u)
            db.session.commit()
            t = M.Tour(title='BV-ohne-at', status='planned',
                       tour_date=dt.date(2026, 11, 9), created_by=u.id)
            db.session.add(t)
            db.session.commit()
            jetzt = dt.datetime.utcnow()
            self.assertTrue(appmod._live_track_add(t.id, u.id, 53.55, 9.98, 8.0, jetzt))
            db.session.commit()
            self.assertEqual(M.LiveTrackPoint.query.filter_by(tour_id=t.id).count(), 1)


class NachsendenEntkoppeltTest(AppTestCase):
    """Punkt 2: Nur ein Lauf zur Zeit, sortiert, größere Blöcke."""

    def test_sperre_gegen_mehrfachstart(self):
        js = _live()
        self.assertIn('let nachsendenLaeuft = false;', js)
        self.assertIn('if (nachsendenLaeuft || !gesichert.length) return;', js)   # Build cf: auch nach dem Beenden
        self.assertIn('finally { nachsendenLaeuft = false; }', js)

    def test_sortiert_nach_aufnahmezeit(self):
        js = _live()
        self.assertIn('gesichert.sort((a, b) => (a.at || 0) - (b.at || 0));', js)

    def test_groesserer_block(self):
        js = _live()
        self.assertIn('gesichert.slice(0, 60)', js)


class PufferTest(AppTestCase):
    """Punkt 3: 200 Punkte waren nur 20 Minuten im Sparmodus."""

    def test_puffer_gross_genug(self):
        js = _live()
        self.assertIn('const GESICHERT_MAX = 1200;', js)
        self.assertNotIn('const GESICHERT_MAX = 200;', js)

    def test_begruendung_steht_dabei(self):
        js = _live()
        self.assertIn('Build bv', js)
        self.assertIn('20 Minuten', js)


class AussetzerTest(AppTestCase):
    """Punkt 4: Ein GPS-Sprung darf nicht gespeichert werden und nicht blockieren."""

    def test_filter_vorhanden(self):
        js = _live()
        self.assertIn('if (kmhFix > 120 && seitFixM > 60) {', js)   # Build cf: Fix gegen Fix
        self.assertIn('let lastOwnAtVorher = 0;', js)

    def test_filter_veraendert_den_zustand_nicht(self):
        """Wichtig: Ein Aussetzer darf lastPos NICHT überschreiben, sonst blockiert er danach."""
        js = _live()
        stelle = js.index('if (kmhFix > 120 && seitFixM > 60) {')
        snippet = js[stelle:stelle + 320]
        self.assertIn('return;', snippet)
        self.assertNotIn('lastPos =', snippet)
        self.assertNotIn('lastSent =', snippet)

    def test_dt_fix_wird_in_onpos_berechnet(self):
        js = _live()
        self.assertIn('const dtFixS = lastOwnAtVorher ? Math.max(0.5, (_jetztFix - lastOwnAtVorher) / 1000) : 0;', js)


class AchtStundenTest(AppTestCase):
    """Punkt 5: Vorwarnung statt stiller Abschaltung."""

    def test_vorwarnung_30_minuten(self):
        js = _live()
        self.assertIn('_achtStdGewarnt', js)
        self.assertIn('7.5 * 3600 * 1000', js)
        self.assertIn('Noch 30 Minuten bis zur 8-Stunden-Grenze', js)

    def test_erklaerung_nach_dem_stopp(self):
        js = _live()
        self.assertIn('Aufzeichnung nach 8 Stunden automatisch beendet', js)
        self.assertIn('Zum Weiterschienen', js)

    def test_alte_kurze_meldung_ist_weg(self):
        js = _live()
        self.assertNotIn("setStatus('Fahrt nach 8 Stunden automatisch beendet.');", js)


class JavaScriptGueltigTest(AppTestCase):
    """Der ganze Block muss syntaktisch gültig bleiben (node --check)."""

    def test_template_js_ist_gueltig(self):
        import re
        import shutil
        import subprocess
        import tempfile
        node = shutil.which('node')
        if not node:
            self.skipTest('node nicht gefunden')
        with open(LIVE, encoding='utf-8') as f:
            roh = f.read()
        bloecke = re.findall(r'<script>(.*?)</script>', roh, re.S)
        self.assertTrue(bloecke, 'kein <script>-Block gefunden')
        js = bloecke[0]
        js = re.sub(r'\{\{.*?\}\}', '0', js)          # Jinja-Ausdruecke
        js = re.sub(r'\{%.*?%\}', '', js)             # Jinja-Tags
        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as fh:
            fh.write(js)
            pfad = fh.name
        try:
            r = subprocess.run([node, '--check', pfad], capture_output=True, text=True, timeout=60)
        finally:
            os.unlink(pfad)
        self.assertEqual(r.returncode, 0, f'JavaScript-Fehler: {r.stderr[:500]}')


if __name__ == '__main__':
    unittest.main()
