# Changelog – De jungen Olen

Neueste Version oben. Die Versionskennung steht in `app.py` (`APP_VERSION`, `APP_BUILD`) und im Footer jeder Seite.

## 1.4.0 – 2026-10-15 (Build ah) – Tourseite auf dem Handy kompakter

Rückmeldung zum Smartphone-Layout der Tour-Detailseite: Kennzahlen-Kärtchen und Aktions-Knöpfe
nahmen oberhalb der Karte fast die halbe erste Bildschirmseite ein.

- **Kennzahlen in einer Zeile** – km, Anstieg, Fahrzeit, Ø km/h und „Dabei“ stehen auf
  Smartphones gestaucht nebeneinander (kleinere Zahlen, dz. Beschriftung) statt als 2×2 große
  Kärtchen; die Wetter-Kachel (vergangene Touren) wird eine schmale eigene Zeile darunter.
  Die Karte beginnt dadurch merklich weiter oben.
- **Knöpfe kompakter** – Bearbeiten, Als Vorlage speichern, Nochmal fahren, Löschen, Rückblick
  & Video usw. sind auf dem Handy etwas kleiner, sodass 2–3 in eine Reihe passen (vorher oft
  nur einer je Zeile). Alle Knöpfe bleiben sichtbar – nichts ist in Menüs versteckt.
- **Nur unter 576 px Bildschirmbreite und nur ohne Großschrift-Modus**: Desktop-Ansicht und der
  Großschrift-Modus (große Kacheln, große Tipp-Flächen) bleiben unverändert. Das CSS wird über
  den Build-Parameter neu geladen (`style.css?v=…ah`), der Service-Worker-Cache wechselt automatisch.
- 2 neue Tests (`tests/test_build_ag.py`), insgesamt 179.

Geänderte Dateien: `app.py` (Build-Kennung), `templates/touren/detail.html`, `static/css/style.css`,
`tests/test_build_ag.py`, `CHANGELOG.md`.

## 1.4.0 – 2026-10-15 (Build ag) – Uploads schneller & robuster, Erinnerung pünktlich per Cron

Komplett-Review von Code, Templates und Tests vorab: keine Sicherheits- oder Stabilitätsprobleme.
Umsetzung der dabei gefundenen Punkte:

- **Foto-Upload deutlich schneller bei Touren ohne Zeitquelle** – Der Cache für die Zeitstempel-Punkte
  (GPX, sonst Live-Aufzeichnung) merkte sich nur *nicht-leere* Ergebnisse: Hatte die Tour einen GPX
  **ohne** Zeitstempel (geplante Route) und keine Live-Aufzeichnung, wurde der GPX für **jedes** Foto
  ohne GPS neu geparst (gemessen ~100 ms je 3 000 Punkte am Server) plus je zwei Abfragen. Jetzt wird
  pro Upload genau einmal geladen – auch wenn das Ergebnis leer ist.
- **Erinnerungen pünktlich per Plesk-Cron** – Die Tourtag-/Vorabend-Erinnerung wird bisher nur mit
  ~3 % Wahrscheinlichkeit pro Seitenaufruf ausgelöst; bei einer kleinen Gruppe kam „ab 7 Uhr" real
  oft erst gegen Mittag. Neuer Endpunkt **`/api/reminder/trigger`** (gleiches Muster und gleiches
  Token wie `/api/backup/trigger`): In Plesk als Geplante Aufgabe z. B. alle 15 Minuten aufrufen,
  dann geht die Erinnerung pünktlich raus. Doppelt schicken ist unmöglich (Tagesflags), der
  Selbst-Trigger bleibt als Rückfallebene und wird durch den Cron-Aufruf nicht zusätzlich angestoßen.
  Fertige URL mit Kopier-Knopf: **Admin → Benachrichtigungen** (unter den Erinnerungs-Uhrzeiten).
- **Freundliche 413-Seite** – Uploads über der Gesamtgrenze (z. B. Video > 500 MB, ein ganzer
  Foto-Stapel) zeigen jetzt eine verständliche Fehlerseite mit Tipps statt eines technischen Fehlers.
- **Größen-Caps vor dem Einlesen** – Fotos/ZIP-Einträge über **60 MB** (`MAX_PHOTO_SIZE`) und
  Profilbilder über **20 MB** werden abgewiesen, **bevor** sie in den RAM gelesen werden (vorher:
  erst komplett einlesen, dann prüfen). ZIP-Archive werden nicht mehr komplett in den Speicher
  geladen, sondern Eintrag für Eintrag direkt aus dem Upload-Tempfile gelesen. Meldung zählt
  „⚖️ n zu groß" getrennt auf.
- **Aufräumen des Rate-Limiter-Speichers** – Veraltete Keys (älter als 1 h) werden entfernt, sobald
  der Speicher über 512 Einträge wächst; vorher sammelten sich je gesehener IP Keys auf Dauer an.
- **Kleine Aufräumarbeiten** (kein Verhalten geändert): `utcfromtimestamp` → `fromtimestamp(…, tz=utc)`
  (ab Python 3.12 veraltet), tote Imports entfernt (u. a. `locale`/`cal_month` im Newsletter,
  `selectinload`, doppeltes `shutil`), toter Inspector-Refresh in `migrate_db` jetzt wirksam
  (`nonlocal`), `invite_url`-Leckvariable entfernt. Pack-Skript: `_DEPLOY_HINWEISE.txt` aus dem
  Repo-Root wird nicht mehr zusätzlich zur generierten Datei ins ZIP gepackt (Doppelteintrag-Warnung).
- **Tests**: 35 neue (15 in `tests/test_build_ag.py`, 20 in `tests/test_bereiche.py` – schließen die
  im Audit 3 genannten Lücken: Registrierung/Einladung, Passwort-Reset, Kommentare, Zeitabstimmung,
  Vorlagen, Ankündigungen, Video-Upload), insgesamt **177**.

Geänderte Dateien: `app.py`, `config.py`, `templates/errors/413.html` (neu),
`templates/admin/notifications.html`, `tests/test_build_ag.py` (neu), `tests/test_bereiche.py` (neu),
`README.md`, `CHANGELOG.md`.

## 1.4.0 – 2026-10-15 (Build af) – Foto unterwegs (Option C) und Live-Karte als Aufzeichnung (Option D)

**Option C – Foto unterwegs mit Handy-Standort**
- Neuer Knopf **„📷 Foto unterwegs aufnehmen“** in der Foto-Karte der Tour (nur auf Touch-Geräten eingeblendet)
  und **„📷 Foto“** in der Leiste der Live-Karte: Die Kamera öffnet sich, das Foto wird sofort hochgeladen und
  bekommt den **aktuellen Standort des Handys** (`gps_source='device'`), falls die Kamera keinen Standort ins
  Bild schreibt. Ohne Standortfreigabe/Empfang wird es ohne Position gespeichert (per ✏️ nachträglich setzbar).
  Fehlt die EXIF-Aufnahmezeit, gilt der Aufnahmezeitpunkt (`exif_dt_0`). Auf der Live-Karte bleibt die Seite
  offen – Teilen läuft weiter; die frische Position vom laufenden Standort-Watch wird direkt verwendet.
- Erfolgsmeldung zählt „📱 n mit aktuellem Handy-Standort“.

**Option D – Live-Karte als Aufzeichnung**
- Neue Tabelle `live_track_points` (wird automatisch angelegt): Jede beim „Standort teilen“ gesendete Position
  bleibt als Punkt erhalten – bisher hielt `live_locations` nur die letzte. Nicht aufgezeichnet werden ungenaue
  Fixe (> 100 m), Doppelsendungen (< 3 s) und unplausible Sprünge (> 90 km/h).
- **Live-Karte:** Der zurückgelegte Weg jeder Person erscheint als dünne Linie (eigene blau), auch für Zuschauer;
  das Polling holt nur neue Punkte (`?since=`), die Antwort auf das Senden liefert sie gleich mit.
- **Tourseite:** Karte **„Live-Aufzeichnung“** (sichtbar für Tourleitung/Orga/Admin und für alle mit eigener
  Aufzeichnung) mit Zeitraum, km und Punkten je Person. Tourleitung/Orga/Admin können eine Aufzeichnung
  **als GPX-Track der Tour übernehmen** (`POST /touren/<id>/live/aufzeichnung`, `action=adopt`): GPX 1.1 mit
  Zeitstempeln, ohne Höhen (Handy-Höhen sind unbrauchbar) und ohne Personenbezug in der Datei; Kennzahlen
  (km, Fahrzeit, Ø-Tempo, Vorschau) werden wie beim GPX-Upload gesetzt, ein vorhandener Track (geplante Route)
  wird ersetzt, Fotos ohne Standort gleich per Aufnahmezeit platziert. Download als GPX
  (`/touren/<id>/live/aufzeichnung.gpx?user_id=`): eigene für jeden, fremde für Tourleitung/Orga/Admin.
  Löschen: eigene Aufzeichnung jeder, alle Tourleitung/Orga/Admin.
- **Fotos per Aufnahmezeit (Build ac) ohne GPX-Zeiten:** Hat der GPX der Tour keine Zeitstempel (geplante Route)
  oder gibt es gar keinen, dient die Live-Aufzeichnung als Zeitquelle – bevorzugt die des hochladenden Nutzers,
  sonst die längste der Tour (`_tour_timed_source`). Gilt für den Upload und den Knopf „… auf der Strecke platzieren“.
- Aufbewahrung: Rohpunkte werden 30 Tage nach Aufzeichnung automatisch gelöscht (`_live_cleanup`), beim Löschen
  einer Tour oder Anonymisieren eines Nutzers sofort. Datenschutz- und Hilfeseite ergänzt.
- 17 neue Tests (`tests/test_build_af.py`), insgesamt 142.

Geänderte Dateien: `app.py`, `models.py`, `templates/touren/detail.html`, `templates/touren/live.html`,
`templates/hilfe.html`, `templates/datenschutz.html`, `tests/test_build_af.py`, `README.md`, `CHANGELOG.md`.

## 1.4.0 – 2026-10-15 (Build ae) – Startfehler sichtbar machen

- Nach dem Upload von Build ad startete die App auf dem Server nicht; Passenger meldete nur
  `module 'passenger_wsgi' has no attribute 'application'` – ohne SSH war die eigentliche Ursache nicht
  zu sehen. `passenger_wsgi.py` fängt den Import von `app.py` jetzt ab (auch `SystemExit`): Der
  Traceback erscheint als Antwortseite (HTTP 500, Klartext) **und** in `logs/startup_error.log` im
  App-Ordner (per FTP lesbar). Zusätzlich wird geprüft, dass wirklich `<App-Ordner>/app.py` geladen
  wurde und kein gleichnamiges Fremdmodul aus einem site-packages-Ordner.
- Inhaltlich keine Änderung gegenüber Build ad (flache Bottom-Navigation) und ac (Fotos per
  Aufnahmezeit). Troubleshooting-Tabelle in `docs/INSTALLATION_PLESK_FTP.md` ergänzt.

Geänderte Dateien: `passenger_wsgi.py`, `app.py` (Build-Kennung), `docs/INSTALLATION_PLESK_FTP.md`, `CHANGELOG.md`.

## 1.4.0 – 2026-10-15 (Build ad) – Bottom-Navigation wieder flach

- Rückmeldung vom S23: Die untere Navigationsleiste war mit Build ab „nach oben gerutscht“. Ursache: Build ab
  hatte nur die Beschriftung vergrößert (.6 → .75 rem), die Leiste wuchs dadurch nach oben – mit Großschrift
  von ≈ 65 auf ≈ 69 px. Jetzt enge Abstände (Leiste 3 px, Einträge 2 px), feste Zeilenhöhe 1.2, kein Umbruch,
  Plus-Knopf 44 px ohne Außenabstand: Die Leiste ist mit ≈ 51 px (Großschrift ≈ 53 px) **niedriger als vor
  Build ab** (63 px), die Beschriftung bleibt mit .72 rem gut lesbar. Platzhalter unter dem Seiteninhalt und
  Höhe des ausgeklappten Menüs entsprechend angepasst (58 px).

Geänderte Dateien: `app.py` (Build-Kennung), `templates/base.html`, `tests/test_build_ab.py`, `CHANGELOG.md`.

## 1.4.0 – 2026-10-15 (Build ac) – Fotos per Aufnahmezeit auf der Strecke platzieren

Hintergrund: Android (seit 10) und iOS entfernen beim Hochladen über die Galerie/Fotos-Auswahl den
Standort aus den Bildern – das passiert im Handy, bevor der Browser die Datei sieht. Die
Aufnahmezeit bleibt dabei erhalten (Ausnahme: WhatsApp). 125 Smoke-Tests (28 neu in
`tests/test_build_ac.py`).

- **Automatisch beim Hochladen:** Hat die Tour eine GPX-**Aufzeichnung mit Zeitstempeln**
  (Garmin, Komoot, Wahoo – keine geplante Route), bekommen Fotos ohne Standort die Position, an der
  die Gruppe laut Track zur Aufnahmezeit war (zwischen den Nachbarpunkten interpoliert; bis 15 min
  vor Start/nach Ende → erster/letzter Punkt; bei Lücken > 10 min kein Interpolieren). Solche
  Positionen sind als **geschätzt** markiert: gelbes ≈-Badge am Foto, Hinweis im Karten-Popup
  (`tour_photos.gps_source = 'track'`, Migration). Echte Positionen (EXIF, Kartenklick,
  Handy-Standort) haben Vorrang und werden nie überschrieben.
- **Nachträglich für bestehende Fotos:** Knopf „… Foto(s) ohne Standort auf der Strecke platzieren“
  oberhalb der Fotos (Tourleitung/Organisator/Admin, `POST /touren/<id>/fotos/platzieren`), mit
  **Zeitkorrektur in Minuten** für falsch gehende Kamera-Uhren (geschätzte Positionen werden dabei
  neu berechnet) und „geschätzte Positionen wieder entfernen“ (`action=undo`). Der Block zeigt die
  Spanne der Aufzeichnung („Aufzeichnung 10:02–12:41 Uhr“); liegen alle Fotos um ±1/±2 h daneben
  (App schreibt Ortszeit statt UTC in den GPX), schlägt die Meldung die passende Zeitkorrektur vor.
  Ohne Zeitstempel im GPX erklärt die Seite stattdessen, warum es nicht automatisch geht.
- **Hinweis nach dem Upload** (Paket B): „n Foto(s) ohne Standort. Tipp fürs Handy: Fotos über die
  App „Dateien“ (DCIM/Camera) auswählen …“ – je nach Tour ergänzt um den Grund (keine Aufnahmezeit /
  außerhalb der Aufzeichnung / GPX ohne Zeitstempel). Die Erfolgsmeldung zählt „📍 n anhand der
  Aufnahmezeit auf der Strecke platziert“ getrennt von „🗺️ n mit GPS“; der Hinweis vor dem Upload
  kündigt das automatische Platzieren an, wenn der GPX Zeiten hat.
- **Herkunft der Position** wird jetzt gespeichert (`gps_source`: exif / manual / device / track):
  Kartenklick setzt `manual`, der Handy-Standort beim Hochladen `device`, „GPS entfernen“ löscht sie.
- **EXIF-Aufnahmezeit korrekt gelesen:** `extract_datetime_from_exif` folgt jetzt dem Zeiger auf das
  Exif-Unter-IFD und nimmt **DateTimeOriginal** (vorher wurde nur das IFD0 gelesen – also bei
  bearbeiteten Fotos das Änderungsdatum, womit das Foto an der falschen Stelle gelandet wäre);
  HEIC wird ebenfalls durchsucht, Pillow ist letzter Fallback. Pillow-GPS-Fallback schließt die Datei
  wieder (ResourceWarning).
- Hilfe: Abschnitt „Automatisch per Aufnahmezeit platzieren“ + iPhone-Weg „In Dateien sichern“.

Geänderte Dateien: `app.py`, `models.py`, `templates/touren/detail.html`, `templates/hilfe.html`,
`tests/test_build_ac.py` (neu), `tests/test_build_ab.py`, `README.md`, `CHANGELOG.md`.

## 1.4.0 – 2026-10-14 (Build ab) – Audit 3

Drittes Komplett-Audit (Bericht in `docs/AUDIT_BERICHT.md`, Abschnitt „Audit 3“) und Umsetzung aller
drei vereinbarten Pakete. 97 Smoke-Tests (27 neu in `tests/test_build_ab.py`).

### Paket 1 – Pflicht (Erinnerungen, Absagen, Kleinkram)

- **Tourtag-Erinnerung erst ab 7 Uhr** (Europe/Berlin, im Admin einstellbar): Bisher ging sie beim
  ersten Seitenaufruf nach Mitternacht raus – nachts um 0:30 Uhr ein Push „Tour heute!“. Neue
  gemeinsame Funktion `_run_tour_reminders(now)`; Tagesflags räumen ältere Flags auf (`_set_day_flag`),
  statt in `site_config` jeden Tag eine neue Zeile zu hinterlassen.
- **Vorabend-Erinnerung** („Morgen ist Tourtag!“, ab 18 Uhr, abschaltbar): Telegram an die Gruppe,
  Push an „Dabei“ **und** „Vielleicht“ – mit Uhrzeit, Treffpunkt, Einkehr. Bisher gab es sie nur als
  undokumentierten CLI-Befehl ohne Cron; `flask send-reminders` nutzt jetzt dieselbe Funktion.
  Admin → Benachrichtigungen: Karte „Automatische Erinnerungen“ (Uhrzeiten, Vorabend an/aus) und
  Test-Knöpfe „Tourtag“ / „Vorabend“ je Tour.
- **Tour absagen** (`POST /touren/<id>/absagen`, Knopf „Absagen“ für Tourleitung/Organisator/Admin) mit
  optionalem Grund (`tours.cancel_reason`, Migration): Push an Zugesagte/Unentschlossene, Telegram-
  Nachricht, roter Hinweis mit Grund auf der Tour-Seite. **„Absage zurücknehmen“**
  (`POST /touren/<id>/reaktivieren`) informiert ebenfalls. Bisher konnte nur der Admin über das
  Status-Feld absagen – und niemand erfuhr davon.
- **„Änderung mitteilen“** beim Bearbeiten (Haken, bei künftigen geplanten Touren vorausgewählt):
  ändern sich Datum, Uhrzeit, Treffpunkt oder Titel, bekommen die Angemeldeten eine Push-Nachricht
  „alt → neu“ und Telegram eine Zusammenfassung. Admin-Status-Feld akzeptiert nur noch
  `planned/completed/cancelled`.
- RSVP und Fahrgemeinschaft auf abgesagten/abgeschlossenen Touren gesperrt (Hinweis statt stiller Änderung).
- Login: **„Angemeldet bleiben“ vorausgewählt** (Zielgruppe wurde sonst nach jedem Browserstart
  abgemeldet); Bottom-Navigation **Schrift .6 → .75 rem**.
- **Service-Worker-Cache je Build**: `/sw.js` ersetzt den Platzhalter `__BUILD__` durch den App-Build,
  `style.css` wird mit `?v=<build>` eingebunden → nach jedem Deploy frische CSS/JS statt bis zu 24 h
  alter Dateien aus dem Cache (`Cache-Control: no-cache` für den Worker selbst).
- **Telegram-Escaping** (`_tg()`): Tourtitel, Treffpunkt, Kommentare, Challenge-Thema usw. werden
  HTML-escaped – ein „<3“ oder „<b>“ im Titel ließ die ganze Nachricht scheitern (7 Stellen).
- Live-Karte: OpenStreetMap-Hinweis oben rechts (unten verdeckte ihn die Statusleiste).

### Paket 2 – Betrieb (Backup, Speicher, Datenbank)

- **Backup in zwei Stufen** (`backup.sh [full|db]`): die **Datenbank täglich** (klein, Sekunden),
  das **Komplett-Backup** (Datenbank + Fotos/GPX/Avatare) im gewählten Intervall. Videos sind nur
  noch mit der neuen Einstellung „Videos einschließen“ dabei (sie lassen sich jederzeit neu rendern).
  Automatische Läufe starten in einem **Hintergrund-Thread** (`_start_backup_in_background`) – der
  auslösende Seitenaufruf hängt nicht mehr; ein Lock verhindert parallele Läufe („läuft bereits“).
  Rotation (7 Tage / 8 Wochen / 12 Monate) **je Art getrennt**, Backup-Liste mit Spalte „Art“ und
  Knopf „Nur Datenbank“; Wiederherstellung versteht beide Arten. Cron-Endpunkt liefert den Modus mit.
- Wiederherstellung entpackt nur noch reguläre Dateien innerhalb des Zielordners (`_safe_extractall`,
  kein `..`/absoluter Pfad/Symlink).
- `parse_gpx`-Cache 64 → 16 Einträge (bei 10 000-Punkte-Tracks ≈ 40 statt 170 MB je Prozess).
- **Tour-Seite, Druck- und Video-Seite betten höchstens 2 000 GPX-Punkte** ein (`gpx_for_page`,
  3-D-Douglas-Peucker inkl. Höhe → Höhenprofil bleibt, Hügel verschwinden nicht); km/Anstieg bleiben
  exakt. Vorher ~0,7 MB JSON pro Aufruf bei langen Tracks.
- **Keine N+1-Abfragen** mehr: `badge_stats_bulk()` liefert Touren/km aller Mitglieder in einer Abfrage
  (`/mitglieder` vorher 44 SQL bei 4 Mitgliedern → 8, `/profil/<id>` 96 → 8, `/rueckblick` 59 → 12;
  Rangliste nutzt die schon berechneten Werte). Profil-Teilnahmen laden die Tour per `contains_eager`,
  der Rückblick zählt Teilnehmer je Tour in einer Abfrage (`attend_counts`).
- Video-Rendern: **Sperrdatei je Tour** (`.render_<id>.lock`, 15 min) – zweiter Klick/Tab startet
  kein zweites ffmpeg, sondern zeigt „wird gerade erstellt“.

### Paket 3 – Neue Funktionen

- **Notfallkontakt**: Profil bearbeiten → „Erreichbarkeit & Notfallkontakt“ (Handy, Name/Telefon des
  Notfallkontakts; `users.phone/emergency_name/emergency_phone`). Sichtbar **nur** auf der neuen
  druckbaren **Teilnehmerliste** `GET /touren/<id>/teilnehmerliste` (Tourleitung/Organisator/Admin,
  Knopf „Liste“ in der Teilnehmer-Karte): Name, Telefon, Notfallkontakt, Rad, Ankreuzkästchen,
  Fahrgemeinschaften, Notizzeilen, „Notruf 112“.
- **Fahrgemeinschaften** je geplanter Tour (`tour_rides`, ein Eintrag je Nutzer): „Ich fahre mit dem
  Auto und habe Platz“ (Plätze 1–9, Ort, Hinweis) oder „Ich suche eine Mitfahrt“. Suchende bekommen
  Push, sobald jemand Plätze anbietet; Organisatoren können Einträge entfernen; Tour löschen /
  Nutzer anonymisieren räumen auf.
- **Anmelde-Link per E-Mail** (nur wenn `MAIL_SERVER` gesetzt): Knopf auf der Login-Seite → Einmal-Link
  (`/anmelden/<token>`, 15 Minuten, `password_resets.purpose='login'`), meldet dauerhaft an.
  Antwort verrät nicht, ob die Adresse existiert; Limits 5/5 min je IP und 3/h je Konto; Login-Token
  taugen nicht für den Passwort-Reset.

### Sicherheit / Aufräumen

- Passwort im Profil ändern **nur mit aktuellem Passwort**; Mindestlänge überall **8 Zeichen**
  (Registrierung, Reset, Admin, Setup, Profil – vorher 6/8 gemischt).
- Entfernt: `/admin/run-migration` (Token = Anfang des `SECRET_KEY`; Migration läuft ohnehin beim
  Start) und acht `/proposals/…`-Stub-Routen (Feature längst entfernt).
- Unverändert gelassen (bewusst): `/api/backup/trigger`-Token (in Plesk-Cron eingetragen), `.htaccess`.

### Geänderte Dateien (Build ab)

`app.py`, `models.py`, `backup.sh`, `static/sw.js`, `templates/base.html`, `templates/auth/login.html`,
`templates/auth/register.html`, `templates/auth/reset_password.html`, `templates/setup.html`,
`templates/profil_edit.html`, `templates/hilfe.html`, `templates/touren/detail.html`,
`templates/touren/edit.html`, `templates/touren/live.html`, `templates/touren/teilnehmerliste.html` (neu),
`templates/rueckblick.html`,
`templates/admin/notifications.html`, `templates/admin/backups_list.html`, `templates/admin/dashboard.html`,
`tests/test_build_ab.py` (neu), `tests/test_routes.py`, `README.md`, `CHANGELOG.md`,
`docs/AUDIT_BERICHT.md`, `docs/BACKUP_WIEDERHERSTELLEN.md`, `docs/INSTALLATION_PLESK_FTP.md`.

## 1.4.0 – 2026-10-14 (Build aa) – Audit 2

### Live-Karte je Tour (Build aa)

- Befund: Der Menüpunkt hieß „Live-Karte“, zeigte aber nichts Lebendiges; das eigentliche Standort-Teilen
  steckte hinter einem unbeschrifteten 📍 auf der (3 300 Zeilen schweren) Tour-Seite, sendete
  ungedrosselt (≈ jede Sekunde ein POST), lief beim Verlassen der Seite weiter (roter Punkt bis zu 10
  Minuten), fragte auch bei verdecktem Tab weiter ab, und nur wer selbst sendete, sah die anderen.
- Neue schlanke Seite **`/touren/<id>/live`** (`templates/touren/live.html`, Route `tour_live`):
  Strecke (vereinfachter GPX-Track), Treffpunkt 🏁, geplante Einkehr ☕ und die Standorte der Mitfahrer
  als farbige Punkte mit Initialen (grün < 1 min, gelb < 5 min, grau älter; Richtungspfeil bei Fahrt).
  **Zuschauen kann jeder aus der Gruppe** (Nachzügler, Pannen, Daheimgebliebene) – ohne selbst zu senden.
- Knöpfe: „📍 Standort teilen“, „🎯 Karte folgt mir“ (endet beim Verschieben der Karte), „👥 Alle
  zeigen“, „⛶“ Vollbild (per CSS, funktioniert auch auf iPhone/iPad). Liste „Unterwegs“ mit
  Streckenkilometer, Tempo, Alter des Signals und Spannweite der Gruppe („über 1,8 km verteilt“).
- Unter der Haube: ein gemeinsamer `watchPosition`, Senden höchstens alle 10 s (ohne Bewegung alle
  30 s), `sendBeacon` beim Schließen der Seite → Punkt verschwindet sofort, keine Abfragen bei
  verdecktem Tab, Wake Lock hält den Bildschirm an, automatisches Ende nach 8 h, Fehlertexte auf Deutsch
  (Standortfreigabe verweigert, kein GPS …).
- Server (`app.py`, Abschnitt „Build aa: Live-Karte“): Teilen nur **vom Vortag bis einen Tag nach dem
  Tourtag** (Organisatoren jederzeit, abgesagte Touren nie) → sonst 403 mit Hinweis; `speed`/`heading`
  werden gespeichert (Migration `live_locations.speed/heading`); Standorte älter als 15 min ausgeblendet,
  älter als 24 h gelegentlich gelöscht; `/api/location/tour/<id>` liest Nutzer per Join (vorher je Zeile
  eine Abfrage); `/api/location/stop` nimmt die `tour_id` auch aus der URL (leerer Beacon-Body).
- Tour-Seite: Toolbar-Knopf „📍 Live“ und grüne Leiste „Live-Karte öffnen“ unter der Karte (ab dem Vortag,
  nicht bei abgesagten/älteren Touren); der alte Live-JS-Block (~90 Zeilen) ist entfernt.

### Gruppen-Karte (Build aa)

- Menüpunkt heißt jetzt **„Gruppen-Karte“** (vorher irreführend „Live-Karte“); Hilfe-Text neu.
- Sprechblasen vollständig: Öffnungszeiten, Ruhetag-Badge, Mittagstisch-Badge (gleiche Logik wie die
  Gastro-Liste, `osm_gastro.js`), **„🟢 jetzt geöffnet – bis 18:00“ / „🔴 geschlossen – öffnet 09:00“**
  (neue Funktion `open_now()` auf Basis von `_oh_week`, Zeitzone Europe/Berlin), Bewertung, Notiz,
  Adresse, Links „Details & Bewertungen“, „Route (Fahrrad)“; Treffpunkte mit „Zur Tour“ (orange =
  geplant, grau = gefahren) und Datum **„offen“ statt „31.12.9999“**; POIs mit Link auf die Ortsliste.
- **Filterleiste** für die Gastro-Ebene: Suche (Name/Adresse/Notiz/Typ), Typ, ☀️ Frühöffner,
  🍽️ Mittagstisch, 🟢 jetzt geöffnet – mit Trefferzähler. Gastro und POIs werden **gebündelt**
  (MarkerCluster, ab Zoom 14 einzeln).
- Startansicht auf dem **Standard-Treffpunkt** der Gruppe (Site-Config), ohne Treffpunkt werden alle
  Punkte eingepasst; Ebenen- und Filterwahl merkt sich der Browser (`localStorage`).
- Bewertungsschnitt in einer Abfrage statt je Eintrag; nur Touren mit Koordinaten und nicht abgesagt
  (max. 40 neueste).
- Veraltete Leaflet-Option `tap:` aus allen Karten entfernt (Leaflet ≥ 1.8 kennt sie nicht mehr).
- Tests: `tests/test_live.py` (11 Tests: Zeitfenster, `open_now`, Initialen, Migration, API-Rechte,
  Stale/Cleanup, Live-Seite, Tour-Seite, Gruppen-Karte) – Suite jetzt 70 Tests.

## 1.4.0 – 2026-10-14 (Build z) – Audit 2

### Mittagstisch finden (Build z)

- Wunsch aus der Gruppe: bei der Suche nach einer Einkehr muss ein Restaurant **mit Mittagstisch**
  zu finden sein. Da OpenStreetMap den Tag `lunch=*` in Deutschland nur selten enthält, wertet die
  App zusätzlich die Öffnungszeiten aus.
- Neue Auswertung `noon_days()` (app.py, nach `closed_days`): liest OSM-`opening_hours` **und**
  deutschen Freitext („Montag Ruhetag, Di–So 11.30–14 Uhr und 17–22 Uhr“, „täglich 10–22 Uhr“,
  „Dienstag bis Sonntag …“) je Wochentag; „mittags geöffnet“ = um 12:45 Uhr offen und mindestens
  60 Minuten zwischen 12 und 14 Uhr. Küchenzeiten (`opening_hours:kitchen`) gehen vor, Feiertags-
  regeln (`PH`) werden übersprungen, Texte ohne Uhrzeit ergeben bewusst **keine** Aussage.
  Dieselbe Logik liegt für die Browser-Fallbacks in `static/js/osm_gastro.js` (ohne Lookbehind,
  läuft auch auf älteren iPads).
- OSM-Treffer (Streckensuche auf der Tour-Seite, Kartenausschnitt-Suche im Formular) tragen jetzt
  `lunch`/`lunch_text` (aus `lunch=*`, `lunch:menu/buffet/specials/tourist_menu=*`), Küchenzeiten,
  Küche (`cuisine`, eingedeutscht) und den abgeleiteten Status; Abzeichen
  „🍽️ Mittagstisch“ / „🕛 mittags geöffnet Mo–Fr“ / „mittags geschlossen“ in Listen und Popups.
  Häkchen **„nur mittags“** filtert ohne neue Overpass-Abfrage.
- Eigene Gastro-Einträge: neue Spalten `gastro_spots.lunch` (yes/no/leer) und `lunch_text`
  (Migration automatisch); Formular mit Auswahl „keine Angabe / ja / nein“ + Textfeld, OSM-Übernahme
  füllt beides vor; Schnell-Übernahme von der Tour-Seite übernimmt die OSM-Angabe mit.
- Gastro-Liste: Filter **Mittagstisch** („ja / mittags offen“ oder „mittags offen am Mo … So“),
  Abzeichen auf den Karten, Mittagstisch im Volltext-Filter („mittag“ eintippen), Detailseite mit
  Abschnitt „Mittagstisch“ und Hinweis-Kasten.
- Geplante Einkehr: Tour-Kopf zeigt „🍽️ Mittagstisch“ bzw. warnt „mittags geschlossen am Tourtag?“
  (wenn der Ruhetag-Hinweis nicht schon greift); Kurztext (Erinnerung, ICS, tour.txt, Druck) ergänzt
  „Mittagstisch: …“ bzw. „Achtung: am Tourtag mittags geschlossen?“.
- Hilfe-Seite: Abschnitt „Mittagstisch finden“ erklärt die drei Abzeichen.
- Tests: `tests/test_gastro.py` +7 (Parser mit OSM- und Freitext-Fällen, Küchenzeiten, OSM-Tag-
  Zuordnung, Listenfilter inkl. Wochentag, Formular/Schnell-Übernahme, Einkehr-Hinweis, statische JS-
  Datei) → 59 Tests.

### Smoke-Tests im Repo (Build y)

- Neuer Ordner `tests/` (nur Standardbibliothek `unittest`, keine neue Abhängigkeit): `python -m unittest`
  im Projektordner führt 52 Tests in ≈10 s aus – eigene SQLite-Datei im Temp-Ordner, Upload-Ordner
  umgebogen, keine Netzzugriffe (Push/Telegram/E-Mail/Overpass/Wetter als Attrappen, zufällige
  Hintergrund-Trigger abgeschaltet). Läuft unter Windows, macOS und Linux.
- Abgedeckt: Login/Zugriffsschutz, **alle GET-Routen** als Mitglied/Organisator/Admin, Gruppen-Trennung,
  Touren (Anlegen, RSVP, GPX-Kennzahlen, Archiv, „Nochmal fahren“, Anwesenheit, Kalender-Abo, Großschrift),
  Gastro (Schnell-Übernahme, Overpass-Attrappe mit 406-Ausweich/Cache/502, Streckensuche, Einkehr),
  Downloads (GPX, Archiv-ZIP, Tour-Paket, Druck) und reine Helfer (parse_gpx, Vorschau, ICS, Parser).
- Dabei gefunden und behoben: das Großschrift-CSS aus Build x stand versehentlich innerhalb der
  Mobil-Media-Query in `base.html` und hätte am Desktop nicht gegriffen.
- README: Abschnitt „Tests“.

## 1.4.0 – 2026-10-14 (Build x) – Audit 2

### Großschrift, geplante Einkehr, Anwesenheit (Build x)

- **Großschrift-Modus** (pro Nutzer, `users.large_text`): umschaltbar im Konto-Menü („Große Schrift“ /
  „Normale Schrift“, Desktop und Mobil) und als Haken unter Profil bearbeiten. Setzt `<html class="big-text">`:
  Grundschrift +20 %, größere Knöpfe/Eingabefelder/Haken (min. 44 px), kräftigere Grautöne, Mini-Schriften
  angehoben – auf allen Geräten gleich, da serverseitig gespeichert.
- **Geplante Einkehr an der Tour** (`tours.gastro_spot_id` + `tours.einkehr_text`): Auswahl aus der
  Gastro-Liste und/oder Freitext beim Anlegen/Bearbeiten; auf der Tour-Seite außerdem per Klick aus der
  Gastro-Ebene der Karte und aus der OSM-Streckensuche („☕ Als Einkehr festlegen“, legt OSM-Treffer bei
  Bedarf erst in der Gastro-Liste an). Anzeige im Tour-Kopf (mit Öffnungszeiten und Warnung „Ruhetag am
  Tourtag?“), eigener Marker in der Karte, in der Tourtag-Erinnerung (Telegram + Push), im Kalender-Eintrag
  (ICS/Abo), in der Druckansicht, in `tour.txt` des Tour-Pakets und als erste Zeile der Video-Folie
  „Einkehr unterwegs“. „Nochmal fahren“ übernimmt die Einkehr.
- **Anwesenheit abhaken**: Teilnehmer können am Tourtag und bis drei Tage danach selbst „Ich war dabei“
  drücken (zählt für die Rangliste; legt bei Bedarf die Teilnahme an). Organisatoren sehen das Formular
  „Anwesenheit bestätigen“ jetzt auch bei vergangenen, noch nicht abgeschlossenen Touren (aufgeklappt,
  solange nichts bestätigt ist) und in der Touren-Übersicht einen Hinweis auf Touren der letzten 14 Tage ohne
  Bestätigung. Abends ab 17 Uhr (Europe/Berlin) geht ohne Cron ein Push „✅ Wer war dabei?“ an Ersteller
  und Organisatoren der Gruppe (ohne Push-Abo: E-Mail an den Ersteller), einmal je Tour
  (`tours.attendance_reminded_at`); Admin → Werkzeuge kann den Lauf sofort anstoßen.
- Hilfe-Seite um Kalender-Abo, „Ich war dabei“, geplante Einkehr und Große Schrift ergänzt.
- Betroffene Dateien: `app.py`, `models.py`, `templates/base.html`, `templates/profil_edit.html`,
  `templates/hilfe.html`, `templates/touren/create.html`, `templates/touren/edit.html`,
  `templates/touren/detail.html`, `templates/touren/list.html`, `templates/touren/print.html`,
  `templates/admin/tools.html`.

## 1.4.0 – 2026-10-14 (Build w) – Audit 2

### Kalender-Abo, Fahrzeit/Ø-Tempo, Streckenvorschau, „Nochmal fahren“ (Build w)

- **Kalender-Abo (webcal)**: Profil → Bearbeiten → „Kalender-Abo“ (Button auch oben in der
  Touren-Übersicht). Persönlicher Link `/kalender/<token>.ics` ohne Login – Touren der eigenen Gruppe
  aus den letzten 12 Monaten und alle kommenden; Änderungen und Absagen (STATUS:CANCELLED) kommen
  beim nächsten Abgleich automatisch an. „Link erneuern“ macht den alten ungültig; inaktive Konten
  liefern 404. Einzel-ICS nutzt denselben Ereignis-Bauer: stabile UID, korrekt maskierte Kommas/
  Semikolons/Zeilenumbrüche, Zeilen ≤ 75 Oktette, GEO/URL-Felder.
- **Fahrzeit und Ø-Tempo** (reine Fahrzeit ohne Pausen, aus GPX-Zeitstempeln): neue Spalten
  `tours.gpx_moving_s`, `gpx_avg_kmh`; Anzeige in Tour-Detail (Kacheln), Archiv (Spalte ⏱) und
  Jahresrückblick („Fahrzeit gesamt“, streckengewichtetes „Ø Tempo“). Neue Uploads werden sofort
  erfasst, ältere Touren beim ersten Aufruf der Tour-Seite oder gesammelt über
  Admin → Werkzeuge → „GPX-Kennzahlen nachrechnen“ (≈20 s pro Klick).
- **Mini-Streckenvorschau** im Archiv (Tabelle und Karten ohne Titelfoto): Inline-SVG aus dem auf
  ≤ 60 Punkte vereinfachten Track (`tours.gpx_preview`), keine Kachel-Anfragen.
- **„Nochmal fahren“** (Organisatoren): Button in Archiv-Zeilen und auf abgeschlossenen/abgesagten
  Tour-Seiten legt eine neue geplante Tour ohne Termin an – Titel, Beschreibung, Startzeit, Level,
  Link, Treffpunkt und GPX-Kopie werden übernommen, Teilnehmer/Fotos/Fahrzeit nicht.
- Betroffene Dateien: `app.py`, `models.py`, `templates/touren/_track.html` (neu),
  `templates/touren/archiv.html`, `templates/touren/detail.html`, `templates/touren/list.html`,
  `templates/rueckblick.html`, `templates/profil_edit.html`, `templates/admin/tools.html`.

### Archiv & Downloads: GPX, Tour-Paket, Foto-Download (Build v)

- **Archiv-Liste**: je Tour ein GPX-Download-Symbol und ein „Tour-Paket“-Symbol direkt in der Zeile
  (mobil als kleine Leiste unter der Karte); oben **„GPX-ZIP (n)“** lädt alle Tracks der aktuellen
  Auswahl – ohne Filter alle Jahre, sonst Suchbegriff/Jahr/Level (`/archiv/gpx-zip`). Dateinamen
  `2025-06-14_Titel.gpx`, bei gleichem Namen `_2`, `_3`. Nebenbei: die Jahresauswahl im Archiv war
  ohne vorherige Suche leer und `year=abc` lieferte einen 500er – beides behoben.
- **Tour-Paket** (`/touren/<id>/paket`, Button auf der Tour-Seite neben „GPX herunterladen“): ZIP mit
  dem GPX-Track, allen Fotos (`fotos/01_Beschriftung.jpg`, Reihenfolge wie auf der Seite, unverändert
  gespeichert) und `tour.txt` (Datum, Status, Strecke/Höhenmeter, Wetter, Treffpunkt, Link,
  Beschreibung, Teilnehmer, Fotoliste mit Fotograf/Zeit/Koordinaten, Videoliste). Videos bleiben
  wegen der Größe draußen.
- **Foto-Lightbox**: Download-Button oben rechts speichert das aktuelle Foto als
  `Datum_Titel_NN.jpg`.
- **Auslieferung privater Dateien**: GPX läuft jetzt über `/touren/<id>/gpx-datei` (Login +
  Gruppen-Prüfung + sprechender Dateiname), Videos über die vorhandene Route `/videos/file/…`
  (mit Range-Unterstützung fürs Spulen); keine Seite verweist mehr direkt auf
  `/static/uploads/{gpx,photos,videos}`. Zusätzlich legt die App in diesen drei Ordnern einmalig
  eine `.htaccess` („Require all denied“) an – wirkt, falls der Hoster `/static` an der App vorbei
  über Apache ausliefert; der Login-Schutz aus Audit 1.4.0 (`_protect_private_uploads`) bleibt.
- ZIPs werden in einer Temp-Datei statt im Arbeitsspeicher aufgebaut (auch der Jahres-Export im
  Rückblick), Fotos im Paket unkomprimiert (schneller, JPEG lässt sich ohnehin nicht verkleinern).
- Betroffene Dateien: `app.py` (Abschnitt „Build v: Downloads“, `archiv`, `archiv_suche`,
  `gpx_export_all`, `_auto_migrate_once`), `templates/touren/archiv.html`,
  `templates/touren/detail.html`.

### Einkehr entlang der Strecke aus OpenStreetMap (Build u)

- **Tour-Detailseite, Karten-Leiste, Button 🔍☕** (bei Touren mit GPX): sucht in OpenStreetMap alle
  Cafés, Kneipen, Restaurants, Imbisse, Bäckereien und Eisdielen in wählbarem Abstand (150 m / 250 m /
  500 m / 1 km) links und rechts der Strecke. Ergebnis als Liste nach Streckenkilometer („km 12,3 ·
  80 m abseits“) mit Öffnungszeiten, Ruhetag-Badge und Adresse, dazu orange Marker auf der Karte
  (Klick in der Liste zentriert die Karte). Orte, die schon in der Gastro-Liste stehen, sind als
  „✓ in Liste“ verlinkt; alle anderen lassen sich mit **„Übernehmen“** per Klick anlegen (Typ,
  Adresse, Öffnungszeiten, Telefon, Website, OSM-Verknüpfung werden übernommen; Duplikate werden
  erkannt und stattdessen der vorhandene Eintrag verlinkt).
- Technik: `GET /api/touren/<id>/osm-gastro?radius=` (nur eigene Gruppe) vereinfacht den Track per
  Douglas-Peucker auf ≤ 120 Stützpunkte und fragt Overpass mit `around:<r>,lat1,lon1,…` ab
  (identifizierender User-Agent, Ausweich-Server, 30-Minuten-Cache je Tour und Radius); scheitert
  der Server-Proxy, fragt der Browser overpass-api.de direkt und berechnet km/Abstand selbst.
  `POST /api/gastro/quick-add` legt den Eintrag an (Validierung wie im Formular).
- Betroffene Dateien: `app.py` (`_gastro_match_known`, `_simplify_track`, `_along_track`,
  `api_tour_osm_gastro`, `api_gastro_quick_add`, Build-Kennung), `templates/touren/detail.html`
  (Button, Panel, JS-Block „Build u“).

### Gastro-Bereich: Öffnungszeiten/Ruhetage, Duplikate, Liste (Build t)

- **Öffnungszeiten als Text + Ruhetage:** neue Spalte `gastro_spots.hours_text` (automatische
  Migration). Freitext („Mo Ruhetag, Di–So 9–18 Uhr“) oder OSM-Format; OSM-Format wird lesbar
  angezeigt („Mo–Fr 08:00–18:00 · So geschlossen“, Filter `hours_de`) und Ruhetage werden erkannt
  (Filter `closed_days`, auch „montags geschlossen“, „Ruhetag: Mo + Di“) und als rotes Badge in
  Liste, Detailseite und den Einkehr-Popups der Tour-Karte gezeigt. OSM-Übernahme und OSM-Abgleich
  speichern jetzt den kompletten opening_hours-Text statt nur der ersten Uhrzeit.
- **Doppelte Einträge:** Beim Anlegen wird geprüft, ob derselbe Ort schon existiert (gleiche
  OSM-Verknüpfung, gleicher Name im Umkreis von 100 m oder ein Eintrag näher als 25 m) → Warnung mit
  Link zum bestehenden Eintrag; „Trotzdem anlegen“ als bewusste Ausnahme.
- **Formular:** Bei Fehlermeldungen (fehlende Koordinaten, Duplikat) bleiben alle Eingaben erhalten
  (vorher leeres Formular).
- **Liste:** Marker mit Typ-Symbol (☕🥐🍺🍽️🥪), Popup mit Öffnungszeiten/Ruhetag/Bewertung und Link,
  Clustering ab 25 Einträgen, Treffpunkt-Fahne; Sofort-Filter (Text, Typ, Frühöffner) für Karten und
  Marker ohne Neuladen; Frühöffner-Schwelle direkt in der Filterleiste; Sortierung „Nähe zu mir“
  (Standort) und „Nähe zum Treffpunkt“ mit Entfernungs-Badges; „Auf der Karte zeigen“ je Eintrag.
- Betroffene Dateien: `app.py` (`hours_de`, `closed_days`, `_gastro_form_vals`,
  `_gastro_find_duplicate`, `gastro_new`/`gastro_edit`/`gastro_list`/`gastro_import`,
  `gastro_near_track`, `migrate_db`, Build-Kennung), `models.py` (`hours_text`),
  `templates/gastro/form.html`, `templates/gastro/detail.html`, `templates/gastro/list.html`,
  `templates/touren/detail.html` (Einkehr-Popup).

### Gastro-Bereich: Fehler und tote Funktionen (Build s)

- **Bearbeiten repariert:** Die Route gab es, aber keinen Link, und das Formular blieb beim
  Bearbeiten leer. Jetzt: Bearbeiten-Button in der Detailseite (Ersteller, Organisatoren, Admins),
  Formular vollständig vorbelegt, Karte startet beim Eintrag, Marker ziehbar; die OSM-/Namenssuche
  ergänzt im Bearbeiten-Modus nur leere Felder.
- **Fotos eingebunden:** Upload (mit Bildunterschrift), Galerie und Löschen in der Detailseite;
  Löschen eines Eintrags mit Fotos führte zu einem 500er (NOT NULL) – Fotos und Dateien werden jetzt
  mit entfernt (zusätzlich Cascade im Model).
- **OSM-Abgleich statt Google Places:** Der Places-Abgleich brauchte einen kostenpflichtigen Key und war
  nie in der Oberfläche. Neu: „Daten aus OSM holen“ auf der Detailseite – sucht über die gespeicherte
  osm_id, sonst im Umkreis von 80 m, zeigt Unterschiede (alt → neu) und übernimmt nur nach Klick
  (`/api/gastro/<id>/osm-lookup`, `/gastro/<id>/import` mit Validierung). Places-Route und
  Admin-Feld „Google Places API-Key“ entfernt.
- **Namenssuche (Nominatim):** Treffer im Kartenausschnitt zuerst (viewbox) und nach Entfernung
  sortiert statt weltweit; Trefferliste HTML-sicher (Namen mit Apostroph brachen den Klick);
  übernimmt jetzt auch Schließzeit, Telefon, Website und die OSM-Verknüpfung.
- **Liste:** 221 → 16 Datenbank-Abfragen bei 30 Einträgen (Bewertungsschnitt in einer Abfrage,
  Frühöffner-Schwelle einmal je Request über `models.morning_threshold()` – berücksichtigt jetzt
  auch die persönliche Schwelle); Suche findet zusätzlich Adresse und Notizen.
- osm_id wird ab jetzt im OSM-Format `node/123` gespeichert und in der Detailseite verlinkt.
- Betroffene Dateien: `app.py` (Gastro-Abschnitt, Overpass-Helfer `_overpass_fetch`, Admin-Keys,
  Build-Kennung), `models.py` (`morning_threshold`, `avg_rating`-Cache, Cascade),
  `templates/gastro/form.html`, `templates/gastro/detail.html`, `templates/admin/settings.html`.

### Gastro-Suche „OSM-Gebiet“ repariert (Build r)

- **Ursache:** overpass-api.de lehnt seit April 2026 Anfragen ohne eindeutig identifizierenden
  User-Agent mit „406 Not Acceptable“ ab; der Proxy `/api/overpass-gastro` schickte den Standard-
  User-Agent von python-requests, der Ausweich-Server kumi.systems antwortet nicht mehr zuverlässig,
  und das Formular zeigte den Server-Fehler als „Keine Treffer“ an.
- **Server:** eigener User-Agent `DeJungenOlen/<Version> (+<Host>; …)` + Referer, vier Ausweich-
  Server (overpass-api.de, private.coffee, kumi.systems, maps.mail.ru) mit 12 s Einzel-Timeout und
  40 s Gesamtbudget, 10-Minuten-Cache je Kartenausschnitt, sprechende Fehlertexte (406/429/504);
  Bäckereien, Konditoreien und Eisdielen werden jetzt mitgesucht (`shop=bakery|pastry|ice_cream`
  – „bakery“ war fälschlich als amenity abgefragt); Treffer enthalten Adresse und Kontakt.
- **Browser:** Fehler werden angezeigt statt verschluckt; scheitert der Server-Proxy (z. B. Rate-Limit
  der Hosting-IP), fragt der Browser overpass-api.de direkt (eigene IP, Referer); „Kartenausschnitt
  zu groß“ wird als Hinweis zum Heranzoomen gemeldet. Übernahme füllt zusätzlich Adresse,
  Schließzeit, Telefon und Website; Trefferliste HTML-sicher aufgebaut.
- Betroffene Dateien: `app.py` (`OVERPASS_ENDPOINTS`, `_osm_user_agent`, `_overpass_gastro_query`,
  `_overpass_elements_to_results`, `api_overpass_gastro`, Build-Kennung), `templates/gastro/form.html`
  (`overpassQuery`, `overpassDirect`, `searchOverpass`, `renderOverpassResults`, `fillForm`).

### Tour-Karte & Detailseite: fünf Ergänzungen (Build q)

- **Einkehr an der Strecke:** Gastro-Einträge höchstens 150 m neben dem Track (gleicher Helfer
  wie die Video-Folie) erscheinen als kleine Marker (☕ 🥐 🍺 🍽️ 🥪) auf der Tour-Karte, mit Popup
  (Art, Streckenkilometer, Abstand, Link zu Details & Bewertungen). Per ☕-Knopf in der
  Kartenleiste ausblendbar; sichtbare Einkehr-Marker werden von den Foto-Badges freigehalten.
- **Wetter-Rückblick:** Bei vergangenen Touren zeigt eine neue Kachel in der Statistik-Leiste
  das Wetter am Tourtag (Symbol, Höchst-/Tiefsttemperatur, Regenmenge bzw. „trocken“, Wind;
  Tooltip mit Klartext und Sonnenstunden). Asynchron geladen über die neue Route
  `/touren/<id>/wetter-tag`; ohne Treffpunkt dient der GPX-Start als Ort.
- **Wetter-Cache:** Das Tageswetter vergangener Touren wird einmalig in `tours.weather_json`
  gespeichert (neue Spalte, Migration automatisch beim ersten Aufruf) – Video-Seite, Server-
  Rendering und Rückblick brauchen danach keinen Open-Meteo-Aufruf mehr. `_tour_day_weather`
  liefert zusätzlich `label`, `rain_mm`, `wind_kmh`, `wind_dir`, `sun_h`.
- **Fahrtrichtung:** Kleine Richtungspfeile entlang des Tracks (etwa alle 5 km, 3–12 Stück,
  eigene Karten-Ebene unter den Markern, nicht klickbar) – bei Schleifen sieht man, wie herum
  gefahren wurde.
- **Fotos ein/aus:** 📷-Knopf in der Kartenleiste blendet alle Foto-Marker aus und wieder ein.
- **Treffpunkt am Start:** Liegt der Treffpunkt < 150 m vom Start, bekommt der Start-Marker
  (bzw. „S/Z“) eine 📍-Plakette und das Popup „Start & Treffpunkt“ – statt einer Nadel, die den
  Start-Marker verdeckt. Treffpunkt-Nadel sonst wie gehabt, jetzt mit weißem Rand.
- Betroffene Dateien: `app.py` (`_tour_day_weather`, neue Route `tour_weather_day`,
  `tour_detail` → `gastro_near`, `migrate_db`, Build-Kennung), `models.py` (`Tour.weather_json`),
  `templates/touren/detail.html` (Toolbar, Wetter-Kachel, `addDirectionArrows`, Einkehr-Ebene,
  `togglePhotoLayer`, `toggleGastroLayer`, Treffpunkt-Logik, Rückblick-Skript).

### Tour-Karte: Foto-Marker neben dem Track (Build p)

- **Tour-Detail, Karte:** Foto-Marker (einzeln und Cluster) sitzen nicht mehr auf dem Track,
  sondern daneben – als Thumbnail-Badge mit kurzer Verbindungslinie und Punkt am Aufnahmeort
  (gleiches Prinzip wie auf der Karten-Folie im Video). Die Richtung wird je Zoomstufe so
  gewählt, dass möglichst wenig Track, Start/Ziel/Treffpunkt, andere Badges und Kartenrand
  verdeckt werden; nach Zoomen/Verschieben wird neu platziert.
- Cluster zeigen jetzt das erste Foto als Thumbnail mit roter Zähl-Blase statt „📷 N“.
- Rundkurs (Start und Ziel < 150 m auseinander): ein gemeinsamer „S/Z“-Marker statt zwei
  übereinanderliegender; Start-/Ziel-Marker mit weißem Rand.
- Galerie ↔ Karte: Hover auf ein Foto hebt auch dessen Cluster hervor; Klick auf das grüne
  GPS-Badge eines Fotos scrollt zur Karte, zoomt bis das Foto einzeln sichtbar ist und öffnet
  das Popup (bisher ohne Funktion, wenn das Foto in einem Cluster steckte).
- Betroffene Dateien: `templates/touren/detail.html` (neu: `trackPointsPx`, `clipLen`,
  `bestPinOffset`, `makePinIcon`, `clusterThumb`, `placePhotoPins`; geändert: Start/Ziel-Marker,
  `highlightMarker`, `unhighlightMarker`, `jumpToMarker`), `app.py` (nur Build-Kennung).

### Mini-Karte pro Foto (Build o)

- **Video (MP4 + Browser-Vorschau):** Fotos mit GPS-Position bekommen eine kleine
  Karten-Einblendung (unten rechts, über der Unterschrift-Leiste, falls vorhanden):
  Track-Umriss in Weiß, der bis zum Aufnahmeort gefahrene Teil in Orange, Marker am
  Aufnahmeort und der Kilometerstand („km 15,2“).
- Es werden nur Fotos berücksichtigt, deren Position plausibel zum Track passt
  (gleicher Filter wie bei der Karten-Folie) – Fotos ohne GPS oder mit Ausreißer-Koordinaten
  erhalten keine Mini-Karte, Touren ohne GPX-Datei bleiben unverändert.
- Betroffene Dateien: `app.py` (`_photo_on_mini_map`, `_draw_mini_map`, `make_photo_overlay`,
  Datenblock `_mini_track`), `templates/touren/video.html` (`miniTrack`, `drawMiniMap`,
  `drawPhotoFrame`).

### Server-MP4: animiertes Höhenprofil (Build n)
- Neue Folie „Höhenprofil“ (3,5 s) im MP4 – an derselben Stelle wie in der Browser-Vorschau (nach den Fotos, vor dem Outro) und über dasselbe Häkchen „Höhenprofil zeigen“ steuerbar (Formularfeld `show_profile`, Standard an). Die Kurve baut sich von links nach rechts auf (gefüllte Fläche mit Verlauf + Linie), mit Höhen-Raster, km-Achse aus den echten Streckenkilometern, laufendem Höhenwert an der Spitze und Markierung des höchsten Punkts („↑ 92 m“). Höhen werden leicht geglättet (Mittel über 5 Punkte); Tracks ohne Höhendaten (flacher als 1 m) bekommen keine Folie. `build_profile_frames()` in `tour_video_render`.

### Video: Logo freigestellt, Titelfolie mit Wetter/Teilnehmern, km in der Kartenkopfzeile (Build m)
- **Gruppenlogo ohne schwarzen Kasten:** Logos ohne echten Alphakanal (JPEG bzw. vor Build f verkleinerte PNGs) werden beim Rendern automatisch freigestellt – `_logo_auto_alpha()` macht den einfarbigen Hintergrund von den Ecken aus per Flood-Fill transparent (schwarz, weiß oder jede andere Eckfarbe); innenliegende Flächen in derselben Farbe bleiben erhalten. Logos mit Transparenz bleiben unverändert. Sauberste Kanten gibt weiterhin ein neu hochgeladenes PNG mit Transparenz (bleibt seit Build f erhalten).
- **Titelfolie** zeigt wie die Browser-Vorschau zusätzlich Wetter (gezeichnetes Symbol + Tageshöchsttemperatur) und Teilnehmerzahl („5 dabei“).
- **Kartenkopfzeile** zeigt wie die Vorschau „68 % der Strecke · 13.8 / 20.0 km“.

### Kartenfolie: Foto-Kacheln größer (Build l)
- Foto-Kacheln auf der Kartenfolie von 7 % auf 8,4 % der kurzen Bildkante vergrößert: Browser-Vorschau 50 → 60 px, Server-MP4 (1080er Formate) 76 → 90 px. Abstand zur Verbindungslinie und Bündel-Radius wachsen automatisch mit.

### Kartenfolie: Track sichtbar, Foto-Marker neben dem Track (Build k)
- **Problem:** Die Foto-Kacheln lagen direkt auf dem Track und stapelten sich an gleichen Aufnahmeorten – der Track war kaum zu erkennen; außerdem wurde der Kartenausschnitt oft zu weit herausgezoomt (Track winzig).
- **Foto-Marker** (Browser-Vorschau `video.html` und Server-MP4 `build_track_frames()`): kleiner (max. 76 px), Fotos mit nahe beieinander-liegenden Positionen werden zu einer Kachel mit „+N“-Plakette gebündelt, und jede Kachel wird an der von 8 Positionen rund um den Aufnahmeort platziert, die am wenigsten Track verdeckt (und keine andere Kachel überlappt). Eine Verbindungslinie zeigt vom Foto auf den Aufnahmepunkt (kleiner blauer Punkt).
- **Kartenausschnitt:** Der Track darf die Fläche unter der Kopfzeile füllen (vorher nur 82 % von „Höhe − 240“). Es wird die größte Zoomstufe gewählt, bei der er passt; füllt er die Fläche damit unter 66 %, wird eine Stufe feiner geladen und das Kachelbild auf 70–100 % skaliert – der Track nutzt so immer rund 70–92 % der Fläche. Kachelbereich wird eng berechnet (kaum mehr Kachel-Downloads als vorher).
- **GPS-Ausreißer:** Fotos, deren Koordinaten weit abseits des Tracks liegen (falsche EXIF-Position), blähen den Ausschnitt nicht mehr auf und bekommen keinen Marker.
- Fallback-Projektion der Vorschau (ohne Kacheln) berücksichtigt jetzt die Längengrad-Verkürzung (keine verzerrten Tracks mehr).
- Getestet: Node-Test der Bündelung/Platzierung (0 Trackpunkte unter den Kacheln, alle im Bild), MP4 Hoch- und Querformat mit Einzelbildern.

### Video: Einkehr nahe der Route, Fahrzeit & Schnitt, gezeichnete Wettersymbole (Build j)
- **Fahrzeit & Ø Tempo aus GPX-Zeitstempeln:** `parse_gpx()` liefert zusätzlich `moving_s` (reine Fahrzeit, Pausen = Abschnitte langsamer als 1 km/h), `total_s` (gesamt), `avg_kmh`, `max_kmh`, `start_time`/`end_time` (Ortszeit Europe/Berlin). Statistik-Folie (Server-MP4 **und** Browser-Vorschau) zeigt zwei neue Kacheln „Fahrzeit · x:xx h gesamt“ und „Ø Tempo · max. xx km/h“ – nur wenn der Track Zeitstempel hat. Bei mehr als 4 Kacheln im Querformat/Quadrat drei Spalten; zu breite Werte werden automatisch kleiner gesetzt.
- **Einkehr nahe der Route:** neuer Helfer `gastro_near_track()` (Gastro-Einträge höchstens `GASTRO_NEAR_M` = 150 m neben dem Track, mit Streckenkilometer und Abstand). Im MP4: eigene Folie „Einkehr unterwegs“ (max. 6 Zeilen + „… und N weitere“, gestaffelt eingeblendet) nach der Kartenfolie, und auf der Karte violette Marker mit Namensschild, sobald der Track dort vorbeikommt (Schilder bis 6 Treffer). Neue Option „🍴 Einkehr nahe der Route (nur MP4)“ in den Video-Einstellungen (Formularfeld `show_gastro`, Standard an).
- **Wetter-Kachel ohne Emoji:** Das Symbol wird jetzt mit Pillow gezeichnet (Sonne, teils bewölkt, Wolke, Nebel, Regen, Schnee, Gewitter) – auf dem Server gibt es keinen Emoji-Font. Wetterabruf in `_tour_day_weather()` zusammengeführt (Videoseite + MP4); liegt die Tour länger als ~3 Monate zurück, wird das Open-Meteo-Archiv (`archive-api`) befragt, das die Prognose-API dann nicht mehr abdeckt. Voraussetzung bleibt: festes Datum + Treffpunkt-Koordinaten.
- Getestet mit synthetischem GPX (Zeitstempel, 15-min-Pause), 7 Gastro-Einträgen und allen drei Formatfamilien; Einzelbilder geprüft.

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
