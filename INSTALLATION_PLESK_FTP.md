# 🚴 De jungen Olen – Installation auf Netcup Plesk (nur FTP, kein SSH)

Diese Anleitung erklärt die komplette Installation **ohne Shell-Zugriff**,
nur mit FTP und dem Plesk-Webinterface.

---

## Schritt 1 – Dateien per FTP hochladen

1. ZIP entpacken → Ordner `dejungen_olen/` entsteht
2. FTP-Programm öffnen (z.B. FileZilla)
3. **Alle Dateien** aus `dejungen_olen/` hochladen nach:
   ```
   /var/www/vhosts/hosting139268.a2e64.netcup.net/djo.wulmstorf.net/dejungen_olen/
   ```
   (Pfad aus deinen Plesk-Zugangsdaten ergibt sich automatisch)

4. **`.env` anlegen:** Kopiere `.env.example` → `.env`, öffne sie im FTP-Editor und setze:
   ```
   SECRET_KEY=irgendein-langer-zufaelliger-string-mindestens-32-zeichen
   BASE_URL=https://djo.wulmstorf.net
   SETUP_KEY=mein-geheimer-setup-schluessel
   ```
   Lade die geänderte `.env`-Datei hoch.

---

## Schritt 2 – Python-App in Plesk einrichten

1. Plesk öffnen → **Websites & Domains** → deine Domain
2. Klick auf **Python** (oder „Webapplikationen" → Python)
3. Einstellungen:

   | Feld | Wert |
   |---|---|
   | Python-Version | 3.11 oder 3.12 (höchste verfügbare wählen) |
   | Anwendungs-Root | `dejungen_olen` |
   | Anwendungs-URL | `/` |
   | Startup-Datei | `passenger_wsgi.py` |

4. Klick **OK** oder **Speichern** → Plesk erstellt automatisch ein virtualenv

---

## Schritt 3 – Pakete installieren (in Plesk)

1. Auf der gleichen Python-Seite: **„pip install"** oder **„Pakete installieren"**
2. Wähle `requirements.txt` oder gib manuell ein:
   ```
   flask flask-sqlalchemy flask-login gpxpy pillow python-dotenv requests
   ```
3. Klick **Installieren** – warten bis fertig

   > Falls Plesk kein pip-Interface hat: Gehe zu Schritt 3b

### Schritt 3b – Alternative: requirements.txt über Plesk-Terminal (falls vorhanden)

Manche Plesk-Versionen haben einen **Web-Terminal** unter:
`Websites & Domains → deine Domain → Terminal`

Dort eingeben:
```bash
cd /var/www/vhosts/.../djo.wulmstorf.net/dejungen_olen
source venv/bin/activate
pip install -r requirements.txt
```

---

## Schritt 4 – App starten (Passenger neu starten)

In Plesk:
1. **Python** → **Neu starten** oder
2. **Websites & Domains** → Domain → **„App neu starten"**

---

## Schritt 5 – Ersteinrichtung im Browser

Öffne in deinem Browser:

```
https://djo.wulmstorf.net/setup/mein-geheimer-setup-schluessel
```

(Der Schlüssel ist dein `SETUP_KEY` aus der `.env`-Datei)

Auf der Setup-Seite:
- Admin-Name und E-Mail eingeben
- Sicheres Passwort wählen
- Optional: Telegram Bot-Token und Chat-ID
- Klick **App einrichten**

**Fertig!** Die Datenbank wird automatisch angelegt und du wirst direkt eingeloggt.

---

## Schritt 6 – Erste Schritte nach der Einrichtung

1. **Mitglieder einladen:** Admin-Bereich → Einladungslink erstellen → Link per Telegram teilen
2. **Einstellungen prüfen:** `/admin/einstellungen`
   - Standard-Treffpunkt (Dörphus Wulmstorf ist voreingestellt)
   - Telegram-Bot testen
   - Frühöffner-Schwellzeit anpassen
3. **Erste Tour anlegen:** Navigation → Touren → Neue Tour

---

## Häufige Probleme

### „Internal Server Error" nach Upload

**Ursache A – `.env` fehlt oder SECRET_KEY nicht gesetzt:**
- Prüfe ob `.env` im Projektordner liegt (nicht `.env.example`)
- SECRET_KEY muss gesetzt sein (kein leerer String)

**Ursache B – Pakete nicht installiert:**
- Schritt 3 wiederholen
- In der Plesk-Python-App prüfen ob das virtualenv existiert

**Ursache C – Falscher Anwendungs-Root:**
- In Plesk prüfen: Anwendungs-Root muss auf `dejungen_olen/` zeigen
- Startup-Datei: `passenger_wsgi.py`

**Ursache D – Python-Version:**
- `passenger_wsgi.py` sucht automatisch nach `venv/lib/python3.X/`
- In Plesk: Python 3.9+ wählen

### Setup-Seite zeigt „bereits eingerichtet"

Das Admin-Konto existiert schon. Gehe zu `/login`.
Falls du das Passwort vergessen hast → Plesk-Terminal nutzen:
```bash
flask --app app create-admin
```

### Fotos erscheinen nicht auf der Karte

- Fotos müssen GPS-EXIF-Daten enthalten (iPhone/Android-Kamera mit Standortzugriff)
- Nach dem Upload: Klick auf das ✏️-Icon beim Foto → GPS manuell auf Karte setzen

---

## Dateistruktur nach dem Upload

```
djo.wulmstorf.net/
└── dejungen_olen/
    ├── .env                    ← Deine Konfiguration (per FTP anlegen)
    ├── app.py
    ├── models.py
    ├── config.py
    ├── passenger_wsgi.py
    ├── requirements.txt
    ├── static/
    │   ├── logo.png
    │   └── uploads/            ← Wird automatisch befüllt
    ├── templates/
    └── venv/                   ← Wird von Plesk automatisch erstellt
```

---

## Cron-Job für Telegram-Erinnerungen (optional)

In Plesk → **Geplante Aufgaben** → Neue Aufgabe:

```
Kommando:  /var/www/vhosts/.../dejungen_olen/venv/bin/flask --app /var/www/vhosts/.../dejungen_olen/app send-reminders
Zeitplan:  Täglich 18:00 Uhr
```

---

*De jungen Olen Radgruppe · djo.wulmstorf.net*
