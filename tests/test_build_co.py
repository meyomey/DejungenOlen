"""Build co: mehr aus Traccar – Akku (batt/charge), Höhe (altitude → GPX <ele>, Höhenmeter), valid.

  1. batt + charging in LiveLocation, im Payload, in Liste/Tooltip der Live-Karte („🔋 23 % ⚡"),
     rot unter 15 % ohne Ladegerät; der Fahrer selbst bekommt einmal eine Warnung.
  2. valid=false (Netzwerk-Ortung ohne GPS-Fix) → Punkt verworfen, Notiz „kein gültiger GPS-Fix".
  3. altitude → LiveTrackPoint.ele → GPX <ele> + Höhenmeter (Schwellwert 10 m) in der Zusammenfassung.
"""
import datetime as dt
import os
import unittest

from tests.base import AppTestCase, ROOT, appmod, db
import models as M

LIVE = os.path.join(ROOT, 'templates', 'touren', 'live.html')
DETAIL = os.path.join(ROOT, 'templates', 'touren', 'detail.html')


def _ts(d):
    return int(d.replace(tzinfo=dt.timezone.utc).timestamp())


class TraccarMehrDatenTest(AppTestCase):
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

    def _push(self, lat=53.4, minutes_ago=1, **extra):
        q = dict(id='tok-hein', lat=lat, lon=9.8, accuracy=8,
                 timestamp=_ts(dt.datetime.utcnow() - dt.timedelta(minutes=minutes_ago)))
        q.update(extra)
        return self.client.get('/api/traccar', query_string=q)

    def _loc(self):
        return M.LiveLocation.query.filter_by(tour_id=self.tid, user_id=self.mem.id).first()

    def test_akku_und_laden_landen_im_standort_und_payload(self):
        self._push(batt=23, charge='true')
        loc = self._loc()
        self.assertEqual(loc.batt, 23); self.assertTrue(loc.charging)
        self.login_org()
        me = next(l for l in self.client.get(f'/api/location/tour/{self.tid}').get_json()['locations']
                  if l['user_id'] == self.mem.id)
        self.assertEqual(me['batt'], 23); self.assertTrue(me['charging'])
        self.assertIn('🔋 23 % ⚡', db.session.get(M.User, self.mem.id).tracker_note)

    def test_ohne_batt_bleibt_alter_wert(self):
        self._push(batt=50, charge='false', minutes_ago=2)
        self._push(lat=53.401, minutes_ago=1)           # Punkt ohne batt-Feld
        self.assertEqual(self._loc().batt, 50); self.assertFalse(self._loc().charging)

    def test_valid_false_wird_verworfen(self):
        r = self._push(valid='false').get_json()
        self.assertEqual(r.get('ignored'), 'kein GPS-Fix')
        self.assertIsNone(self._loc())
        self.assertEqual(M.LiveTrackPoint.query.filter_by(tour_id=self.tid).count(), 0)
        self.assertIn('kein gültiger GPS-Fix', db.session.get(M.User, self.mem.id).tracker_note)
        # valid=true / fehlend → normal
        self.assertTrue(self._push(valid='true', lat=53.401).get_json().get('recorded'))

    def test_hoehe_in_spur_gpx_und_hoehenmeter(self):
        base = dt.datetime.utcnow() - dt.timedelta(minutes=30)
        eles = [10, 12, 25, 40, 38, 30, 55, 60]
        for i, e in enumerate(eles):
            self.client.get('/api/traccar', query_string=dict(id='tok-hein', lat=53.4 + i * 0.002, lon=9.8, accuracy=8,
                                                               altitude=e, timestamp=_ts(base + dt.timedelta(minutes=i * 2))))
        pts = appmod._live_track_rows(self.tid, self.mem.id)
        self.assertEqual([p.ele for p in pts], eles)
        summ = next(s for s in appmod._live_track_summaries(self.tid) if s['user_id'] == self.mem.id)
        # 10→25 (+15, Schwelle erreicht) → 25→40 (+15) → Tal 30 → 30→55 (+25) → 55→60 nur +5 (unter Schwelle) = 55 Hm
        self.assertEqual(summ['hm'], 55)
        xml = appmod._live_track_gpx_xml(summ, self.plan)
        self.assertIn('<ele>25.0</ele>', xml)

    def test_browser_punkte_ohne_hoehe_kein_hm(self):
        self.login_member()
        base = dt.datetime.utcnow()
        for i in range(5):
            self.client.post('/api/location/update', json={'tour_id': self.tid, 'lat': 53.4 + i * 0.001, 'lng': 9.8, 'accuracy': 8})
        summ = appmod._live_track_summaries(self.tid)
        if summ:
            self.assertIsNone(summ[0]['hm'])
            self.assertNotIn('<ele>', appmod._live_track_gpx_xml(summ[0], self.plan))

    def test_ascent_funktion(self):
        a = appmod._live_track_ascent
        self.assertEqual(a([100, 103, 101, 104, 102, 105]), 0, 'Rauschen unter 10 m zählt nicht')
        self.assertEqual(a([100, 120, 100, 120]), 40)
        self.assertIsNone(a([None, None, 5]))
        self.assertIsNone(a([]))

    def test_tracker_bool(self):
        b = appmod._tracker_bool
        self.assertTrue(b('true')); self.assertTrue(b(1)); self.assertFalse(b('0')); self.assertIsNone(b(None)); self.assertIsNone(b('x'))


class TemplateTest(unittest.TestCase):
    def test_live_karte_zeigt_akku(self):
        with open(LIVE, encoding='utf-8') as f:
            js = f.read()
        self.assertIn("const BATT_WARN = 15;", js)
        self.assertIn("if (battTxt(r.loc)) parts.push(battHtml(r.loc));", js)
        self.assertIn("battCheckMe(lastLocs);", js)
        self.assertIn("Powerbank dran", js)

    def test_tourseite_zeigt_hoehenmeter(self):
        with open(DETAIL, encoding='utf-8') as f:
            h = f.read()
        self.assertIn('{% if r.hm is not none %}{{ r.hm }}{% else %}', h)

    def test_build_stempel(self):
        self.assertGreaterEqual(appmod.APP_BUILD, '2026-11-12 co')
