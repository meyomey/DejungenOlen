"""Build cl: „Ist das normal dass Tracker App läuft? Die Tracker App habe ich beendet."

Traccar meldet kein „Dienst aus"; der Server hält den Tracker 15 min nach dem letzten Punkt für
aktiv (Build ci). Deshalb:
  1. ehrlicher Knopf „📡 Tracker-App · vor X min" + Hinweis „gilt bis HH:MM als aktiv",
  2. Link „Tracker beendet? Fahrt jetzt abschließen" → POST /api/location/stop mit force=1:
     Siegel sofort, Standort weg; Traccar-Nachzügler < 10 min ignoriert, > 10 min neue Fahrt.
"""
import datetime as dt
import os
import unittest

from tests.base import AppTestCase, ROOT, appmod, db
import models as M

LIVE = os.path.join(ROOT, 'templates', 'touren', 'live.html')


def _ts(d):
    return int(d.replace(tzinfo=dt.timezone.utc).timestamp())


class ForceStopTest(AppTestCase):
    def setUp(self):
        super().setUp()
        for cls in (M.LiveTrackPoint, M.LiveStop, M.LiveLocation):
            cls.query.delete()
        self.plan = db.session.get(M.Tour, self.t_plan.id)
        self.hein = db.session.get(M.User, self.mem.id)
        self.plan.tour_date = dt.date.today()
        self.hein.tracker_token = 'tok-hein'
        db.session.commit()
        self.tid = self.plan.id

    def _tracker(self, lat=53.4, minutes_ago=0):
        return self.client.get('/api/traccar', query_string=dict(
            id='tok-hein', lat=lat, lon=9.8, accuracy=8,
            timestamp=_ts(dt.datetime.utcnow() - dt.timedelta(minutes=minutes_ago))))

    def _siegel(self):
        return M.LiveStop.query.filter_by(tour_id=self.tid, user_id=self.mem.id).first()

    def test_force_stop_schliesst_trotz_aktivem_tracker_ab(self):
        self.login_member()
        self._tracker(minutes_ago=1)
        r = self.client.post('/api/location/stop', json={'tour_id': self.tid, 'force': 1})
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertTrue(d['ok']); self.assertNotIn('tracker', d)
        self.assertIsNotNone(self._siegel(), 'Siegel sofort')
        self.assertIsNone(M.LiveLocation.query.filter_by(tour_id=self.tid, user_id=self.mem.id).first())
        # Nachzügler aus Traccar kurz danach: ignoriert, kein Standort
        d2 = self._tracker(lat=53.401).get_json()
        # sekundengenau gleich alt wie das Siegel → „late" (nur Spur); sonst „ignored" – nie Standort
        self.assertTrue(d2.get('late') or d2.get('ignored') == 'Fahrt beendet', d2)
        self.assertIsNone(M.LiveLocation.query.filter_by(tour_id=self.tid, user_id=self.mem.id).first())

    def test_ohne_force_bleibt_vorfahrt(self):
        self.login_member()
        self._tracker(minutes_ago=1)
        d = self.client.post('/api/location/stop', json={'tour_id': self.tid, 'force': 0}).get_json()
        self.assertTrue(d.get('tracker'))
        self.assertIsNone(self._siegel())

    def test_force_auch_als_query(self):
        self.login_member()
        self._tracker(minutes_ago=1)
        d = self.client.post(f'/api/location/stop?tour_id={self.tid}&force=1').get_json()
        self.assertNotIn('tracker', d)
        self.assertIsNotNone(self._siegel())


class ClientTest(unittest.TestCase):
    def setUp(self):
        with open(LIVE, encoding='utf-8') as f:
            self.js = f.read()

    def test_knopf_und_hinweis_ehrlich(self):
        self.assertIn("'📡 Tracker-App · vor ' + trackerMinAgo() + ' min'", self.js)
        self.assertIn("gilt der Tracker bis '\n       + trackerBisUhr() + ' Uhr als aktiv", self.js)
        self.assertNotIn("'📡 Tracker-App läuft'", self.js)

    def test_link_zum_abschliessen(self):
        self.assertIn('Tracker beendet? Fahrt jetzt abschließen', self.js)
        self.assertIn("JSON.stringify({tour_id: TOUR_ID, force: 1})", self.js)
        # Status-Meldungen mit Link müssen als HTML gesetzt werden
        self.assertIn("setStatus(trackerStatusHtml(), 'sharing', true)", self.js)

    def test_build_stempel(self):
        self.assertGreaterEqual(appmod.APP_BUILD, '2026-11-12 cl')
