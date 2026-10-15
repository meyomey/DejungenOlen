# 🚴 De jungen Olen – Radgruppen-App

Eine selbst gehostete Web-App für Radgruppen. Gebaut mit Python/Flask, SQLite und Leaflet.js. Unterstützt mehrere unabhängige Gruppen in einer Installation.

> **Live-Demo:** [djo.wulmstorf.net](https://djo.wulmstorf.net)

---

## Features

### 🏘️ Mehrere Gruppen (Multi-Tenancy)
- Beliebig viele unabhängige Radgruppen in einer Installation
- Jede Gruppe hat eigene Mitglieder, Touren, Fotos, Einstellungen
- Eigenes Logo pro Gruppe mit integriertem Zuschneide-Editor (Zoom & Verschieben)
- Admins können zwischen Gruppen wechseln
- Gruppen können leer oder inklusive aller Daten gelöscht werden

### 🗓️ Touren
- Geplante Touren mit Datum, Treffpunkt, Schwierigkeitsgrad
- **Touren ohne Termin** – Routenideen sammeln und bewerten (👍/😐/👎)
- RSVP (Dabei / Vielleicht / Absage) mit Teilnehmerübersicht
- Startzeit-Abstimmung (09:00–11:00 Uhr)
- Termin nachträglich fixieren (Organizer)
- Tour-Karten mit Cover-Foto aus Tourfotos + Kartenvorschau
- Tour absagen (mit Grund) / Absage zurücknehmen – Push an Angemeldete + Telegram; „Änderung mitteilen“
  beim Bearbeiten von Datum, Uhrzeit, Treffpunkt
- Automatische Erinnerungen am Vorabend (ab 18 Uhr) und am Tourtag (ab 7 Uhr), Uhrzeiten im Admin einstellbar
- Fahrgemeinschaften je Tour (Plätze anbieten / Mitfahrt suchen, Push an Suchende)
- Druckbare Teilnehmerliste mit Telefon und Notfallkontakt (nur Tourleitung/Admin)

### 🗺️ Karte & GPX
- GPX-Upload mit automatischer Streckenberechnung (km, Höhenmeter)
- Leaflet/OSM-Karte mit GPX-Track, Start/Ziel-Marker, Treffpunkt
- Höhenprofil (Chart.js)
- Kartenvorschau auf Tourenkarten (lazy-loading Leaflet Mini-Maps)
- Live-Karte je Tour (`/touren/<id>/live`): zuschauen oder Standort teilen, Mitfahrer mit Initialen, Streckenkilometer, Vollbild, Wake Lock
- Gruppen-Karte: Gastro (mit Öffnungszeiten, Ruhetag, Mittagstisch, „jetzt geöffnet“, Filter, Clustering), Orte, Treffpunkte
- Offline-Kartenkacheln cachen (Service Worker)
- Kartensperre auf Mobile (Tippen zum Aktivieren)
- Export: alle GPX-Tracks eines Jahres als ZIP

### 📷 Fotos
- Einzel- oder ZIP-Upload
- Automatische GPS-EXIF-Erkennung (inkl. HEIC) → Marker auf Karte
- Manuelle Positions-Korrektur per Kartenklick
- Fotos ohne Standort (Galerie-Upload vom Handy) werden anhand der Aufnahmezeit auf der GPX-Aufzeichnung platziert – automatisch beim Hochladen, nachträglich per Knopf mit Zeitkorrektur; geschätzte Positionen sind markiert (Build ac)
- Lightbox mit Swipe/Keyboard-Navigation
- Beschriftung direkt in der Lightbox (AJAX, kein Reload)
- Bulk-Auswahl und Löschung

### 🌤️ Wetter
- Open-Meteo Integration (kostenlos, kein API-Key nötig)
- Wetter-Badge auf Tourenkarten (bis 14 Tage im Voraus)
- Stündlicher Tagesverlauf als interaktives Chart (Temperatur, Regen, Wind)
- Startzeitmarkierung im Tagesverlauf

### 🏆 Rangliste
- Podium (🥇🥈🥉) mit Avataren und Balkengrafik
- 3 Tabs: Gesamt · Dieses Jahr · Kilometer
- Fortschrittsbalken relativ zum Erstplatzierten

### 👤 Benutzer & Profile
- Einladungsbasierte Registrierung (kein offener Zugang)
- Rollen: Admin / Organizer / Mitglied
- Avatare, Fahrrad-Typ, Bio, Geburtstag, Handynummer + Notfallkontakt (nur für Tourleitung sichtbar)
- Anmelde-Link per E-Mail (ohne Passwort, 15 Minuten gültig) – wenn SMTP konfiguriert ist
- Persönliche Tour-Statistiken
- Letzter Login sichtbar (eigenes Profil)

### 🗂️ Archiv & Rückblick
- Abgeschlossene Touren mit Fotos, Teilnehmerliste, GPX
- Jahresrückblick mit Infografik-Stats (Touren, km, Höhenmeter, Fotos)
- Nachträglich alte Touren mit GPX eintragen

### 🍺 Gastronomie
- Einkehrmöglichkeiten mit Bewertung, Öffnungszeiten, Karte
- Mittagstisch: Filter in der Gastro-Liste (auch nach Wochentag), Häkchen „nur mittags“ in der
  OpenStreetMap-Suche (Tour-Seite und Eintragsformular); Abzeichen aus OSM-Tag `lunch` oder aus den
  Öffnungs-/Küchenzeiten abgeleitet („mittags geöffnet Mo–Fr“ / „mittags geschlossen“)

### ⚙️ Admin
- Mitglieder verwalten (Rollen, Sperren, Passwort-Reset)
- Einladungslinks erstellen und verwalten
- Geburtstags-Erinnerung (14 Tage voraus)
- Inaktive Mitglieder anzeigen (>90 Tage)
- Backups: Datenbank täglich, Komplett-Backup (Fotos/GPX, Videos optional) im gewählten Intervall –
  im Hintergrund, Rotation 7 Tage / 8 Wochen / 12 Monate je Art, Wiederherstellung im Admin
- Erinnerungs-Uhrzeiten, Test-Knöpfe für Tourtag-/Vorabend-Erinnerung
- API-Dokumentation unter `/api/docs`

### 📱 Mobile & PWA
- Responsive Bootstrap 5 Design mit Bottom Navigation
- PWA (installierbar als App)
- Dark Mode

---

## Tech Stack

| Komponente | Technologie |
|---|---|
| Backend | Python 3.9+, Flask, SQLAlchemy |
| Datenbank | SQLite (WAL-Modus) |
| Frontend | Bootstrap 5, Leaflet.js, Chart.js |
| Karten | OpenStreetMap |
| Wetter | Open-Meteo API (kostenlos) |
| Hosting | getestet auf Netcup / Plesk / Phusion Passenger |

---

## Schnellstart (lokale Entwicklung)

```bash
# 1. Repo klonen
git clone https://github.com/DEIN_USER/dejungen-olen.git
cd dejungen-olen

# 2. Virtuelle Umgebung
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. Abhängigkeiten
pip install -r requirements.txt

# 4. Umgebungsvariablen
cp .env.example .env
# .env öffnen und SECRET_KEY setzen (siehe Kommentar in der Datei)

# 5. Starten
python app.py
```

→ App läuft auf `http://localhost:5000`

Beim ersten Aufruf erscheint der Setup-Wizard: Admin-Account anlegen, erste Gruppe (Name, Logo, Standard-Treffpunkt) einrichten.

---

## Tests (Smoke-Tests)

Im Ordner `tests/` liegen Smoke-Tests auf Basis der Standardbibliothek (`unittest`) – keine
zusätzlichen Pakete nötig. Sie laufen gegen eine eigene SQLite-Datei im Temp-Ordner und bauen
keine Netzverbindungen auf (Push, Telegram, E-Mail, Overpass und Wetter sind durch Attrappen ersetzt).

```bash
# im Projektordner, mit aktivierter virtueller Umgebung
python -m unittest                      # alle Tests (~35 s)
python -m unittest -v tests.test_touren # ein Modul, ausführlich
python -m unittest tests.test_routes.RoutesTest.test_all_get_routes_member
```

| Modul | Prüft |
|---|---|
| `tests/test_routes.py` | Login, Zugriffsschutz, **jede GET-Route** als Mitglied/Organisator/Admin ohne 500er, Gruppen-Trennung |
| `tests/test_touren.py` | Tour anlegen/bearbeiten, RSVP, GPX-Upload → Fahrzeit/Ø-Tempo/Vorschau, Archiv, „Nochmal fahren“, „Ich war dabei“, Abend-Erinnerung, Kalender-Abo/ICS, Großschrift |
| `tests/test_gastro.py` | Gastro-Liste, Schnell-Übernahme mit Duplikat-Schutz, Overpass-Suche (Attrappe: 406-Ausweich, Cache, 502), Streckensuche, Öffnungszeiten-Helfer, geplante Einkehr, Mittagstisch (Parser, OSM-Tags, Filter, Formular, Einkehr-Hinweis) |
| `tests/test_downloads.py` | GPX-Download, Archiv-ZIP, Tour-Paket (tour.txt), Druckansicht |
| `tests/test_live.py` | Live-Karte: Zeitfenster, `open_now`, Initialen, Migration, API-Rechte, veraltete Standorte, Seiten; Gruppen-Karte (Filter, Popup-Daten, „offen“) |
| `tests/test_helpers.py` | `parse_gpx`, Track-Vereinfachung, SVG-Vorschau, ICS-Maskierung/-Faltung, Formular-Parser, Template-Filter |
| `tests/test_build_ac.py` | Fotos per Aufnahmezeit auf dem GPX-Track platzieren (Interpolation, Toleranz, Lücken, Zeitkorrektur), Upload-Hinweise, `gps_source`, EXIF-DateTimeOriginal |
| `tests/test_build_ab.py` | Erinnerungen mit Uhrzeit-Schranke, Absage/Reaktivierung + Benachrichtigung, „Änderung mitteilen“, Anmelde-Link, Notfallkontakt/Teilnehmerliste, Fahrgemeinschaften, Backup-Modi/Rotation/sicheres Entpacken, GPX-Ausdünnung, Service-Worker-Cache, entfernte Routen |

Vor jeder Auslieferung einmal `python -m unittest` laufen lassen – ein roter Test heißt: nicht hochladen.

---

## Deployment (Plesk / Netcup)

Vollständige Anleitung: [docs/INSTALLATION_PLESK_FTP.md](docs/INSTALLATION_PLESK_FTP.md)

Kurzfassung:
1. Dateien per FTP hochladen
2. In Plesk: Python 3.9+ (aktuell 3.11), `passenger_wsgi.py` als Startup-File
3. `.env` mit eigenem `SECRET_KEY` anlegen (siehe `.env.example`)
4. App neu starten
5. Setup-Wizard aufrufen

---

## Mehrere Gruppen betreiben

Es gibt zwei Möglichkeiten:

**A) Eine Installation, mehrere Gruppen (empfohlen)**
Eingebautes Feature: Admin → Gruppen verwalten → Neue Gruppe. Jede Gruppe hat eigene Mitglieder, Touren und Daten, alle in einer Datenbank sauber getrennt.

**B) Separate Installationen**
Für vollständig getrennte Server/Domains: [docs/NEUE_GRUPPE.md](docs/NEUE_GRUPPE.md)

---

## Projektstruktur

```
dejungen_olen/
├── tests/                 # Smoke-Tests (python -m unittest)
├── app.py                  # Flask-App (150 Routen)
├── config.py                # Konfiguration (liest aus .env)
├── models.py                 # SQLAlchemy-Modelle
├── exif_gps.py               # Pure-Python EXIF/GPS-Parser (JPEG + HEIC)
├── passenger_wsgi.py         # Phusion Passenger Einstiegspunkt
├── requirements.txt
├── .env.example               # Vorlage für Umgebungsvariablen
├── backup.sh                 # Backup: `backup.sh db` (nur Datenbank) / `backup.sh full` (+ Fotos/GPX)
├── make_deploy_zip.py        # Deploy-Pakete erzeugen (siehe unten)
├── CHANGELOG.md
├── docs/                     # Anleitungen & Audit-Bericht
│   ├── INSTALLATION_PLESK_FTP.md
│   ├── BACKUP_WIEDERHERSTELLEN.md
│   ├── NEUE_GRUPPE.md
│   ├── GITHUB_DESKTOP_SETUP.md
│   └── AUDIT_BERICHT.md
├── deploy/                   # Fertige ZIPs für den FTP-Upload
├── templates/
│   ├── base.html              # Layout, Bottom Nav, Dark Mode, Logo-Cropper
│   ├── index.html             # Startseite
│   ├── gruppe_neu.html        # Neue Gruppe anlegen
│   ├── admin/
│   │   ├── dashboard.html
│   │   └── gruppen.html       # Gruppenverwaltung
│   ├── auth/
│   │   └── register.html
│   └── touren/
│       ├── list.html          # Tourenliste (mit Mini-Karten)
│       ├── detail.html        # Tour-Details
│       ├── archiv.html        # Tourarchiv
│       └── geplant.html       # Touren ohne Termin
└── static/
    ├── js/osm_gastro.js        # Mittagstisch-Auswertung im Browser (OSM-Fallback, Abzeichen, Filter)
    ├── uploads/                # Fotos, GPX, Avatare, Videos, Gruppen-Logos
    └── sw.js                    # Service Worker (Offline-Karte)
```

---

## Auslieferung per FTP

Nach jeder Änderung liegen in `deploy/` zwei fertige Pakete (erzeugt mit `python make_deploy_zip.py`):

- `deploy_v<Version>_<Build>_komplett.zip` – gesamtes Projekt (ohne `.env`, Datenbank, Uploads, Backups, venv, ffmpeg)
- `deploy_v<Version>_<Build>_aenderungen.zip` – nur die Dateien, die sich seit dem Stand geändert haben, der auf dem Server liegt (gemerkt in `deploy/LAST_DEPLOY.txt`; nach einem Upload mit `python make_deploy_zip.py --deployed` fortschreiben)

ZIP entpacken, Inhalt mit gleicher Ordnerstruktur per FTP in den App-Ordner kopieren, Passenger neu starten. Die `_DEPLOY_HINWEISE.txt` in jeder ZIP listet die Dateien, ggf. auf dem Server zu löschende Dateien und die Schritte nach dem Upload.

---

## Konfiguration

Über Umgebungsvariablen (`.env`, siehe `.env.example`):

| Variable | Bedeutung | Pflicht |
|---|---|---|
| `SECRET_KEY` | Flask Session Key | ✅ ja |
| `DATABASE_URL` | SQLite Pfad | nein (Default: `sqlite:///dejungen_olen.db`) |
| `HTTPS` | `true` wenn per HTTPS gehostet | nein |
| `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_FROM` | SMTP für Passwort-Reset & Benachrichtigungen | nein |

---

## Lizenz

MIT – privates Hobby-Projekt, kein Support garantiert.
