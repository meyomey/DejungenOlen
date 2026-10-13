# Changelog – De jungen Olen

Neueste Version oben. Die Versionskennung steht in `app.py` (`APP_VERSION`, `APP_BUILD`) und im Footer jeder Seite.

## 1.4.0 – 2026-10-13 (Build i) – Audit 2

### Server-MP4: Übergänge, Bildunterschriften, Logo, Profilbilder (Build i)
- **Weiche Übergänge:** Jedes Segment (Folien und Fotos) blendet kurz ein (0,25 s) und aus (0,35 s) statt hart zu schneiden. Der Ken-Burns-Zoom läuft jetzt um die Bildmitte (vorher zog er Richtung linke obere Ecke).
- **Bildunterschrift & Uhrzeit auf den Fotos:** Unten links eine halbtransparente Leiste mit Aufnahmezeit (`taken_at`, „10:42 Uhr“) und Bildunterschrift (`caption`, max. 2 Zeilen, Rest „…“), Breite passt sich dem Text an. Fotos ohne beides bleiben unverändert. Technisch als transparentes PNG, das ffmpeg NACH dem Zoom auflegt (`overlay`) – bleibt dadurch scharf und ortsfest.
- **Gruppenlogo:** Als Wasserzeichen oben rechts auf Fotos und Statistik-Folie, unten links auf der Karte; auf Titel- und Outro-Folie größer mittig über dem Text. Transparente PNG-Logos werden korrekt überblendet (siehe Build f). Ohne Logo ändert sich nichts.
- **Teilnehmer mit Profilbildern:** Auf der Statistik-Folie erscheinen statt der Namenszeile runde Profilbilder mit Vornamen (ohne Bild: Initialen auf farbigem Kreis), max. 8, Rest als „+N“ – blenden wie bisher ab 55 % ein.
- Fallback-Pfad ohne ffmpeg-Zoom (`make_frame`) legt das Overlay per Pillow auf. Getestet mit der Projekt-ffmpeg in Hoch- und Querformat (Einzelbilder bei Titel, Statistik, Foto, Übergang, Outro geprüft; Übergangsbild ist dunkel).

### Server-MP4: Statistik-Folie wieder animiert (Build h)
- Die Zahlen auf der Folie „Die Tour in Zahlen“ zählen im Server-MP4 wieder hoch – gleiche Choreografie wie in der Browser-Vorschau (`drawStatsFrame`): Kacheln blenden gestaffelt ein, Strecke/Höhenmeter/Teilnehmer/Temperatur laufen in den ersten 60 % der 4 s mit Ease-out auf den Zielwert, danach erscheinen die Teilnehmernamen (max. 8, Rest als „+N“, auf Breite gekürzt). Technisch: 54 Einzelbilder (15/s) + Haltebild → ein Video-Segment über `frames_to_segment()`; schlägt das fehl, kommt wie bisher die statische Folie. Getestet mit der Projekt-ffmpeg (7.0.2) in der Sandbox: Bilder bei 3,2/3,7/4,4/6,5 s zeigen 10,9 → 31,5 → 43,9 → 47,3 km.

### Pillow-Pfade nachgezogen (Build f/g)
- Hintergrund: Das Pillow in `venv/Lib/site-packages` war ein auf dem Server installierter Build für Python 3.9 (der Ordnername mit großem L stammt aus dem alten `passenger_wsgi.py`, nicht von einer Windows-venv). Es funktionierte unter 3.9 und fiel erst mit dem Python-Update auf 3.11 aus (`cannot import name '_imaging'`); seit Build e liegt dort ein 3.11-Build, Server-MP4s haben wieder Titel-/Statistik-Folie, Kartenanimation und Blur-Hintergrund. Zwei Punkte im Pillow-Pfad korrigiert:
  - `_resize_photo_if_needed` speicherte mit Pillow **alles als JPEG** – transparente PNG-Gruppenlogos hätten einen schwarzen Hintergrund bekommen, WebP wäre zu JPEG geworden. Jetzt bleibt PNG PNG (inkl. Transparenz), WebP bleibt WebP; nur JPEG wird als JPEG gespeichert, und Transparenz wird dabei auf Weiß gelegt statt auf Schwarz.
  - Avatar-Upload verkleinerte mit Pillow **ohne EXIF-Drehung** – Handy-Fotos als Profilbild wären gekippt erschienen. Jetzt `exif_transpose` vor dem Thumbnail; Paletten-/Alpha-Bilder werden für JPEG nach RGB gewandelt.
- Geprüft: keine in Pillow ≥ 10 entfernten APIs im Code (`textsize`, `getsize`, `ANTIALIAS`); Video-Rendering nutzt `textbbox`/`LANCZOS`.

### Pakete reparieren ohne SSH (Build e)
- Admin → Pakete installieren kann jetzt auch **Pillow** und **piexif** installieren bzw. reparieren (beide stehen in `requirements.txt`). Jedes Paket hat ein Auswahl-Häkchen (fehlende/defekte sind vorangehakt) und den Status „installiert / fehlt / defekt“ mit Version und Pfad; Pillow wird funktional geprüft (C-Erweiterung `_imaging`), weil ein am Windows-PC erstelltes oder für Python 3.9 gebautes Pillow zwar vorhanden aussieht, aber nicht arbeitet. Neue Diagnosezeile: ist `pip` für den laufenden Interpreter verfügbar. Installation mit `pip --target --upgrade`, Fallbacks `--user` / `--break-system-packages`, bei fehlendem pip einmalig `ensurepip`; Fehlerprotokoll wird je Paket angezeigt.
- Hintergrund: Das Pillow in `venv/Lib/site-packages` war für Python 3.9 gebaut und lud nach dem Update auf 3.11 nicht mehr (`cannot import name '_imaging'`); Bildverarbeitung lief seitdem über ImageMagick, Server-MP4s ohne Folien.

### Auslieferung & Aufräumen (Build c/d)
- Neues Skript `make_deploy_zip.py`: erzeugt nach jeder Änderung zwei Pakete in `deploy/` – `…_komplett.zip` (gesamtes Projekt ohne `.env`, Datenbank, Uploads, Backups, venv, ffmpeg) und `…_aenderungen.zip` (nur geänderte Dateien seit der letzten Auslieferung). Jede ZIP enthält eine `_DEPLOY_HINWEISE.txt` mit Dateiliste, ggf. zu löschenden Dateien und den Schritten nach dem Upload.
- Streuner aus dem Projektstamm entfernt: `create.html` (veraltete Kopie von `templates/touren/create.html`, nirgends verwendet) und `htaccess` ohne Punkt (identische Kopie von `.htaccess`). Beide können auch auf dem Server gelöscht werden.
- Projektstamm aufgeräumt (Build d): Anleitungen und Audit-Bericht liegen jetzt in `docs/` (`INSTALLATION_PLESK_FTP.md`, `BACKUP_WIEDERHERSTELLEN.md`, `NEUE_GRUPPE.md`, `GITHUB_DESKTOP_SETUP.md`, `AUDIT_BERICHT.md`); `README.md` und `CHANGELOG.md` bleiben im Stamm. Die fünf ungenutzten Teil-Templates in `templates/touren/partials/` wurden entfernt (seit der Zusammenführung in `touren/detail.html` nirgends mehr eingebunden). README: Projektbaum aktualisiert, Abschnitt „Auslieferung per FTP“.

### Server-Python 3.9 → 3.11
- `passenger_wsgi.py` ermittelt die Python-Version selbst (kein fest verdrahtetes `python3.9` mehr); der 3.9-Altbestand steht nur noch als letzter Fallback im Suchpfad, frisch installierte Pakete gewinnen. Auto-Install nutzt `pip --target --upgrade` (ersetzt für 3.9 gebaute Reste, umgeht die Debian-12-Sperre „externally-managed-environment“).
- Admin → Pakete installieren zeigt jetzt die laufende Python-Version und den Import-Status von Pillow, piexif, gpxpy, cryptography, pywebpush sowie den ImageMagick-Pfad – Server-Zustand ohne SSH prüfbar. Ziel-Pfad überspringt site-packages fremder Python-Versionen.
- INSTALLATION_PLESK_FTP.md: Abschnitt „Python-Update des Servers“.

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
`app.py`, `passenger_wsgi.py`, `backup.sh`, `templates/base.html`, `templates/karte.html`, `templates/admin/install_packages.html`, `templates/gastro/list.html`, `templates/orte/list.html`, `templates/touren/detail.html`, `templates/admin/dashboard.html`, `templates/admin/announcements.html`, `templates/admin/notifications.html`, `templates/admin/gruppen.html`, `INSTALLATION_PLESK_FTP.md`, `README.md`, `AUDIT_BERICHT.md`, `CHANGELOG.md`, `make_deploy_zip.py` (neu), `deploy/` (neu), `docs/` (verschoben); entfernt: `create.html`, `htaccess`, `templates/touren/partials/*`

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
