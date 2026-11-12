"""Build cn: „Traccar Client ist aktiv. Man sieht auch einen kleinen roten Punkt, aber es springt
nicht um und keiner ist unterwegs"

Wahrscheinlichste Ursache: Siegel aus „Fahrt jetzt abschließen" (cl) war keine 10 min alt → Punkte
„ignoriert: Fahrt beendet". Zwei Änderungen:
  1. TRACKER_NEUSTART_MIN 10 → 2: ein Siegel heißt „Tracker war aus"; jeder Punkt, der mehr als 2 min
     nach dem Siegel liegt, startet eine neue Fahrt. Punkte VOR dem Siegel bleiben Nachzügler (nur Spur).
  2. users.tracker_note: was der Server mit dem letzten Punkt gemacht hat – steht auf der Live-Karte
     im Zuschauer-Hinweis („letzter Punkt Do 12.11., 17:44 · ignoriert: Fahrt gerade beendet – neue
     Fahrt ab 17:46 Uhr"), damit so etwas nie wieder ein Rätsel ist.
"""
import datetime as dt
import os
import unittest

from tests.base import AppTestCase, ROOT, appmod, db
import models as M

LIVE = os.path.join(ROOT, 'templates', 'touren', 'live.html')


def _ts(d):
    return int(d.replace(tzinfo=dt.timezone.utc).timestamp())


class NeustartUndNotizTest(AppTestCase):
    def setUp(self):
        super().setUp()
        for cls in (M.LiveTrackPoint, M.LiveStop, M.LiveLocation):
            cls.query.delete()
        self.plan = db.session.get(M.Tour, self.t_plan.id)
        self.hein = db.session.get(M.User, self.mem.id)
        self.plan.tour_date = dt.date.today()
        self.hein.tracker_token = 'tok-hein'
        self.hein.tracker_note = None
        db.session.commit()
        self.tid = self.plan.id

    def _push(self, lat=53.4, when=None):
        when = when or dt.datetime.utcnow()
        return self.client.get('/api/traccar', query_string=dict(id='tok-hein', lat=lat, lon=9.8, accuracy=8,
                                                                  timestamp=_ts(when)))

    def _note(self):
        return db.session.get(M.User, self.mem.id).tracker_note or ''

    def test_neustart_nach_2_min(self):
        self.assertEqual(appmod.TRACKER_NEUSTART_MIN, 2)
        db.session.add(M.LiveStop(tour_id=self.tid, user_id=self.mem.id,
                                  stopped_at=dt.datetime.utcnow() - dt.timedelta(minutes=3)))
        db.session.commit()
        r = self._push().get_json()
        self.assertTrue(r.get('recorded') and 'ignored' not in r, r)
        self.assertIsNotNone(M.LiveLocation.query.filter_by(tour_id=self.tid, user_id=self.mem.id).first())
        self.assertIsNone(M.LiveStop.query.filter_by(tour_id=self.tid, user_id=self.mem.id).first())
        self.assertIn('übernommen', self._note())

    def test_notiz_ignoriert_mit_uhrzeit(self):
        stop = dt.datetime.utcnow() - dt.timedelta(seconds=30)
        db.session.add(M.LiveStop(tour_id=self.tid, user_id=self.mem.id, stopped_at=stop))
        db.session.commit()
        r = self._push().get_json()
        self.assertEqual(r.get('ignored'), 'Fahrt beendet')
        n = self._note()
        self.assertIn('ignoriert: Fahrt gerade beendet – neue Fahrt ab', n)
        self.assertIn(appmod._fmt_local_hm(stop + dt.timedelta(minutes=2)) + ' Uhr', n)

    def test_notiz_nachzuegler_und_kein_tourtag(self):
        db.session.add(M.LiveStop(tour_id=self.tid, user_id=self.mem.id, stopped_at=dt.datetime.utcnow()))
        db.session.commit()
        self._push(when=dt.datetime.utcnow() - dt.timedelta(minutes=5))
        self.assertIn('Nachzügler', self._note())
        self.plan.tour_date = dt.date.today() + dt.timedelta(days=10)
        db.session.commit()
        self._push()
        self.assertIn('kein Tourtag', self._note())

    def test_notiz_auf_der_live_karte(self):
        self.hein.tracker_note = 'Do 12.11., 17:44 · ignoriert: Fahrt gerade beendet – neue Fahrt ab 17:46 Uhr'
        db.session.commit()
        self.login_member()
        html = self.client.get(f'/touren/{self.tid}/live').get_data(as_text=True)
        self.assertIn('const TRACKER_NOTE = "Do 12.11., 17:44 ', html)


class ClientTest(unittest.TestCase):
    def test_hinweis_nutzt_notiz(self):
        with open(LIVE, encoding='utf-8') as f:
            js = f.read()
        self.assertIn("const letzter = TRACKER_NOTE ? esc(TRACKER_NOTE) : esc(TRACKER_SEEN_TXT) + ' Uhr';", js)
        self.assertIn("'📡 Traccar ist eingerichtet (letzter Punkt ' + letzter + ')", js)

    def test_build_stempel(self):
        self.assertGreaterEqual(appmod.APP_BUILD, '2026-11-12 cn')
