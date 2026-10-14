"""Touren: Anlegen, RSVP, GPX-Kennzahlen, Archiv, „Nochmal fahren“, Anwesenheit, Kalender."""
import datetime as dt
import os

from tests.base import AppTestCase, app, appmod, db, M, make_gpx, FAR_FUTURE


class TourenTest(AppTestCase):

    # ── Anlegen / Bearbeiten ──
    def test_create_tour_with_einkehr(self):
        self.login_org()
        html = self.get_html('/touren/neu')
        self.assertIn('name="gastro_spot_id"', html)
        r = self.client.post('/touren/neu', data={
            'title': 'Neue Tour', 'tour_date': (dt.date.today() + dt.timedelta(days=14)).isoformat(),
            'difficulty': 'mittel', 'start_time': '09:30', 'meeting_desc': 'Marktplatz',
            'gastro_spot_id': str(self.spot_id), 'einkehr_text': 'Kuchen vorbestellt'})
        self.assertIn(r.status_code, (302, 303))
        t = M.Tour.query.filter_by(title='Neue Tour').first()
        self.assertIsNotNone(t)
        self.assertEqual((t.gastro_spot_id, t.einkehr_text, t.status), (self.spot_id, 'Kuchen vorbestellt', 'planned'))
        html = self.get_html(f'/touren/{t.id}')
        self.assertIn('Café Deichblick', html)
        self.assertIn('Kuchen vorbestellt', html)

    def test_create_requires_title_and_valid_date(self):
        self.login_org()
        before = M.Tour.query.count()
        self.client.post('/touren/neu', data={'title': '', 'tour_date': '2030-01-01', 'difficulty': 'mittel'})
        self.client.post('/touren/neu', data={'title': 'X', 'tour_date': 'kein-datum', 'difficulty': 'mittel'})
        self.assertEqual(M.Tour.query.count(), before)

    def test_member_cannot_edit_or_create(self):
        self.login_member()
        self.assertIn(self.client.get(f'/touren/{self.t_plan_id}/bearbeiten').status_code, (302, 403))
        self.assertIn(self.client.post(f'/touren/{self.t_plan_id}/einkehr', json={'spot_id': self.spot_id}).status_code,
                      (302, 403))

    def test_einkehr_ruhetag_warning(self):
        """Mühle hat montags Ruhetag → Tour an einem Montag zeigt die Warnung."""
        self.login_org()
        today = dt.date.today()
        monday = today + dt.timedelta(days=(7 - today.weekday()) % 7 or 7)
        r = self.client.post(f'/touren/{self.t_plan_id}/bearbeiten', data={
            'title': 'Deichtour, mit Komma', 'tour_date': monday.isoformat(), 'difficulty': 'mittel',
            'gastro_spot_id': str(self.spot2_id)})
        self.assertIn(r.status_code, (302, 303))
        html = self.get_html(f'/touren/{self.t_plan_id}')
        self.assertIn('Zur alten Mühle', html)
        self.assertIn('Ruhetag am Tourtag?', html)
        self.assertIn('Ruhetag', appmod._tour_einkehr_text(self.tour(self.t_plan_id)))
        # per JSON wieder entfernen (Knopf ✕ / Karte)
        r = self.client.post(f'/touren/{self.t_plan_id}/einkehr', json={'spot_id': ''})
        self.assertEqual(r.get_json()['spot_id'], None)

    # ── Teilnahme ──
    def test_rsvp(self):
        self.login_member()
        r = self.client.post(f'/touren/{self.t_plan_id}/rsvp', data={'status': 'attending'})
        self.assertIn(r.status_code, (302, 303))
        p = M.TourParticipant.query.filter_by(tour_id=self.t_plan_id, user_id=self.mem_id).first()
        self.assertEqual(p.status, 'attending')
        self.client.post(f'/touren/{self.t_plan_id}/rsvp', data={'status': 'declined'})
        db.session.expire_all()
        self.assertEqual(M.TourParticipant.query.filter_by(tour_id=self.t_plan_id, user_id=self.mem_id).first().status,
                         'declined')

    def test_self_confirm_window(self):
        today = dt.date.today()
        t = M.Tour(title='Gestern', tour_date=today - dt.timedelta(days=1), status='planned',
                   group_id=self.g1_id, created_by=self.org_id)
        t_old = M.Tour(title='Vor einer Woche', tour_date=today - dt.timedelta(days=7), status='completed',
                       group_id=self.g1_id, created_by=self.org_id)
        db.session.add_all([t, t_old])
        db.session.commit()
        tid, old_id = t.id, t_old.id
        self.login_member()
        html = self.get_html(f'/touren/{tid}')
        self.assertIn('Ich war dabei', html)
        r = self.client.post(f'/touren/{tid}/ich-war-dabei')
        self.assertIn(r.status_code, (302, 303))
        p = M.TourParticipant.query.filter_by(tour_id=tid, user_id=self.mem_id).first()
        self.assertTrue(p and p.confirmed_present and p.status == 'attending')
        self.assertIn('Du warst dabei', self.get_html(f'/touren/{tid}'))
        # außerhalb des Fensters: keine Änderung
        self.client.post(f'/touren/{old_id}/ich-war-dabei')
        self.assertIsNone(M.TourParticipant.query.filter_by(tour_id=old_id, user_id=self.mem_id).first())
        self.assertNotIn('id="ich-war-dabei"', self.get_html(f'/touren/{self.t_plan_id}'))

    def test_attendance_reminder(self):
        today = dt.date.today()
        t = M.Tour(title='Offen von gestern', tour_date=today - dt.timedelta(days=1), status='planned',
                   group_id=self.g1_id, created_by=self.org_id)
        db.session.add(t)
        self.ensure_participant(self.t_done_id, self.mem2_id)
        db.session.commit()
        tid = t.id
        n = appmod._run_attendance_reminders(force=True)
        self.assertEqual(n, 1, 'nur die offene Tour der letzten 3 Tage ist fällig')
        emails = sorted(p[0] for p in self.pushes)
        self.assertEqual(emails, ['admin@test.de', 'orga@test.de'])
        self.assertIn('Wer war dabei', self.pushes[0][1])
        self.assertEqual(self.pushes[0][3], f'/touren/{tid}#anwesenheit')
        self.assertIsNotNone(self.tour(tid).attendance_reminded_at)
        self.assertEqual(appmod._run_attendance_reminders(force=True), 0, 'keine doppelte Erinnerung')
        # Organisator sieht den Hinweis in der Übersicht und das aufgeklappte Formular
        self.login_org()
        self.assertIn('id="anwesenheit-offen"', self.get_html('/touren'))
        self.assertIn('id="anwesenheit"', self.get_html(f'/touren/{tid}'))
        self.login_member()
        self.assertNotIn('id="anwesenheit-offen"', self.get_html('/touren'))

    def test_attendance_mail_fallback(self):
        t = M.Tour(title='Ohne Push', tour_date=dt.date.today(), status='planned',
                   group_id=self.g1_id, created_by=self.org_id)
        db.session.add(t)
        db.session.commit()
        appmod.send_push_to_user.side_effect = lambda *a, **k: (0, 0)
        self.assertEqual(appmod._run_attendance_reminders(force=True), 1)
        self.assertEqual(len(self.mails), 1)
        self.assertEqual(self.mails[0][0], 'orga@test.de')
        self.assertIn('Ohne Push', self.mails[0][1])

    def test_confirm_participants_form(self):
        self.login_org()
        self.ensure_participant(self.t_done_id, self.mem2_id)
        db.session.commit()
        r = self.client.post(f'/touren/{self.t_done_id}/bestaetigen',
                             data={'confirmed': [str(self.mem2_id)]})
        self.assertIn(r.status_code, (302, 303))
        db.session.expire_all()
        confirmed = {p.user_id for p in M.TourParticipant.query.filter_by(tour_id=self.t_done_id) if p.confirmed_present}
        self.assertEqual(confirmed, {self.mem2_id})

    # ── GPX, Kennzahlen, Archiv ──
    def test_gpx_upload_sets_metrics(self):
        self.login_org()
        r = self.upload_gpx(self.t_plan_id, make_gpx())
        self.assertIn(r.status_code, (302, 303))
        t = self.tour(self.t_plan_id)
        self.assertTrue(t.gpx_file and os.path.isfile(os.path.join(app.config['UPLOAD_FOLDER_GPX'], t.gpx_file)))
        self.assertGreater(t.gpx_km, 10)
        self.assertTrue(2500 < t.gpx_moving_s < 2800, t.gpx_moving_s)      # 120 × 22 s ohne die 10-min-Pause
        self.assertTrue(15 < t.gpx_avg_kmh < 21, t.gpx_avg_kmh)
        self.assertRegex(t.gpx_preview, r'^\d+,\d+\|(\d+,\d+ ?)+$')
        html = self.get_html(f'/touren/{self.t_plan_id}')
        self.assertIn('Fahrzeit', html)
        self.assertIn('Ø km/h', html)

    def test_lazy_metrics_and_admin_backfill(self):
        """Bestandstour ohne Kennzahlen: Detailseite rechnet nach; Admin-Knopf macht den Rest."""
        t = self.tour(self.t_done_id)
        t.gpx_preview = None
        t.gpx_moving_s = None
        db.session.commit()
        self.login_member()
        self.get_html(f'/touren/{self.t_done_id}')
        db.session.expire_all()
        t = self.tour(self.t_done_id)
        self.assertTrue(t.gpx_preview and t.gpx_moving_s)
        t.gpx_preview = None
        db.session.commit()
        self.login_admin()
        r = self.client.post('/admin/gpx-kennzahlen', follow_redirects=True)
        self.assertIn('GPX-Kennzahlen: 1 Touren berechnet', r.get_data(as_text=True))

    def test_archive_shows_preview_and_repeat(self):
        self.login_org()
        self.get_html(f'/touren/{self.t_done_id}')          # berechnet die Streckenvorschau nach (lazy)
        html = self.get_html('/archiv')
        self.assertIn('Alte Marschtour', html)
        self.assertIn('<svg class="track-mini', html)
        self.assertIn(f'/touren/{self.t_done_id}/nochmal', html)
        html = self.get_html('/archiv/suche?q=Marsch')
        self.assertIn('Alte Marschtour', html)

    def test_repeat_tour(self):
        self.login_member()
        self.assertIn(self.client.post(f'/touren/{self.t_done_id}/nochmal').status_code, (302, 403))
        self.login_org()
        before = M.Tour.query.count()
        r = self.client.post(f'/touren/{self.t_done_id}/nochmal')
        self.assertIn(r.status_code, (302, 303))
        self.assertEqual(M.Tour.query.count(), before + 1)
        new = M.Tour.query.order_by(M.Tour.id.desc()).first()
        src = self.tour(self.t_done_id)
        self.assertEqual((new.title, new.status, new.tour_date), (src.title, 'planned', FAR_FUTURE))
        self.assertTrue(new.gpx_file and new.gpx_file != src.gpx_file)
        self.assertTrue(os.path.isfile(os.path.join(app.config['UPLOAD_FOLDER_GPX'], new.gpx_file)))
        self.assertEqual(new.participants.count(), 0)

    def test_rueckblick(self):
        self.login_member()
        year = (dt.date.today() - dt.timedelta(days=30)).year
        r = self.client.get(f'/rueckblick/{year}')
        if r.status_code == 404:
            r = self.client.get(f'/rueckblick?year={year}')
        self.assertEqual(r.status_code, 200)
        self.assertIn('Fahrzeit gesamt', r.get_data(as_text=True))

    # ── Kalender ──
    def test_calendar_feed(self):
        self.login_member()
        html = self.get_html('/profil/bearbeiten')
        self.assertIn('id="kalender"', html)
        token = self.user(self.mem_id).calendar_token
        self.assertTrue(token and len(token) >= 20)
        self.assertIn(f'/kalender/{token}.ics', html)
        anon = app.test_client()
        r = anon.get(f'/kalender/{token}.ics')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.headers['Content-Type'].startswith('text/calendar'))
        body = r.get_data(as_text=True)
        self.assertTrue(body.startswith('BEGIN:VCALENDAR\r\n') and body.endswith('END:VCALENDAR\r\n'))
        unfolded = body.replace('\r\n ', '')
        self.assertIn(f'UID:tour-{self.t_plan_id}@dejungenolen', unfolded)
        self.assertIn('SUMMARY:🚴 Deichtour\\, mit Komma', unfolded)
        self.assertIn('STATUS:CANCELLED', unfolded)
        self.assertNotIn(f'UID:tour-{self.t_fremd_id}@', unfolded)        # andere Gruppe
        self.assertNotIn(f'UID:tour-{self.t_open_id}@', unfolded)         # Datum offen
        self.assertTrue(all(len(line.encode()) <= 75 for line in body.split('\r\n')), 'ICS-Zeilen ≤ 75 Oktette')
        self.assertEqual(anon.get('/kalender/' + 'x' * 24 + '.ics').status_code, 404)
        # Link erneuern → alter Link tot
        self.client.post('/profil/kalender/erneuern')
        db.session.expire_all()
        new_token = self.user(self.mem_id).calendar_token
        self.assertNotEqual(new_token, token)
        self.assertEqual(anon.get(f'/kalender/{token}.ics').status_code, 404)
        self.assertEqual(anon.get(f'/kalender/{new_token}.ics').status_code, 200)

    def test_single_ics(self):
        self.login_member()
        r = self.client.get(f'/touren/{self.t_plan_id}/ical')
        self.assertEqual(r.status_code, 200)
        self.assertIn('attachment', r.headers.get('Content-Disposition', ''))
        self.assertIn(f'UID:tour-{self.t_plan_id}@dejungenolen', r.get_data(as_text=True))

    # ── Großschrift ──
    def test_large_text_toggle(self):
        self.login_member()
        html = self.get_html('/touren')
        self.assertIn('<html lang="de">', html)
        r = self.client.post('/profil/grossschrift', headers={'Referer': 'http://localhost/archiv'})
        self.assertTrue(r.headers['Location'].endswith('/archiv'))
        html = self.get_html('/touren')
        self.assertIn('<html lang="de" class="big-text">', html)
        self.assertIn('Normale Schrift', html)
        self.client.post('/profil/grossschrift')
        db.session.expire_all()
        self.assertFalse(self.user(self.mem_id).large_text)
