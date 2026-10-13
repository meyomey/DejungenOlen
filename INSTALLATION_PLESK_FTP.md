# Installation auf Netcup / Plesk (FTP-only)

Schritt-für-Schritt Anleitung für die Bereitstellung auf einem Netcup-Webhosting
mit Plesk-Oberfläche und FTP-Zugang (kein SSH erforderlich).

---

## Voraussetzungen

- Netcup Webhosting mit Plesk
- Python 3.9 oder neuer (aktuell 3.11 auf dem Server) – in Plesk unter „Python"
- FTP-Client (z.B. FileZilla)
- Domain oder Subdomain eingerichtet

---

## Schritt 1 – Dateien hochladen

Per FTP alle Projektdateien in das App-Verzeichnis hochladen:

```
/var/www/vhosts/HOSTING_ID/DOMAIN/dejungen_olen/
├── app.py
├── config.py
├── passenger_wsgi.py
├── requirements.txt
├── templates/
├── static/
└── backups/          ← leeren Ordner anlegen!
```

**Wichtig:** Den Ordner `backups/` manuell anlegen (sonst schlägt der Cronjob fehl).

---

## Schritt 2 – config.py anpassen

```python
SECRET_KEY   = 'HIER-EINEN-ZUFAELLIGEN-SCHLUESSEL-EINTRAGEN'
DATABASE_URL = 'sqlite:///dejungen_olen.db'
```

Zufälligen Key generieren (lokal in Python):
```python
import secrets; print(secrets.token_hex(32))
```

---

## Schritt 3 – passenger_wsgi.py prüfen

Die mitgelieferte `passenger_wsgi.py` ermittelt die Python-Version selbst
(`python3.11`, `python3.9` …) und trägt nur vorhandene Paketpfade ein – nach einem
Python-Update des Servers muss hier nichts mehr angepasst werden. Anzupassen sind nur
`project_root` und `vhost_home` (HOSTING_ID / DOMAIN):

```python
project_root = '/var/www/vhosts/HOSTING_ID/DOMAIN/dejungen_olen'
vhost_home   = '/var/www/vhosts/HOSTING_ID'
```

Gesucht wird (in dieser Reihenfolge): `~/.local/lib/pythonX.Y/site-packages`,
`dejungen_olen/venv/Lib/site-packages` (Ziel von „Admin → Pakete installieren“),
`dejungen_olen/venv/lib/pythonX.Y/site-packages`, zuletzt der Altbestand für Python 3.9.

---

## Schritt 4 – Python-App in Plesk konfigurieren

1. Plesk → Domain → **Python**
2. Python-Version: **3.9**
3. Application root: `dejungen_olen`
4. Application startup file: `passenger_wsgi.py`
5. **Install Python packages** klicken (installiert requirements.txt)
6. **Apply** → **Restart**

---

## Schritt 5 – Erste Anmeldung

`https://DEINE-DOMAIN.de` aufrufen → Setup-Wizard erscheint:

1. Admin-Name, E-Mail und Passwort eingeben
2. Gruppenname festlegen (z.B. „De jungen Olen")
3. Standard-Treffpunkt auf Karte setzen
4. Fertig – Einladungslinks unter Admin → Einladen erstellen

---

## Schritt 6 – Backup-Cronjob einrichten

In Plesk → **Geplante Aufgaben**:

```bash
0 2 * * * mkdir -p /PFAD/backups && bash /PFAD/backup.sh >> /PFAD/backups/backup.log 2>&1
```

---

## Bekannte Besonderheiten

### Pillow (Bildbearbeitung)
Falls Pillow auf dem Server nicht funktioniert, wird automatisch ImageMagick als
Fallback verwendet. Kein Handlungsbedarf.

### pywebpush
Wird über den `.local`-Pfad eingebunden (vendored). Nicht upgraden.

### SQLite WAL-Modus
Automatisch aktiv – ermöglicht parallele Lesezugriffe ohne Locks.

### Passenger neu starten
Nach Code-Änderungen: In Plesk → Python → **Restart** klicken.
Alternativ: `tmp/restart.txt` im App-Verzeichnis per FTP anlegen oder aktualisieren.

### Python-Update des Servers (z. B. 3.9 → 3.11)
Die App selbst ist versionsunabhängig; betroffen sind nur installierte Pakete mit
C-Erweiterungen (Pillow, cryptography/cffi), die für die alte Version gebaut wurden.

1. Plesk → Python: Version auf die neue (z. B. 3.11) stellen, Startup-File bleibt
   `passenger_wsgi.py` → **Apply** → **Restart**.
2. Als Admin anmelden → Admin → Tools → **Pakete installieren**: Der Kasten
   „Python-Umgebung auf dem Server“ zeigt die laufende Version und ob Pillow,
   cryptography, pywebpush und ImageMagick importierbar sind.
3. Steht dort bei cryptography/pywebpush „FEHLT/DEFEKT“: Button **Pakete installieren /
   aktualisieren** klicken – die Pakete werden passend zur neuen Python-Version nach
   `venv/Lib/site-packages` installiert (`pip --target --upgrade`, funktioniert auch
   trotz Debian-12-Sperre „externally-managed-environment“).
4. Pillow „FEHLT/DEFEKT“ ist unkritisch – die Bildverarbeitung läuft dann über
   ImageMagick (Fallback ist eingebaut).

---

## Troubleshooting

| Problem | Lösung |
|---|---|
| 500 Internal Server Error | `passenger_wsgi.py` temporär auf `sys.stderr.write(traceback) + raise` umschreiben |
| Karte lädt nicht | Leaflet CDN erreichbar? HTTPS korrekt? |
| Fotos werden nicht gespeichert | `static/uploads/` Ordner vorhanden und schreibbar? |
| E-Mails kommen nicht an | SMTP-Einstellungen in Plesk/config.py prüfen |
| Login schlägt fehl | `SESSION_COOKIE_SAMESITE = 'Lax'` in config.py gesetzt? |
