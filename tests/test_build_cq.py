"""Build cq: Audit 10 – Dokumentation nachgezogen; Profil zeigt Tracker-Status und Regeln."""
import datetime as dt
import os
import unittest

from tests.base import AppTestCase, ROOT, appmod, db
import models as M


class ProfilStatusTest(AppTestCase):
    def test_profil_zeigt_tracker_status_und_regeln(self):
        self.login_member()
        html = self.client.get('/profil/bearbeiten').get_data(as_text=True)
        self.assertIn('Noch kein Punkt aus Traccar angekommen.', html)
        self.assertIn('Tracker hat Vorfahrt', html)
        u = db.session.get(M.User, self.mem.id)
        u.tracker_seen_at = dt.datetime(2026, 11, 12, 16, 44)
        u.tracker_note = 'Do 12.11., 17:44 · ignoriert: Fahrt gerade beendet – neue Fahrt ab 17:46 Uhr'
        db.session.commit()
        html = self.client.get('/profil/bearbeiten').get_data(as_text=True)
        self.assertIn('letzter Punkt Do 12.11., 17:44 · ignoriert: Fahrt gerade beendet', html)


class DokuTest(unittest.TestCase):
    def test_readme_und_audit_kennen_traccar(self):
        with open(os.path.join(ROOT, 'README.md'), encoding='utf-8') as f:
            self.assertIn('Traccar Client', f.read())
        with open(os.path.join(ROOT, 'docs', 'AUDIT_BERICHT.md'), encoding='utf-8') as f:
            self.assertTrue(f.read().startswith('# Audit-Bericht – De jungen Olen, Audit 10'))
        with open(os.path.join(ROOT, 'UEBERGABE.md'), encoding='utf-8') as f:
            u = f.read()
        self.assertNotIn('Feldtest mit Traccar steht aus', u)
        self.assertIn('traccar_push', u)

    def test_build_stempel(self):
        self.assertGreaterEqual(appmod.APP_BUILD, '2026-11-13 cq')
