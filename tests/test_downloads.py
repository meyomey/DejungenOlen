"""Downloads (Build v): GPX-Datei, Archiv-ZIP, Tour-Paket, Druckansicht."""
import io
import zipfile

from tests.base import AppTestCase, db, M


class DownloadsTest(AppTestCase):

    def test_gpx_download(self):
        self.login_member()
        r = self.client.get(f'/touren/{self.t_done_id}/gpx-datei')
        self.assertEqual(r.status_code, 200)
        self.assertIn('attachment', r.headers.get('Content-Disposition', ''))
        self.assertIn('.gpx', r.headers.get('Content-Disposition', ''))
        self.assertIn(b'<trkpt', r.data)
        # Tour ohne GPX → 404, fremde Gruppe → 404
        self.assertEqual(self.client.get(f'/touren/{self.t_open_id}/gpx-datei').status_code, 404)
        self.assertEqual(self.client.get(f'/touren/{self.t_fremd_id}/gpx-datei').status_code, 404)

    def test_archive_gpx_zip(self):
        self.login_member()
        r = self.client.get('/archiv/gpx-zip')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers['Content-Type'], 'application/zip')
        z = zipfile.ZipFile(io.BytesIO(r.data))
        names = z.namelist()
        self.assertTrue(any(n.endswith('.gpx') for n in names), names)
        self.assertEqual(len([n for n in names if n.endswith('.gpx')]), 1)   # nur die abgeschlossene Tour mit GPX
        # Filter ohne Treffer → Hinweis statt leerem ZIP
        r = self.client.get('/archiv/gpx-zip?q=gibtesnicht', follow_redirects=True)
        self.assertIn(r.status_code, (200, 404))

    def test_tour_package(self):
        t = self.tour(self.t_done_id)
        t.gastro_spot_id = self.spot_id
        db.session.commit()
        self.login_member()
        r = self.client.get(f'/touren/{self.t_done_id}/paket')
        self.assertEqual(r.status_code, 200)
        z = zipfile.ZipFile(io.BytesIO(r.data))
        names = z.namelist()
        txt = [n for n in names if n.endswith('.txt')]
        self.assertTrue(txt, names)
        info = z.read(txt[0]).decode('utf-8')
        self.assertIn('Alte Marschtour', info)
        self.assertIn('Einkehr:', info)
        self.assertIn('Café Deichblick', info)
        self.assertTrue(any(n.endswith('.gpx') for n in names))

    def test_print_view(self):
        t = self.tour(self.t_plan_id)
        t.gastro_spot_id = self.spot2_id
        db.session.commit()
        self.login_member()
        html = self.get_html(f'/touren/{self.t_plan_id}/drucken')
        self.assertIn('Deichtour, mit Komma', html)
        self.assertIn('☕ Einkehr', html)
        self.assertIn('Zur alten Mühle', html)

    def test_photo_pages(self):
        """Foto-Übersicht und Tour-Detail ohne Fotos dürfen nicht brechen."""
        self.login_member()
        for path in ('/fotos', f'/touren/{self.t_done_id}'):
            r = self.client.get(path)
            self.assertIn(r.status_code, (200, 302, 404), f'{path} → {r.status_code}')
        self.assertEqual(M.TourPhoto.query.count(), 0)
