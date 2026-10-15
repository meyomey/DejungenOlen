"""Regressionsschutz für Bereiche, die bisher keine Tests hatten (Audit 3, offene Testlücken):
Registrierung per Einladung, Passwort-Reset-Formular, Kommentare (inkl. Antworten/Löschen),
Zeitabstimmung, Tour-Vorlagen, Ankündigungen (inkl. Sichtbarkeit) und Video-Upload.

Fixtures aus tests/base.py: Gruppe 1 (admin/org/mem/mem2), Gruppe 2 (fremd, „Fremde Tour“)."""
import datetime as dt
import io
import unittest

from tests.base import AppTestCase, appmod, app, db, M, PASSWORD


class RegistrationTest(AppTestCase):
    """Einladung erstellen → Registrierung → Einladung ist verbraucht."""

    def test_invite_register_flow(self):
        self.login_admin()
        r = self.client.post('/admin/einladen', data={'email': 'neu@test.de', 'label': 'Test-Label'},
                             follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn('Einladungslink für Test-Label erstellt', r.get_data(as_text=True))
        invite = M.InviteToken.query.order_by(M.InviteToken.id.desc()).first()
        self.assertIsNotNone(invite)
        self.assertEqual(invite.email, 'neu@test.de')

        # Registrierungsseite zeigt das Label/die Gruppe
        r = self.client.get(f'/registrieren/{invite.token}')
        self.assertEqual(r.status_code, 200)

        # Passwörter ungleich → abgewiesen
        r = self.client.post(f'/registrieren/{invite.token}',
                             data={'email': 'neu@test.de', 'name': 'Neue Ole',
                                   'password': 'geheim1234', 'password2': 'andere1234'})
        self.assertIn('stimmen nicht überein', r.get_data(as_text=True))
        self.assertIsNone(M.User.query.filter_by(email='neu@test.de').first())

        # Erfolgreiche Registrierung → eingeloggt, Gruppe übernommen, Token verbraucht
        r = self.client.post(f'/registrieren/{invite.token}',
                             data={'email': 'neu@test.de', 'name': 'Neue Ole', 'nickname': 'Neu',
                                   'password': 'geheim1234', 'password2': 'geheim1234'},
                             follow_redirects=True)
        self.assertIn('Willkommen', r.get_data(as_text=True))
        user = M.User.query.filter_by(email='neu@test.de').first()
        self.assertIsNotNone(user)
        self.assertEqual(user.group_id, self.g1_id)
        self.assertTrue(invite.used)

        # Token ist einmalig: zweite Registrierung → 404
        r = self.client.get(f'/registrieren/{invite.token}')
        self.assertEqual(r.status_code, 404)

    def test_unknown_token_404(self):
        r = self.client.get('/registrieren/gibt-es-nicht')
        self.assertEqual(r.status_code, 404)

    def test_duplicate_email_rejected(self):
        invite = M.InviteToken(token='dup-test-token', group_id=self.g1_id)
        db.session.add(invite)
        db.session.commit()
        r = self.client.post('/registrieren/dup-test-token',
                             data={'email': 'hein@test.de', 'name': 'Doppelt',
                                   'password': 'geheim1234', 'password2': 'geheim1234'})
        self.assertIn('bereits registriert', r.get_data(as_text=True))
        invite.used = True
        db.session.commit()


class PasswordResetTest(AppTestCase):
    """Passwort vergessen: Mail mit Token → Formular → neues Passwort; abgelaufen/verbraucht."""

    def _request_reset(self, email='hein@test.de'):
        n_before = len(self.mails)
        r = self.client.post('/passwort-vergessen', data={'email': email})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(self.mails), n_before + 1, 'Es sollte eine Reset-Mail geben')
        self.assertIn('Passwort', self.mails[-1][1])            # Subject
        return M.PasswordReset.query.filter_by(user_id=self.mem_id, used=False) \
                                    .order_by(M.PasswordReset.id.desc()).first()

    def test_forgot_password_unknown_email_no_hint(self):
        r = self.client.post('/passwort-vergessen', data={'email': 'nirgends@test.de'})
        self.assertIn('Falls diese E-Mail-Adresse registriert ist', r.get_data(as_text=True))

    def test_reset_flow_changes_password(self):
        pr = self._request_reset()
        self.assertIsNotNone(pr)
        # zu kurz / ungleich
        r = self.client.post(f'/passwort-reset/{pr.token}',
                             data={'password': 'kurz123', 'password2': 'kurz123'})
        self.assertIn('mindestens 8 Zeichen', r.get_data(as_text=True))
        r = self.client.post(f'/passwort-reset/{pr.token}',
                             data={'password': 'lang genug 1', 'password2': 'lang genug 2'})
        self.assertIn('stimmen nicht überein', r.get_data(as_text=True))
        # erfolgreich
        r = self.client.post(f'/passwort-reset/{pr.token}',
                             data={'password': 'neugeheim123', 'password2': 'neugeheim123'},
                             follow_redirects=True)
        self.assertIn('Passwort geändert', r.get_data(as_text=True))
        self.assertTrue(db.session.get(M.User, self.mem_id).check_password('neugeheim123'))
        self.assertTrue(pr.used)
        # zweites Mal → 404
        r = self.client.get(f'/passwort-reset/{pr.token}')
        self.assertEqual(r.status_code, 404)
        # altes Passwort geht nicht mehr
        self.client.get('/logout')
        r = self.client.post('/login', data={'email': 'hein@test.de', 'password': PASSWORD},
                             follow_redirects=True)
        self.assertIn('falsch', r.get_data(as_text=True))

    def test_expired_reset_redirects(self):
        pr = self._request_reset()
        M.PasswordReset.query.filter_by(id=pr.id) \
            .update({'created_at': dt.datetime.utcnow() - dt.timedelta(hours=2)})
        db.session.commit()
        r = self.client.get(f'/passwort-reset/{pr.token}')
        self.assertEqual(r.status_code, 302)                    # → /passwort-vergessen


class CommentsTest(AppTestCase):
    """Kommentare: anlegen, beantworten, löschen (eigene/als Admin), Mandanten-Trennung."""

    def _comment(self, tour_id, content='Schöne Tour!', parent_id=None):
        return self.client.post(f'/touren/{tour_id}/kommentieren',
                                data={'content': content, 'parent_id': parent_id or ''},
                                follow_redirects=True)

    def test_create_and_reply(self):
        self.login_member()
        r = self._comment(self.t_plan_id, 'Ich fahre mit!')
        self.assertIn('Kommentar gespeichert', r.get_data(as_text=True))
        c = M.TourComment.query.filter_by(tour_id=self.t_plan_id).order_by(M.TourComment.id.desc()).first()
        self.assertEqual(c.content, 'Ich fahre mit!')
        self.assertEqual(c.user_id, self.mem_id)

        r = self._comment(self.t_plan_id, 'Antwort auf den ersten', parent_id=c.id)
        reply = M.TourComment.query.filter_by(tour_id=self.t_plan_id) \
                                   .order_by(M.TourComment.id.desc()).first()
        self.assertEqual(reply.parent_id, c.id)

    def test_empty_comment_rejected(self):
        self.login_member()
        n = M.TourComment.query.count()
        r = self._comment(self.t_plan_id, '   ')
        self.assertIn('nicht leer', r.get_data(as_text=True))
        self.assertEqual(M.TourComment.query.count(), n)

    def test_foreign_tour_404(self):
        self.login_member()
        r = self._comment(self.t_fremd_id, 'Fremder Kommentar')
        self.assertEqual(r.status_code, 404)
        self.assertIsNone(M.TourComment.query.filter_by(tour_id=self.t_fremd_id).first())

    def test_delete_own_only_admin_else(self):
        self.login_member()
        self._comment(self.t_plan_id, 'Zum Löschen')
        c = M.TourComment.query.filter_by(tour_id=self.t_plan_id).order_by(M.TourComment.id.desc()).first()

        self.login_member()  # anderer Nutzer (mem2) – nicht Besitzer, kein Admin → 403
        self.client.get('/logout')
        self.login('fiete@test.de')
        r = self.client.post(f'/touren/{self.t_plan_id}/kommentare/{c.id}/loeschen')
        self.assertEqual(r.status_code, 403)
        self.assertIsNotNone(db.session.get(M.TourComment, c.id))

        self.login_admin()
        r = self.client.post(f'/touren/{self.t_plan_id}/kommentare/{c.id}/loeschen',
                             follow_redirects=True)
        self.assertIn('Kommentar gelöscht', r.get_data(as_text=True))
        self.assertIsNone(db.session.get(M.TourComment, c.id))


class TimeVoteTest(AppTestCase):
    """Startzeit-Abstimmung für Touren ohne Termin; Organizer übernimmt die beste Zeit."""

    def test_vote_replace_and_set(self):
        self.login_member()
        t = self.tour(self.t_open_id)
        self.assertTrue(t.is_date_open)

        r = self.client.post(f'/touren/{self.t_open_id}/zeitabstimmung',
                             data={'slots': ['09:00', '10:00']}, follow_redirects=True)
        self.assertIn('gespeichert', r.get_data(as_text=True))
        self.assertEqual(M.TimeVote.query.filter_by(tour_id=self.t_open_id, user_id=self.mem_id).count(), 2)

        # Erneutes Abstimmen ersetzt die eigenen Stimmen
        self.client.post(f'/touren/{self.t_open_id}/zeitabstimmung', data={'slots': ['10:00']})
        votes = M.TimeVote.query.filter_by(tour_id=self.t_open_id, user_id=self.mem_id).all()
        self.assertEqual([v.time_slot for v in votes], ['10:00'])

        html = self.get_html(f'/touren/{self.t_open_id}/zeitabstimmung')
        self.assertIn('10:00', html)

        # Mitglied darf keine Zeit setzen (organizer_required)
        self.client.get('/logout')
        self.login_member()
        r = self.client.post(f'/touren/{self.t_open_id}/zeitabstimmung/setzen', data={'slot': '10:00'})
        self.assertEqual(r.status_code, 403)

        self.login_org()
        r = self.client.post(f'/touren/{self.t_open_id}/zeitabstimmung/setzen',
                             data={'slot': '10:00'}, follow_redirects=True)
        self.assertIn('10:00 Uhr gesetzt', r.get_data(as_text=True))
        self.assertEqual(self.tour(self.t_open_id).start_time, '10:00')

    def test_fixed_date_tour_redirects(self):
        self.login_member()
        r = self.client.get(f'/touren/{self.t_plan_id}/zeitabstimmung')
        self.assertEqual(r.status_code, 302)                    # zurück zur Tour-Detailseite


class TemplatesTest(AppTestCase):
    """Tour-Vorlagen: speichern, auflisten, Tour daraus erstellen, löschen, Mandanten-Trennung."""

    def test_template_lifecycle(self):
        self.login_org()
        r = self.client.post(f'/touren/{self.t_plan_id}/als-vorlage',
                             data={'template_name': 'Deichtour Standard'}, follow_redirects=True)
        html = r.get_data(as_text=True)
        self.assertIn('Deichtour Standard', html)
        self.assertIn('gespeichert', html)
        tmpl = M.TourTemplate.query.filter_by(name='Deichtour Standard').first()
        self.assertIsNotNone(tmpl)
        self.assertEqual(tmpl.title, 'Deichtour, mit Komma')
        self.assertEqual(tmpl.group_id, self.g1_id)

        html = self.get_html('/touren/vorlagen')
        self.assertIn('Deichtour Standard', html)

        # Tour aus Vorlage: ohne Termin (Sentinel), Startzeit übernommen
        r = self.client.post(f'/touren/neu/aus-vorlage/{tmpl.id}', follow_redirects=True)
        self.assertIn('aus Vorlage erstellt', r.get_data(as_text=True))
        new_tour = M.Tour.query.order_by(M.Tour.id.desc()).first()
        self.assertEqual(new_tour.title, 'Deichtour, mit Komma')
        self.assertTrue(new_tour.is_date_open)
        self.assertEqual(new_tour.start_time, '10:00')

        # Mitglied darf nichts – organizer_required
        self.client.get('/logout')
        self.login_member()
        self.assertEqual(self.client.post(f'/touren/{tmpl.id}/als-vorlage',
                                          data={'template_name': 'x'}).status_code, 403)
        self.assertEqual(self.client.post(f'/touren/vorlagen/{tmpl.id}/loeschen').status_code, 403)

    def test_delete_and_foreign_group_404(self):
        self.login_org()
        tmpl = M.TourTemplate(name='Fremde Vorlage', title='X', group_id=self.g2_id,
                              created_by=self.fremd_id)
        db.session.add(tmpl)
        db.session.commit()
        # Vorlage einer fremden Gruppe ist für Orga unsichtbar (404)
        self.assertEqual(self.client.post(f'/touren/vorlagen/{tmpl.id}/loeschen').status_code, 404)
        self.assertEqual(self.client.post(f'/touren/neu/aus-vorlage/{tmpl.id}').status_code, 404)

        # eigene Vorlage löschen
        mine = M.TourTemplate(name='Meine Vorlage', title='Y', group_id=self.g1_id,
                              created_by=self.org_id)
        db.session.add(mine)
        db.session.commit()
        r = self.client.post(f'/touren/vorlagen/{mine.id}/loeschen', follow_redirects=True)
        self.assertIn('gelöscht', r.get_data(as_text=True))
        self.assertIsNone(db.session.get(M.TourTemplate, mine.id))


class AnnouncementsTest(AppTestCase):
    """Ankündigungen: anlegen, sichtbar (ein-/ausgeloggt), umschalten, bearbeiten, löschen."""

    def _create(self, title, **kw):
        data = {'title': title, 'content': kw.get('content', 'Wichtiger Hinweis'),
                'visibility': kw.get('visibility', 'both')}
        return self.client.post('/admin/ankuendigungen/neu', data=data, follow_redirects=True)

    def test_member_forbidden(self):
        self.login_member()
        self.assertEqual(self.client.post('/admin/ankuendigungen/neu',
                                          data={'title': 'X'}).status_code, 403)

    def test_create_visible_and_toggle(self):
        self.login_admin()
        r = self._create('Storno am Samstag')
        self.assertIn('erstellt', r.get_data(as_text=True))
        ann = M.Announcement.query.order_by(M.Announcement.id.desc()).first()
        self.assertEqual(ann.title, 'Storno am Samstag')

        # ausgeloggt (both) auf der Login-Seite sichtbar
        self.client.get('/logout')
        self.assertIn('Storno am Samstag', self.get_html('/login'))
        # und eingeloggt auf der Startseite
        self.login_member()
        self.assertIn('Storno am Samstag', self.get_html('/'))

        # ausblenden (Redirect folgen, sonst blitzt der Flash-Titel auf der nächsten Seite auf)
        self.login_admin()
        r = self.client.post(f'/admin/ankuendigungen/{ann.id}/umschalten', follow_redirects=True)
        self.assertIn('deaktiviert', r.get_data(as_text=True))
        self.assertFalse(ann.is_active)
        self.login_member()
        self.assertNotIn('Storno am Samstag', self.get_html('/'))

    def test_logged_out_only_not_on_index(self):
        self.login_admin()
        self._create('Nur für Ausgeloggte', visibility='logged_out')
        ann = M.Announcement.query.order_by(M.Announcement.id.desc()).first()
        self.client.get('/logout')
        self.assertIn('Nur für Ausgeloggte', self.get_html('/login'))
        self.login_member()
        self.assertNotIn('Nur für Ausgeloggte', self.get_html('/'))

    def test_edit_requires_title_and_updates(self):
        self.login_admin()
        self._create('Erster Titel')
        ann = M.Announcement.query.order_by(M.Announcement.id.desc()).first()
        r = self.client.post(f'/admin/ankuendigungen/{ann.id}/bearbeiten', data={'title': '   '},
                             follow_redirects=True)
        self.assertIn('Titel ist erforderlich', r.get_data(as_text=True))
        r = self.client.post(f'/admin/ankuendigungen/{ann.id}/bearbeiten',
                             data={'title': 'Neuer Titel', 'content': 'Neu',
                                   'visibility': 'logged_in'}, follow_redirects=True)
        self.assertIn('aktualisiert', r.get_data(as_text=True))
        self.assertEqual(ann.title, 'Neuer Titel')
        self.assertEqual(ann.visibility, 'logged_in')

        # löschen
        r = self.client.post(f'/admin/ankuendigungen/{ann.id}/loeschen', follow_redirects=True)
        self.assertIn('gelöscht', r.get_data(as_text=True))
        self.assertIsNone(db.session.get(M.Announcement, ann.id))


class VideoUploadTest(AppTestCase):
    """Video-Upload: MP4 landet mit Titel bei der Tour, falsche Endung wird abgewiesen."""

    def _mp4(self):
        return b'\x00\x00\x00\x18ftypisom' + b'0' * 2000       # Mini-"MP4" (Magie reicht für den Test)

    def test_upload_and_delete(self):
        self.login_org()
        data = {'video': (io.BytesIO(self._mp4()), 'rennwand.mp4'),
                'video_title': 'Rennwand-Clip'}
        r = self.client.post(f'/touren/{self.t_done_id}/videos', data=data,
                             content_type='multipart/form-data', follow_redirects=True)
        self.assertIn('Rennwand-Clip', r.get_data(as_text=True))
        video = M.TourVideo.query.filter_by(tour_id=self.t_done_id).order_by(M.TourVideo.id.desc()).first()
        self.assertIsNotNone(video)
        self.assertEqual(video.title, 'Rennwand-Clip')
        self.assertGreater(video.filesize, 0)

        # Löschen durch den Uploader
        r = self.client.post(f'/videos/{video.id}/loeschen', follow_redirects=True)
        self.assertIn('gelöscht', r.get_data(as_text=True))
        self.assertIsNone(db.session.get(M.TourVideo, video.id))

    def test_bad_extension_rejected(self):
        self.login_org()
        n = M.TourVideo.query.count()
        data = {'video': (io.BytesIO(b'MZ binaer'), 'programm.exe')}
        r = self.client.post(f'/touren/{self.t_done_id}/videos', data=data,
                             content_type='multipart/form-data', follow_redirects=True)
        self.assertIn('nicht erlaubt', r.get_data(as_text=True))
        self.assertEqual(M.TourVideo.query.count(), n)


if __name__ == '__main__':
    unittest.main()
