"""Build bs / Audit 8: drei Befunde aus dem achten Komplett-Audit.

1. **Kommentar an fremder Tour löschbar** (Befund aus Audit 7, damals nur notiert und
   offen geblieben): `comment_delete` prüfte nur den Autor, nicht die Gruppe. Ein Mitglied
   konnte einen EIGENEN Kommentar löschen, dessen `tour_id` auf eine fremde Tour zeigt –
   die Route antwortete 302 und leitete auf `/touren/<fremde_id>` um (dort 404). Kein
   Datenabfluss, aber eine Route, die auf ein unerreichbares Objekt schreibt.
   Jetzt: erst `_tour_or_404(tour_id)`, dann `comment.tour_id != tour_id → 404`.

2. **Kein CSRF-Schutz** (neu in Audit 8): Es gab weder Flask-WTF-Token noch eine
   Herkunftsprüfung – ein POST von einer fremden Seite (mit `Origin`-Kopf, ohne
   SameSite-Schutz für Top-Level-Formulare) wurde angenommen (gemessen: Teilnahme wurde
   angelegt). Jetzt weist `_csrf_herkunft` POST/PUT/PATCH/DELETE mit fremdem
   `Origin`/`Referer` mit 403 ab, solange der Host nicht der eigene ist. `/api/` und die
   Anmeldung bleiben frei (Token-/Cron-Aufrufe und Login-Hilfsskripte).

3. **Hilfe widersprach dem Code** (Doku): Zeile 310 sagte, der 🔒-Knopf sei „auch im
   Vollbild" da; der Code (`guardWanted()` → `if (_fsAn()) return false`) und Zeile 281
   sagen das Gegenteil. Der Text folgt jetzt dem Code.
"""
import unittest
from unittest import mock

from tests.base import AppTestCase, appmod, app, db, M

PASSWORD = 'geheim123'


class KommentarFremdeTourTest(AppTestCase):
    """B1: Löschen eines Kommentars an einer fremden Tour muss 404 liefern."""

    def _kommentar_an_fremder_tour(self):
        """Kommentar von `mem` (Gruppe Olen) an einer Tour der ANDEREN Gruppe."""
        with app.app_context():
            t = db.session.get(M.Tour, self.t_fremd_id)
            k = M.TourComment(tour_id=t.id, user_id=self.mem_id,
                              content='eigener Kommentar an fremder Tour')
            db.session.add(k)
            db.session.commit()
            return t.id, k.id

    def test_loeschen_an_fremder_tour_ist_404(self):
        tid, kid = self._kommentar_an_fremder_tour()
        self.login_member()
        r = self.client.post(f'/touren/{tid}/kommentare/{kid}/loeschen')
        self.assertEqual(r.status_code, 404,
                         'Kommentar an fremder Tour wurde angenommen (Audit-7-Befund offen)')

    def test_kommentar_bleibt_erhalten(self):
        """Der abgewiesene Aufruf darf nichts gelöscht haben."""
        tid, kid = self._kommentar_an_fremder_tour()
        self.login_member()
        self.client.post(f'/touren/{tid}/kommentare/{kid}/loeschen')
        with app.app_context():
            self.assertIsNotNone(db.session.get(M.TourComment, kid),
                                 'Der Kommentar wurde trotz 404 gelöscht')

    def test_eigener_kommentar_an_eigener_tour_geht(self):
        """Gegenprobe: der normale Weg bleibt offen (302 + gelöscht)."""
        with app.app_context():
            k = M.TourComment(tour_id=self.t_plan_id, user_id=self.mem_id, content='normal')
            db.session.add(k)
            db.session.commit()
            kid = k.id
        self.login_member()
        r = self.client.post(f'/touren/{self.t_plan_id}/kommentare/{kid}/loeschen')
        self.assertIn(r.status_code, (302, 303))
        with app.app_context():
            self.assertIsNone(db.session.get(M.TourComment, kid))

    def test_kommentar_id_passt_nicht_zur_tour_id(self):
        """Eigener Kommentar, aber fremde Tour in der URL → 404 (kein stilles Umschreiben)."""
        with app.app_context():
            k = M.TourComment(tour_id=self.t_plan_id, user_id=self.mem_id, content='x')
            db.session.add(k)
            db.session.commit()
            kid = k.id
        self.login_member()
        r = self.client.post(f'/touren/{self.t_fremd_id}/kommentare/{kid}/loeschen')
        self.assertEqual(r.status_code, 404)
        with app.app_context():
            self.assertIsNotNone(db.session.get(M.TourComment, kid))


class CsrfHerkunftTest(AppTestCase):
    """B2: POST von einer fremden Seite wird abgewiesen, eigener Host nicht."""

    BOESE = 'https://boese.example'

    def test_fremder_origin_wird_abgewiesen(self):
        self.login_member()
        r = self.client.post(f'/touren/{self.t_plan_id}/rsvp', data={'status': 'attending'},
                             headers={'Origin': self.BOESE})
        self.assertEqual(r.status_code, 403)

    def test_fremder_origin_schreibt_nichts(self):
        """Die Teilnahme darf durch den abgewiesenen Aufruf nicht entstehen."""
        self.login_member()
        with app.app_context():
            vorher = M.TourParticipant.query.filter_by(tour_id=self.t_plan_id).count()
        self.client.post(f'/touren/{self.t_plan_id}/rsvp', data={'status': 'attending'},
                         headers={'Origin': self.BOESE})
        with app.app_context():
            nachher = M.TourParticipant.query.filter_by(tour_id=self.t_plan_id).count()
            self.assertEqual(nachher, vorher,
                             'CSRF-Aufruf hat trotzdem eine Teilnahme angelegt')

    def test_fremder_referer_wird_abgewiesen(self):
        """Ohne Origin greift der Referer."""
        self.login_member()
        r = self.client.post(f'/touren/{self.t_plan_id}/rsvp', data={'status': 'attending'},
                             headers={'Referer': self.BOESE + '/angriff.html'})
        self.assertEqual(r.status_code, 403)

    def test_eigener_origin_geht_durch(self):
        self.login_member()
        r = self.client.post(f'/touren/{self.t_plan_id}/rsvp', data={'status': 'attending'},
                             headers={'Origin': 'http://localhost'})
        self.assertIn(r.status_code, (302, 303),
                      f'eigener Origin wurde abgewiesen ({r.status_code})')

    def test_ohne_origin_und_referer_geht_durch(self):
        """Ältere Browser, curl und Cron schicken keinen der beiden Köpfe."""
        self.login_member()
        r = self.client.post(f'/touren/{self.t_plan_id}/rsvp', data={'status': 'attending'})
        self.assertIn(r.status_code, (302, 303))

    def test_api_bleibt_frei(self):
        """Ein Token-Aufruf von einem fremden Host (Cron auf einem anderen Server) darf
        NICHT an der Herkunftsprüfung scheitern. Der Endpunkt antwortet ohne gültiges
        Token mit 403 `invalid token` – genau diese Antwort beweist, dass die Anfrage
        bis zur Token-Prüfung durchkam (die CSRF-Prüfung hätte „fremde Seite" gemeldet).
        """
        r = self.client.post('/api/backup/trigger', headers={'Origin': self.BOESE})
        self.assertEqual(r.status_code, 403)          # Endpunkt-Token, nicht CSRF
        self.assertIn(b'invalid token', r.data,
                      'API-Pfad wurde von der CSRF-Prüfung blockiert statt vom Token')

    def test_api_csrf_meldet_nicht(self):
        """Negativbeleg: die CSRF-Warnung darf im Log nicht auftauchen.

        `assertLogs` schlägt fehl, wenn GAR NICHTS geloggt wird – deshalb wird der
        Logger-Aufruf mitgeschnitten und danach gefiltert.
        """
        zeilen = []
        with mock.patch.object(app.logger, 'warning',
                               side_effect=lambda msg, *a, **k: zeilen.append(str(msg))):
            self.client.post('/api/backup/trigger', headers={'Origin': self.BOESE})
        self.assertFalse([z for z in zeilen if 'CSRF' in z],
                         'CSRF-Prüfung hat einen /api/-Aufruf angefasst')

    def test_login_bleibt_frei(self):
        """Das Login-Formular ist ausgenommen (eigene Seite, aber auch Hilfe-Skripte)."""
        r = self.client.post('/login', data={'email': 'hein@test.de', 'password': PASSWORD},
                             headers={'Origin': self.BOESE})
        self.assertNotEqual(r.status_code, 403)

    def test_get_wird_nicht_geprueft(self):
        self.login_member()
        r = self.client.get('/touren', headers={'Origin': self.BOESE})
        self.assertEqual(r.status_code, 200)


class HilfeSperreImVollbildTest(AppTestCase):
    """B3: Hilfe und Code müssen dasselbe sagen – im Vollbild gibt es kein 🔒."""

    def test_hilfe_sagt_nicht_mehr_dass_der_knopf_im_vollbild_da_ist(self):
        with open(str(appmod.os.path.join(appmod.os.path.dirname(appmod.__file__),
                                          'templates', 'hilfe.html')), encoding='utf-8') as f:
            text = f.read()
        alt = 'auch während einer Fahrt, beim Folgen und im Vollbild'
        self.assertNotIn(alt, text, 'Die Hilfe behauptet weiter, der 🔒-Knopf sei im Vollbild da')
        self.assertIn('Im Vollbild gibt es ihn nicht', text)

    def test_code_sperrt_im_vollbild_nicht(self):
        """Beleg für den Text: `guardWanted()` gibt im Vollbild immer False."""
        with open(str(appmod.os.path.join(appmod.os.path.dirname(appmod.__file__),
                                          'templates', 'touren', 'live.html')), encoding='utf-8') as f:
            js = f.read()
        i = js.find('function guardWanted()')
        self.assertGreater(i, 0)
        block = js[i:i + 400]
        self.assertIn('if (_fsAn()) return false;', block)


if __name__ == '__main__':
    unittest.main()
