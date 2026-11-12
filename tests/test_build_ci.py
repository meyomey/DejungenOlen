"""Build ci: „Tracker hat Vorfahrt" – Traccar-Nutzer und Browser-Nutzer nebeneinander.

Der Nutzer: „Wie geht man am besten damit um wenn jemand Traccar Client nutzt und ein anderer
nicht? ‚Fahrt starten' Button ist ja auch noch da in der Live Karte und Fahren auf der Tourseite.
Wenn Traccar Client aktiv ist kann man trotzdem die Knöpfe drücken. Das muss entwirrt werden?"

Regel (Server + Live-Karte + Tourseite): Kommt die eigene Position aus der Tracker-App (letzter
Tracker-Punkt < 15 min, `LiveLocation.tracker_at`), dann
  · schreibt der Server keinen Browser-Punkt mehr (`tracker: true` statt doppelter Punkte),
  · setzt „Beenden" im Browser kein Siegel und löscht den Standort nicht,
  · zeigt die Live-Karte „📡 Tracker-App läuft" statt „Fahrt starten" und startet kein GPS,
  · zeigt die Tourseite „Tracker läuft" statt „Fahren".
Wer kein Traccar nutzt: alles wie bisher.
"""
import datetime as dt
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from tests.base import AppTestCase, ROOT, app, appmod, db
import models as M

LIVE = os.path.join(ROOT, 'templates', 'touren', 'live.html')


def _ts(d):
    return int(d.replace(tzinfo=dt.timezone.utc).timestamp())


class ServerVorfahrtTest(AppTestCase):
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

    def _browser(self, lat=53.5, **kw):
        body = {'tour_id': self.tid, 'lat': lat, 'lng': 9.8, 'accuracy': 8}
        body.update(kw)
        return self.client.post('/api/location/update', json=body)

    def _loc(self):
        return M.LiveLocation.query.filter_by(tour_id=self.tid, user_id=self.mem.id).first()

    def test_tracker_punkt_setzt_tracker_at_browser_punkt_nicht(self):
        self.login_member()
        self._browser()
        self.assertIsNone(self._loc().tracker_at)
        self.assertIsNone(appmod._tracker_ago(self.tid, self.mem.id))
        self._tracker()
        self.assertIsNotNone(self._loc().tracker_at)
        self.assertLess(appmod._tracker_ago(self.tid, self.mem.id), 5)
        self.assertTrue(appmod._tracker_active(self.tid, self.mem.id))

    def test_browser_punkt_wird_bei_aktivem_tracker_nicht_geschrieben(self):
        """Keine doppelten Punkte: Browser sendet weiter, der Server antwortet tracker:true."""
        self.login_member()
        self._tracker(lat=53.4)
        n0 = M.LiveTrackPoint.query.count()
        r = self._browser(lat=53.5)
        d = r.get_json()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(d['tracker'])
        self.assertFalse(d['recorded'])
        self.assertLess(d['tracker_ago'], 5)
        self.assertEqual(M.LiveTrackPoint.query.count(), n0)
        self.assertAlmostEqual(self._loc().lat, 53.4)          # Standort bleibt der Tracker-Punkt
        self.assertIn('locations', d)

    def test_browser_punkt_zaehlt_wieder_wenn_tracker_still(self):
        self.login_member()
        self._tracker(minutes_ago=1)
        self._loc().tracker_at = dt.datetime.utcnow() - dt.timedelta(minutes=16)
        db.session.commit()
        d = self._browser(lat=53.401).get_json()
        self.assertNotIn('tracker', d)
        self.assertTrue(d['recorded'])
        self.assertAlmostEqual(self._loc().lat, 53.401)

    def test_beenden_im_browser_setzt_bei_tracker_kein_siegel(self):
        self.login_member()
        self._tracker(minutes_ago=1)
        r = self.client.post(f'/api/location/stop?tour_id={self.tid}')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json().get('tracker'))
        self.assertIsNone(M.LiveStop.query.filter_by(tour_id=self.tid, user_id=self.mem.id).first())
        self.assertIsNotNone(self._loc(), 'Standort bleibt – die Fahrt läuft über den Tracker')
        # nächster Tracker-Punkt kommt normal durch
        self.assertTrue(self._tracker(lat=53.41).get_json()['recorded'])

    def test_beenden_ohne_tracker_wie_bisher(self):
        self.login_member()
        self._browser()
        self.client.post(f'/api/location/stop?tour_id={self.tid}')
        self.assertIsNotNone(M.LiveStop.query.filter_by(tour_id=self.tid, user_id=self.mem.id).first())
        self.assertIsNone(self._loc())

    def test_payload_traegt_tracker_ago(self):
        self.login_member()
        self._tracker()
        self.login_org()
        locs = self.client.get(f'/api/location/tour/{self.tid}').get_json()['locations']
        me = next(l for l in locs if l['user_id'] == self.mem.id)
        self.assertIsNotNone(me['tracker_ago'])
        self.assertLess(me['tracker_ago'], 5)
        # Browser-Nutzer: None
        self._browser_as_org()
        locs = self.client.get(f'/api/location/tour/{self.tid}').get_json()['locations']
        org = next(l for l in locs if l['user_id'] == self.org.id)
        self.assertIsNone(org['tracker_ago'])

    def _browser_as_org(self):
        return self.client.post('/api/location/update', json={'tour_id': self.tid, 'lat': 53.6, 'lng': 9.8})

    def test_live_karte_bekommt_tracker_ago(self):
        self.login_member()
        self._tracker()
        html = self.client.get(f'/touren/{self.tid}/live').get_data(as_text=True)
        self.assertRegex(html, r'let trackerSeen = \d+;')
        self.assertIn('const TRACKER_ACTIVE_MS = 900 * 1000;', html)
        self.login_org()
        html = self.client.get(f'/touren/{self.tid}/live').get_data(as_text=True)
        self.assertIn('let trackerSeen = null;', html)

    def test_tourseite_zeigt_tracker_laeuft(self):
        self.login_member()
        html = self.client.get(f'/touren/{self.tid}').get_data(as_text=True)
        self.assertIn('<span class="lbl">Fahren</span>', html)
        self.assertNotIn('Tracker läuft', html)
        self._tracker()
        html = self.client.get(f'/touren/{self.tid}').get_data(as_text=True)
        self.assertIn('Tracker läuft', html)
        self.assertNotIn('<span class="lbl">Fahren</span>', html)

    def test_migration_spalte(self):
        from sqlalchemy import inspect
        cols = {c['name'] for c in inspect(db.engine).get_columns('live_locations')}
        self.assertIn('tracker_at', cols)


# ── Client-Logik: die echten Funktionen aus live.html in Node ─────────────────────────────────
HARNESS = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
function grab(name) {
  const m = src.match(new RegExp('function ' + name + '\\([^)]*\\) \\{[\\s\\S]*?\\n\\}'));
  if (!m) { console.error('fehlt: ' + name); process.exit(1); }
  return m[0];
}
let log = [], btn = {textContent: '', cls: new Set(), attrs: {},
  classList: {toggle(c, on) { on ? btn.cls.add(c) : btn.cls.delete(c); }},
  setAttribute(k, v) { btn.attrs[k] = v; }};
const ctx = {
  TRACKER_ACTIVE_MS: 900000, trackerSeen: 0, trackerModus: false, sharing: false,
  ME: {id: 7}, CAN_SHARE: true, stopped: 0, started: 0,
};
const code = [grab('trackerAktiv'), grab('noteTrackerAgo'), grab('noteTrackerLocs'), grab('fmtUhr'),
              grab('refreshTrackerUi'), grab('toggleShare'), grab('updateShareBtn')].join('\n');
const body = `
  let {TRACKER_ACTIVE_MS, trackerSeen, trackerModus, sharing, ME, CAN_SHARE} = ctx;
  const document = {getElementById: () => btn};
  const setStatus = (t, k) => log.push([k, t]);
  const updatePauseBtn = () => {};
  const stopShare = () => { ctx.stopped++; sharing = false; };
  const startShare = () => { if (trackerAktiv()) { refreshTrackerUi(); return; } ctx.started++; sharing = true; updateShareBtn(); };
  ${code}
  return {noteTrackerLocs, noteTrackerAgo, toggleShare, startShare, refreshTrackerUi,
          state: () => ({trackerModus, sharing, trackerSeen})};
`;
const make = () => new Function('ctx', 'btn', 'log', body)(ctx, btn, log);
const api = make();
const out = {};
// 1) Kein Tracker: Knopf normal, Start erlaubt
api.noteTrackerLocs([{user_id: 7, tracker_ago: null}]);
api.startShare();
out.ohneTracker = {text: btn.textContent, started: ctx.started, sharing: api.state().sharing};
// 2) Tracker setzt ein, während die Browser-Fahrt läuft → Browser stoppt, Knopf wechselt
api.noteTrackerLocs([{user_id: 7, tracker_ago: 12}]);
out.trackerKommt = {text: btn.textContent, stopped: ctx.stopped, sharing: api.state().sharing,
                    modus: api.state().trackerModus, info: btn.cls.has('btn-info'), status: log[log.length-1][1].slice(0, 22)};
// 3) Knopf drücken tut nichts außer Hinweis
const s0 = ctx.started; api.toggleShare();
out.knopfImTrackerModus = {started: ctx.started - s0, sharing: api.state().sharing, hinweis: log[log.length-1][1].includes('Traccar')};
// 4) fremder Tracker-Punkt zählt nicht (frische Instanz)
const api2 = make();
api2.noteTrackerLocs([{user_id: 9, tracker_ago: 1}]);
out.fremderTracker = {modus: api2.state().trackerModus};
// 5) ein älterer Wert (16 min) überschreibt einen frischen nicht
api.noteTrackerLocs([{user_id: 7, tracker_ago: 16 * 60}]);
out.altWert = {modus: api.state().trackerModus};
console.log(JSON.stringify(out));
"""

HARNESS_STILL = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
function grab(name) { return src.match(new RegExp('function ' + name + '\\([^)]*\\) \\{[\\s\\S]*?\\n\\}'))[0]; }
let log = [], btn = {textContent: '', cls: new Set(), attrs: {},
  classList: {toggle(c, on) { on ? btn.cls.add(c) : btn.cls.delete(c); }}, setAttribute(k, v) { btn.attrs[k] = v; }};
const code = [grab('trackerAktiv'), grab('noteTrackerAgo'), grab('noteTrackerLocs'), grab('fmtUhr'),
              grab('refreshTrackerUi'), grab('updateShareBtn')].join('\n');
const body = `
  let TRACKER_ACTIVE_MS = 900000, trackerSeen = Date.now() - 14 * 60000, trackerModus = false, sharing = false;
  const ME = {id: 7};
  const document = {getElementById: () => btn};
  const setStatus = (t, k) => log.push([k, t]);
  const updatePauseBtn = () => {}; const stopShare = () => {};
  ${code}
  refreshTrackerUi();
  const a = {text: btn.textContent, modus: trackerModus};
  trackerSeen = Date.now() - 16 * 60000;           // 2 Minuten später, kein neuer Punkt
  refreshTrackerUi();
  return {a, b: {text: btn.textContent, modus: trackerModus, warn: log[log.length-1][0], msg: log[log.length-1][1]}};
`;
console.log(JSON.stringify(new Function('btn', 'log', body)(btn, log)));
"""


@unittest.skipUnless(shutil.which('node'), 'node fehlt')
class ClientVorfahrtTest(unittest.TestCase):
    def _run(self, harness):
        fd, path = tempfile.mkstemp(suffix='.js')
        os.write(fd, harness.encode()); os.close(fd)
        try:
            r = subprocess.run(['node', path, LIVE], capture_output=True, text=True, timeout=60)
        finally:
            os.unlink(path)
        self.assertEqual(r.returncode, 0, r.stderr[:800])
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_umschalten_in_den_tracker_modus(self):
        d = self._run(HARNESS)
        self.assertEqual(d['ohneTracker'], {'text': '⏹ Fahrt beenden', 'started': 1, 'sharing': True})
        t = d['trackerKommt']
        self.assertEqual(t['text'], '📡 Tracker-App läuft')
        self.assertEqual(t['stopped'], 1, 'laufende Browser-Fahrt muss stoppen')
        self.assertFalse(t['sharing'])
        self.assertTrue(t['modus'] and t['info'])
        self.assertTrue(t['status'].startswith('📡 Tracker-App läuft'))
        self.assertEqual(d['knopfImTrackerModus'], {'started': 0, 'sharing': False, 'hinweis': True})
        self.assertFalse(d['fremderTracker']['modus'], 'Tracker eines anderen zählt nicht für mich')
        self.assertTrue(d['altWert']['modus'], 'älterer Wert darf den frischen nicht überschreiben')

    def test_zurueck_wenn_tracker_still(self):
        d = self._run(HARNESS_STILL)
        self.assertEqual(d['a'], {'text': '📡 Tracker-App läuft', 'modus': True})
        self.assertEqual(d['b']['text'], '▶ Fahrt starten')
        self.assertFalse(d['b']['modus'])
        self.assertEqual(d['b']['warn'], 'warning')
        self.assertIn('still', d['b']['msg'])

    def test_update_antwort_tracker_wird_beachtet(self):
        with open(LIVE, encoding='utf-8') as f:
            js = f.read()
        self.assertIn("if (d.tracker) {", js)
        self.assertIn("noteTrackerAgo(d.tracker_ago != null ? d.tracker_ago : 0);", js)
        self.assertIn("if (trackerAktiv()) { refreshTrackerUi(); return; }", js)   # startShare
        self.assertIn("noteTrackerLocs(lastLocs);", js)                             # render
        self.assertIn("' · 📡 Tracker'", js)                                        # Tooltip


class StempelTest(unittest.TestCase):
    def test_build_ci(self):
        self.assertGreaterEqual(appmod.APP_BUILD, '2026-11-12 ci')
