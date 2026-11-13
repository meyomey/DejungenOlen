"""Build cp: „Bin jetzt testweise eine Tour ohne Datum gefahren mit Traccar aktiv. In der App wird mit
Traccar nicht getrackt weil kein Datum eingetragen ist, oder?" – Ja. Jetzt: Öffnet ein Organisator
die Live-Karte einer Tour (und dürfte dort fahren), ist die Tour 12 h das Rückfall-Ziel seines
Trackers (users.tracker_tour_id/_at). Datum bleibt vorrangig; Mitglieder weiter an den Termin gebunden.
"""
import datetime as dt
import os
import unittest

from tests.base import AppTestCase, ROOT, appmod, db
import models as M

LIVE = os.path.join(ROOT, 'templates', 'touren', 'live.html')


def _ts(d):
    return int(d.replace(tzinfo=dt.timezone.utc).timestamp())


class PinTest(AppTestCase):
    def setUp(self):
        super().setUp()
        for cls in (M.LiveTrackPoint, M.LiveStop, M.LiveLocation):
            cls.query.delete()
        self.org_u = db.session.get(M.User, self.org.id)
        self.org_u.tracker_token = 'tok-orga'
        self.org_u.tracker_tour_id = None; self.org_u.tracker_tour_at = None
        self.mem_u = db.session.get(M.User, self.mem.id)
        self.mem_u.tracker_token = 'tok-hein'
        db.session.commit()
        self.open_id = self.t_open.id
        self.plan = db.session.get(M.Tour, self.t_plan.id)
        # Keine Tour der Gruppe darf zufällig im Datumsfenster liegen (t_done = gestern)
        for t in M.Tour.query.filter_by(group_id=self.plan.group_id).all():
            if not t.is_date_open:
                t.tour_date = dt.date.today() + dt.timedelta(days=30)
        db.session.commit()

    def _push(self, tok, lat=53.4):
        return self.client.get('/api/traccar', query_string=dict(
            id=tok, lat=lat, lon=9.8, accuracy=8, timestamp=_ts(dt.datetime.utcnow() - dt.timedelta(minutes=1))))

    def test_ohne_pin_kein_tourtag(self):
        r = self._push('tok-orga').get_json()
        self.assertEqual(r.get('ignored'), 'kein Tourtag')
        self.assertIn('Live-Karte der Tour öffnen', db.session.get(M.User, self.org.id).tracker_note)

    def test_orga_oeffnet_live_karte_dann_landet_traccar_auf_tour_ohne_termin(self):
        self.login_org()
        html = self.client.get(f'/touren/{self.open_id}/live').get_data(as_text=True)
        self.assertIn('const TRACKER_PINNED = true;', html)
        u = db.session.get(M.User, self.org.id)
        self.assertEqual(u.tracker_tour_id, self.open_id)
        r = self._push('tok-orga').get_json()
        self.assertEqual(r.get('tour_id'), self.open_id)
        self.assertTrue(r.get('recorded'))
        self.assertIsNotNone(M.LiveLocation.query.filter_by(tour_id=self.open_id, user_id=self.org.id).first())

    def test_pin_laeuft_nach_12h_ab(self):
        u = db.session.get(M.User, self.org.id)
        u.tracker_tour_id = self.open_id
        u.tracker_tour_at = dt.datetime.utcnow() - dt.timedelta(hours=13)
        db.session.commit()
        self.assertEqual(self._push('tok-orga').get_json().get('ignored'), 'kein Tourtag')
        u.tracker_tour_at = dt.datetime.utcnow() - dt.timedelta(hours=11)
        db.session.commit()
        self.assertEqual(self._push('tok-orga', lat=53.401).get_json().get('tour_id'), self.open_id)

    def test_datum_hat_vorrang_vor_pin(self):
        u = db.session.get(M.User, self.org.id)
        u.tracker_tour_id = self.open_id; u.tracker_tour_at = dt.datetime.utcnow()
        self.plan.tour_date = dt.date.today()
        db.session.commit()
        self.assertEqual(self._push('tok-orga').get_json().get('tour_id'), self.plan.id)

    def test_mitglied_bekommt_keinen_pin(self):
        self.login_member()
        html = self.client.get(f'/touren/{self.open_id}/live').get_data(as_text=True)
        self.assertIn('const TRACKER_PINNED = false;', html)
        self.assertIsNone(db.session.get(M.User, self.mem.id).tracker_tour_id)
        self.assertEqual(self._push('tok-hein').get_json().get('ignored'), 'kein Tourtag')

    def test_pin_fremde_gruppe_oder_abgesagt_zaehlt_nicht(self):
        u = db.session.get(M.User, self.org.id)
        u.tracker_tour_id = self.t_canc.id; u.tracker_tour_at = dt.datetime.utcnow()
        db.session.commit()
        self.assertIsNone(appmod._tracker_pinned_tour(u))


class TemplateTest(unittest.TestCase):
    def test_hinweis(self):
        with open(LIVE, encoding='utf-8') as f:
            js = f.read()
        self.assertIn("Diese Tour ist jetzt 12 h lang das Ziel deines Trackers, auch ohne Termin.", js)

    def test_build_stempel(self):
        self.assertGreaterEqual(appmod.APP_BUILD, '2026-11-12 cp')
