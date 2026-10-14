"""Smoke-Tests: Login, Zugriffsschutz und „keine Seite wirft einen 500er“."""
from tests.base import AppTestCase, app, appmod

# GET-Routen ohne URL-Parameter, die absichtlich keinen 200/3xx liefern
EXPECTED_NON_OK = {
    '/push/vapid-public-key': {503},      # ohne VAPID-Schlüssel in der Testumgebung
}
SKIP_ENDPOINTS = {'static', 'logout'}


class RoutesTest(AppTestCase):

    def test_login_page(self):
        html = self.get_html('/login')
        self.assertIn('name="email"', html)
        self.assertIn('name="password"', html)

    def test_anonymous_is_redirected(self):
        for path in ('/touren', '/archiv', '/gastro', '/profil/bearbeiten', '/admin/tools'):
            r = self.client.get(path)
            self.assertIn(r.status_code, (302, 303), path)
            self.assertIn('/login', r.headers['Location'], path)

    def test_wrong_password(self):
        appmod._rl_store.clear()
        self.client.post('/login', data={'email': 'hein@test.de', 'password': 'falsch'})
        r = self.client.get('/touren')
        self.assertIn(r.status_code, (302, 303), 'falsches Passwort darf nicht einloggen')

    def test_login_rate_limit_resets(self):
        """Das Login-Limit (10/min je IP) darf einen korrekten Login nach _rl_store.clear() nicht blockieren."""
        self.login_member()
        self.assertEqual(self.client.get('/touren').status_code, 200)

    def test_member_pages(self):
        self.login_member()
        for path in ('/', '/touren', '/archiv', '/rueckblick', '/gastro', '/hilfe', '/profil/bearbeiten'):
            r = self.client.get(path)
            self.assertIn(r.status_code, (200, 302), f'{path} → {r.status_code}')

    def test_member_cannot_open_admin(self):
        self.login_member()
        self.assertIn(self.client.get('/admin/tools').status_code, (302, 403))
        self.assertIn(self.client.post('/admin/gpx-kennzahlen').status_code, (302, 403))

    def _all_get_routes(self):
        bad = []
        for rule in app.url_map.iter_rules():
            if 'GET' not in rule.methods or rule.arguments or rule.endpoint in SKIP_ENDPOINTS:
                continue
            try:
                code = self.client.get(rule.rule).status_code
            except Exception as ex:                      # noqa: BLE001 – wir wollen jede Ausnahme sehen
                bad.append((rule.rule, f'{ex.__class__.__name__}: {ex}'))
                continue
            if code >= 500 and code not in EXPECTED_NON_OK.get(rule.rule, set()):
                bad.append((rule.rule, code))
        return bad

    def test_all_get_routes_member(self):
        self.login_member()
        self.assertEqual(self._all_get_routes(), [])

    def test_all_get_routes_organizer(self):
        self.login_org()
        self.assertEqual(self._all_get_routes(), [])

    def test_all_get_routes_admin(self):
        self.login_admin()
        self.assertEqual(self._all_get_routes(), [])

    def test_tour_pages_all_states(self):
        """Detail-, Druck- und ICS-Seite jeder Beispieltour (geplant, offen, abgeschlossen, abgesagt)."""
        self.login_org()
        for tid in (self.t_plan_id, self.t_open_id, self.t_done_id, self.t_canc_id):
            for suffix in ('', '/drucken', '/ical', '/bearbeiten'):
                r = self.client.get(f'/touren/{tid}{suffix}')
                self.assertIn(r.status_code, (200, 302), f'/touren/{tid}{suffix} → {r.status_code}')

    def test_other_group_is_invisible(self):
        self.login_org()
        self.assertEqual(self.client.get(f'/touren/{self.t_fremd_id}').status_code, 404)
        self.assertEqual(self.client.post(f'/touren/{self.t_fremd_id}/nochmal').status_code, 404)

    def test_version_in_footer(self):
        self.login_member()
        html = self.get_html('/touren')
        self.assertIn(appmod.APP_VERSION, html)
