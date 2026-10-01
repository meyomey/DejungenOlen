# Neue Gruppe einrichten – Schritt-für-Schritt

## Voraussetzungen
- Zugang zu Plesk (Netcup)
- FTP-Zugang
- Eine neue Domain oder Subdomain

---

## Schritt 1 – Domain/Subdomain in Plesk anlegen

1. Plesk öffnen → **Domains** → **Domain hinzufügen**
2. Subdomain eingeben, z.B. `gruppe2.deinedomain.de`
3. Document Root: Plesk vergibt automatisch einen Pfad, z.B.:
   `/var/www/vhosts/hosting139268.a2e64.netcup.net/gruppe2.deinedomain.de/`
4. **SSL-Zertifikat aktivieren** (Let's Encrypt, kostenlos, direkt in Plesk)

---

## Schritt 2 – App-Dateien kopieren

Per FTP den gesamten Ordner `dejungen_olen/` kopieren und als z.B. `gruppe2/` im
Document-Root der neuen Domain ablegen.

Wichtig: Folgende Ordner mitkopieren:
```
gruppe2/
├── app.py
├── config.py
├── passenger_wsgi.py
├── requirements.txt
├── templates/
├── static/
├── venv/          ← virtual environment
└── backups/       ← leerer Ordner
```

Die Ordner `static/uploads/` und `backups/` können leer bleiben – werden
beim ersten Start automatisch befüllt.

---

## Schritt 3 – config.py anpassen

In `gruppe2/config.py` folgende Werte ändern:

```python
SECRET_KEY = 'ein-anderer-zufaelliger-schluessel-hier'  # WICHTIG: anders als DjO!
DATABASE_URL = 'sqlite:///gruppe2.db'                    # anderer DB-Name
```

Neuen SECRET_KEY generieren – z.B. in Python:
```python
import secrets
print(secrets.token_hex(32))
```

---

## Schritt 4 – passenger_wsgi.py prüfen

In `gruppe2/passenger_wsgi.py` den Pfad anpassen:

```python
import sys, os
sys.path.insert(0, '/var/www/vhosts/hosting139268.a2e64.netcup.net/gruppe2.deinedomain.de/gruppe2')
# ... Rest bleibt gleich
```

---

## Schritt 5 – Plesk: Python-App konfigurieren

1. Plesk → neue Domain → **Python**
2. Python-Version: **3.9**
3. Application root: `/gruppe2`
4. Application startup file: `passenger_wsgi.py`
5. **Apply** klicken
6. **Restart** klicken

---

## Schritt 6 – Erste Anmeldung

1. `https://gruppe2.deinedomain.de` aufrufen
2. Setup-Wizard erscheint automatisch (neue leere Datenbank)
3. Admin-Account anlegen
4. Gruppenname, Logo, Standard-Treffpunkt einstellen
5. Einladungslinks für neue Mitglieder erstellen

---

## Was ist komplett getrennt?

| | DjO | Gruppe 2 |
|---|---|---|
| Mitglieder | eigene | eigene |
| Touren | eigene | eigene |
| Fotos | eigene | eigene |
| Datenbank | `dejungen_olen.db` | `gruppe2.db` |
| Einstellungen | eigene | eigene |
| Admin | eigene Admins | eigene Admins |

Die Gruppen sehen sich gegenseitig **nicht** – völlig isoliert.

---

## Wartung

- Updates: Änderungen an `app.py` oder Templates müssen in **beide** Ordner
  eingespielt werden.
- Backups: Jede Instanz hat ihren eigenen Cronjob und eigenen `backups/`-Ordner.
- venv: Kann geteilt werden (Symlink) oder kopiert werden.

---

## Tipp: venv teilen (spart Speicherplatz)

Statt das venv zu kopieren, in `passenger_wsgi.py` der neuen Gruppe auf das
bestehende venv verweisen:

```python
VENV_PATH = '/var/www/vhosts/hosting139268.a2e64.netcup.net/djo.wulmstorf.net/dejungen_olen/venv'
```

So müssen Python-Pakete nur einmal installiert sein.
