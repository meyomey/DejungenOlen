# Changelog – De jungen Olen

Neueste Version oben. Die Versionskennung steht in `app.py` (`APP_VERSION`, `APP_BUILD`) und im Footer jeder Seite.

## 1.4.0 – 2026-10-13 (Build a) – Audit 2

### Sicherheit
- **Stored XSS auf der Karte und in Popups:** Namen/Notizen von Gastro-Spots, Orten, Tourtiteln, Treffpunkten, Bildunterschriften und Live-Standort-Namen wurden ungeschützt in `<script>`-Daten bzw. Leaflet-Popups eingesetzt. JSON wird jetzt `</script>`-sicher eingebettet (`_json_for_script`), Popups escapen Nutzerdaten über die neue globale JS-Funktion `escHtml()` (base.html). Inline-`confirm()`-Handler in Admin/Detail nutzen `|tojson|forceescape`.
- **Path Traversal beim Tour-Anlegen:** Das versteckte Feld `proposal_gpx_file` erlaubte Organisatoren, beliebige Server-Dateien (z. B. `.env`) als „GPX“ zu kopieren und herunterzuladen. Jetzt nur noch `.gpx`-Dateinamen aus dem GPX-Ordner.
- **Private Uploads ohne Login:** `/static/uploads/photos|videos|gpx|avatars|group_music/…` war ohne Anmeldung abrufbar (umging `serve_photo`/`serve_video`). Neuer `before_request`-Schutz; Gruppen-Logos und Ankündigungsbilder bleiben öffentlich.
- **Open Redirect:** `?next=` beim Login akzeptiert nur noch relative Pfade.
- **Passwort-Reset-Links** laufen jetzt wirklich nach 1 Stunde ab (vorher unbegrenzt gültig).
- **Mandantentrennung nachgezogen:** Vorlagen löschen/verwenden, Teilnehmer hinzufügen/entfernen, Foto-Beschriftung/GPS/Löschen/Re-Extract, Video löschen, Live-Standorte (`/api/location/tour/<id>`), Admin „Nutzer entfernen“ und die Foto-Challenge zeigen/ändern nur noch Daten der eigenen Gruppe.
- Gruppenwechsel per Session (`active_group_id`) wirkt nur noch für Admins.
- Externe Links (Komoot, Webseite) werden auf `http(s)` geprüft (`javascript:`-Links werden verworfen, fehlendes Schema wird ergänzt).

### Behoben
- **Setup-Wizard ohne `SETUP_KEY` lief auf 405:** `/setup` erlaubte nur GET, das Formular sendet aber per POST dorthin. Zusätzlich leitet `/login` jetzt zum Wizard um, solange kein Admin existiert (wie dokumentiert).
- **Admin „Nutzer entfernen“ lieferte 500** (IntegrityError), sobald der Nutzer je an einer Tour teilgenommen hatte. Das Konto wird jetzt – wie beim DSGVO-Selbstlöschen – anonymisiert und gesperrt (`_anonymize_user`); Historie bleibt konsistent, anonymisierte Konten werden im Dashboard ausgeblendet.
- **Video-Faststart lief nie:** `subprocess` war nicht importiert (NameError wurde still geschluckt). Jetzt Modul-Import; fehlgeschlagene Temp-Dateien werden entfernt.
- **Tour löschen** hinterließ verwaiste Videos, Kommentare, Zeitabstimmungen, Bewertungen und Live-Standorte (`_delete_tour_dependents`, auch beim endgültigen Gruppen-Löschen).
- **500 bei ungültigen Eingaben:** Tour anlegen/bearbeiten (Datum, km, Treffpunkt), Archiv-Nachtrag (Datum, km mit Komma), Gastro/Ort anlegen (leere Koordinaten), Gastro-Bewertung (Score außerhalb 1–5), Kommentar-Antwort (`parent_id`), iCal-Export (Startzeit wie „9 Uhr“), Live-Standort-Update (Strings statt Zahlen). Leerer Tourtitel beim Bearbeiten wird abgewiesen.
- `migrate_db()`: Gruppen-Block benutzte eine bereits geschlossene DB-Verbindung und lief nie durch (Start-Migration deckte es ab).
- `backup.sh`: Fallback-Rotation `MAX_BACKUPS=14` löschte die Wochen-/Monats-Generationen der App-Rotation wieder (jetzt 40); Erfolgsprüfung testete den Exit-Code von `rm` statt `tar`.
- Toter Code (unerreichbarer alter `parse_gpx`-Rest) entfernt.

### Geänderte Dateien
`app.py`, `backup.sh`, `templates/base.html`, `templates/karte.html`, `templates/gastro/list.html`, `templates/orte/list.html`, `templates/touren/detail.html`, `templates/admin/dashboard.html`, `templates/admin/announcements.html`, `templates/admin/notifications.html`, `templates/admin/gruppen.html`, `AUDIT_BERICHT.md`, `CHANGELOG.md`

---

## 1.3.0 – 2026-10-07 (Build h)

### Neu
- **WhatsApp-Einladungstext im Admin:** Nach „Link erstellen“ erscheint ein fertiger, editierbarer Einladungstext (mit Name, Gruppenname und persönlichem Registrierungslink, Emoji als Unicode-Escapes im Code) mit Buttons „In WhatsApp senden“ und „Text kopieren“. Bei jedem offenen Einladungslink gibt es zusätzlich einen WhatsApp-Button.

### Geänderte Dateien
`app.py`, `templates/admin/dashboard.html`, `CHANGELOG.md`

---

## 1.2.0 – 2026-10-07 (Build e) – Audit

### Sicherheit
- **Mandantentrennung:** Mitglieder einer Gruppe konnten per direkter URL Touren (und Profile) anderer Gruppen aufrufen. Alle Tour-Zugriffe laufen jetzt über `_tour_or_404()`; Profile anderer Gruppen sind für Nicht-Admins gesperrt.
- Token-Endpunkte (`/api/backup/trigger`, `/admin/run-migration`) vergleichen zeitkonstant und lehnen den Standard-`SECRET_KEY` ab.
- Fehlerseite zeigt keine technischen Exception-Texte mehr.
- Sicherheits-Header (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`).

### Behoben
- **Archiv-Suche** lieferte 500 (fehlende Zähler/Cover/Seitenwerte); Jahresliste der Suche war nicht gruppengefiltert.
- **Gastro-Google-Places-Lookup** lieferte 500 (`cfg()` kannte keinen Default-Parameter).
- **Startzeit-Abstimmung** hätte 500 geliefert, wenn die Vorlage `touren/zeitabstimmung.html` fehlt → eingebaute Ersatzseite.
- **Neuinstallation:** Start-Migration brach ab, wenn `site_config` noch nicht existierte (frische Datenbank).

### Geprüft (ohne Befund)
81 GET-Routen mit Testdaten gerendert, alle `url_for`-Ziele und Templates abgeglichen, Mandanten-Isolation (Liste, Mitglieder, Rangliste, Start, Archiv, Karte, Rückblick), Foto-Upload inkl. Duplikat-Schutz, Tour/Gastro/Ort anlegen.

### Geänderte Dateien
`app.py`, `CHANGELOG.md`, `AUDIT_BERICHT.md`

---

## 1.1.1 – 2026-10-07 (Build d)

### Behoben
- **„Gastro“ und „Orte & POIs“ zeigten die Tourenliste.** In den Auslieferungs-ZIPs lagen für `templates/gastro/list.html`, `gastro/detail.html`, `gastro/form.html`, `orte/list.html` und `orte/form.html` versehentlich falsche Dateien (Tour-Vorlagen mit gleichem Dateinamen). Die richtigen Vorlagen sind wiederhergestellt; Seitentitel nutzen jetzt den Gruppennamen.

### Geänderte Dateien
`app.py` (Version), `templates/gastro/{list,detail,form}.html`, `templates/orte/{list,form}.html`, `CHANGELOG.md`

### Deployment
Dateien hochladen (Neustart nur wegen der Versionsnummer nötig).

---

## 1.1.0 – 2026-10-07 (Build c)

### Neu
- **Versionskennung** im Footer jeder Seite (`Version 1.1.0 · 2026-10-07 c`), definiert in `app.py`.
- **Foto-Upload mit Fortschritt:** Fortschrittsbalken mit Prozent/MB, Statustext, Button-Sperre gegen Doppelklick, Warnung beim Verlassen der Seite während des Uploads (`templates/touren/detail.html`).
- **Duplikat-Schutz für Fotos:** SHA-256 des Originals wird pro Tour gespeichert (`tour_photos.orig_hash`); identische Fotos werden übersprungen und gemeldet („♻️ X Duplikate ignoriert“) – auch bei ZIP-Uploads.
- **MP4-Erstellung mit Fortschrittsanzeige:** Laufzeit-Uhr, Phasen-Statustext, geschätzte Dauer, Button-Sperre; Download startet automatisch, Fehler werden weiterhin als Meldung angezeigt (`templates/touren/video.html`).

### Behoben
- **500-Fehler auf der Startseite** nach Einführung von `orig_hash`: Die Spalte wird jetzt direkt beim Start ergänzt.
- **`migrate_db()` brach beim Start ab** („This Connection is closed“), weshalb nachfolgende Spalten-Migrationen nie liefen. Verbindungen werden jetzt korrekt geöffnet.
- **Video-Vorschau: Musik endete zu früh.** Die Ausblendung wurde vorab auf die berechnete Länge geplant, die Vorschau läuft aber real länger. Jetzt Fade-out erst zu Beginn des Outros; Frame-Takt gleicht Zeichenzeit aus.
- **Video-Titel im Hochformat abgeschnitten:** Titel wird umgebrochen (bis 4 Zeilen) und bei Bedarf verkleinert – im MP4-Export (Pillow) und in der Browser-Vorschau. Kürzung auf 40 Zeichen entfernt.

### Datenbank
- Neue Spalte `tour_photos.orig_hash VARCHAR(64)` – wird beim Start automatisch angelegt.

### Geänderte Dateien
`app.py`, `models.py`, `templates/base.html`, `templates/touren/detail.html`, `templates/touren/video.html`, `CHANGELOG.md`

### Deployment
Dateien hochladen, danach Passenger in Plesk neu starten.

---

## 1.0.0 – Stand bis 2026-10-07

Ausgangsstand dieses Changelogs: Mehrere Gruppen, Backup/Restore im Admin, Web-Push + Telegram, Ankündigungen (ein-/ausgeloggt), WhatsApp-Link und Kontakt-E-Mail, Video-Rückblick (Browser-Vorschau + MP4-Export mit Formaten, Standardmusik, Outro), Tour-Vorlagen, „Unsere Landkarte“, „Vor Jahren an diesem Tag“, Admin-Werkzeuge, optimierte mobile Navigation.
