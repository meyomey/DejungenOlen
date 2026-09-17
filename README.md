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

### 🗺️ Karte & GPX
- GPX-Upload mit automatischer Streckenberechnung (km, Höhenmeter)
- Leaflet/OSM-Karte mit GPX-Track, Start/Ziel-Marker, Treffpunkt
- Höhenprofil (Chart.js)
- Kartenvorschau auf Tourenkarten (lazy-loading Leaflet Mini-Maps)
- Live-Standort teilen während der Tour
- Offline-Kartenkacheln cachen (Service Worker)
- Kartensperre auf Mobile (Tippen zum Aktivieren)
- Export: alle GPX-Tracks eines Jahres als ZIP

### 📷 Fotos
- Einzel- oder ZIP-Upload
- Automatische GPS-EXIF-Erkennung (inkl. HEIC) → Marker auf Karte
- Manuelle Positions-Korrektur per Kartenklick
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
- Avatare, Fahrrad-Typ, Bio, Geburtstag
- Persönliche Tour-Statistiken
- Letzter Login sichtbar (eigenes Profil)

### 🗂️ Archiv & Rückblick
- Abgeschlossene Touren mit Fotos, Teilnehmerliste, GPX
- Jahresrückblick mit Infografik-Stats (Touren, km, Höhenmeter, Fotos)
- Nachträglich alte Touren mit GPX eintragen

### 🍺 Gastronomie
- Einkehrmöglichkeiten mit Bewertung, Öffnungszeiten, Karte

### ⚙️ Admin
- Mitglieder verwalten (Rollen, Sperren, Passwort-Reset)
- Einladungslinks erstellen und verwalten
- Geburtstags-Erinnerung (14 Tage voraus)
- Inaktive Mitglieder anzeigen (>90 Tage)
- Datenbank-Backup
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

## Deployment (Plesk / Netcup)

Vollständige Anleitung: [INSTALLATION_PLESK_FTP.md](INSTALLATION_PLESK_FTP.md)

Kurzfassung:
1. Dateien per FTP hochladen
2. In Plesk: Python 3.9+, `passenger_wsgi.py` als Startup-File
3. `.env` mit eigenem `SECRET_KEY` anlegen (siehe `.env.example`)
4. App neu starten
5. Setup-Wizard aufrufen

---

## Mehrere Gruppen betreiben

Es gibt zwei Möglichkeiten:

**A) Eine Installation, mehrere Gruppen (empfohlen)**
Eingebautes Feature: Admin → Gruppen verwalten → Neue Gruppe. Jede Gruppe hat eigene Mitglieder, Touren und Daten, alle in einer Datenbank sauber getrennt.

**B) Separate Installationen**
Für vollständig getrennte Server/Domains: [NEUE_GRUPPE.md](NEUE_GRUPPE.md)

---

## Projektstruktur

```
dejungen_olen/
├── app.py                  # Flask-App (120+ Routen)
├── config.py                # Konfiguration (liest aus .env)
├── models.py                 # SQLAlchemy-Modelle
├── exif_gps.py               # Pure-Python EXIF/GPS-Parser (JPEG + HEIC)
├── passenger_wsgi.py         # Phusion Passenger Einstiegspunkt
├── requirements.txt
├── .env.example               # Vorlage für Umgebungsvariablen
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
│       ├── geplant.html       # Touren ohne Termin
│       └── partials/          # Fotos, Videos, Kommentare, Lightbox, JS
└── static/
    ├── uploads/                # Fotos, GPX, Avatare, Videos, Gruppen-Logos
    └── sw.js                    # Service Worker (Offline-Karte)
```

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
