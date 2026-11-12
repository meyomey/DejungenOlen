"""Build cm: „Hier steht nur Fahrt starten. Hier sollte auch Traccar erwähnt werden, falls eingerichtet"

Eingerichtet = von diesem Nutzer ist je ein Traccar-Punkt angekommen (User.tracker_seen_at; der
Token selbst entsteht schon beim Öffnen des Profils). Dann zeigt die Live-Karte im Zuschauer-Zustand
„📡 Traccar ist eingerichtet (zuletzt gesendet …): Dienst in der Traccar-App einschalten … Oder Fahrt
starten".
"""
import datetime as dt
import os
import unittest

from tests.base import AppTestCase, ROOT, appmod, db
import models as M

LIVE = os.path.join(ROOT, 'templates', 'touren', 'live.html')


def _ts(d):
    return int(d.replace(tzinfo=dt.timezone.utc).timestamp())


class TrackerSeenTest(AppTestCase):
    def setUp(self):
        super().setUp()
        for cls in (M.LiveTrackPoint, M.LiveStop, M.LiveLocation):
            cls.query.delete()
        self.plan = db.session.get(M.Tour, self.t_plan.id)
        self.hein = db.session.get(M.User, self.mem.id)
        self.plan.tour_date = dt.date.today()
        self.hein.tracker_token = 'tok-hein'
        self.hein.tracker_seen_at = None
        db.session.commit()
        self.tid = self.plan.id

    def test_traccar_punkt_merkt_tracker_seen_at(self):
        self.client.get('/api/traccar', query_string=dict(id='tok-hein', lat=53.4, lon=9.8, accuracy=8,
                                                           timestamp=_ts(dt.datetime.utcnow() - dt.timedelta(minutes=1))))
        self.assertIsNotNone(db.session.get(M.User, self.mem.id).tracker_seen_at)

    def test_auch_bei_verworfenem_punkt(self):
        # zu alter Punkt (> 12 h) wird verworfen – „eingerichtet" ist Traccar trotzdem
        self.client.get('/api/traccar', query_string=dict(id='tok-hein', lat=53.4, lon=9.8,
                                                           timestamp=_ts(dt.datetime.utcnow() - dt.timedelta(hours=20))))
        self.assertIsNotNone(db.session.get(M.User, self.mem.id).tracker_seen_at)

    def test_live_karte_erwaehnt_traccar_nur_wenn_eingerichtet(self):
        self.login_member()
        html = self.client.get(f'/touren/{self.tid}/live').get_data(as_text=True)
        self.assertIn('const TRACKER_SEEN_TXT = "";', html)
        u = db.session.get(M.User, self.mem.id)
        u.tracker_seen_at = dt.datetime(2026, 11, 12, 16, 10)   # UTC → 17:10 Ortszeit
        db.session.commit()
        html = self.client.get(f'/touren/{self.tid}/live').get_data(as_text=True)
        self.assertIn('const TRACKER_SEEN_TXT = "Do 12.11., 17:10";', html)

    def test_seen_txt_format(self):
        class U: tracker_seen_at = dt.datetime(2026, 11, 12, 16, 10)
        self.assertEqual(appmod._tracker_seen_txt(U()), 'Do 12.11., 17:10')
        U.tracker_seen_at = None
        self.assertEqual(appmod._tracker_seen_txt(U()), '')


class ClientTest(unittest.TestCase):
    def test_hinweis_im_zuschauer_zustand(self):
        with open(LIVE, encoding='utf-8') as f:
            js = f.read()
        self.assertIn("if (TRACKER_SEEN_TXT && !trackerAktiv() && CAN_SHARE) setStatus(trackerIdleHtml(), '', true);", js)
        self.assertIn('Traccar ist eingerichtet (zuletzt gesendet', js)
        self.assertIn('Dienst in der Traccar-App', js)

    def test_build_stempel(self):
        self.assertGreaterEqual(appmod.APP_BUILD, '2026-11-12 cm')
