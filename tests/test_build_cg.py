"""Build cg: Hintergrund-Tracking über die Tracker-App „Traccar Client".

Der Nutzer: „Wird noch getrackt wenn Display aus ist oder eine andere App genutzt wird?" – nein,
eine Webseite darf im Hintergrund nicht orten (watchPosition friert mit der Seite ein).
„Hintergrund Tracking wäre schon gut zu haben" · „traccar client habe ich eh schon installiert".

Traccar Client schickt jede Position per HTTP (OsmAnd-Protokoll) an eine frei wählbare URL:
  <Server-URL>?id=<Geräte-ID>&lat=…&lon=…&timestamp=<unix s>&speed=<Knoten>&bearing=…&accuracy=…
Neu: `/api/traccar` (Geräte-ID = persönlicher Token aus dem Profil, alternativ `/api/traccar/<token>`).
Die Punkte landen in derselben Aufzeichnung und auf derselben Live-Karte wie die aus dem Browser,
ohne „Fahren" zu drücken – die Tour ergibt sich aus dem Datum des Punktes (Tourtag ±1, heute zuerst).
"""
import datetime as dt
import unittest

from tests.base import AppTestCase, app, appmod, db
import models as M


def _ts(d):
    return int(d.replace(tzinfo=dt.timezone.utc).timestamp())


class TraccarTest(AppTestCase):
    def setUp(self):
        super().setUp()
        for cls in (M.LiveTrackPoint, M.LiveStop, M.LiveLocation):
            cls.query.delete()
        # Seed-Objekte sind nach dem Session-Wechsel losgelöst – frisch laden
        self.plan = db.session.get(M.Tour, self.t_plan.id)
        self.hein = db.session.get(M.User, self.mem.id)
        self.frd = db.session.get(M.User, self.fremd.id)
        self.plan.tour_date = dt.date.today()
        self.hein.tracker_token = 'tok-hein-123'
        self.frd.tracker_token = 'tok-fremd-456'
        db.session.commit()
        self.tid = self.plan.id

    def _push(self, token='tok-hein-123', method='get', path=None, **q):
        p = dict(lat=53.4, lon=9.8, timestamp=_ts(dt.datetime.utcnow()), accuracy=8)
        p.update(q)
        if token is not None:
            p.setdefault('id', token)
        url = path or '/api/traccar'
        return getattr(self.client, method)(url, query_string=p)

    # ── Zugang ────────────────────────────────────────────────────────────────────────────
    def test_unbekannter_token_404_kein_login_noetig(self):
        self.assertEqual(self._push(token='gibtsnicht').status_code, 404)
        self.assertEqual(self._push(token=None).status_code, 404)
        self.assertEqual(self._push().status_code, 200)        # ohne Login, nur Token

    def test_kaputte_koordinaten_400(self):
        self.assertEqual(self._push(lat='abc').status_code, 400)
        self.assertEqual(self._push(lat=95).status_code, 400)
        self.assertEqual(self._push(lat='nan').status_code, 400)

    def test_inaktiver_nutzer_404(self):
        self.hein.is_active = False
        db.session.commit()
        try:
            self.assertEqual(self._push().status_code, 404)
        finally:
            self.hein.is_active = True
            db.session.commit()

    # ── Kern: Punkt landet bei der Tour des Tages ─────────────────────────────────────────
    def test_punkt_landet_in_standort_und_spur(self):
        r = self._push(speed=10, bearing=90)       # 10 Knoten = 5,14 m/s
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertEqual(d['tour_id'], self.tid)
        self.assertTrue(d['recorded'])
        loc = M.LiveLocation.query.filter_by(tour_id=self.tid, user_id=self.mem.id).one()
        self.assertAlmostEqual(loc.speed, 5.144, places=2)
        self.assertEqual(loc.heading, 90)
        self.assertEqual(M.LiveTrackPoint.query.filter_by(tour_id=self.tid, user_id=self.mem.id).count(), 1)

    def test_post_und_pfad_token_gehen_auch(self):
        self.assertEqual(self._push(method='post').status_code, 200)
        r = self._push(token=None, path='/api/traccar/tok-hein-123', lat=53.41)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['tour_id'], self.tid)

    def test_kein_tourtag_wird_ignoriert_aber_200(self):
        """200 statt Fehler – sonst behält Traccar den Punkt im Puffer und schickt ihn endlos neu."""
        self.plan.tour_date = dt.date.today() + dt.timedelta(days=5)
        db.session.commit()
        r = self._push()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json().get('ignored'), 'kein Tourtag')
        self.assertEqual(M.LiveTrackPoint.query.count(), 0)
        self.assertEqual(M.LiveLocation.query.count(), 0)

    def test_tourtag_plus_minus_eins_heute_bevorzugt(self):
        heute = dt.date.today()
        self.plan.tour_date = heute - dt.timedelta(days=1)
        db.session.commit()
        self.assertEqual(self._push().get_json()['tour_id'], self.tid)          # gestern zählt noch
        t2 = M.Tour(title='Heute', tour_date=heute, group_id=self.mem.group_id, created_by=self.org.id,
                    status='planned')
        db.session.add(t2); db.session.commit()
        self.assertEqual(self._push(lat=53.41).get_json()['tour_id'], t2.id)    # heute vor gestern
        db.session.get(M.Tour, self.t_canc.id).tour_date = heute
        db.session.commit()
        self.assertEqual(self._push(lat=53.42).get_json()['tour_id'], t2.id)    # abgesagte nie

    def test_fremde_gruppe_bleibt_getrennt(self):
        db.session.get(M.Tour, self.t_fremd.id).tour_date = dt.date.today()
        db.session.commit()
        r = self._push(token='tok-fremd-456')
        self.assertEqual(r.get_json()['tour_id'], self.t_fremd.id)
        self.assertEqual(M.LiveLocation.query.filter_by(tour_id=self.tid).count(), 0)

    # ── Zeit ──────────────────────────────────────────────────────────────────────────────
    def test_aufnahmezeit_wird_uebernommen_nachzuegler_ueberschreiben_nicht(self):
        t0 = dt.datetime.utcnow() - dt.timedelta(minutes=30)
        self._push(timestamp=_ts(t0), lat=53.40)
        self._push(timestamp=_ts(t0 + dt.timedelta(minutes=20)), lat=53.42)       # frisch
        self._push(timestamp=_ts(t0 + dt.timedelta(minutes=10)), lat=53.41)       # Nachzügler aus dem Puffer
        loc = M.LiveLocation.query.filter_by(tour_id=self.tid).one()
        self.assertAlmostEqual(loc.lat, 53.42)                                      # bleibt der neueste
        pts = appmod._live_track_rows(self.tid, self.mem.id)
        self.assertEqual([round(p.lat, 2) for p in pts], [53.40, 53.41, 53.42])    # zeitrichtig einsortiert
        self.assertLess(abs((pts[0].recorded_at - t0).total_seconds()), 1)

    def test_unplausible_zeit_nimmt_ankunft(self):
        for raw in ('x', 1e30, _ts(dt.datetime.utcnow() + dt.timedelta(hours=3)),
                    _ts(dt.datetime.utcnow() - dt.timedelta(hours=20))):
            M.LiveTrackPoint.query.delete(); db.session.commit()
            r = self._push(timestamp=raw)
            self.assertEqual(r.status_code, 200, raw)
            p = M.LiveTrackPoint.query.first()
            self.assertLess(abs((p.recorded_at - dt.datetime.utcnow()).total_seconds()), 5, raw)

    def test_millisekunden_und_iso_zeit(self):
        t0 = dt.datetime.utcnow() - dt.timedelta(minutes=5)
        self._push(timestamp=_ts(t0) * 1000)
        self.assertLess(abs((M.LiveTrackPoint.query.first().recorded_at - t0).total_seconds()), 1)
        M.LiveTrackPoint.query.delete(); db.session.commit()
        self._push(timestamp=t0.replace(microsecond=0).isoformat() + 'Z', lat=53.41)
        self.assertLess(abs((M.LiveTrackPoint.query.first().recorded_at - t0).total_seconds()), 1)

    # ── Zusammenspiel mit „Beenden" in der App ─────────────────────────────────────────────
    def test_nach_beenden_nachzuegler_spur_dann_sperre_dann_neue_fahrt(self):
        self.login_member()
        self._push(timestamp=_ts(dt.datetime.utcnow() - dt.timedelta(minutes=5)))
        # Build ci: solange der Tracker aktiv ist, setzt „Beenden" im Browser kein Siegel –
        # hier den Tracker als 20 min still markieren, damit das Siegel entsteht.
        M.LiveLocation.query.filter_by(tour_id=self.tid).one().tracker_at = dt.datetime.utcnow() - dt.timedelta(minutes=20)
        db.session.commit()
        self.assertEqual(self.client.post(f'/api/location/stop?tour_id={self.tid}').status_code, 200)
        stop = M.LiveStop.query.filter_by(tour_id=self.tid, user_id=self.mem.id).one()
        # 1) Nachzügler von vor dem Ende → nur Spur, kein Standort
        r = self._push(timestamp=_ts(stop.stopped_at - dt.timedelta(minutes=2)), lat=53.401)
        self.assertTrue(r.get_json().get('late'))
        self.assertIsNone(M.LiveLocation.query.filter_by(tour_id=self.tid).first())
        # 2) kurz nach dem Ende → ignoriert (kein Zombie); Build cn: Luft nur noch 2 min
        r = self._push(timestamp=_ts(stop.stopped_at + dt.timedelta(minutes=1)), lat=53.402)
        self.assertEqual(r.get_json().get('ignored'), 'Fahrt beendet')
        self.assertIsNone(M.LiveLocation.query.filter_by(tour_id=self.tid).first())
        # 3) > 2 min danach (Build cn, vorher 10) → neue Fahrt, Siegel weg
        stop.stopped_at = dt.datetime.utcnow() - dt.timedelta(minutes=3)
        db.session.commit()
        r = self._push(lat=53.403)
        self.assertTrue(r.get_json().get('recorded'))
        self.assertIsNone(M.LiveStop.query.filter_by(tour_id=self.tid, user_id=self.mem.id).first())
        self.assertIsNotNone(M.LiveLocation.query.filter_by(tour_id=self.tid).first())

    # ── Sichtbar auf der Live-Karte und in der Zusammenfassung ────────────────────────────
    def test_erscheint_auf_live_karte_und_in_aufzeichnung(self):
        t0 = dt.datetime.utcnow() - dt.timedelta(minutes=20)
        for i in range(120):                                       # 20 min, 10-s-Takt, ~5 km
            self._push(timestamp=_ts(t0 + dt.timedelta(seconds=10 * i)), lat=53.4 + i * 0.0004)
        self.login_org()
        r = self.client.get(f'/api/location/tour/{self.tid}')
        self.assertEqual(r.status_code, 200)
        ids = [l['user_id'] for l in r.get_json()['locations']]
        self.assertIn(self.mem.id, ids)
        summ = appmod._live_track_summaries(self.tid)
        mine = next(d for d in summ if d['user_id'] == self.mem.id)
        self.assertEqual(mine['n'], 120)
        self.assertAlmostEqual(mine['km'], 5.3, delta=0.3)

    # ── Profil ────────────────────────────────────────────────────────────────────────────
    def test_profil_zeigt_url_und_token_und_erzeugt_ihn(self):
        self.hein.tracker_token = None
        db.session.commit()
        self.login_member()
        r = self.client.get('/profil/bearbeiten')
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        db.session.expire_all()
        tok = db.session.get(M.User, self.mem.id).tracker_token
        self.assertTrue(tok and len(tok) >= 12)
        self.assertIn(tok, html)
        self.assertIn('/api/traccar', html)
        self.assertIn('Traccar Client', html)
        self.assertIn('id="tracker"', html)

    def test_token_erneuern(self):
        self.login_member()
        r = self.client.post('/profil/tracker/erneuern', headers={'Origin': 'http://localhost'})
        self.assertEqual(r.status_code, 302)
        db.session.expire_all()
        neu = db.session.get(M.User, self.mem.id).tracker_token
        self.assertNotEqual(neu, 'tok-hein-123')
        self.assertEqual(self._push(token='tok-hein-123').status_code, 404)
        self.assertEqual(self._push(token=neu).status_code, 200)

    def test_build_stempel(self):
        self.assertGreaterEqual(appmod.APP_BUILD, '2026-11-12 cg')


if __name__ == '__main__':
    unittest.main()
