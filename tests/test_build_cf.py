"""Build cf (Audit 9): Lücken im Tracking – mit und ohne Stromsparmodus.

Auftrag: „Mache ein komplettes Audit, gibt es irgendwo Lücken in den Funktionen? Check auch ob
das Tracken mit und ohne Stromsparmodus optimal funktioniert."

Gefunden (alles am echten Code aus `templates/touren/live.html` bzw. `app.py` nachgestellt):

1. **Aussetzer-Filter maß Fix gegen SENDUNG** (Build bv). `moved` ist die Strecke seit dem zuletzt
   GESENDETEN Punkt, `dtFixS` die Zeit seit dem letzten FIX. Nach drei übersprungenen Fixen lag
   der Quotient über 120 km/h, der Fix flog raus – und weil `lastPos` dann nicht nachrückte, blieb
   es dabei. Gemessen: GPS jede Sekunde, 25 km/h, Normalmodus → **1 Punkt auf 4,2 km**;
   40 km/h bei 3-s-Fixen → 1 Punkt auf 6,6 km. Jetzt: Fix gegen Fix (`lastFixPos`).
2. **Nachsenden schickte nur 60 Punkte je Aufwachen.** 300 im Puffer → 60 gesendet, 240 blieben.
   Jetzt: Blöcke bis der Puffer leer ist; Start auch aus dem 5-s-Wächter, beim `online`-Event,
   nach jeder erfolgreichen Normalsendung, beim Laden und beim Beenden.
3. **Nach „Beenden" waren liegen gebliebene Punkte verloren** (`!sharing` + Siegel 409).
   Jetzt: Der Server nimmt Punkte mit Aufnahmezeit VOR dem Ende noch in die Aufzeichnung
   (kein Standort-Update → kein Zombie); der Client sendet auch ohne `sharing` nach.
4. **Ein endgültig abgelehnter Punkt (403/409) blockierte den ganzen Lauf** für immer.
   Jetzt: wird aus dem Puffer genommen, der Lauf geht weiter.
5. **Server-Dublettenfilter 3 s** verwarf die Kurven-Sofortsendung bei 1-s-GPS (66 von 365
   Punkten einer 30-min-Runde) und **jeden Nachzügler, der nach einem frischen Punkt ankam**
   (dt negativ). Jetzt 1 s, und ältere Punkte werden zeitrichtig einsortiert.
6. `at = 1e30` oder `NaN` → OverflowError/ValueError → **HTTP 500**. Jetzt 200 (Zeit ignoriert).
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


def _live():
    with open(LIVE, encoding='utf-8') as f:
        return f.read()


# ── Teil 1: der echte Sendepfad (Auto-Pause + Aussetzer-Filter + Drossel) in Node ──────────────
HARNESS = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
eval(src.match(/function _bearing\(a, b\) \{[\s\S]*?\n\}/)[0]);
const consts = src.match(/const PAUSE_DIST_M = \d+, PAUSE_AFTER_S = \d+, PAUSE_RESUME_M = \d+;/)[0];
const start = src.indexOf('  const now = Date.now();\n  if (!moveAnchor)');
const ende = src.indexOf('lastSent = now; lastPos = ownLatLng;', start) + 'lastSent = now; lastPos = ownLatLng;'.length;
if (start < 0 || ende < 40) { console.error('Block nicht gefunden'); process.exit(1); }
const block = src.slice(start, ende).replace('const now = Date.now();', '');
const DIST = (a,b)=>Math.hypot((b[0]-a[0])*111320,(b[1]-a[1])*111320*Math.cos(a[0]*Math.PI/180));
const step = new Function('S','now','ownLatLng','dtFixS','_bearing','DIST', consts + `
  const map={distance:DIST}; const setStatus=()=>{}; const updatePauseBtn=()=>{};
  let {manualPause,autoPause,moveAnchor,moveAnchorAt,pauseSince,pauseLatLng,saverOn,lastPos,prevSentPos,lastSent,lastFixPos}=S;
  const isPaused=()=>manualPause||autoPause;
  let sent=false;
  (function(){ ${block}; sent=true; })();
  Object.assign(S,{manualPause,autoPause,moveAnchor,moveAnchorAt,pauseSince,pauseLatLng,lastPos,prevSentPos,lastSent,lastFixPos});
  return {sent, paused: isPaused()};`);
function run(fixes, saver){
  const S={manualPause:false,autoPause:false,moveAnchor:null,moveAnchorAt:0,pauseSince:0,pauseLatLng:null,
           saverOn:saver,lastPos:null,prevSentPos:null,lastSent:0,lastFixPos:null};
  let last=0, out=[];
  for(const f of fixes){ const d=last?Math.max(0.5,(f.t-last)/1000):0; last=f.t;
    const r=step(S,f.t,[f.lat,f.lng],d,_bearing,DIST); if(r.sent&&!r.paused) out.push(f); }
  return out;
}
const LAT0=53.55,LNG0=9.98, m2lat=1/111320, m2lng=1/(111320*Math.cos(LAT0*Math.PI/180));
let seed=42; const rnd=()=>{seed=(seed*1664525+1013904223)%4294967296;return seed/4294967296;};
const gauss=()=>{const u=rnd()||1e-9,v=rnd();return Math.sqrt(-2*Math.log(u))*Math.cos(2*Math.PI*v);};
function ride(segments, dtS, noise){
  const f=[]; let t=0,x=0,y=0,k=0;
  for(const s of segments){ for(let i=0;i<s.secs;i+=dtS){ const v=s.kmh/3.6; k+=(s.turn||0)*dtS;
    x+=Math.cos(k*Math.PI/180)*v*dtS; y+=Math.sin(k*Math.PI/180)*v*dtS; t+=dtS;
    f.push({t:t*1000,lat:LAT0+(y+gauss()*noise)*m2lat,lng:LNG0+(x+gauss()*noise)*m2lng,tx:x,ty:y}); } }
  return f;
}
function trueLen(f){let s=0;for(let i=1;i<f.length;i++)s+=Math.hypot(f[i].tx-f[i-1].tx,f[i].ty-f[i-1].ty);return s;}
function sentLen(a){let s=0;for(let i=1;i<a.length;i++)s+=DIST([a[i-1].lat,a[i-1].lng],[a[i].lat,a[i].lng]);return s;}
const curvy=(secs,kmh)=>{const seg=[];let t=0;while(t<secs){seg.push({secs:60,kmh});seg.push({secs:12,kmh,turn:7.5});t+=72;}return seg;};
const out={};
function mess(name, fixes){ for(const saver of [false,true]){ const o=run(fixes,saver);
  out[name+(saver?'|spar':'|normal')]={fixes:fixes.length,gesendet:o.length,spurM:Math.round(sentLen(o)),echtM:Math.round(trueLen(fixes))}; } }
mess('25kmh_1s', ride([{secs:600,kmh:25}],1,3));
mess('40kmh_3s', ride([{secs:600,kmh:40}],3,3));
mess('abfahrt45_kurvig', ride(curvy(600,45),3,4));
mess('radtour18_kurvig', ride(curvy(1800,18),3,4));
{ const f=ride([{secs:600,kmh:18}],3,3); f[100].lat+=200*m2lat; mess('aussetzer200m', f); }
console.log(JSON.stringify(out));
"""


@unittest.skipUnless(shutil.which('node'), 'node fehlt')
class SendepfadSimulationTest(unittest.TestCase):
    """Der komplette Sendepfad aus live.html gegen simulierte Fahrten – mit und ohne Sparmodus."""

    @classmethod
    def setUpClass(cls):
        fd, path = tempfile.mkstemp(suffix='.js')
        os.write(fd, HARNESS.encode()); os.close(fd)
        try:
            r = subprocess.run(['node', path, LIVE], capture_output=True, text=True, timeout=60)
        finally:
            os.unlink(path)
        assert r.returncode == 0, r.stderr[:600]
        cls.d = json.loads(r.stdout.strip().splitlines()[-1])

    def _ok(self, key, min_pts, max_fehler=0.06):
        m = self.d[key]
        self.assertGreaterEqual(m['gesendet'], min_pts, m)
        self.assertLess(abs(m['spurM'] / m['echtM'] - 1), max_fehler, m)

    def test_25_kmh_mit_1s_gps_normalmodus(self):
        """Vorher: 1 Punkt auf 4,2 km (Filter sperrte dauerhaft). Jetzt: Spur vollständig."""
        self._ok('25kmh_1s|normal', 80)
        self._ok('25kmh_1s|spar', 120)

    def test_40_kmh_mit_3s_gps(self):
        """Vorher Normalmodus: 1 Punkt auf 6,6 km."""
        self._ok('40kmh_3s|normal', 45)
        self._ok('40kmh_3s|spar', 90)

    def test_abfahrt_45_kmh_kurvig(self):
        """Vorher Normalmodus: 9 von 216 Fixen, Spur 0,35 statt 8,06 km (−95,6 %)."""
        self._ok('abfahrt45_kurvig|normal', 60)
        self._ok('abfahrt45_kurvig|spar', 100)

    def test_radtour_18_kmh_beide_modi(self):
        self._ok('radtour18_kurvig|normal', 200)
        self._ok('radtour18_kurvig|spar', 300)

    def test_aussetzer_wird_weiter_uebersprungen(self):
        """Der Zweck des Filters bleibt: 200 m quer ist kein Punkt – in beiden Modi."""
        for k in ('aussetzer200m|normal', 'aussetzer200m|spar'):
            m = self.d[k]
            self.assertLess(abs(m['spurM'] / m['echtM'] - 1), 0.03, m)   # 400 m Zickzack wären +13 %

    def test_sparmodus_liefert_mehr_punkte_als_normal(self):
        for n in ('25kmh_1s', '40kmh_3s', 'abfahrt45_kurvig', 'radtour18_kurvig'):
            self.assertGreater(self.d[n + '|spar']['gesendet'], self.d[n + '|normal']['gesendet'], n)


class AussetzerFilterCodeTest(unittest.TestCase):
    def test_misst_fix_gegen_fix(self):
        js = _live()
        self.assertIn('let lastFixPos = null;', js)
        self.assertIn('const seitFixM = lastFixPos ? map.distance(lastFixPos, ownLatLng) : 0;', js)
        self.assertIn('const kmhFix = (lastFixPos && dtFixS) ? seitFixM / dtFixS * 3.6 : 0;', js)
        self.assertIn('if (kmhFix > 120 && seitFixM > 60) {', js)
        self.assertNotIn('moved / dtFixS', js)

    def test_lastfixpos_rueckt_nach_dem_filter_nach(self):
        js = _live()
        a = js.index('if (kmhFix > 120 && seitFixM > 60) {')
        b = js.index('lastFixPos = ownLatLng;', a)
        self.assertLess(b - a, 300)                       # direkt nach dem Filter, vor der Drossel
        self.assertLess(b, js.index('const sendEvery = saverOn', a))


# ── Teil 2: Nachsenden – echte Funktion aus dem Template, fetch simuliert ──────────────────────
NACHSEND = r"""
const fs=require('fs'); const src=fs.readFileSync(process.argv[2],'utf8');
const s=src.indexOf('let nachsendenLaeuft = false;');
const e=src.indexOf('\n}\n', src.indexOf('function sicherNachsenden'))+3;
const code=src.slice(s,e);
const modus=process.argv[3];
let sent=0, calls=[];
global.fetch=async(url,opt)=>{ const b=JSON.parse(opt.body); calls.push(b);
  if(modus==='netzweg' && calls.length>5) throw new Error('offline');
  if(modus==='ein409' && b.lng===9.5) return {ok:false,status:409,json:async()=>({})};
  if(modus==='server500' && calls.length>5) return {ok:false,status:500,json:async()=>({})};
  sent++; return {ok:true,json:async()=>({})}; };
global.localStorage={removeItem(){},setItem(){}};
let gesichert=[]; const n=parseInt(process.argv[4]||'300',10);
const base=Date.now()-n*6000-1000;
for(let i=0;i<n;i++) gesichert.push({id:'p'+i, lat:53, lng:(i===5?9.5:9), at:base+(i+1)*6000 - (modus==='alt'&&i<10 ? 8*3600*1000 : 0)});
const ctx={TOUR_ID:1, trailSince:0, sharing:false, render(){}, addTrails(){}, sicherSpeichern(){}, SICHER_KEY:'k'};
const fn=new Function(...Object.keys(ctx),'gesichert', code+'\nreturn {sicherNachsenden, rest:()=>gesichert};');
const r=fn(...Object.values(ctx), gesichert);
(async()=>{ r.sicherNachsenden(); await new Promise(x=>setTimeout(x,300));
  console.log(JSON.stringify({gesendet:sent, offen:r.rest().length, ats:calls.map(c=>c.at)})); })();
"""


@unittest.skipUnless(shutil.which('node'), 'node fehlt')
class NachsendenTest(unittest.TestCase):
    def _lauf(self, modus, n=300):
        fd, path = tempfile.mkstemp(suffix='.js')
        os.write(fd, NACHSEND.encode()); os.close(fd)
        try:
            r = subprocess.run(['node', path, LIVE, modus, str(n)], capture_output=True, text=True, timeout=60)
        finally:
            os.unlink(path)
        self.assertEqual(r.returncode, 0, r.stderr[:600])
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_puffer_wird_ganz_geleert(self):
        """Vorher: 300 im Puffer → 60 gesendet, 240 offen. Jetzt alles, in Aufnahme-Reihenfolge."""
        d = self._lauf('ok', 300)
        self.assertEqual((d['gesendet'], d['offen']), (300, 0))
        self.assertEqual(d['ats'], sorted(d['ats']))

    def test_auch_ohne_sharing(self):
        """Nach „Beenden" (sharing=false) wird trotzdem nachgesendet – der Harness setzt sharing=false."""
        self.assertEqual(self._lauf('ok', 5)['gesendet'], 5)

    def test_endgueltig_abgelehnter_punkt_blockiert_nicht(self):
        """Ein 409 für einen Punkt: der fliegt raus, die anderen 299 kommen durch."""
        d = self._lauf('ein409', 300)
        self.assertEqual((d['gesendet'], d['offen']), (299, 0))

    def test_netzabbruch_behaelt_den_rest(self):
        d = self._lauf('netzweg', 100)
        self.assertEqual(d['gesendet'], 5)
        self.assertEqual(d['offen'], 95)

    def test_serverfehler_behaelt_den_rest(self):
        d = self._lauf('server500', 100)
        self.assertEqual((d['gesendet'], d['offen']), (5, 95))

    def test_zu_alte_punkte_werden_verworfen(self):
        """Älter als 6 h nimmt der Server nicht mit Aufnahmezeit – sie würden nur Müll erzeugen."""
        d = self._lauf('alt', 50)
        self.assertEqual((d['gesendet'], d['offen']), (40, 0))


class NachsendenAusloeserTest(unittest.TestCase):
    def test_ausloeser_vorhanden(self):
        js = _live()
        self.assertIn("window.addEventListener('online', () => sicherNachsenden());", js)
        self.assertIn('if (gesichert.length && navigator.onLine !== false) sicherNachsenden();', js)   # wachTick
        self.assertIn('if (gesichert.length) sicherNachsenden();      // Build cf: Rest aus einem Funkloch', js)
        stop = js.index('function stopShare(')
        self.assertIn('if (gesichert.length) sicherNachsenden();   // Build cf', js[stop:stop + 1200])
        self.assertIn('if (gesichert.length) sicherNachsenden();                        // Build cf: Rest einer früheren Sitzung', js)

    def test_nachsenden_vor_dem_siegel(self):
        js = _live()
        stop = js.index('function stopShare(')
        self.assertLess(js.index('sicherNachsenden();', stop), js.index("'/api/location/stop?tour_id='", stop))


# ── Teil 3: Server ────────────────────────────────────────────────────────────────────────────
class ServerTest(AppTestCase):
    def setUp(self):
        super().setUp()
        M.LiveTrackPoint.query.delete(); M.LiveStop.query.delete(); M.LiveLocation.query.delete()
        db.session.commit()
        self.tid = self.t_plan.id
        self.login_org()            # Organisatoren dürfen jederzeit fahren – das Zeitfenster ist hier nicht Thema
        self.uid = self.org.id

    def _post(self, **kw):
        body = {'tour_id': self.tid, 'lat': 53.4, 'lng': 9.8, 'accuracy': 8}
        body.update(kw)
        return self.client.post('/api/location/update', json=body)

    def _n(self):
        return M.LiveTrackPoint.query.filter_by(tour_id=self.tid).count()

    def test_unsinnige_aufnahmezeit_gibt_keinen_500(self):
        """Vorher: OverflowError bzw. ValueError → HTTP 500."""
        for at in (1e30, -1e30, float('nan'), 'x'):
            r = self._post(at=at)
            self.assertEqual(r.status_code, 200, at)
        r = self.client.post('/api/location/update', data='{"tour_id": %d, "lat": 53.4, "lng": 9.8, "at": NaN}' % self.tid,
                             content_type='application/json')
        self.assertEqual(r.status_code, 200)

    def test_nachzuegler_nach_dem_ende_werden_aufgezeichnet(self):
        """Display aus → Beenden → Puffer: Punkte mit `at` vor dem Ende kommen in die Spur,
        aber nicht als Standort (kein Zombie). Punkte mit `at` nach dem Ende: weiter 409."""
        t0 = dt.datetime.utcnow() - dt.timedelta(minutes=10)
        ms = lambda d: int(d.replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
        self.assertEqual(self._post(at=ms(t0), resume=True).status_code, 200)
        self.assertEqual(self.client.post(f'/api/location/stop?tour_id={self.tid}').status_code, 200)
        self.assertIsNone(M.LiveLocation.query.filter_by(tour_id=self.tid, user_id=self.uid).first())
        vorher = self._n()
        r = self._post(at=ms(t0 + dt.timedelta(minutes=2)), lat=53.401)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json().get('late'))
        self.assertEqual(self._n(), vorher + 1)
        self.assertIsNone(M.LiveLocation.query.filter_by(tour_id=self.tid, user_id=self.uid).first(),
                          'Nachzügler darf keinen Standort anlegen')
        # Zombie: Aufnahmezeit jetzt (nach dem Ende) → 409 wie bisher; ohne at → 409
        self.assertEqual(self._post(at=ms(dt.datetime.utcnow()), lat=53.402).status_code, 409)
        self.assertEqual(self._post(lat=53.403).status_code, 409)
        self.assertEqual(self._n(), vorher + 1)

    def test_dubletten_filter_1s_statt_3s(self):
        """Kurven-Sofortsendung bei 1-s-GPS: Punkte 1,5 s auseinander müssen beide bleiben."""
        now = dt.datetime.utcnow()
        with app.test_request_context():
            self.assertTrue(appmod._live_track_add(self.tid, self.uid, 53.4, 9.8, 8.0, now))
            self.assertFalse(appmod._live_track_add(self.tid, self.uid, 53.40001, 9.8, 8.0,
                                                    now + dt.timedelta(milliseconds=400)))   # echte Dublette
            self.assertTrue(appmod._live_track_add(self.tid, self.uid, 53.40005, 9.8, 8.0,
                                                   now + dt.timedelta(milliseconds=1500)))
            self.assertTrue(appmod._live_track_add(self.tid, self.uid, 53.40010, 9.8, 8.0,
                                                   now + dt.timedelta(milliseconds=3000)))

    def test_aelterer_nachzuegler_wird_einsortiert(self):
        """Funkloch bei Display an: der frische Punkt kommt zuerst durch, der Rest danach.
        Vorher: dt negativ → „Doppelsendung" → weg. Jetzt: gespeichert, Dublette (gleiche Sekunde) nicht."""
        now = dt.datetime.utcnow()
        with app.test_request_context():
            self.assertTrue(appmod._live_track_add(self.tid, self.uid, 53.4, 9.8, 8.0, now - dt.timedelta(minutes=5)))
            self.assertTrue(appmod._live_track_add(self.tid, self.uid, 53.41, 9.8, 8.0, now))          # frisch
            self.assertTrue(appmod._live_track_add(self.tid, self.uid, 53.403, 9.8, 8.0, now - dt.timedelta(minutes=3)))
            self.assertTrue(appmod._live_track_add(self.tid, self.uid, 53.406, 9.8, 8.0, now - dt.timedelta(minutes=2)))
            self.assertFalse(appmod._live_track_add(self.tid, self.uid, 53.406, 9.8, 8.0,
                                                    now - dt.timedelta(minutes=2, milliseconds=-300)))     # Dublette
        rows = appmod._live_track_rows(self.tid, self.uid)
        self.assertEqual([round(r.lat, 3) for r in rows], [53.4, 53.403, 53.406, 53.41])

    def test_ganzer_puffer_ueber_http_zeitrichtig(self):
        """300 Punkte, 6 s Takt, Reihenfolge wie der Client sie schickt (sortiert) – alle da."""
        t0 = dt.datetime.utcnow() - dt.timedelta(minutes=35)
        ms = lambda d: int(d.replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
        for i in range(300):
            r = self._post(at=ms(t0 + dt.timedelta(seconds=6 * i)), lat=53.4 + i * 0.0003, resume=(i == 0))
            self.assertEqual(r.status_code, 200, i)
        self.assertEqual(self._n(), 300)


class StempelTest(unittest.TestCase):
    def test_build_cf(self):
        self.assertGreaterEqual(appmod.APP_BUILD, '2026-11-12 cf')
