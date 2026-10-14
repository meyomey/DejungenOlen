"""Build ab – Audit-3-Pakete: Erinnerungen mit Uhrzeit, Absage/Reaktivierung, Änderung mitteilen,
Anmelde-Link, Notfallkontakt + Teilnehmerliste, Fahrgemeinschaften, Backup-Modi, GPX-Ausdünnung,
Service-Worker-Cache je Build, Telegram-Escaping, entfernte Routen."""
import datetime as dt
import io
import json
import os
import tarfile
import tempfile
import unittest
from unittest import mock

from tests.base import AppTestCase, appmod, app, db, M, make_gpx, PASSWORD

with app.app_context(), app.test_request_context():
    ADMIN_REMINDER_TEST_URL = appmod.url_for('admin_reminder_test')


class ReminderTest(AppTestCase):
    """A1/A2: Tourtag- und Vorabend-Erinnerung laufen erst ab der eingestellten Uhrzeit."""

    def _now(self, hour, day_offset=0):
        d = appmod._berlin_today() + dt.timedelta(days=day_offset)
        return dt.datetime(d.year, d.month, d.day, hour, 5)

    def _clear_flags(self):
        M.SiteConfig.query.filter(M.SiteConfig.key.like('%_reminder_sent_%')).delete(synchronize_session=False)
        M.SiteConfig.query.filter(M.SiteConfig.key.in_(
            ['reminder_morning_hour', 'reminder_evening_hour', 'reminder_evening_enabled'])).delete(
            synchronize_session=False)
        db.session.commit()

    def test_morning_reminder_respects_hour_gate(self):
        self._clear_flags()
        today = appmod._berlin_today()
        t = M.Tour(title='Heute <b>los</b>', tour_date=today, status='planned', start_time='10:00',
                   group_id=self.g1_id, created_by=self.org_id, meeting_desc='Dörphus')
        db.session.add(t)
        db.session.flush()
        self.ensure_participant(t.id, self.mem_id, 'attending')
        db.session.commit()
        try:
            # 06:05 Uhr → noch nichts (Standard 7 Uhr)
            self.assertEqual(appmod._run_tour_reminders(now=self._now(6)), 0)
            self.assertEqual(self.telegrams, [])
            self.assertNotEqual(appmod.cfg(f'morning_reminder_sent_{today.isoformat()}'), '1')
            # 07:05 Uhr → Versand + Flag; HTML im Titel ist escaped
            n = appmod._run_tour_reminders(now=self._now(7))
            self.assertGreaterEqual(n, 1)
            self.assertTrue(any('Heute ist Tourtag' in m for m in self.telegrams))
            msg = next(m for m in self.telegrams if 'Heute ist Tourtag' in m)
            self.assertIn('&lt;b&gt;los&lt;/b&gt;', msg)
            self.assertNotIn('<b>los</b>', msg)
            self.assertTrue(any(p[0] == 'hein@test.de' and 'Tour heute' in p[1] for p in self.pushes))
            self.assertEqual(appmod.cfg(f'morning_reminder_sent_{today.isoformat()}'), '1')
            # zweiter Lauf am selben Tag → nichts mehr
            before = len(self.telegrams)
            appmod._run_tour_reminders(now=self._now(9))
            self.assertEqual(len(self.telegrams), before)
        finally:
            M.TourParticipant.query.filter_by(tour_id=t.id).delete()
            db.session.delete(t)
            db.session.commit()

    def test_morning_hour_configurable_and_old_flags_cleaned(self):
        self._clear_flags()
        today = appmod._berlin_today()
        M.SiteConfig.set('reminder_morning_hour', '9')
        M.SiteConfig.set('morning_reminder_sent_2020-01-01', '1')      # Altlast
        db.session.commit()
        self.assertEqual(appmod._run_tour_reminders(now=self._now(8)), 0)
        self.assertNotEqual(appmod.cfg(f'morning_reminder_sent_{today.isoformat()}'), '1')
        appmod._run_tour_reminders(now=self._now(9))
        self.assertEqual(appmod.cfg(f'morning_reminder_sent_{today.isoformat()}'), '1')
        self.assertIsNone(M.SiteConfig.query.get('morning_reminder_sent_2020-01-01'))

    def test_evening_reminder_for_tomorrow(self):
        self._clear_flags()
        tomorrow = appmod._berlin_today() + dt.timedelta(days=1)
        t = M.Tour(title='Morgentour', tour_date=tomorrow, status='planned', start_time='09:30',
                   group_id=self.g1_id, created_by=self.org_id)
        db.session.add(t)
        db.session.flush()
        self.ensure_participant(t.id, self.mem_id, 'attending')
        self.ensure_participant(t.id, self.mem2_id, 'maybe')
        db.session.commit()
        try:
            self.assertEqual(appmod._run_tour_reminders(now=self._now(17)), 0)
            self.assertFalse(any('Morgen ist Tourtag' in m for m in self.telegrams))
            appmod._run_tour_reminders(now=self._now(18))
            self.assertTrue(any('Morgen ist Tourtag' in m and 'Morgentour' in m for m in self.telegrams))
            mails = sorted(p[0] for p in self.pushes if 'Morgen ist Tourtag' in p[1])
            self.assertEqual(mails, ['fiete@test.de', 'hein@test.de'])   # Dabei + Vielleicht
            self.assertEqual(appmod.cfg(f'evening_reminder_sent_{tomorrow.isoformat()}'), '1')
            # abgeschaltet → kein Versand
            self._clear_flags()
            M.SiteConfig.set('reminder_evening_enabled', '0')
            db.session.commit()
            self.telegrams.clear()
            appmod._run_tour_reminders(now=self._now(20))
            self.assertFalse(any('Morgen ist Tourtag' in m for m in self.telegrams))
        finally:
            M.TourParticipant.query.filter_by(tour_id=t.id).delete()
            db.session.delete(t)
            db.session.commit()

    def test_admin_reminder_settings_and_test_buttons(self):
        self.login_admin()
        r = self.client.post('/admin/benachrichtigungen/erinnerungen',
                             data={'reminder_morning_hour': '8', 'reminder_evening_hour': '19',
                                   'reminder_evening_enabled': '1'})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(appmod.cfg('reminder_morning_hour'), '8')
        self.assertEqual(appmod.cfg('reminder_evening_hour'), '19')
        html = self.get_html('/admin/benachrichtigungen')
        self.assertIn('name="reminder_morning_hour"', html)
        self.assertIn('value="8"', html)
        r = self.client.post(ADMIN_REMINDER_TEST_URL, data={'tour_id': self.t_plan_id, 'kind': 'evening'})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(any('Morgen ist Tourtag' in m for m in self.telegrams))
        self.login_member()
        r = self.client.post('/admin/benachrichtigungen/erinnerungen', data={'reminder_morning_hour': '3'})
        self.assertIn(r.status_code, (302, 403))
        self.assertEqual(appmod.cfg('reminder_morning_hour'), '8')


class CancelTest(AppTestCase):
    """A3: Absagen mit Grund + Benachrichtigung, Reaktivieren, Änderung mitteilen, RSVP-Sperre."""

    def test_member_cannot_cancel(self):
        self.login_member()
        r = self.client.post(f'/touren/{self.t_plan_id}/absagen', data={'reason': 'x'})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.tour(self.t_plan_id).status, 'planned')

    def test_cancel_and_uncancel_with_notifications(self):
        today = dt.date.today()
        t = M.Tour(title='Regentour', tour_date=today + dt.timedelta(days=4), status='planned',
                   start_time='10:00', group_id=self.g1_id, created_by=self.org_id)
        db.session.add(t)
        db.session.flush()
        self.ensure_participant(t.id, self.mem_id, 'attending')
        self.ensure_participant(t.id, self.mem2_id, 'maybe')
        self.ensure_participant(t.id, self.admin_id, 'declined')
        db.session.commit()
        tid = t.id
        self.login_org()
        r = self.client.post(f'/touren/{tid}/absagen', data={'reason': 'Dauerregen & Sturm'})
        self.assertEqual(r.status_code, 302)
        t = self.tour(tid)
        self.assertEqual(t.status, 'cancelled')
        self.assertEqual(t.cancel_reason, 'Dauerregen & Sturm')
        self.assertTrue(any('Tour abgesagt' in m and 'Dauerregen &amp; Sturm' in m for m in self.telegrams))
        targets = sorted(p[0] for p in self.pushes if 'abgesagt' in p[1])
        self.assertEqual(targets, ['fiete@test.de', 'hein@test.de'])          # nicht der Absagende, nicht Abgesagte
        html = self.get_html(f'/touren/{tid}')
        self.assertIn('Diese Tour ist abgesagt', html)
        self.assertIn('Dauerregen &amp; Sturm', html)
        self.assertIn('Absage zurücknehmen', html)
        # RSVP auf abgesagter Tour gesperrt
        self.login_member()
        self.client.post(f'/touren/{tid}/rsvp', data={'status': 'declined'})
        self.assertEqual(M.TourParticipant.query.filter_by(tour_id=tid, user_id=self.mem_id).first().status,
                         'attending')
        # Fahrgemeinschaft auf abgesagter Tour gesperrt
        r = self.client.post(f'/touren/{tid}/mitfahrt', data={'kind': 'offer', 'seats': '2'})
        self.assertEqual(r.status_code, 302)
        self.assertIsNone(M.TourRide.query.filter_by(tour_id=tid).first())
        # Reaktivieren
        self.login_org()
        self.pushes.clear()
        r = self.client.post(f'/touren/{tid}/reaktivieren')
        self.assertEqual(r.status_code, 302)
        t = self.tour(tid)
        self.assertEqual(t.status, 'planned')
        self.assertIsNone(t.cancel_reason)
        self.assertTrue(any('findet doch statt' in m for m in self.telegrams))
        self.assertEqual(sorted(p[0] for p in self.pushes), ['fiete@test.de', 'hein@test.de'])

    def test_cancel_button_in_toolbar_for_creator_only_when_planned(self):
        self.login_org()
        html = self.get_html(f'/touren/{self.t_plan_id}')
        self.assertIn('cancelTourModal', html)
        self.assertIn(f'/touren/{self.t_plan_id}/absagen', html)
        html = self.get_html(f'/touren/{self.t_done_id}')
        self.assertNotIn('cancelTourModal', html)
        self.login_member()
        html = self.get_html(f'/touren/{self.t_plan_id}')
        self.assertNotIn('cancelTourModal', html)

    def test_rsvp_blocked_on_completed_tour(self):
        self.login('fiete@test.de')
        self.client.post(f'/touren/{self.t_done_id}/rsvp', data={'status': 'attending'})
        self.assertIsNone(M.TourParticipant.query.filter_by(tour_id=self.t_done_id, user_id=self.mem2_id).first())

    def test_edit_notifies_changes_and_whitelists_status(self):
        today = dt.date.today()
        t = M.Tour(title='Verschiebetour', tour_date=today + dt.timedelta(days=6), status='planned',
                   start_time='10:00', meeting_desc='Dörphus', group_id=self.g1_id, created_by=self.org_id)
        db.session.add(t)
        db.session.flush()
        self.ensure_participant(t.id, self.mem_id, 'attending')
        db.session.commit()
        tid = t.id
        self.login_admin()
        html = self.get_html(f'/touren/{tid}/bearbeiten')
        self.assertIn('name="notify_changes"', html)
        new_date = (today + dt.timedelta(days=7)).isoformat()
        r = self.client.post(f'/touren/{tid}/bearbeiten', data={
            'title': 'Verschiebetour', 'tour_date': new_date, 'start_time': '11:00',
            'difficulty': 'mittel', 'meeting_desc': 'Dörphus', 'status': 'bogus', 'notify_changes': '1'})
        self.assertEqual(r.status_code, 302)
        t = self.tour(tid)
        self.assertEqual(t.status, 'planned')                       # „bogus“ verworfen
        self.assertEqual(t.start_time, '11:00')
        msg = next((m for m in self.telegrams if 'Tour geändert' in m), None)
        self.assertIsNotNone(msg)
        self.assertIn('Uhrzeit: 10:00 → 11:00', msg)
        self.assertIn('Datum:', msg)
        self.assertTrue(any(p[0] == 'hein@test.de' and 'Geändert' in p[1] for p in self.pushes))
        # ohne Haken: keine Nachricht
        self.telegrams.clear()
        self.client.post(f'/touren/{tid}/bearbeiten', data={
            'title': 'Verschiebetour', 'tour_date': new_date, 'start_time': '12:00',
            'difficulty': 'mittel', 'meeting_desc': 'Dörphus'})
        self.assertFalse(any('Tour geändert' in m for m in self.telegrams))
        self.assertEqual(self.tour(tid).start_time, '12:00')


class LoginLinkTest(AppTestCase):
    """Login: „Angemeldet bleiben“ vorausgewählt, Anmelde-Link per E-Mail."""

    def test_remember_checked_by_default(self):
        self.client.get('/logout')
        html = self.get_html('/login')
        self.assertRegex(html, r'name="remember"[^>]*checked')

    def test_login_link_flow(self):
        self.client.get('/logout')
        appmod._rl_store.clear()
        with mock.patch.dict(os.environ, {'MAIL_SERVER': 'smtp.example'}):
            html = self.get_html('/login')
            self.assertIn('/login-link', html)
            r = self.client.post('/login-link', data={'email': 'HEIN@test.de'})
            self.assertEqual(r.status_code, 302)
            self.assertEqual(len(self.mails), 1)
            to, subject, body = self.mails[0]
            self.assertEqual(to, 'hein@test.de')
            self.assertIn('/anmelden/', body)
            # unbekannte Adresse: gleiche Antwort, keine Mail
            r = self.client.post('/login-link', data={'email': 'niemand@test.de'})
            self.assertEqual(r.status_code, 302)
            self.assertEqual(len(self.mails), 1)
        token = body.split('/anmelden/')[1].split()[0].strip()
        pr = M.PasswordReset.query.filter_by(token=token).first()
        self.assertEqual(pr.purpose, 'login')
        # Login-Token taugt nicht zum Passwort-Reset
        self.assertEqual(self.client.get(f'/passwort-reset/{token}').status_code, 404)
        # Link einlösen → angemeldet
        r = self.client.get(f'/anmelden/{token}')
        self.assertEqual(r.status_code, 302)
        html = self.get_html('/profil/bearbeiten')
        self.assertIn('hein@test.de', html)
        # Zweite Verwendung → abgelehnt
        self.client.get('/logout')
        r = self.client.get(f'/anmelden/{token}', follow_redirects=True)
        self.assertIn('ungültig oder abgelaufen', r.get_data(as_text=True))
        self.assertEqual(self.client.get('/profil/bearbeiten').status_code, 302)

    def test_login_link_expired(self):
        self.client.get('/logout')
        pr = M.PasswordReset(user_id=self.mem_id, token='alt-token-xyz', purpose='login',
                             created_at=dt.datetime.utcnow() - dt.timedelta(minutes=20))
        db.session.add(pr)
        db.session.commit()
        r = self.client.get('/anmelden/alt-token-xyz', follow_redirects=True)
        self.assertIn('ungültig oder abgelaufen', r.get_data(as_text=True))
        self.assertEqual(self.client.get('/profil/bearbeiten').status_code, 302)

    def test_login_link_without_mail_server(self):
        self.client.get('/logout')
        appmod._rl_store.clear()
        with mock.patch.dict(os.environ, {'MAIL_SERVER': ''}):
            html = self.get_html('/login')
            self.assertNotIn('/login-link', html)
            r = self.client.post('/login-link', data={'email': 'hein@test.de'}, follow_redirects=True)
            self.assertIn('nicht eingerichtet', r.get_data(as_text=True))
        self.assertEqual(self.mails, [])


class ProfileAndListTest(AppTestCase):
    """Notfallkontakt im Profil, Passwortwechsel nur mit aktuellem Passwort, Teilnehmerliste."""

    def test_profile_contacts_and_password_change(self):
        self.login('fiete@test.de')
        html = self.get_html('/profil/bearbeiten')
        self.assertIn('name="emergency_phone"', html)
        self.assertIn('name="current_password"', html)
        r = self.client.post('/profil/bearbeiten', data={
            'name': 'Fiete', 'phone': '0170 111', 'emergency_name': 'Frauke', 'emergency_phone': '04204 99',
            'password': 'neuesPasswort1', 'password2': 'neuesPasswort1'})         # ohne aktuelles Passwort
        self.assertEqual(r.status_code, 302)
        u = self.user(self.mem2_id)
        self.assertEqual((u.phone, u.emergency_name, u.emergency_phone), ('0170 111', 'Frauke', '04204 99'))
        self.assertTrue(u.check_password(PASSWORD))                      # unverändert
        r = self.client.post('/profil/bearbeiten', data={
            'name': 'Fiete', 'current_password': PASSWORD, 'password': 'kurz12', 'password2': 'kurz12'})
        self.assertTrue(self.user(self.mem2_id).check_password(PASSWORD))   # zu kurz (< 8)
        r = self.client.post('/profil/bearbeiten', data={
            'name': 'Fiete', 'current_password': PASSWORD, 'password': 'neuesPasswort1',
            'password2': 'neuesPasswort1'})
        self.assertTrue(self.user(self.mem2_id).check_password('neuesPasswort1'))
        # zurücksetzen für andere Tests
        self.user(self.mem2_id).set_password(PASSWORD)
        db.session.commit()

    def test_participant_list_visibility(self):
        u = self.user(self.mem_id)
        u.phone, u.emergency_name, u.emergency_phone = '0171 222', 'Hilde', '04204 77'
        self.ensure_participant(self.t_plan_id, self.mem_id, 'attending')
        self.ensure_participant(self.t_plan_id, self.mem2_id, 'maybe')
        db.session.commit()
        self.login_member()
        self.assertEqual(self.client.get(f'/touren/{self.t_plan_id}/teilnehmerliste').status_code, 403)
        html = self.get_html(f'/touren/{self.t_plan_id}')
        self.assertNotIn('/teilnehmerliste', html)
        self.assertNotIn('0171 222', html)
        self.login_org()
        html = self.get_html(f'/touren/{self.t_plan_id}')
        self.assertIn(f'/touren/{self.t_plan_id}/teilnehmerliste', html)
        html = self.get_html(f'/touren/{self.t_plan_id}/teilnehmerliste')
        self.assertIn('0171 222', html)
        self.assertIn('Hilde', html)
        self.assertIn('vielleicht', html)
        self.assertIn('Notruf 112', html)
        # fremde Gruppe → 404
        self.login('fremd@test.de')
        self.assertEqual(self.client.get(f'/touren/{self.t_plan_id}/teilnehmerliste').status_code, 404)


class RideTest(AppTestCase):
    """Fahrgemeinschaften: Angebot, Gesuch, Push an Suchende, Löschen, Tour-Löschung räumt auf."""

    def test_offer_request_and_push(self):
        tid = self.t_plan_id
        self.login('fiete@test.de')
        r = self.client.post(f'/touren/{tid}/mitfahrt', data={'kind': 'request', 'place': 'Blender'})
        self.assertEqual(r.status_code, 302)
        self.login_member()
        r = self.client.post(f'/touren/{tid}/mitfahrt',
                             data={'kind': 'offer', 'seats': '3', 'place': 'Thedinghausen', 'note': 'Träger für 2 Räder'})
        self.assertEqual(r.status_code, 302)
        rides = M.TourRide.query.filter_by(tour_id=tid).all()
        self.assertEqual(len(rides), 2)
        offer = next(x for x in rides if x.kind == 'offer')
        self.assertEqual((offer.seats, offer.place, offer.note), (3, 'Thedinghausen', 'Träger für 2 Räder'))
        self.assertTrue(any(p[0] == 'fiete@test.de' and 'Mitfahrgelegenheit' in p[1] for p in self.pushes))
        html = self.get_html(f'/touren/{tid}')
        self.assertIn('id="fahrgemeinschaft"', html)
        self.assertIn('Thedinghausen', html)
        self.assertIn('Blender', html)
        self.assertIn('Meinen Eintrag ändern', html)
        # Update statt zweitem Eintrag
        self.client.post(f'/touren/{tid}/mitfahrt', data={'kind': 'offer', 'seats': '12'})
        offer = M.TourRide.query.filter_by(tour_id=tid, user_id=self.mem_id).first()
        self.assertEqual(offer.seats, 1)                                   # 12 ungültig → 1
        self.assertEqual(M.TourRide.query.filter_by(tour_id=tid).count(), 2)
        # Ungültige Art
        self.assertEqual(self.client.post(f'/touren/{tid}/mitfahrt', data={'kind': 'x'}).status_code, 400)
        # eigenen Eintrag löschen; fremden nicht (als Mitglied)
        self.client.post(f'/touren/{tid}/mitfahrt/loeschen', data={'user_id': self.mem2_id})
        self.assertEqual(M.TourRide.query.filter_by(tour_id=tid).count(), 1)
        self.assertEqual(M.TourRide.query.filter_by(tour_id=tid).first().user_id, self.mem2_id)
        # Organisator darf fremde entfernen
        self.login_org()
        self.client.post(f'/touren/{tid}/mitfahrt/loeschen', data={'user_id': self.mem2_id})
        self.assertEqual(M.TourRide.query.filter_by(tour_id=tid).count(), 0)

    def test_ride_removed_with_tour(self):
        t = M.Tour(title='Wegwerftour', tour_date=dt.date.today() + dt.timedelta(days=9), status='planned',
                   group_id=self.g1_id, created_by=self.admin_id)
        db.session.add(t)
        db.session.flush()
        db.session.add(M.TourRide(tour_id=t.id, user_id=self.mem_id, kind='offer', seats=2))
        db.session.commit()
        tid = t.id
        self.login_admin()
        self.client.post(f'/touren/{tid}/loeschen')
        self.assertIsNone(self.tour(tid))
        self.assertEqual(M.TourRide.query.filter_by(tour_id=tid).count(), 0)


class OpsTest(AppTestCase):
    """Paket 2: Backup-Modi, Rotation je Art, sichere Entpackung, GPX-Ausdünnung, Badge-Statistik, SW-Cache."""

    def _set(self, **kw):
        for k, v in kw.items():
            if v is None:
                M.SiteConfig.query.filter_by(key=k).delete()
            else:
                M.SiteConfig.set(k, v)
        db.session.commit()

    def test_backup_due_modes(self):
        now = dt.datetime.utcnow()
        self._set(backup_interval='off', backup_last_run=None, backup_last_full_run=None, backup_last_db_run=None)
        self.assertIsNone(appmod._backup_is_due())
        self._set(backup_interval='weekly')
        self.assertEqual(appmod._backup_is_due(), 'full')                 # noch nie gelaufen
        self._set(backup_last_full_run=(now - dt.timedelta(days=2)).isoformat(),
                  backup_last_db_run=(now - dt.timedelta(hours=2)).isoformat())
        self.assertIsNone(appmod._backup_is_due())
        self._set(backup_last_db_run=(now - dt.timedelta(hours=25)).isoformat())
        self.assertEqual(appmod._backup_is_due(), 'db')
        self._set(backup_last_full_run=(now - dt.timedelta(days=8)).isoformat())
        self.assertEqual(appmod._backup_is_due(), 'full')
        # Altinstallation: nur backup_last_run vorhanden
        self._set(backup_last_full_run=None, backup_last_db_run=None,
                  backup_last_run=(now - dt.timedelta(hours=1)).isoformat())
        self.assertIsNone(appmod._backup_is_due())
        self._set(backup_interval='off')

    def test_run_backup_passes_mode_and_lock(self):
        calls = []

        def fake_run(cmd, **kw):
            calls.append((cmd, kw.get('env', {}).get('INCLUDE_VIDEOS')))
            return mock.Mock(returncode=0, stdout='Backup OK', stderr='')

        self._set(backup_include_videos='1')
        with mock.patch('subprocess.run', side_effect=fake_run), \
                mock.patch.object(appmod, '_rotate_backups', return_value=0):
            ok, msg = appmod._run_backup(triggered_by='test', mode='db')
            self.assertTrue(ok, msg)
            self.assertEqual(calls[-1][0][-1], 'db')
            self.assertEqual(calls[-1][1], '1')
            self.assertEqual(appmod.cfg('backup_last_mode'), 'db')
            self.assertTrue(appmod.cfg('backup_last_db_run'))
            # Sperre: während ein Lauf „läuft“, wird kein zweiter gestartet
            appmod._backup_lock.acquire()
            try:
                ok, msg = appmod._run_backup(triggered_by='test', mode='full')
                self.assertFalse(ok)
                self.assertIn('läuft bereits', msg)
                self.assertFalse(appmod._start_backup_in_background('full'))
            finally:
                appmod._backup_lock.release()
        self._set(backup_include_videos=None)

    def test_rotation_per_kind(self):
        today = dt.date.today()
        with tempfile.TemporaryDirectory() as d:
            entries = {'djo_backup_': [], 'djo_db_': []}
            for prefix in entries:
                for days in (1, 2, 3, 10, 12, 20, 70, 400):
                    fd = today - dt.timedelta(days=days)
                    name = f'{prefix}{fd.isoformat()}_120000.tar.gz'
                    path = os.path.join(d, name)
                    open(path, 'wb').close()
                    entries[prefix].append((fd, name, path))
            deleted = sum(appmod._rotate_backup_entries(list(v)) for v in entries.values())
            left = sorted(os.listdir(d))
            # je Art: 3 (≤7 Tage) + Wochen-Generationen (10/12 → 1 oder 2, 20 → 1) + 70 Tage (Monat) ; 400 weg
            self.assertEqual(deleted, 16 - len(left))
            for prefix in entries:
                mine = [n for n in left if n.startswith(prefix)]
                self.assertTrue(all(f'{(today - dt.timedelta(days=x)).isoformat()}' in ''.join(mine) for x in (1, 2, 3)))
                self.assertFalse(any((today - dt.timedelta(days=400)).isoformat() in n for n in mine))
                self.assertGreaterEqual(len(mine), 5)

    def test_safe_extractall(self):
        with tempfile.TemporaryDirectory() as d:
            tar_path = os.path.join(d, 'x.tar.gz')
            with tarfile.open(tar_path, 'w:gz') as tf:
                for name in ('ok.sqlite', 'static/uploads/photos/a.jpg', '../evil.txt', '/abs.txt'):
                    data = b'x'
                    ti = tarfile.TarInfo(name)
                    ti.size = len(data)
                    tf.addfile(ti, io.BytesIO(data))
                ln = tarfile.TarInfo('link')
                ln.type = tarfile.SYMTYPE
                ln.linkname = '/etc/passwd'
                tf.addfile(ln)
            out = os.path.join(d, 'out')
            os.makedirs(out)
            with tarfile.open(tar_path, 'r:gz') as tf:
                appmod._safe_extractall(tf, out)
            self.assertTrue(os.path.exists(os.path.join(out, 'ok.sqlite')))
            self.assertTrue(os.path.exists(os.path.join(out, 'static', 'uploads', 'photos', 'a.jpg')))
            self.assertFalse(os.path.exists(os.path.join(d, 'evil.txt')))
            self.assertFalse(os.path.exists(os.path.join(out, 'abs.txt')))
            self.assertFalse(os.path.lexists(os.path.join(out, 'link')))

    def test_thin_points_keeps_shape_and_elevation(self):
        pts = [{'lat': 53.0 + i * 0.00002, 'lng': 9.0 + (i % 7) * 0.00001,
                'ele': 10 + (40 if 4000 < i < 4100 else 0)} for i in range(9000)]
        out = appmod._thin_points(pts, 2000)
        self.assertLessEqual(len(out), 2000)
        self.assertGreater(len(out), 20)
        self.assertIs(out[0], pts[0])
        self.assertIs(out[-1], pts[-1])
        self.assertTrue(any(p['ele'] == 50 for p in out))                 # Hügel bleibt im Höhenprofil
        self.assertEqual(appmod._thin_points(pts[:100], 2000), pts[:100])   # kleine Tracks unverändert

    def test_detail_embeds_thinned_gpx(self):
        xml = make_gpx(n=6000, with_time=False)
        t = M.Tour(title='Langer Track', tour_date=dt.date.today() + dt.timedelta(days=2), status='planned',
                   group_id=self.g1_id, created_by=self.org_id)
        db.session.add(t)
        db.session.flush()
        self.write_gpx(t, xml)
        db.session.commit()
        tid = t.id
        self.login_member()
        html = self.get_html(f'/touren/{tid}')
        m = next(line for line in html.splitlines() if line.startswith('const GPX_DATA = '))
        data = json.loads(m[len('const GPX_DATA = '):].rstrip(';'))
        self.assertLessEqual(len(data['points']), appmod.GPX_PAGE_MAX_PTS)
        self.assertIn('ele', data['points'][0])
        self.assertAlmostEqual(data['km'], self.tour(tid).gpx_km, places=1)
        self.assertEqual(appmod.parse_gpx.cache_info().maxsize, 16)
        self.assertEqual(self.client.get(f'/touren/{tid}/drucken').status_code, 200)

    def test_badge_stats_bulk_matches_single(self):
        self.ensure_participant(self.t_plan_id, self.mem2_id, 'attending', confirmed=True)
        db.session.commit()
        stats = appmod.badge_stats_bulk([self.mem_id, self.mem2_id, self.fremd_id])
        self.assertEqual(stats[self.mem_id][0], 1)
        self.assertAlmostEqual(stats[self.mem_id][1], self.tour(self.t_done_id).gpx_km or 0, places=2)
        self.assertEqual(stats[self.mem2_id][0], 1)
        self.assertNotIn(self.fremd_id, stats)
        u = self.user(self.mem_id)
        self.assertEqual(appmod.compute_badges(u), appmod.compute_badges(u, stats=stats[self.mem_id]))
        self.login_member()
        for path in ('/mitglieder', f'/profil/{self.mem_id}', '/rangliste', '/rueckblick'):
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_service_worker_and_asset_version(self):
        r = self.client.get('/sw.js')
        self.assertEqual(r.status_code, 200)
        body = r.get_data(as_text=True)
        self.assertNotIn('__BUILD__', body)
        self.assertIn("const CACHE_VERSION = 'djo-2026-10-14-ab'", body)
        self.assertEqual(r.headers.get('Cache-Control'), 'no-cache')
        self.login_member()
        html = self.get_html('/')
        self.assertIn('css/style.css?v=2026-10-14ab', html)
        self.assertIn('font-size: .75rem', html)                          # Bottom-Nav lesbar

    def test_live_map_attribution_top_right(self):
        self.login_member()
        html = self.get_html(f'/touren/{self.t_plan_id}/live')
        self.assertIn("L.control.attribution({position: 'topright'})", html)


class RemovedRoutesTest(AppTestCase):
    def test_removed_routes_404(self):
        self.login_admin()
        self.assertEqual(self.client.get('/admin/run-migration?token=x').status_code, 404)
        self.assertEqual(self.client.get('/proposals/new').status_code, 404)
        self.assertEqual(self.client.post('/proposals/1/vote').status_code, 404)
        self.assertEqual(appmod.APP_BUILD, '2026-10-14 ab')


if __name__ == '__main__':
    unittest.main()
