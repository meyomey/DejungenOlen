# Audit-Bericht – De jungen Olen (Version 1.4.0, 13.10.2026)

Zweites Komplett-Audit (Stand Repo `main` = 1.3.0, Build 2026-10-07 h). Der erste Bericht (1.2.0) steht am Ende.

## Vorgehen
- Statisches Review von `app.py` (7.300 Zeilen, 150 Routen), `models.py`, `config.py`, `passenger_wsgi.py`, `backup.sh`, `.htaccess`, allen 44 Templates und `static/sw.js`
- `pyflakes` + Python-3.9-Kompatibilitätsprüfung aller `.py`-Dateien (Server läuft 3.9)
- Dynamischer Testlauf gegen eine temporäre SQLite-DB: 2 Gruppen, 5 Rollen (anonym, Mitglied A, Mitglied B, Organizer A, Admin), 81 GET-Routen; gezielte Angriffs-/Fehlerszenarien (Mandanten-Zugriffe, XSS-Nutzdaten, Path Traversal, Open Redirect, abgelaufene Tokens, Löschkaskaden, ungültige Formulareingaben)
- Alle `url_for`-Ziele gegen die Routen-Tabelle, alle `render_template`-Aufrufe gegen vorhandene Dateien
- Nach den Fixes: kompletter Wiederholungslauf (keine 500er, alle Rollen-Statuscodes unverändert außer den gewollten) + `node --check` aller Inline-Skripte/Handler der geänderten Seiten mit bösartigen Testdaten

## Ergebnis auf einen Blick
| Schwere | Befund | Status |
|---|---|---|
| **Hoch** | 11 Templates fehlten im GitHub-Repo – ein frischer Clone war nicht lauffähig | behoben (vom Server nachcommittet, geprüft) |
| **Mittel** | Setup-Wizard ohne `SETUP_KEY`: Formular sendete an `/setup`, das nur GET erlaubte → **405** bei jeder Neuinstallation; außerdem kein automatischer Sprung zum Wizard (Doku verspricht ihn) | behoben |
| **Hoch** | Path Traversal: Organizer konnte über `proposal_gpx_file` beliebige Server-Dateien (z. B. `.env`, DB) als GPX kopieren und herunterladen | behoben |
| **Hoch** | Stored XSS: `</script>` bzw. HTML in Gastro-/Ort-Namen, Tourtiteln, Treffpunkten, Bildunterschriften, Live-Standort-Namen → beliebiges JavaScript bei allen Mitgliedern/Admins (Karte, Listen, Tour-Detail-Popups) | behoben |
| **Mittel** | Private Uploads (`/static/uploads/photos|videos|gpx|avatars|group_music/…`) ohne Login abrufbar – umging `serve_photo`/`serve_video` | behoben |
| **Mittel** | Admin „Nutzer entfernen“ → **500** (IntegrityError), sobald der Nutzer je an einer Tour teilgenommen hatte | behoben (Anonymisierung wie DSGVO-Löschen) |
| **Mittel** | Mandanten-Lücken: Vorlagen löschen/nutzen, Teilnehmer entfernen/hinzufügen, Foto-Caption/GPS/Löschen, Video löschen, Live-Standorte, Admin-Nutzerlöschung, Foto-Challenge zeigten/änderten Daten fremder Gruppen | behoben |
| **Mittel** | Passwort-Reset-Link lief nie ab (Mail verspricht 1 Stunde) | behoben |
| **Mittel** | Open Redirect über `/login?next=https://…` | behoben |
| **Mittel** | Inline-`confirm()`-Handler mit Nutzernamen/Titeln → JS-Injection (Admin-Dashboard, Ankündigungen, Benachrichtigungen, Tour-Detail, Gruppen) | behoben |
| **Mittel** | Video-Faststart lief nie (`subprocess` nicht importiert → NameError still geschluckt) → Videos starten im Browser erst nach komplettem Download | behoben |
| **Mittel** | Tour löschen hinterließ verwaiste Videos/Kommentare/Abstimmungen/Bewertungen/Live-Standorte | behoben |
| **Mittel** | `backup.sh`: `MAX_BACKUPS=14` löschte die Wochen-/Monats-Generationen der App-Rotation wieder; Erfolgsprüfung testete `rm` statt `tar` | behoben |
| **Niedrig** | 500 bei ungültigen Formulareingaben (Datum, km, Koordinaten, Score, `parent_id`, iCal-Startzeit „9 Uhr“, Live-Standort als Text, Archiv-Nachtrag ohne/mit falschem Datum) | behoben |
| **Niedrig** | `javascript:`-URLs in Komoot-/Webseiten-Links möglich | behoben (nur `http(s)`) |
| **Niedrig** | Gruppenwechsel per Session wirkte auch für Nicht-Admins | behoben |
| **Niedrig** | `migrate_db()`: Gruppen-Block nutzte geschlossene DB-Verbindung (lief nie, Start-Migration deckte es ab) | behoben |
| **Niedrig** | Toter Code (alter `parse_gpx`-Rest hinter `return`) | entfernt |

## Details zu den behobenen Punkten

### Sicherheit
1. **Path Traversal (`tour_create`)** – Das Formular-Feld `proposal_gpx_file` (Relikt des entfernten Vorschlags-Features) wurde ungefiltert an `os.path.join(UPLOAD_FOLDER_GPX, …)` übergeben. Nachweis im Test: Fremddatei als GPX kopiert und per `/api/gpx/<id>` lesbar. Jetzt `os.path.basename()` + nur `.gpx`-Dateien, die wirklich im GPX-Ordner liegen.
2. **Stored XSS** – Zwei Wege:
   - `karte.html` bettete `json.dumps(...)|safe` in `<script>` ein → `</script>` im Gastro-Namen beendet den Block. Neue Hilfsfunktion `_json_for_script()` maskiert `<`, `>`, `&` als `\u003c` usw.
   - Leaflet-Popups (`karte.html`, `gastro/list.html`, `orte/list.html`, `touren/detail.html`) bauten HTML per Template-Literal aus Nutzerdaten. Neue globale JS-Funktion `escHtml()` in `base.html` (steht damit allen Seiten zur Verfügung), alle Popup-Interpolationen escapen jetzt; der Treffpunkt-Popup nutzt `|tojson`. Lightbox-Caption-Handler wird HTML- und JS-korrekt escaped.
   - Inline-Handler `onsubmit="return confirm('{{ u.name }} …')"` → `{{ u.name|tojson|forceescape }}` (Jinja-Autoescape dekodiert `&#39;` im Attribut wieder, daher war das vorher angreifbar).
3. **Private Uploads** – Flask liefert `static/` ohne Login aus. Neuer `before_request` `_protect_private_uploads()` beantwortet `/static/uploads/{photos,videos,gpx,avatars,group_music}/…` ohne Login mit 404. Gruppen-Logos (Login-/Registrierungsseite) und Ankündigungsbilder bleiben öffentlich. **Hinweis:** Direkt per URL geteilte Fotos/Videos funktionieren jetzt nur noch eingeloggt – gewollt, aber bitte bewusst sein.
4. **Mandantentrennung** – Neue Helfer `_own_group_or_404(obj)` (Vorlagen, Nutzer) und `_photo_tour_or_404(photo)`; verwendet in `tour_template_delete`, `tour_create_from_template`, `tour_add_participant`, `tour_remove_participant`, `photo_set_caption`, `photo_delete`, `photo_set_gps`, `photo_clear_gps`, `api_reextract_gps`, `tour_delete_video`, `location_get`, `admin_delete_user`. `foto_challenge` joint Fotos über die Tour auf die aktive Gruppe. Im Test griff Mitglied B auf alle genannten Gruppe-A-Ressourcen zu: vorher 200/302 mit Wirkung, jetzt 404.
5. **Login/Reset** – `_safe_redirect_target()` lässt nur relative Pfade zu. `reset_password` prüft `created_at` ≤ 1 h und verwaiste Tokens (`pr.user is None`).
6. **Externe Links** – `_clean_url()`: nur `http://`/`https://`, fehlendes Schema wird mit `https://` ergänzt, andere Schemata werden verworfen (Tour anlegen/bearbeiten, Gastro anlegen/bearbeiten/importieren).

### Stabilität
7. **Admin-Nutzerlöschung** – `db.session.delete(user)` scheiterte an `tour_participants.user_id NOT NULL` (SQLAlchemy versucht, die FK auf NULL zu setzen). Jetzt `_anonymize_user()` (gemeinsam mit `datenschutz_delete_account`): Name/E-Mail/Passwort/Avatar/Bio/Geburtstag entfernt, Konto gesperrt, Rolle auf `member`, Push-Abos/Live-Standorte/Reset-Tokens gelöscht. Teilnahmen, Fotos und Kommentare bleiben der Historie erhalten („Gelöschter Nutzer N“). Anonymisierte Konten werden im Admin-Dashboard ausgeblendet.
8. **Tour löschen** – `_delete_tour_dependents(tour_id)` räumt `TourVideo`, `TourComment`, `TimeVote`, `RouteRating`, `LiveLocation` ab (SQLite erzwingt keine FKs; Modelle haben nur für Teilnehmer/Fotos eine Cascade). Wird auch beim endgültigen Gruppen-Löschen genutzt.
9. **Formular-Robustheit** – Helfer `_parse_float/_parse_int/_parse_date`: ungültige Eingaben ergeben Hinweis/Default statt Traceback (`tour_create`, `tour_edit`, `gastro_new`, `gastro_review`, `poi_new`, `tour_comment`, `tour_ical`, `location_update`). `tour_edit` weist leeren Titel ab. Gastro-Score nur 1–5. Kommentar-`parent_id` muss zu einem Kommentar derselben Tour gehören.
10. **Video-Faststart** – Modul-Import `subprocess`; temporäre `.fast.mp4` wird bei Fehlschlag entfernt. (Am Server muss `ffmpeg` im Projektordner ausführbar sein – Rechte 755 per FTP-Client; im Git liegt die Datei mit 644.)
11. **backup.sh** – `MAX_BACKUPS=40` (App-Rotation hält max. 7 + 8 + 12 = 27), `TAR_RC=$?` direkt nach `tar`.
12. **Setup-Wizard** – `/setup` akzeptiert jetzt auch POST (ohne `SETUP_KEY` lief das Formular auf 405); `/login` leitet auf `/setup` um, solange noch kein Admin existiert (wie in README/INSTALLATION beschrieben). Nach dem ersten Admin bleibt `/setup` gesperrt.

### Die 11 nachgelieferten Templates (geprüft)
`auth/login.html`, `auth/forgot_password.html`, `auth/reset_password.html`, `setup.html`, `mitglieder.html`, `datenschutz.html`, `errors/403|404|500.html`, `touren/archiv_new.html`, `admin/gps_diagnose.html`: alle `url_for`-Ziele und `extends` gültig, kein `|safe`, keine Jinja-Variablen in Inline-Handlern oder `<script>`, Ankündigungen auf der Login-Seite werden escaped, keine privaten Uploads auf ausgeloggten Seiten (Login/Registrierung nutzen nur Gruppen-Logos). Alle 80 GET-Routen rendern mit den echten Templates in 5 Rollen ohne 500er; Fehlerseiten zeigen keinen Traceback; Setup-, Login-, Reset- und Archiv-Nachtrag-Flows durchgespielt.

## Offen – Entscheidung nötig (nicht geändert)
1. **Toter Code:** `templates/touren/partials/*` ist nirgends eingebunden und `_photos.html` verweist auf eine nicht existierende Route `photo_caption`; kann gelöscht werden.
2. **Gastro/POIs/Challenge gruppenübergreifend** (bekannt aus Audit 1): `GastroSpot`, `GastroReview`, `GastroPhoto`, `POI`, Challenge-Thema haben keine `group_id`. Zwei Gruppen teilen sich Orte und Challenge. Trennen = `group_id`-Spalte + Migration + Filter in ~12 Routen.
3. **Site-Einstellungen sind global**, nicht pro Gruppe: Telegram-Bot/Chat, WhatsApp-Link, `site_name`, Standard-Treffpunkt, Backup-Einstellungen (`SiteConfig`). Mit einer zweiten Gruppe landen deren Telegram-Meldungen in Gruppe 1. Lösung: `group_id` in `site_config` oder Felder am `Group`-Modell.
4. **Kein CSRF-Token**, nur `SameSite=Lax`. In Kombination mit dem (jetzt behobenen) XSS war das kritisch; weiterhin sind alle Formulare ohne Token. Empfehlung: einfaches Session-Token + `before_request`-Prüfung für POST (ca. 30 Zeilen, aber jedes `<form>` braucht ein Hidden-Feld – ~80 Formulare).
5. **Backup-Umfang:** `backup.sh`/`admin_backup` packen alle Uploads inkl. Videos (bis 500 MB je Datei) synchron in ein Tar – bei großen Videobeständen Timeout/Plattenplatz. Vorschlag: Videos ausschließen oder separat sichern.
6. **Video-Rendering** (`tour_video_render`): synchroner ffmpeg-Lauf bis 300 s im Request, kein Schutz gegen parallele Starts. Auf Shared Hosting riskant; Vorschlag: Sperrdatei + Hinweis „läuft bereits“.
7. **Profil: Passwort ändern ohne aktuelles Passwort** (`profil_edit`) – bei gestohlener Session Kontoübernahme. Empfehlung: aktuelles Passwort abfragen. Mindestlänge ist uneinheitlich (6 bei Registrierung/Setup/Admin-Reset, 8 im Profil).
8. **Token aus `SECRET_KEY` abgeleitet:** `/api/backup/trigger` (`SECRET_KEY[:20]`, im Admin-UI sichtbar) und `/admin/run-migration` (`SECRET_KEY[:16]`). Wer den Token sieht, kennt einen Teil des Secret Keys. Besser: eigener Wert in `.env` (`BACKUP_TOKEN`) oder HMAC-Ableitung. Änderung bricht die in Plesk eingetragene Cron-URL – daher nicht automatisch geändert.
9. **Uploads außerhalb von `static/`** wären die saubere Lösung statt des `before_request`-Schutzes (dann kann auch Apache/Passenger nichts direkt ausliefern, falls eine spätere `.htaccess`-Regel `static/` durchreicht).
10. **`is_active`-Prüfung bei aktiven Sessions:** funktioniert bereits (Flask-Login 0.6 behandelt inaktive Nutzer als nicht angemeldet) – geprüft, kein Handlungsbedarf.

## Weitere Beobachtungen (Niedrig, nicht geändert)
- `gastro_detail` reicht den Google-Places-Key an alle Mitglieder ins Template; `admin_settings` zeigt ihn. Key in der Google-Konsole auf die Domain beschränken.
- Gastro-/Avatar-Uploads prüfen keine Magic Bytes (Tour-Fotos schon); bei kaputtem Pillow wird die Rohdatei gespeichert.
- `gastro_delete` löscht `GastroPhoto`-Zeilen/Dateien nicht; `tour_upload_gpx` lässt die alte GPX-Datei liegen.
- `parse_gpx` hält bis zu 64 vollständige Tracks im Prozess-Speicher (`lru_cache`), `_rl_store` wächst unbegrenzt (nur IP-Keys, unkritisch).
- `api_reextract_gps` ändert Daten per GET; `api_exif_debug` lädt `exif_gps` per `importlib.reload` bei jedem Aufruf.
- `MAX_CONTENT_LENGTH` = 500 MB gilt für alle Requests (auch Login).
- Telegram-Nachrichten im HTML-Modus: `<` in Tourtiteln/Kommentaren lässt die Nachricht scheitern (wird nur geloggt).
- Backup-Restore: `extractall` ohne Pfadfilter und ohne `PRAGMA integrity_check` auf der eingespielten DB.
- `tours_this_day_past_years` fängt den 29. Februar nicht ab (liefert an dem Tag leer).
- CDN-Skripte (Bootstrap, Leaflet, Chart.js) ohne `integrity`-Attribut; Service Worker cacht Fotos „cache-first“ (bleiben nach Logout im Browser-Cache).
- `passenger_wsgi.py` installiert fehlende Pakete per `pip` beim Start (120 s Timeout) – kann Kaltstarts verlangsamen; doppelter `import subprocess`.
- `.gitattributes` `* text=auto` zusammen mit 80 MB `ffmpeg`-Binary im Repo; Binary liegt mit Modus 644 (nicht ausführbar) im Git.

## Geänderte Dateien (1.4.0)
`app.py`, `backup.sh`, `.gitignore`, `templates/base.html`, `templates/karte.html`, `templates/gastro/list.html`, `templates/orte/list.html`, `templates/touren/detail.html`, `templates/admin/dashboard.html`, `templates/admin/announcements.html`, `templates/admin/notifications.html`, `templates/admin/gruppen.html`, `CHANGELOG.md`, `AUDIT_BERICHT.md`

---

# Audit-Bericht – Version 1.2.0 (07.10.2026)

## Vorgehen
- Alle 81 GET-Routen mit Testdaten (2 Gruppen, Admin/Mitglied/Fremdgruppe) automatisch aufgerufen
- Templates ↔ `render_template` und `url_for`-Ziele ↔ Routen abgeglichen
- Routen ohne Login-Schutz geprüft
- Mandanten-Isolation getestet, Foto-Upload, Duplikat-Schutz, Anlegen von Tour/Gastro/Ort

## Gefunden und behoben
| Schwere | Befund | Status |
|---|---|---|
| Hoch | Mitglieder konnten per URL Touren/Profile anderer Gruppen öffnen | behoben |
| Hoch | Archiv-Suche → 500 | behoben |
| Mittel | Gastro Places-Lookup → 500 (`cfg()`-Signatur) | behoben |
| Mittel | Startzeit-Abstimmung: Vorlage fehlt im Repo/Original-ZIP → Fallback eingebaut | behoben |
| Mittel | Neuinstallation (leere DB) brach in Start-Migration ab | behoben |
| Niedrig | Token-Vergleich nicht zeitkonstant; Standard-SECRET_KEY akzeptiert | behoben |
| Niedrig | Fehlerseite zeigte Exception-Text | behoben |
| Niedrig | Keine Security-Header | behoben |

## Offen / bewusst so gelassen
- **Gastro-Orte und POIs sind gruppenübergreifend** (kein `group_id`). Bei zwei Gruppen sehen beide dieselben Einträge. Falls getrennt gewünscht: `group_id` ergänzen.
- **Kein CSRF-Token** in Formularen; Schutz nur über `SameSite=Lax`-Cookie. Für diese App akzeptabel, bei Bedarf Flask-WTF/eigenes Token ergänzen.
- `templates/vorschlaege/*` sind toter Code (Feature entfernt) und können gelöscht werden.
- `SECRET_KEY` in `.env` muss gesetzt sein (sonst Warnung + Token-Endpunkte gesperrt).
- Push (`/push/vapid-public-key` = 503) funktioniert nur mit installiertem `pywebpush`.

## Tipps
1. **Backup-Test:** Einmal pro Quartal einen Restore auf einer Kopie testen.
2. **`.env` und `instance/*.db` niemals ins GitHub-Repo** (steht in `.gitignore`).
3. **Fotos verkleinern:** Server-seitig wird bereits skaliert; ältere Uploads ggf. einmal nachkomprimieren.
4. **Statusseite:** Version im Footer + Admin-Diagnose reichen zur Fehlersuche; ein Eintrag „Letzter Backup-Zeitpunkt“ im Dashboard wäre nützlich.
5. **Fehlerlog:** Passenger-Log (`logs/error_log` in Plesk) bei 500ern zuerst ansehen.
6. **Datenexport:** Ein „Meine Daten exportieren“-Button (JSON/ZIP) hilft bei DSGVO-Anfragen.
7. **Mitglieder-Einladung per WhatsApp-Link** mit Vorlagentext direkt im Admin.
