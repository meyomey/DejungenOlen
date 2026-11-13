"""Build cr: „Testnachricht für Desktop funktioniert, aber Handy nicht?"

Push ist je Gerät/Browser. Vorher: /push/test antwortete ok, sobald EIN Gerät erreicht wurde, und das
Profil zeigte „Aktiv", wenn DIESER Browser angemeldet war – ob das Handy überhaupt angemeldet oder
seine Subscription abgelaufen (410, still gelöscht) war, blieb unsichtbar. Jetzt: Geräteliste mit
Label („Android · Chrome"), Ergebnis je Gerät („1 von 2 Geräten erreicht: ❌ Android · Chrome – …"),
„dieses Gerät"-Markierung, Hinweis „jedes Gerät meldet sich einzeln an".
"""
import datetime as dt
import os
import unittest
from unittest import mock

from tests.base import AppTestCase, ROOT, appmod, db
import models as M

PROFIL = os.path.join(ROOT, 'templates', 'profil_edit.html')


class PushJeGeraetTest(AppTestCase):
    def setUp(self):
        super().setUp()
        M.PushSubscription.query.delete(); db.session.commit()
        self.login_member()

    def _sub(self, endpoint, label=None):
        return self.client.post('/push/subscribe', json={'endpoint': endpoint, 'keys': {'p256dh': 'k', 'auth': 'a'}, 'label': label},
                                headers={'User-Agent': 'Mozilla/5.0 (Linux; Android 14) Chrome/120.0 Mobile Safari/537.36'})

    def test_label_aus_client_oder_user_agent(self):
        self._sub('https://push.example/1', 'Windows · Firefox')
        self._sub('https://push.example/2')
        labels = sorted(s.label for s in M.PushSubscription.query.all())
        self.assertEqual(labels, ['Android · Chrome', 'Windows · Firefox'])

    def test_test_antwort_je_geraet(self):
        self._sub('https://push.example/pc', 'Windows · Chrome')
        self._sub('https://push.example/handy', 'Android · Chrome')
        def fake(sub, title, body, url=None):
            ok = 'pc' in sub.endpoint
            appmod._push_mark(sub, ok, 'ok' if ok else 'HTTP 410: gone – wurde entfernt, bitte neu aktivieren')
            return ok, ('ok' if ok else 'Subscription ungültig (HTTP 410) – wurde entfernt, bitte neu aktivieren')
        with mock.patch.object(appmod, 'send_push', side_effect=fake):
            r = self.client.post('/push/test', json={'endpoint': 'https://push.example/pc'})
        d = r.get_json()
        self.assertEqual(r.status_code, 200)
        self.assertEqual((d['sent'], d['total']), (1, 2))
        pc = next(x for x in d['devices'] if x['label'] == 'Windows · Chrome')
        handy = next(x for x in d['devices'] if x['label'] == 'Android · Chrome')
        self.assertTrue(pc['ok'] and pc['this_device'])
        self.assertFalse(handy['ok']); self.assertTrue(handy['removed']); self.assertFalse(handy['this_device'])
        # Ergebnis am Gerät gemerkt
        s = M.PushSubscription.query.filter_by(endpoint='https://push.example/pc').first()
        self.assertIsNotNone(s.last_ok_at)

    def test_kein_geraet(self):
        r = self.client.post('/push/test', json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn('auf jedem Gerät', r.get_json()['error'])

    def test_profil_listet_geraete(self):
        self._sub('https://push.example/pc', 'Windows · Chrome')
        s = M.PushSubscription.query.first(); s.last_error = 'HTTP 410: gone'; db.session.commit()
        html = self.client.get('/profil/bearbeiten').get_data(as_text=True)
        self.assertIn('Windows · Chrome', html)
        self.assertIn('HTTP 410: gone', html)
        self.assertIn('Push ist <strong>je Gerät</strong>', html)
        self.assertIn('data-count="1"', html)

    def test_ua_label(self):
        f = appmod._push_label_from_ua
        self.assertEqual(f('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) AppleWebKit Version/17.0 Mobile Safari/604.1'), 'iPhone · Safari')
        self.assertEqual(f('Mozilla/5.0 (Windows NT 10.0) Chrome/120 Safari/537.36 Edg/120'), 'Windows · Edge')
        self.assertEqual(f(None), 'Gerät · Browser')


class TemplateTest(unittest.TestCase):
    def test_js(self):
        with open(PROFIL, encoding='utf-8') as f:
            h = f.read()
        self.assertIn("' von ' + data.total + ' Geräten erreicht:", h)
        self.assertIn("setPushStatus('Aktiv auf diesem Gerät', 'success')", h)
        self.assertIn("{label: pushLabel()}", h)

    def test_build_stempel(self):
        self.assertGreaterEqual(appmod.APP_BUILD, '2026-11-13 cr')
