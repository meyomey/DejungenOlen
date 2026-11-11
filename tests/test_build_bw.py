"""Build bw: Foto aus der App landet nicht in der Galerie des Handys.

Der Nutzer: „Habe ein Foto innerhalb der App gemacht, das erscheint auch auf der Tourkarte.
Das Foto ist aber nicht in der Galerie des Handys zu finden. Dort hätte ich es auch gerne."

**Ursache.** Das Foto wird über `<input type="file" capture="environment">` aufgenommen und
per `fetch` hochgeladen. Der Browser gibt die Aufnahme **nie** an die Galerie weiter – das kann
eine Webseite grundsätzlich nicht, es gibt dafür keine Schnittstelle. Zusätzlich verkleinerte
der Server jedes Foto auf 1600 px und **verwarf das Original**.

**Umgesetzt (Build bw):**
1. **Original aufbewahren** (`TourPhoto.orig_filename`): Beim Upload wird das unveränderte
   Handyfoto mitgespeichert, bevor `_resize_photo_if_needed` die Web-Fassung schreibt.
2. **Download-Route** `/fotos/<id>/download`: liefert das Original (sonst die Web-Fassung),
   mit lesbarem Dateinamen wie `Fototour_2026-11-11_1817.jpg`.
3. **⬇-Knopf** an jedem Foto auf der Tourseite – Datei landet im Download-Ordner.
4. **„📥 In Galerie sichern"** nach dem Foto in der Live-Karte: übergibt das Original an das
   Teilen-Menü des Handys (`navigator.share`), dort „In Fotos/Galerie speichern". Kann das
   Gerät es nicht, erscheint ein Hinweis auf den ⬇-Knopf.
5. **Aufräumen**: Beim Löschen eines Fotos wird das Original mit entfernt (sonst Karteileichen).
"""
import io
import os
import unittest

from tests.base import AppTestCase, ROOT, app, appmod, db
import models as M

LIVE = os.path.join(ROOT, 'templates', 'touren', 'live.html')
DETAIL = os.path.join(ROOT, 'templates', 'touren', 'detail.html')
APP = os.path.join(ROOT, 'app.py')


def _lies(pfad):
    with open(pfad, encoding='utf-8') as f:
        return f.read()


class OriginalAufbewahrenTest(AppTestCase):
    """Punkt 1: Das Original muss den Upload überleben."""

    def test_modell_hat_das_feld(self):
        self.assertIn('orig_filename', [c.name for c in M.TourPhoto.__table__.columns])

    def test_migration_kennt_die_spalte(self):
        self.assertIn("add_column('tour_photos', 'orig_filename'", _lies(APP))

    def test_hilfsfunktion_liest_die_bildgroesse(self):
        from PIL import Image
        import tempfile
        p = tempfile.mktemp(suffix='.jpg')
        try:
            Image.new('RGB', (3000, 2000), (10, 20, 30)).save(p, 'JPEG')
            self.assertEqual(appmod._image_size(p), (3000, 2000))
            Image.new('RGB', (800, 600), (10, 20, 30)).save(p, 'JPEG')
            self.assertEqual(appmod._image_size(p), (800, 600))
            self.assertEqual(appmod._image_size('/gibt/es/nicht.jpg'), (0, 0))
        finally:
            if os.path.exists(p):
                os.remove(p)


class UploadUndDownloadTest(AppTestCase):
    """Die ganze Kette am echten Endpunkt: Upload -> DB -> Download."""

    _nr = 0

    def setUp(self):
        super().setUp()
        with app.app_context():
            self.tour = M.Tour.query.first()

    def _upload(self, breite, hoehe, name='foto.jpg'):
        # Das Upload-Limit (5/Minute) gilt pro Nutzer und lebt im Prozess – ohne Ruecksetzen
        # scheitert der sechste Upload einer Klasse mit leerer photo_ids-Liste.
        appmod._rl_store.clear()
        from PIL import Image
        buf = io.BytesIO()
        # Jedes Bild braucht eine eigene Farbe: Gleiche Bytes gelten als Duplikat und
        # werden uebersprungen (dann kaeme eine leere photo_ids-Liste zurueck).
        UploadUndDownloadTest._nr += 1
        n = UploadUndDownloadTest._nr
        Image.new('RGB', (breite, hoehe), (n * 37 % 256, n * 91 % 256, n * 53 % 256)).save(
            buf, 'JPEG', quality=90)
        roh = buf.getvalue()
        c = app.test_client()
        with c.session_transaction() as s:
            s['_user_id'] = str(self.admin.id)
            s['_fresh'] = True
        r = c.post(f'/touren/{self.tour.id}/fotos',
                   data={'photos': (io.BytesIO(roh), name)},
                   content_type='multipart/form-data',
                   headers={'X-Requested-With': 'XMLHttpRequest'})
        return c, r, roh

    def test_grosses_foto_bekommt_ein_original(self):
        c, r, roh = self._upload(3000, 2000, 'gross.jpg')
        self.assertEqual(r.status_code, 200)
        ids = r.get_json().get('photo_ids') or []
        self.assertTrue(ids, 'die Antwort muss die Foto-IDs enthalten (für „In Galerie sichern")')
        with app.app_context():
            ph = db.session.get(M.TourPhoto, ids[0])
            self.assertIsNotNone(ph.orig_filename, 'bei 3000 px muss ein Original angelegt werden')
            pfad = os.path.join(app.config['UPLOAD_FOLDER_PHOTOS'], ph.orig_filename)
            self.assertTrue(os.path.isfile(pfad))
            with open(pfad, 'rb') as f:
                self.assertEqual(f.read(), roh, 'das Original muss byte-gleich sein')
            # Die Web-Fassung ist kleiner
            web = os.path.join(app.config['UPLOAD_FOLDER_PHOTOS'], ph.filename)
            self.assertEqual(appmod._image_size(web), (1600, 1066))

    def test_kleines_foto_bleibt_trotzdem_original(self):
        """Auch ein 800-px-Bild wird von Pillow neu gespeichert und dabei kleiner –
        gemessen: 8 230 -> 3 379 Bytes. Deshalb wird auch hier das Original behalten."""
        c, r, roh = self._upload(800, 600, 'klein.jpg')
        ids = r.get_json().get('photo_ids') or []
        with app.app_context():
            ph = db.session.get(M.TourPhoto, ids[0])
            self.assertIsNotNone(ph.orig_filename)

    def test_download_liefert_das_original(self):
        c, r, roh = self._upload(3000, 2000, 'dl.jpg')
        pid = r.get_json()['photo_ids'][0]
        d = c.get(f'/fotos/{pid}/download')
        self.assertEqual(d.status_code, 200)
        self.assertEqual(d.data, roh, 'der Download muss das unveränderte Original sein')
        # Dateiname lesbar, nicht der Hash
        cd = d.headers.get('Content-Disposition', '')
        self.assertIn('filename=', cd)
        self.assertNotIn('_orig', cd)
        self.assertNotIn('jpeg', cd.lower())

    def test_download_ohne_original_faellt_auf_die_webfassung_zurueck(self):
        """Alte Fotos (vor bw) haben kein Original – der Download darf nicht 404 liefern."""
        with app.app_context():
            ph = M.TourPhoto(tour_id=self.tour.id, user_id=self.admin.id,
                             filename='rueckfall_test.jpg', orig_filename=None)
            db.session.add(ph)
            db.session.commit()
            pid = ph.id
            from PIL import Image
            Image.new('RGB', (400, 300), (5, 5, 5)).save(
                os.path.join(app.config['UPLOAD_FOLDER_PHOTOS'], 'rueckfall_test.jpg'), 'JPEG')
        c = app.test_client()
        with c.session_transaction() as s:
            s['_user_id'] = str(self.admin.id)
            s['_fresh'] = True
        d = c.get(f'/fotos/{pid}/download')
        self.assertEqual(d.status_code, 200)

    def test_loeschen_raeumt_das_original_mit_weg(self):
        c, r, roh = self._upload(3000, 2000, 'weg.jpg')
        pid = r.get_json()['photo_ids'][0]
        with app.app_context():
            ph = db.session.get(M.TourPhoto, pid)
            web = os.path.join(app.config['UPLOAD_FOLDER_PHOTOS'], ph.filename)
            orig = os.path.join(app.config['UPLOAD_FOLDER_PHOTOS'], ph.orig_filename)
            self.assertTrue(os.path.isfile(web) and os.path.isfile(orig))
        c.post(f'/fotos/{pid}/loeschen', follow_redirects=False)
        with app.app_context():
            self.assertFalse(os.path.isfile(web), 'Web-Fassung muss weg sein')
            self.assertFalse(os.path.isfile(orig), 'Original muss AUCH weg sein (sonst Karteileiche)')


class OberflaecheTest(AppTestCase):
    """Punkte 3 und 4: Die Knöpfe müssen da sein."""

    def test_download_knopf_auf_der_tourseite(self):
        html = _lies(DETAIL)
        self.assertIn("url_for('photo_download', photo_id=p.id)", html)
        self.assertIn('bi-download', html)

    def test_galerie_knopf_in_der_live_karte(self):
        js = _lies(LIVE)
        self.assertIn('📥 In Galerie sichern', js)
        self.assertIn('async function inGalerieSichern(', js)
        self.assertIn('navigator.canShare', js)
        self.assertIn('navigator.share', js)

    def test_galerie_holt_das_original(self):
        js = _lies(LIVE)
        self.assertIn("'/fotos/' + photoId + '/download'", js)

    def test_fallback_wenn_das_geraet_nicht_kann(self):
        js = _lies(LIVE)
        self.assertIn('kann das Foto nicht direkt an die Galerie geben', js)
        self.assertIn('#fotos', js)

    def test_ehrlicher_kommentar_zur_grenze(self):
        """Im Code soll stehen, WARUM es nur über das Teilen-Menü geht."""
        js = _lies(LIVE)
        self.assertIn('kann eine Webseite nicht', js)


class AufraeumenTest(AppTestCase):
    """Die Hilfsfunktion muss beide Dateien löschen und fehlende tolerieren."""

    def test_loescht_beide_dateien(self):
        pfad = app.config['UPLOAD_FOLDER_PHOTOS']
        os.makedirs(pfad, exist_ok=True)
        for name in ('aufr_a.jpg', 'aufr_a_orig.jpg'):
            with open(os.path.join(pfad, name), 'wb') as f:
                f.write(b'x')

        class P:
            filename = 'aufr_a.jpg'
            orig_filename = 'aufr_a_orig.jpg'

        appmod._delete_photo_files(P())
        self.assertFalse(os.path.exists(os.path.join(pfad, 'aufr_a.jpg')))
        self.assertFalse(os.path.exists(os.path.join(pfad, 'aufr_a_orig.jpg')))

    def test_fehlende_dateien_sind_kein_fehler(self):
        class P:
            filename = 'gibt_es_nicht.jpg'
            orig_filename = None
        appmod._delete_photo_files(P())      # darf nicht werfen


if __name__ == '__main__':
    unittest.main()
