# Audit-Bericht – De jungen Olen, Audit 10 (Version 1.5.0, Build cp → cq, 13.11.2026)

Zehntes Komplett-Audit, Stand Build **cp**. Auftrag: „Bitte noch einmal ein komplettes Audit machen.
Prüfe ausserdem ob die Dokumentation aktuell ist." Scope: der Zuwachs seit Audit 9 (Build cf, 12.11.) –
**Builds cg–cp**, also der komplette Traccar-Strang (Endpunkt `/api/traccar`, Vorfahrtsregel,
Siegel/Neustart, Notiz, Akku/Höhe/valid, Rückfall-Tour) plus Spurfarben (cj/ck) – und ein zweiter,
gleich gewichteter Teil: **stimmt die Dokumentation noch mit dem Code überein?**

Ergebnis im Satz: **Im Code kein Befund** (keine Sicherheitslücke, kein 500, alle Eingabeproben sauber,
749 Tests grün) – **in der Dokumentation fünf Lücken**, alle in Build **cq** geschlossen.

## Vorgehen

- **Statisch:** `pyflakes` über `app.py`, `models.py`, `config.py`, `exif_gps.py`, `make_deploy_zip.py`,
  `passenger_wsgi.py` → **0 Befunde** (außer bekannten ungenutzten Verfügbarkeits-Imports);
  alle Inline-`<script>`-Blöcke in `live.html`, `detail.html`, `karte.html`, `profil_edit.html`,
  `base.html` mit `node --check` → **0 Fehler** (ein Fehlalarm in `detail.html` stammt vom Jinja-`{% if %}`
  in einem Array-Literal, das mein Stripper nicht auflöst – gerendert ist die Seite im Routen-Sweep 200).
- **Routen-Sweep:** **89 GET-Routen × 3 Rollen** (Admin/Orga/Mitglied, `/logout` ausgenommen) →
  **kein 500, keine Ausnahme.** Admin 62×200 · Orga 47×200/18×403 · Mitglied 41×200/24×403; Nicht-200
  nur erwartbar (Token-Routen 404, `/api/wetter*` 400 ohne Parameter, Overpass 502 wegen Netzsperre,
  VAPID 503 ohne Schlüssel). Rollenschutz greift wie in Audit 9.
- **Eingabeproben `/api/traccar`** (bekannter Token, Tour heute):
  `lat=nan` → 400 · `batt=x, charge=maybe, altitude=1e30, valid=?, speed=-5, bearing=720, accuracy=inf`
  → 200, Punkt übernommen, alle unbrauchbaren Felder verworfen (None) · `timestamp` in ms → 200 ·
  ISO-8601 mit `Z` → 200 · `batt=150`/`altitude=-9999` → 200, beide verworfen · `lat=53,4` (Komma)
  → 400 · `hdop=abc` → 200 · POST Formular, POST JSON, Token im Pfad → 200 · kaputtes JSON ohne Token
  → 404. **Kein 500.**
- **Eingabeproben `/api/location/stop`:** `tour_id=abc` → 400; `force='yes'`/`force=[1]` → wie ohne
  force (Vorfahrt bleibt) – nur `1`/`true` zählt; der Client schickt `1`.
- **Logik-Review (Lesen am Code, nicht nur Tests):** Zeitparser (`_tracker_parse_time`: Sekunden/ms/ISO,
  aware → naiv UTC, Plausibilitätsfenster −12 h … +2 min); Siegel-Pfade (`late` nur Spur, `ignored`
  < 2 min, danach Siegel weg); Vorfahrt (`_tracker_active` < 15 min, Browser-Update
  `recorded:false, tracker:true`, Browser-Stop ohne Siegel außer `force`); Notiz nach jedem Pfad
  (`kein Tourtag`, `kein GPS-Fix`, `Nachzügler`, `ignoriert … neue Fahrt ab HH:MM`, `übernommen … 🔋`);
  Rückfall-Tour (nur Organisator, nur `can_share`, 12 h, keine abgesagte/fremde Tour, Datum vorrangig);
  Akku (`batt` None lässt alten Wert stehen, Warnung einmalig mit Hysterese 15/25 %); Höhe (`ele` nur
  aus Traccar, `_live_track_ascent` None bei < 50 % Höhen, GPX `<ele>` nur wo vorhanden).
  Client: Reihenfolge der Statusmeldungen beim Laden (Tracker-Modus hat Vorrang vor Idle-Hinweis,
  da `!trackerAktiv()` geprüft wird); `forceStopTracker` setzt `trackerSeen=0` und der nächste Poll
  liefert keinen `tracker_ago` mehr (Standortzeile gelöscht) – konsistent.
- **Doku-Abgleich:** README, UEBERGABE (alle Abschnitte), CHANGELOG-Kopf, `docs/*`, Profil-Text
  `#tracker`, `_DEPLOY_HINWEISE.txt` (ist nur die Vorlage; die ZIPs enthalten die generierte Fassung).
- **Tests:** volle Suite **749 grün** vor, **752** nach cq.

## Gefunden und behoben (alles Dokumentation, Build cq)

| Nr. | Fund | Behoben |
|---|---|---|
| D1 | **README** erwähnte Traccar mit keinem Wort (Features-Liste endete bei Build af/bv). | Absatz „Hintergrund-Tracking mit Traccar Client" unter *Karte & GPX*: Token, URL, Tourtag-Regel, Vorfahrt, Akku/Höhe. |
| D2 | **Profil `#tracker`** erklärte nur Einrichtung; die Regeln aus ci–cp (Tourtag ±1, Organisator-Rückfall, Vorfahrt 15 min, Beenden, Akku/Höhe) standen nur im CHANGELOG. Wer die Live-Karte nicht offen hat, sah nie die Tracker-Notiz. | Status-Zeile „letzter Punkt … · <Notiz>" (gleiche Quelle wie Live-Karte) + drei Regel-Punkte. Route `profil_edit` liefert `tracker_seen_txt`/`tracker_note`. |
| D3 | **UEBERGABE §3:** Nummer `3.0a` doppelt (cg und cf); §3.0a/3.0b behaupteten „Feldtest steht aus". | cf → `3.0z`; Feldtest-Sätze auf „am 12.11. bestanden". |
| D4 | **UEBERGABE §6/§8:** „Feldtest Traccar steht aus", „neuer Build-Buchstabe (`cf`)", 749 Tests. | §6 neu (erster Blick = Tracker-Notiz), §8 aktualisiert. |
| D5 | **UEBERGABE §4/§7:** Offene Punkte kannten keine Traccar-Themen; Landkarte ohne `traccar_push`, `TRACKER_*`, Spalten, Live-Karten-Funktionen. | Beides ergänzt (Zeilennummern Stand cq). |

## Offen / bewusst so gelassen

- **Akku-Warnung überschreibt den Status** (`battCheckMe` → `setStatus('warning')`): im Tracker-Modus
  verschwindet dadurch einmalig der „📡 Tracker-App …"-Hinweis bis zum nächsten Zustandswechsel.
  Bewusst: die Warnung ist wichtiger; auf Zuruf als eigener Chip.
- **Organisator-Pin gilt auch für Touren weit in der Zukunft** – ein Organisator, der die Live-Karte
  einer Tour in 10 Tagen öffnet, lenkt Traccar 12 h dorthin, sofern heute keine Tour mit Termin liegt.
  Entspricht exakt der Browser-Regel „Organisatoren dürfen jederzeit fahren"; nicht geändert.
- **`force` nur `1`/`true`:** Absicht (kein versehentliches Abschließen durch Fremdclients).
- **Fristen** (`TRACKER_NEUSTART_MIN` 2, `TRACKER_ACTIVE_S` 15 min): Angebote an den Nutzer stehen,
  Änderung nur auf Zuruf (siehe UEBERGABE §4).
- **Aus Audit 9 unverändert:** Auto-Pause-Kosmetik (Anfahren 25 m, Stand-Punkte), σ = 12 m-Rauschen.

## Tipps

- Bei „Traccar sendet, aber nichts passiert": **zuerst die Tracker-Notiz lesen** (Live-Karte
  Zuschauer-Hinweis oder Profil `#tracker`). Sie nennt den Pfad, den der letzte Punkt genommen hat.
- Für Server-Tests am Traccar-Endpunkt: ersten Punkt 1 min zurückdatieren, Folgepunkte wenige
  hundert Meter entfernt (`lat + 0.001`), sonst greifen Dublettenfilter (< 1 s) bzw. Plausibilität
  (> 90 km/h).
- Seed-Touren der Testgruppe liegen teils im Datumsfenster (`t_done` = gestern) – Tests zum
  Rückfall-Pin müssen sie erst aus dem Fenster schieben (siehe `tests/test_build_cp.py`).

---

# Audit-Bericht – De jungen Olen, Audit 9 (Version 1.5.0, Build ce → cf, 12.11.2026)

Neuntes Komplett-Audit, Stand Build **ce**. Auftrag: „Mache ein komplettes Audit, gibt es
irgendwo Lücken in den Funktionen? Check auch ob das Tracken mit und ohne Stromsparmodus optimal
funktioniert." Scope: der Zuwachs seit Audit 8 (Build bs, 09.11.) – **Builds bt–ce** (Tracking bu/bv,
Foto-Galerie bw–by, Video-Vorschau/Wetter cb–ce) – und als Schwerpunkt der **komplette Sendepfad
der Live-Aufzeichnung** (`templates/touren/live.html` + `location_update`/`_live_track_add` in
`app.py`), beide Modi, mit simulierten Fahrten gegen den **echten Template-Code**.

Ergebnis im Satz: **keine Sicherheitslücke, aber sechs Lücken im Tracking** – davon eine, die im
Normalmodus bei 1-s-GPS ab ~22 km/h die Aufzeichnung praktisch stilllegte (1 Punkt auf 4,2 km),
und drei, durch die gepufferte Punkte nach „Display aus" / „Beenden" verloren gingen. Alle in
Build **cf** behoben.

## Vorgehen

- **Statisch:** `py_compile` + **pyflakes** → nur die 3 bekannten `# noqa`-Verfügbarkeitstests;
  gefährliche Muster (`eval`, `os.system`, `shell=True`, `pickle`, rohe SQL-Strings) **0**;
  **36 Inline-`<script>`-Blöcke** + `sw.js`/`map-touch.js`/`osm_gastro.js` syntaktisch geprüft →
  **0 Fehler**; **17 `|safe`-Stellen** – alle JSON-Konstanten aus `json.dumps`, kein Nutzertext
- **Routen-Sweep:** **87 GET-Routen × 3 Rollen** (Admin/Orga/Mitglied) → **kein 500, keine
  Ausnahme**; Nicht-200 nur erwartbar (Token-Routen 404, `/api/wetter*` 400 ohne Parameter,
  Overpass 502 wegen Netzsperre, VAPID 503 ohne Schlüssel); Mitglied 24×403, Orga 18×403 =
  Rollenschutz greift
- **Mandanten-/Eingabeproben am Tracking-API:** Update an Tour der fremden Gruppe → **404**;
  `lat="abc"` → 400; `lat=95` → 400; kein JSON → 400; `accuracy="x"` → 200 (ignoriert);
  `at=1e30` / `NaN` → **500 (→ B6)**
- **Tracking-Simulation (Kern des Audits):** Der Block aus `onPos` (Auto-Pause + Aussetzer-Filter
  + Drossel) wird **unverändert aus dem Template geschnitten** und in Node gegen generierte
  Fahrten laufen gelassen: Geraden mit 90°-Bögen, Rauschen ±3–4 m, Fix-Takt 1 s und 3 s, Tempo
  4–60 km/h, Ampel, Einkehr, 60 s ohne Fix, einzelner Aussetzer 200 m quer – **je Szenario mit und
  ohne Sparmodus**, gemessen: gesendete Punkte, Spurlänge gegen wahre Länge, größte Lücke.
  Dazu `sicherNachsenden()` als echte Funktion mit simuliertem `fetch` (300 Punkte, 409 für
  einen Punkt, Netzabbruch, Server-500, zu alte Punkte) und `_live_track_add` direkt.
- **Tests:** **676** (vorher 654), 22 neue in `tests/test_build_cf.py`

## Befunde

### B1 (hoch) – Aussetzer-Filter sperrte die Aufzeichnung dauerhaft (Normalmodus ab ~22 km/h)
`kmhFix = moved / dtFixS` (Build bv): `moved` = Strecke seit dem zuletzt **gesendeten** Punkt,
`dtFixS` = Zeit seit dem letzten **Fix**. Nach dem dritten per Takt übersprungenen Fix lag der
Quotient über 120 km/h → Fix verworfen → `lastPos` rückt nicht nach → der nächste Fix ist noch
weiter weg → **Dauersperre**. Im Sparmodus (6-s-Takt) trat es erst ab ~36 km/h (1-s-GPS) bzw.
~60 km/h (3-s-GPS) auf – deshalb fiel es bei den Sparmodus-Tests aus bu/bv nicht auf.

| Szenario | Modus | vorher Punkte / Spur | nachher |
|---|---|---|---|
| 25 km/h, GPS jede 1 s, 10 min | Normal | **1 / 0,00 km** (echt 4,16) | 98 / 4,18 km |
| 30 km/h, GPS 1 s | Spar | 89 / 2,97 km (echt 4,99) | 151 / 5,09 km |
| 40 km/h, GPS 3 s | Normal | **1 / 0,00 km** (echt 6,63) | 52 / 6,61 km |
| Abfahrt 45 km/h kurvig | Normal | 9 / 0,35 km (echt 8,06, **−95,6 %**) | 70 / 7,99 km |
| Radtour 18 km/h kurvig, 3-s-GPS | beide | unauffällig (240 / 355 Punkte) | unverändert |
| Aussetzer 200 m quer | beide | übersprungen | weiter übersprungen (+1,0 % / +1,7 %) |

Fix: `lastFixPos` – der Filter misst **Fix gegen Fix**.

### B2 (hoch) – Nachsenden leerte den Puffer nur zu 60 Punkten je Aufwachen
`sicherNachsenden()` nahm `gesichert.slice(0, 60)` und startete danach nichts mehr. Gemessen mit
der echten Funktion: **300 im Puffer → 60 gesendet, 240 bleiben liegen.** Eine Stunde Display
aus im Sparmodus sind ~600 Punkte. Fix: Blöcke laufen, bis der Puffer leer ist (max. 2 400 je
Lauf); zusätzliche Auslöser: 5-s-Wächter, `online`-Event, nach jeder erfolgreichen
Normalsendung, beim Laden der Seite, beim Beenden. Nachher: **300 → 300 gesendet, 0 offen**.

### B3 (hoch) – Nach „Beenden" waren gepufferte Punkte verloren
`stopShare()` setzte `sharing=false` (→ `sicherNachsenden` brach mit `!sharing` ab) und das
Ende-Siegel (`LiveStop`) ließ jeden weiteren Punkt mit **409** abprallen. Fix: Der Server nimmt
Punkte, deren **Aufnahmezeit vor dem Ende** liegt, in die Aufzeichnung (`late: true`, **kein**
Standort-Update – also kein Zombie auf der Karte); Zombie-Sender (`at` ≈ jetzt oder ohne `at`)
bekommen weiter 409. Der Client sendet auch ohne `sharing` nach und stößt das vor dem Siegel an.

### B4 (mittel) – Ein endgültig abgelehnter Punkt blockierte den Lauf für immer
`if (!r.ok) break;` – ein 403/409 für einen Punkt beendete den Lauf, der Punkt blieb an Position 1
im Puffer, beim nächsten Aufwachen dasselbe. Fix: 400/403/409 → Punkt fliegt raus, weiter; 5xx
und Netzfehler → Abbruch, später erneut. Punkte älter als 6 h (nimmt der Server ohnehin nicht
mit Aufnahmezeit) werden vorab verworfen. Gemessen: 1×409 unter 300 → **299 gesendet, 0 offen**.

### B5 (mittel) – Server-Dublettenfilter 3 s traf Kurvenpunkte und Nachzügler
`_live_track_add`: `dt_s < 3 → verwerfen`. Die Kurven-Sofortsendung (Build bu) schickt bei
1-s-GPS Punkte 1–2 s auseinander – auf der 30-min-Runde verwarf der Server **66 von 365**
(Normal) bzw. **76 von 434** (Spar) – genau die Kurvenpunkte, die bu retten wollte. Und ein
Nachzügler, der nach einem frischeren Punkt ankommt (Funkloch bei Display an), hatte **negatives
dt** → ebenfalls „Doppelsendung". Fix: Schwelle **1 s**; ältere Punkte werden zeitrichtig
einsortiert, nur eine gleiche Sekunde gilt als Dublette.

### B6 (niedrig) – `at=1e30` oder `NaN` → HTTP 500
`datetime.utcfromtimestamp()` warf OverflowError/ValueError. Fix: abgefangen, Zeit ignoriert → 200.

## Bestätigt (kein Befund)
- Sparmodus-Drossel (6 s / 20 s Stand / 6 m, Kurve ≥ 20° sofort) und Normalmodus (10 s / 30 s /
  15 m) liefern bei 18 km/h beide Spuren mit < 3 % Längenfehler; der Sparmodus hat in **jedem**
  Szenario mehr Punkte als der Normalmodus (Test `sparmodus_liefert_mehr_punkte_als_normal`)
- 60 s ohne Fix (Wald) → eine Lücke von ~310 m, kein Aussetzer-Fehlalarm, Spur +0,5 %/+1,9 %
- Ampel 90 s: keine Fehl-Pause, Spur +0,2 %/+3,1 %
- `at`-Plausibilität (−6 h / +2 min), 8-h-Grenze mit Vorwarnung, Puffer 1 200, Sortierung nach
  Aufnahmezeit, `nachsendenLaeuft`-Sperre – alles wie in bv beschrieben vorhanden
- Mandantentrennung am Tracking-API (fremde Gruppe 404 für Update/Get/Live/Stop)

## Anmerkungen (nicht geändert)
- **Auto-Pause bei stark rauschendem Stand:** Mit normalverteiltem Rauschen σ = 12 m je Achse
  (Einkehr im Gebäude) wird die Pause in der Simulation **nicht** erkannt – einzelne Fixe
  springen > 25 m und setzen den Anker zurück. Mit gleichverteiltem ±20 m (Messung aus bv)
  klappt es. Bleibt nach Nutzerwunsch („erst fahren und schauen") offen; das kostet keine
  Kilometer, nur ein Knäuel am Pausenort.
- Schieben mit 4 km/h: Spur +19–23 % (Rauschen 4 m bei 26-m-Punktabstand) – physikalisch, kein
  Codefehler; Glättung wäre ein eigenes Thema.
- Browser-Vorschau Video weiterhin 1280×720 statt gewähltem Format (bekannt seit cd).

---

# Audit-Bericht – De jungen Olen, Audit 8 (Version 1.5.0, Build br → bs, 09.11.2026)

Achtes Komplett-Audit, Stand Build **br**. Scope: der Zuwachs seit Audit 7 (Build an,
07.11.2026) – **54 Commits, 20 Builds (ao–br)**, alles auf der Live-Karte: der weiße Hinweis
unten links am Kartenrand, die Symbole im Vollbild als senkrechte Spalte rechts, km/Zeit unten
links, der gelbe Hinweis im Vollbild vollständig sichtbar, der Stromsparmodus, der sich nach
60 s selbst abdunkelt (bp), und der Stromspar-Reststreifen in Rot statt Gelb (br).

Ergebnis im Satz: **eine echte Sicherheitslücke gefunden und geschlossen** (kein CSRF-Schutz –
ein POST von einer fremden Seite wurde angenommen, nachgestellt mit einer angelegten Teilnahme),
dazu **ein seit Audit 7 offener Zugriffsfehler** (Kommentar an fremder Tour löschbar) und eine
**Doku-Stelle, die dem Code widersprach**.

## Vorgehen

- **Statisch:** `py_compile` über app/models/config/exif_gps/make_deploy_zip/passenger_wsgi →
  sauber; **pyflakes** → 3 Hinweise, alle drei absichtliche Verfügbarkeitstests mit `# noqa`
  (`PIL._imaging`, `py_vapid.Vapid02`, `pywebpush`) – kein Befund; **36 Inline-`<script>`-Blöcke**
  aus den Templates einzeln durch `node --check` → **0 Syntaxfehler**; `node --check` über
  `static/sw.js` und `static/js/map-touch.js` → sauber
- **Gefährliche Muster:** `eval` 0, `os.system` 0, `shell=True` 0, `pickle.load` 0,
  `yaml.load` 0, rohe SQL-Strings 0; `exec(` 1× **nur im Test** (`test_build_ag`, führt einen
  Funktionsquelltext aus); `render_template_string` 2× (Import + ein Aufruf mit **fester
  Konstante** als Fallback, kein Injection-Pfad); `Markup()` 1×, mit `escape()` umschlossen
- **Sicherheit (dynamisch, Test-DB):**
  - **Mandantenprobe** gegen eine Tour der **fremden Gruppe** mit einem Nicht-Admin: 8 Endpunkte
    (Detail, Bearbeiten, Live, Teilnehmerliste, Kommentar, RSVP, Zeitabstimmung, Löschen),
    GET und POST → **alle 404**; geprüft, dass der POST **nichts geschrieben** hat (0 Teilnahmen,
    Tour existiert noch). Gegenprobe: eigene Tour 200, Admin darf gruppenübergreifend
  - **Gruppenisolation der Listen:** Start, Touren, Archiv, Karte, Rangliste, Mitglieder – der
    Titel der fremden Tour taucht nirgends im HTML auf
  - **XSS:** Tour mit `<img src=x onerror=alert(1)>` als Titel, `"><script>alert(2)</script>`
    als Beschreibung und `<svg onload=alert(3)>` als Treffpunkt → auf Tourseite, Liste und Start
    vollständig escaped, kein rohes Vorkommen
  - **CSRF (neu geprüft, → B1):** POST mit `Origin: https://boese.example` legte eine Teilnahme
    an. **Es gab keine CSRF-Abwehr** – weder Token noch Herkunftsprüfung
  - **Uploads:** 42 böse Uploads über 6 Feldnamen und 3 Endpunkte (`.php`, `.svg`, `.htaccess`,
    `../../evil.jpg`, `x.jpg\x00.php`) → nur 3 Dateien gespeichert, **alle mit
    serverseitigem Namen** (`avatar_1_<hex>.jpg`, `1_<hex>.gpx`); kein `.php`, kein `.svg`,
    kein `..` im Pfad
  - **Pfad-Traversal in der Auslieferung:** 8 Varianten (`../../app.py`, URL-kodiert,
    doppelte Punkte) gegen `/fotos/img/`, `/videos/file/`, `/gpx/` → **alle 404/308**, keine
    Datei außerhalb des Upload-Ordners
  - **Auth:** Start, Touren, Profil, Karte ohne Login → Umleitung; Cron-Endpunkte ohne und mit
    falschem Token → 403 `invalid token`
  - **Deploy-ZIPs:** 21 bzw. 96 Dateien, **keine** `.env`, keine Datenbank, keine Uploads,
    kein `__pycache__`, nur `.env.example`
- **Robustheit/Fuzzing:** **1 656 Anfragen** – 1 596 GET mit 14 bösen Werten × 6 Parametern auf
  19 Seiten, 9 kaputte/leere Formulare, 42 Uploads, 9 JSON-Körper (`{`, `[]`, `1e400`, …)
  → **kein einziger 500er, keine Ausnahme**
- **Performance:** SQL-Zähler je Seite mit 120 Touren/31 Nutzern/1 404 Teilnahmen:
  10–48 Abfragen, **1,9–12,7 ms**, kein N+1; `EXPLAIN QUERY PLAN` für die vier häufigsten
  Abfragen → durchweg `SEARCH … USING INDEX` (kein Tabellendurchlauf)
- **Browser (Chromium 153, Smartphone-Profil, 461×934):** 15 Seiten durchlaufen; Zustandsmaschine
  der Live-Karte (Vollbild × Stromsparmodus × Sperre, 7 Schritte) mit Messwerten; Reststreifen
  über die vollen 60 s in 5-s-Schritten verfolgt; gelber Hinweis in drei Größen auf Überlauf und
  Knopf-Abschneidung geprüft
- **Tests:** **515** (vorher 500), 15 neue in `tests/test_build_bs.py`

## Befunde

| Nr. | Schwere | Befund | Status (Build bs) |
|---|---|---|---|
| B1 | **Mittel** (Sicherheit) | **Kein CSRF-Schutz.** Weder Flask-WTF-Token noch Herkunftsprüfung. Nachgestellt: ein `POST /touren/<id>/rsvp` mit `Origin: https://boese.example` wurde angenommen und **legte eine Teilnahme an**. `SESSION_COOKIE_SAMESITE='Lax'` hilft dabei nicht zuverlässig, weil ein Top-Level-Formular-POST das Cookie mitnimmt | **behoben:** `_csrf_herkunft()` als `before_request` – POST/PUT/PATCH/DELETE mit fremdem `Origin` bzw. `Referer` → **403** (mit Log-Zeile). Eigener Host erlaubt, `/api/`, `/login`, `/registrieren`, `/passwort-vergessen` frei; fehlen beide Köpfe, bleibt es beim alten Verhalten. Kein Formular musste geändert werden. 8 Tests |
| B2 | Niedrig (Zugriff) | **Kommentar an einer fremden Tour löschbar** – der in Audit 7 nur *notierte* Punkt. `comment_delete` prüfte nur den Autor: Ein Mitglied löschte einen **eigenen** Kommentar, dessen `tour_id` auf eine fremde Tour zeigt, bekam **302** und wurde auf `/touren/<fremde_id>` umgeleitet (dort 404). Kein Datenabfluss, aber eine Route, die auf ein unerreichbares Objekt schreibt und den Fehler verschleiert | **behoben:** erst `_tour_or_404(tour_id)`, dann `comment.tour_id != tour_id → 404`. Nachgestellt: 404, Kommentar bleibt in der DB. Gegenprobe: eigener Kommentar an eigener Tour weiter 302 + gelöscht. 4 Tests |
| B3 | Niedrig (Doku) | **Hilfe widersprach dem Code.** `templates/hilfe.html` sagte beim 🔒-Knopf „**immer** da, auch … im Vollbild"; `guardWanted()` beginnt aber mit `if (_fsAn()) return false;` und die gleiche Hilfeseite sagt 30 Zeilen höher „im Vollbild nicht: dort ist die Karte immer frei". Wer sich auf den ersten Satz verlässt, sucht im Vollbild einen Knopf, den es nicht gibt | **behoben:** der Satz folgt jetzt dem Code („Im Vollbild gibt es ihn nicht – dort ist die Karte immer frei, sonst könnte man sie beim Fahren nicht verschieben"). 2 Tests (Text **und** Code-Seite) |

## Bestätigt (ohne Handlungsbedarf)

- **Mandantentrennung hält** – 8 Endpunkte gegen eine fremde Tour, alle 404, kein Schreibzugriff;
  kein fremder Titel in irgendeiner Liste; Admin darf bewusst gruppenübergreifend
- **XSS-Abwehr hält** – gespeicherte Payloads in Titel, Beschreibung und Treffpunkt werden auf
  allen geprüften Seiten escaped
- **Uploads** vergeben Dateinamen serverseitig (`secrets.token_hex`) und prüfen die Endung;
  bösartige Namen (`.php`, `.svg`, `.htaccess`, `..`) landen nicht im Dateisystem
- **Kein Pfad-Traversal** in der Auslieferung von Fotos, Videos und GPX (8 Varianten)
- **Keine 500er** in 1 656 Fuzzing-Anfragen
- **Cron-Token** weiterhin Pflicht; ohne/mit falschem Token 403 `invalid token`
- **Deploy-Pakete** enthalten keine Geheimnisse, keine Daten, keine Caches
- **Performance** flach und indiziert: 10–48 SQL, < 13 ms, `EXPLAIN` ohne Tabellendurchlauf
- **`comment_delete`-Randfall aus Audit 7** ist mit B2 mit erledigt
- **`.env.example`** warnt seit Audit 7 ausdrücklich, dass der Beispiel-`SECRET_KEY` öffentlich
  bekannt ist und zugleich der Cron-Token ist – die damalige Anmerkung ist damit erledigt

## Am Code gemessen (Browser, Build br/bs)

**Stromspar-Reststreifen (br), 461×934, Sekunde für Sekunde:**

| Sekunde | Rest (ms) | Opazität | Klasse | Breite |
|---|---|---|---|---|
| 5–45 | 54 996 → 14 945 | 0 | — | unsichtbar |
| 50 | 9 938 | 0,15 → 1 | `rest-aktiv` | 459 px (von 461) |
| 55 | 4 876 | 1 | `rest-aktiv` | 225 px |
| 60 | — | — | entfernt | `saverHell` zurück auf `false` |

Farbe `rgb(192, 57, 43)` = `#C0392B`, Höhe 6 px, `y = 928` (Fenster 934) – der Balken liegt
bündig am unteren Rand, `documentElement.scrollHeight == innerHeight` (keine Scrollverschiebung).

**Gelber Hinweis im Vollbild (bq), kein Überlauf, alle Knöpfe ganz sichtbar:**

| Größe | Kasten | Überlauf | Knöpfe |
|---|---|---|---|
| 461×934 | y 611–782 (171 px) | 0 px | 4/4 |
| 412×915 | y 570–763 (193 px) | 0 px | 4/4 |
| 360×740 | y 356–588 (232 px) | 0 px | 4/4 |

**Kartensperre × Vollbild (7 Schritte, gemessen `map.dragging.enabled()` und Sichtbarkeit):**

| Schritt | Vollbild | Karte | 🔒 sichtbar |
|---|---|---|---|
| Start | nein | gesperrt (Pill „Zum Verschieben antippen") | nein |
| Vollbild an | ja | frei | nein ✓ |
| + Stromsparmodus | ja | frei | nein ✓ |
| Vollbild aus | nein | frei | ja |
| ausdrücklich sperren | nein | gesperrt | ja |
| sperren + Vollbild | ja | frei ✓ | nein ✓ |
| Vollbild aus | nein | **wieder gesperrt** ✓ | ja |

Der letzte Schritt belegt, dass die in Audit 7 behobene Regression (B1/ao) hält: Die vor dem
Vollbild gesetzte Sperre kommt danach zurück, statt verloren zu gehen.

## Anmerkungen (kein Befund, zur Kenntnis)

- **CSRF-Prüfung ist eine Herkunftsprüfung, kein Token.** Sie deckt Browser-Angriffe ab
  (`Origin` lässt sich von einer Webseite nicht fälschen). Ein Nicht-Browser-Client, der den
  Kopf einfach weglässt, kommt weiter durch – das ist bewusst so, weil Cron, Erinnerungs-Skripte
  und `curl`-Aufrufe sonst alle ein Token bräuchten. Für diese App (kleine geschlossene Gruppe)
  ist das Verhältnis richtig; ein echtes Token wäre der nächste Schritt.
- **`/api/` bleibt von der Herkunftsprüfung ausgenommen.** Die Live-Karte schickt Standorte per
  `fetch` von der eigenen Seite; die Endpunkte prüfen Login und Tour-Zugehörigkeit selbst.
- **`Query.get()` ist SQLAlchemy-Legacy** und erzeugt bei jedem Start Warnungen (unverändert
  seit Audit 7). Bei einem SQLAlchemy-3-Umstieg bricht es.
- **Testdauer** 79 s für 515 Tests (vorher 74 s für 500).
- **Umgebungsgrenzen der Sandbox** (keine Befunde): Open-Meteo (`api.open-meteo.com`), die
  OSM-Kachelserver und die CDN-Hosts sind hier nicht erreichbar – im Browser-Durchlauf wurden
  die CDN-Dateien lokal ausgeliefert und die Kachel-Fehler als erwartet eingeordnet.

# Audit-Bericht – De jungen Olen, Audit 7 (Version 1.5.0, Build an, 07.11.2026)

Siebtes Komplett-Audit, Stand Build an. Scope: der Zuwachs seit Audit 6 (Build p, 04.11.2026) –
**72 Commits, 6 Builds (ae–an)**, fast ausschließlich auf der Live-Karte: Stromsparmodus neu
gedacht (ganzflächige Abdunklung, zwei Stufen, Bedienbarkeit im hellen Zustand), ehrliches
„Bildschirm bleibt an" mit Messung statt Behauptung (Wake-Lock + Video-Ersatz), die
Kartensperre (immer verfügbar außer im Vollbild, jetzt über dem Info-Block) und drei
Bedienfehler, die der Nutzer im Betrieb gefunden hat (Doppeltipp tot, Seiten-Zoom statt
Karten-Zoom, Doppeltipp zoomte die Karte mit).

Ergebnis im Satz: **keine Sicherheitslücke** – aber **zwei echte Verhaltensfehler und zwei
Ressourcen-Leck**, alle selbst gefunden und behoben: ein Zustandsfehler der Kartensperre nach
dem Vollbild (die Karte blieb gesperrt, obwohl sie vorher frei war), ein unbegrenzt wachsender
Kachel-Cache im Service Worker, fehlende Datenbank-Indizes auf `group_id`/`tour_id` und rund
40 Zeilen toter Code im Stromsparmodus.

## Vorgehen

- **Statisch:** `py_compile` über app/models/config/exif_gps/make_deploy_zip → sauber;
  **pyflakes** (in dieser Umgebung nachinstalliert) → 5 Hinweise, davon 3 absichtliche
  Import-Tests (`# noqa` im Code, von pyflakes ignoriert) und 2 unbenutzte `tour`-Variablen,
  die nur der Zugriffsprüfung dienen (jetzt ohne Zuweisung, damit es niemand für einen Fehler
  hält); `node --check` über **alle 36 Inline-Skript-Blöcke** aus 54 Templates → 0 Fehler;
  `node --check` über sw.js und map-touch.js → sauber
- **Sicherheit (dynamisch, Test-DB):**
  - Gefährliche Muster: `eval`, `exec`, `os.system`, `shell=True`, `pickle.load`,
    `yaml.load`, rohe SQL-Strings → **0 Treffer**; `render_template_string` nur mit einer
    festen Konstante als Fallback (kein Injection-Pfad); `Markup()` einmal, mit `escape()`
    umschlossen
  - **Mandantenprobe** gegen eine Tour der fremden Gruppe (8 Endpunkte, GET und POST):
    überall 404 bzw. 403 – auch Kommentar anlegen, Fotos, Zeitabstimmung, Teilnahme
  - **Gruppenisolation der Listen:** Start, Touren, Archiv, Karte, Mitglieder – der Titel
    der fremden Tour taucht nirgends im HTML auf
  - **XSS:** Tour mit `<img src=x onerror=alert(1)>` als Titel, `"><script>` als Treffpunkt
    und Beschreibung angelegt → auf Tourseite, Liste und Live-Karte vollständig escaped,
    kein rohes Vorkommen
  - **Uploads:** GPX-Upload erzwingt die Endung und vergibt den Dateinamen serverseitig
    (`tour_id_token.gpx`); Fotos werden über **Magic Bytes** geprüft (JPEG/PNG/WebP/HEIC),
    nicht nur über die Endung; Rate-Limit 5 Uploads/Minute
  - **Auth:** Login-Links 32 Byte, einmalig, 15 Minuten, Zweck `login` getrennt von
    `reset`; Antwort verrät nicht, ob die Adresse existiert; Rate-Limit pro IP und pro Nutzer
  - **Cron-Endpunkte** `/api/backup/trigger` und `/api/reminder/trigger`: nur per Token,
    `hmac.compare_digest` (zeitkonstant), Default-Schlüssel wird abgewiesen
  - **Deploy-ZIPs:** keine `.env`, keine Datenbank, keine Backups, kein `__pycache__` –
    nur `.env.example`
- **Robustheit:** 20 Fuzzing-Fälle (`lat=''`, `'x'`, `1e309`, `999`; `tour_id` als
  `1e309`/`-5`/`abc`; 100 kB Kommentar; `parent_id` als Text und als fremde ID; leerer und
  HTML-Slot; unbekannter RSVP-Status; 2 000-Zeichen-Suche, SQL-Fragment in der Suche;
  `page=-1`/`abc`/`999999`) → **kein einziger 500er**; Live-Update liefert korrekt 400
- **Performance:** SQL-Zähler je Seite 9–29 (flach, kein N+1); `EXPLAIN QUERY PLAN` zeigte
  aber drei Tabellendurchläufe (→ B3)
- **Browser (Chromium, Smartphone-Profil, 404 × 854):** Zustandsmaschine der Live-Karte
  durchgespielt (Sparmodus × Sperre × Vollbild, 8 Schritte) → B1 gefunden; dabei auch die
  Konsolenfehler gesichtet (nur erwartete, geblockte CDN/Tiles)
- **Doku:** README kannte keine der neuen Live-Funktionen (→ B4)

## Befunde

| Nr. | Schwere | Befund | Status (Build ao) |
|---|---|---|---|
| B1 | **Mittel** (Bedienung) | **Kartensperre nach dem Vollbild falsch.** `saverStufe()` schrieb `guardUnlocked` auch im Vollbild. Wer im Vollbild den Stromsparmodus beendete, verlor den gemerkten Frei-Zustand – nach dem Verlassen war die Karte gesperrt, obwohl sie vorher frei war (gemessen: `drag` false statt true, Pill zurück) | **behoben:** im Vollbild fasst `saverStufe()` den Guard nicht mehr an; der Vollbild-Zustand regelt ihn selbst. Nachgestellt: 8-Schritt-Sequenz endet jetzt im erwarteten Zustand |
| B2 | **Mittel** (Ressourcen) | **Kachel-Cache wuchs unbegrenzt.** `djo-tiles-v1` ist in `activate` von der Löschung ausgenommen (richtig, offline-Karten sollen Deploys überleben), wurde aber nirgends begrenzt: „Karte offline speichern" legt bis 500 Kacheln je Klick ab, ohne Rotation. Über Monate hunderte MB; dann räumt der Browser alles auf, auch die offline gespeicherten Touren | **behoben:** Obergrenze 1500 Kacheln (≈ 20–30 MB), FIFO – älteste zuerst. Aufgeräumt wird beim Aktivieren einer neuen Build-Version, nach jedem Voraus-Cachen und gelegentlich (2 %) beim normalen Kachel-Laden |
| B3 | Niedrig (Performance) | Fehlende Indizes: `tours.group_id`, `users.group_id`, `tour_videos.tour_id` (und weitere FK-Spalten). `EXPLAIN QUERY PLAN` zeigte `SCAN tours` / `SCAN users` / `SCAN tour_videos`, obwohl nach diesen Spalten bei jeder Anfrage gefiltert wird | **behoben:** 8 Indizes über das bestehende `add_index()`-Muster (`CREATE INDEX IF NOT EXISTS`, greift auch auf bestehenden Datenbanken). Nachgemessen: aus `SCAN` wurde `SEARCH … USING INDEX` |
| B4 | Niedrig (Doku) | README beschrieb die Live-Karte auf dem Stand von Build p – Stromsparmodus, ehrliches „Bildschirm bleibt an" und die Kartensperre fehlten komplett | **behoben:** drei Bullets ergänzt (Stromsparmodus, Wachhalten, Sperre) |
| B5 | Niedrig (Wartbarkeit) | `saverTap()` – rund 40 Zeilen – war seit Build ai **toter Code** (die Tipp-Erkennung wanderte ans Dokument, niemand rief die Funktion mehr). Dazu `const aufKarte = …`, zugewiesen und nie benutzt. Zwei Tests prüften den toten Code und hätten ihn festgehalten | **behoben:** beides entfernt, die zwei Tests auf die tatsächlich laufende Stelle (Dokument-Listener, `saverBlick`) umgestellt. `guardArmed` wird nur geschrieben, nie gelesen – **belassen**, weil ein Test aus Build ag den Anfangswert `guardArmed = true` ausdrücklich verlangt (Nutzer-Vorgabe aus dem Guard-Umbau) |

## Bestätigt (ohne Handlungsbedarf)

- **Mandantentrennung hält** – 8 Endpunkte gegen eine fremde Tour geprüft, alle 404/403;
  kein Titel einer fremden Gruppe in irgendeiner Liste
- **XSS-Abwehr hält** – gespeicherte Payloads in Titel, Treffpunkt und Beschreibung werden
  auf allen Seiten escaped; Kommentare ebenso
- **Uploads** prüfen Inhalt (Magic Bytes) und Endung, vergeben Dateinamen serverseitig
- **Keine 500er** in 20 Fuzzing-Fällen; `lat/lng` außerhalb des Bereichs und Nicht-Zahlen
  liefern sauber 400
- **Cron-Token** zeitkonstant verglichen, Default-Schlüssel abgewiesen
- **Deploy-Pakete** enthalten keine Geheimnisse, keine Daten, keine Caches
- **Service Worker** versioniert den Cache pro Build (kein „alte Version hängt"), Fotos und
  Videos sind seit Build ai network-first (Datenschutz auf geteilten Geräten)
- **SQL-Zähler** flach (9–29 je Seite), kein N+1

## Anmerkungen (kein Befund, zur Kenntnis)

- **Cron-Token = erste 20 Zeichen des `SECRET_KEY`.** Wer `SECRET_KEY` kennt, kann Backups
  auslösen und Erinnerungen verschicken – mehr nicht (beides idempotent bzw. durch Flag
  geschützt). Der Default-Schlüssel wird korrekt abgewiesen. **Aber:** Wer `.env.example`
  wörtlich übernimmt, hat den Token `hier-einen-zufaellig` – der steht öffentlich im Repo.
  Empfehlung: in `.env.example` deutlicher machen, dass der Wert ersetzt werden **muss**
  (bereits als „Pflicht" markiert, aber nicht als Sicherheitsfolge benannt).
- **`comment_delete` prüft Autor, nicht Gruppe.** Ein Mitglied kann einen **eigenen**
  Kommentar löschen, dessen `tour_id` auf eine fremde Tour zeigt (die Tour selbst ist
  unerreichbar, 404). Danach leitet die Route auf `/touren/<fremde_id>` um → 404. Kein
  Datenabfluss, aber unschön; die Route sollte die Tour mitprüfen.
- **`Query.get()` ist SQLAlchemy-Legacy** und erzeugt bei jedem Start Warnungen. Kein
  Fehler, aber bei einem künftigen SQLAlchemy-3-Umstieg bricht es.
- **Testdauer** ist von ~60 s auf ~95 s gewachsen (381 Tests).

Die Berichte zu Audit 1–6 stehen unten.

# Audit-Bericht – De jungen Olen, Audit 6 (Version 1.4.0, Build p, 04.11.2026)

Sechstes Komplett-Audit, Stand Build o. Scope: der Zuwachs seit Audit 5 (Build av, 17.10.2026) –
34 Commits, 29 Dateien, ~1.700 Zeilen: Video-Vorschau (aw–ax), Gastro-Formular/-Suchkarte mobil
(ay, ba–bc), einheitlicher mobiler Kartenschutz `map-touch.js` (bb), Orte-Formular (bd), Fahrmodus
mit Auto-/Manuell-Pause (29b) und die Smartphone-Bedienung der Live-Karte (11-04 a–o: Daumenleiste,
Blitzstart `/fahren`, Status-Leiste, EIN Hinweis-Block, zentraler Live-Punkt mit Selbstaktualisierung,
„Fahrt läuft“ über Seitenwechsel, einheitliche Fahren-Begriffe, Links in Foto-/Beenden-Meldung,
Selbstumschaltung „Fahrt läuft“/„Fahren“ auf der Tourseite).
Ergebnis im Satz: **keine Sicherheitslücke in den neuen UI-Umbauten; zwei selbst gefundene Befunde
behoben (Live-Status war nicht gruppenscharf; ein Overlauf-Wert lieferte HTTP 500) und Doku-Lücken
(README/Hilfe: Fahrmodus) geschlossen.**

## Vorgehen
- **Statisch:** compileall über app/models/config/tests (pyflakes in dieser Umgebung nicht verfügbar –
  ersetzt durch py_compile + vollen Suite-Lauf); Diff-Review `2e54e71..4fecab8`: keine neuen
  `os.system`/`shell=True`/`eval`/`exec`-Muster; nur zwei neue Routen (`/fahren` und `/api/live/now`,
  beide `@login_required`); Review der neuen Live-Kette (`_live_activity`, `/api/location/update`,
  globaler Tracker in base.html, `djoFahren`-Pill, Hook `djoLiveNowUpdate`): localStorage
  `djo_fahren` enthält nur `{tour_id, started}` (keine Standorte); `innerHTML` nur in `applyLive`
  (ausschließlich Zahlen/IDs aus dem Server-JSON) und `setStatus(…, true)` (nur eigene
  Meldungs-Strings, `TOUR_ID` serverseitig als Zahl eingebettet)
- **Dynamisch** (Test-DB): `node --check` über ALLE Inline-Skripte von 7 gerenderten Seiten
  (Start, Touren, Tourseite, Live-Karte, Archiv, Hilfe, Profil) → sauber; SQL-Zähler 8–25 je Seite
  (flach, kein N+1); XSS-Probe mit Tour-Titel `<img src=x onerror=alert(1)>…` → 0 rohe Vorkommen,
  alles escaped (Navbar-Badge zeigt nur Zahlen, nie den Titel); Mandanten-Probe: fremde Gruppe auf
  Live-Seite/Spur-API/Update → 404 (korrekt), ABER `/api/live/now` + Navbar-Badge leakten (→ B1);
  Fuzzing `/api/location/update` (`''`, `'x'`, `<script>`, ±999, None, dict, 50 Zeichen, NaN, 1e309):
  alles < 500 außer B2 (1e309 → 500); lat/lng außerhalb des Bereichs → 400; `/fahren` ausgeloggt →
  302 auf Login; 228 Tests grün
- **Doku:** README und Hilfe kannten den Fahrmodus nicht; Hilfe behauptete zudem veraltet
  „endet automatisch beim Schließen der Seite“ (seit Build g falsch)

## Befunde

| Nr. | Schwere | Befund | Status (Build p) |
|---|---|---|---|
| B1 | **Mittel** (Datenschutz) | `_live_activity()` filterte nicht nach Gruppe: Mitglieder **anderer** Gruppen sahen im Navbar-Punkt und via `/api/live/now` Tour-ID, Titelanfang und Aktivitätszähler fremder Gruppen (die Live-Seite selbst war korrekt 404) | **behoben:** Gruppensperre wie in `_tour_or_404` – nur eigene Gruppe, Admins alle; Test: Fremd-Login sieht `live: None` |
| B2 | Niedrig (Stabilität) | `tour_id=1e309` → `OverflowError` bei `int()` → HTTP 500 (Fehler-Handler griff, aber 500 statt 400) | **behoben:** `except` um `OverflowError` erweitert → 400 `invalid data` |
| B3 | Info | SQL-Zähler konstant (Start 20, Tourseite 25, Live 11, Archiv 16, Hilfe 8) | ohne Handlungsbedarf |
| B4 | Niedrig (Doku) | README ohne Fahrmodus-Abschnitt, Tests-Dauer „~35 s“ veraltet; Hilfe mit veralteter „endet beim Schließen“-Aussage, ohne Auto-Pause und `/fahren` | **behoben:** README-Bullets + „~60 s“, Hilfe-Fahrmodus-/Pause-Abschnitt, veraltete Aussage korrigiert |

## Prozess-Hinweis (kein Code-Befund)
- Am 04.11. wurde versehentlich der stale-Zweig `main` (Stand af, 15.10.) auf den Server kopiert –
  „Live-Karte weg“. Mit dem Komplettpaket Build o wiederhergestellt; `deploy/LAST_DEPLOY.txt` ist
  jetzt wieder auf den echten Server-Stand gesetzt. **Empfehlung:** `main` per Pull Request auf den
  aktuellen Stand bringen (oder künftig ausschließlich den Arena-Zweig deployen), damit der
  Versehentlich-Fall sich nicht wiederholt.

## Bestätigt (ohne Handlungsbedarf)
- Neue Endpunkte minimal und abgesichert: `/fahren` (Login-Gate, wählt Touren nur der eigenen Gruppe,
  endet auf `?share=1`), `/api/live/now` (Login-Gate, jetzt gruppenscharf)
- `/api/location/update` erzwingt Zahlen (jetzt inkl. Overflow-Schutz), Bereichsprüfung lat/lng,
  NaN-sichere Sanitisierung von speed (0–60 m/s) / heading (0–360°), Zeitfenster-Gate 403, Fremd-Tour 404
- App-weiter Tracker: 8-h-Hartlimit doppelt (Live-Seite + Tracker), Senden max. alle 30 s, Standorte
  gehen nie in localStorage; Beenden räumt Marker, Watch und Wake-Lock auf
- Keine neuen rohen SQL-Strings im geprüften Diff; alle Abfragen ORM/gebundene Parameter
- Build n (CSS-Spezifität) und Build o (Selbstumschaltung) sind rein präsentational

Die Berichte zu Audit 1–5 stehen unten.

---

# Audit-Bericht – De jungen Olen, Audit 5 (Version 1.4.0, Build av, 17.10.2026)

Fünftes Komplett-Audit, Stand Build au. Scope: der Zuwachs seit Audit 4 – Vorlesen-Knopf und
Pausen-Erkennung (aj), mobile Kurzschrift/Kachel-Raster (ak), Video-Knopf-Dedup (al), Video-Zahlen
(am), Video-Renderer-Überarbeitung (an–at: Ken-Burns-Vielfalt, Supersampling/Sanftanlauf, 30 fps,
CRF-18-Segmente, tmix-Glättung, Mini-Karte-Position) und Pakete-Doku (au).
Ergebnis im Satz: **keine Sicherheitslücke; ein selbst gefundener Stabilitätsbefund (Lock-Race bei
langen Video-Renders) behoben, zwei Doku-Lücken (Hilfe/README: Videos) geschlossen.**

## Vorgehen
- **Statisch:** py_compile; pyflakes über app.py/models.py/config.py/tests (nur bekannte, absichtliche
  Muster: funktionaler Import-Test in `_pillow_ok`, Probe-Imports im Push-Code, drei ungenutzte
  Test-Variablen); Review aller neuen ffmpeg-Befehlsketten – argv-Listen ohne Shell, Filter-Ausdrücke
  ausschließlich aus festen Effekt-Listen (keine Nutzereingaben), Zeitlimits je Stufe (30/180/300 s);
  `/tmp`-Sweep mit festem Präfix; Sperren-Logik (O_EXCL, verwaiste Sperre 240 s, Cleanup nach Render);
  Vorlesen-Text ausschließlich via `_json_for_script` eingebettet (XSS-fest); Pausen-Berechnung als
  reine Funktion, Spalten-Migration guarded; `video_counts` als Sammel-Query (kein N+1)
- **Dynamisch** (Test-DB, Fake-ffmpeg für den Render-Pfad): `node --check` über alle Inline-Skripte
  von 4 gerenderten Seiten (Tourseite, Video-Seite, Archiv, Tourenliste) → sauber; SQL-Zähler
  Tour-Detail 17 / Archiv 13 (flach, konstant); Mandanten-Probe: Fremd-Login auf Video-Seite und
  -Render → 404; Fuzz `photo_duration` ('', 'x', -5, 99999, 0.5, 50 Zeichen) → kein 500
  („Unerwarteter Fehler“-Handler greift); Sperre nach Render sauber entfernt; Render-Lauf mit und
  ohne tmix-Verfügbarkeit → jeweils 200/video-mp4; 203 Tests grün
- **Doku-Vollständigkeit:** README (Features, Tests-Tabelle, Deployment, Pakete-Admin-Abschnitt),
  `docs/INSTALLATION_PLESK_FTP.md` (Python-3.11, `passenger_wsgi`-Auto-Erkennung, Pakete-Admin,
  eigener Abschnitt „Python-Update 3.9 → 3.11“ – vollständig), `templates/hilfe.html` (Mitglieder-
  Sicht), CHANGELOG-Konsistenz (Build-Buchstaben je einmal, Tests-Zahlen aktuell)

## Befunde

| Nr. | Schwere | Befund | Status (Build av) |
|---|---|---|---|
| B1 | **Mittel** (Stabilität) | Lock-Race: Seit ar gilt eine Render-Sperre nach 4 min als verwaist – ein legitimer langer Render (30 fps + Effekte dauern real mehrere Minuten) erneuerte die Sperre aber nicht; ein zweiter Klick hätte die Sperre entfernt und einen **parallelen ffmpeg** gestartet (doppelte RAM-Last auf dem Hosting) | **behoben:** Sperre wird während des Renderns regelmäßig „angefasst“ (`os.utime` je Foto-Segment + vor dem Final-Render); nur wirklich tote Sperren verfallen nach 4 min |
| B2 | Niedrig (Doku) | Die Video-Seite ist für alle Mitglieder, die Mitglieder-Hilfe hatte aber keinen Video-Abschnitt; README-Foto-Kapitel erwähnte die Video-Erstellung nicht | **behoben:** Hilfe → Fotos um „🎬 Videos zur Tour“ ergänzt, README-Foto-Bullet ergänzt |
| B3 | Info | Archiv-SQL 9 → 13 Abfragen (video_counts + Cover-Fotos), Tour-Detail 17 – konstant pro Seite, kein N+1 | ohne Handlungsbedarf |

## Bestätigt (ohne Handlungsbedarf)
- ffmpeg-Aufrufe: ausschließlich argv-Listen (keine Shell-Interpolation), Effekt-Ausdrücke aus dem
  festen `ken_burns_exprs`-Katalog, tmix nur nach Funktionsprobe (`ffmpeg -filters`), sonst still
  ohne Glättung; Segment-Timeouts je Stufe; temp. Ordner mit festem Präfix, Überreste alter Renders
  (> 2 h) räumt der nächste Render ab
- Doppelklick-Schutz doppelt: Browser-seitig (Button-Sperre + beforeunload) und server-seitig
  (Lock pro Tour, jetzt mit Keep-alive); verwaiste Sperren nach 4 min automatisch weg
- Vorlesen: Text nur als JSON-Script-Block (`_json_for_script`, maskiert `<`, `>`, `&`), Stopp bei
  Seitenwechsel; ohne speechSynthesis wird der Knopf ausgeblendet
- Pausen-Erkennung: reine Funktion über GPX-Zeitpunkte, Schwellen konstant (1 m/s, 180 s), keine
  DB-Zugriffe im Hot Path; `gpx_pauses_n/_s`-Migration guarded (ALTER-try)
- Video-Zahlen: je Liste eine GROUP-BY-Query, Badge auf der Tourseite nutzt die bereits geladene
  `videos`-Liste (0 Extra-Queries)

Die Berichte zu Audit 1–4 stehen unten.

---

# Audit-Bericht – De jungen Olen, Audit 4 (Version 1.4.0, Build ai, 15.10.2026)

Viertes Komplett-Audit, Stand Build ah (Tourseite mobil kompakt). Geprüft wurde vor allem der
Zuwachs seit Audit 3: Fotos per Aufnahmezeit (ac/ae/ad), Foto unterwegs & Live-Aufzeichnung (af),
Upload-Caps & Cron-Trigger (ag), kompakte Tourseite (ah). Die Berichte zu Audit 1–3 stehen darunter.
Ergebnis im Satz: **keine Sicherheits- oder Stabilitätslücke gefunden – ein Verhärtungspunkt
(Service-Worker-Foto-Cache) und erfreulich gute Messwerte.**

## Vorgehen
- Statisches Review der Zuwachs-Routen (`/api/reminder/trigger`, Live-Aufzeichnung, Foto-Upload,
  Größen-Caps, 413), aller `|safe`-Stellen, `text(f…)`-SQL, Upload-Routen (Logo/Musik: admin-only,
  Endungs-Whitelist, servergenerierte Dateinamen), `sw.js`, `passenger_wsgi.py`, `backup.sh`, `.env.example`
- Dynamisch gegen eine temporäre SQLite-DB (2 Gruppen, 5 Rollen):
  - **XSS-Sweep** mit scharfen Nutzdaten (`<svg onload>`, `<img onerror>`, `<script>`, `javascript:`)
    in Tourtitel, Kommentar, Gastro (Name/Adresse/Notizen), POI, Foto-Caption, Video-Titel, Ankündigung,
    Vorlage, Fahrgemeinschaft, Spitzname (→ Live-Karte), Treffpunkt – gescannt wurden ~40 Seiten je
    Rolle (Mitglied, Admin, fremde Gruppe) **und** die JSON-APIs: alle Nutzdaten korrekt maskiert
    (Jinja-Escaping + `_json_for_script` + `escHtml` in den Karten-Popups)
  - **Mandanten-Zugriffe** der fremden Gruppe: 22 POST- und 14 GET-Proben (Touren bearbeiten/löschen/
    absagen, GPX, Fotos, Videos, Live-Aufzeichnung übernehmen/löschen/herunterladen, Gastro, POI,
    Vorlagen, Gruppenwechsel, Tour-Paket, iCal, Druck, Exporte, Heatmap) → durchweg 404/403/405;
    Gruppenwechsel für Fremde wird abgewiesen (Session bleibt unverändert); „Nochmal fahren“ als
    GET → 405. **Gastro bleibt bewusst gruppenübergreifend** (Design-Entscheidung Audit 3): Organisatoren
    fremder Gruppen dürfen geteilte Einträge ändern – dokumentiert und gewollt
  - **Path Traversal** (`/fotos/img`, `/videos/file`, `../`/URL-kodiert) → blockiert
  - **POST-Fuzzing**: 104 Formular-Routen × 3 Müll-Varianten (leer, falsche Typen, Grenzwerte,
    20-kB-Texte) → **0 × 500**
  - **Sonderfälle**: ungültige Daten/IDs/Jahre/Kalender-Tokens → keine 500er (Wetter-API antwortet
    sauber 502 + JSON-Fehler bei Netz-/Eingabeproblemen)
  - **Rate-Limits**: Login greift; beide Cron-Endpunkte (`/api/backup/trigger`, `/api/reminder/trigger`)
    ohne/falschem Token → 403
  - **Header/Cookies**: Security-Header gesetzt; `session` und `remember_token` jeweils `HttpOnly` +
    `SameSite=Lax`
  - **JS**: `node --check` über alle Inline-Skripte von 10 gerenderten Seiten → sauber
  - **CVE-Scan** (pip-audit) über den App-Stack: Flask, Werkzeug, requests, Pillow, gpxpy, piexif,
    itsdangerous, python-dotenv – **keine bekannten Schwachstellen**
- **SQL-Profiling** je Seite (Mitglied, 2 Gruppen, 2 Touren): `/` 16 · `/touren` 11 · `/archiv` 9 ·
  `/gastro` 11 · `/karte` 13 · `/mitglieder` 7 · `/rangliste` 6 · `/rueckblick` 8 · Tour-Detail 15 ·
  `/profil` 8 · Live 8 · Suche 12 – alles unabhängig von der Datenmenge flach, keine N+1-Rückfälle.
  Seitengrößen 26–50 KB (Tour-Detail 140 KB inkl. ≤ 2 000 Trackpunkte), Ladezeiten lokal ≤ 22 ms.

## Befunde

| Nr. | Schwere | Befund | Status (Build ai) |
|---|---|---|---|
| A1 | **Mittel** (Datenschutz) | Service-Worker serviert Fotos/Videos **cache-first**: Wer sich auf einem geteilten Gerät abmeldet, bekam bereits gesehene Fotos weiter aus dem Cache, obwohl der Server inzwischen 404 liefert (Audit 2) | behoben: Foto-/Video-Strategie **network-first** – ausgeloggt gilt der Server-404, offline (Radtour ohne Netz) springt weiterhin der Cache ein; nie wird eine nicht-okay-Antwort gecacht |
| A2 | Niedrig | `logout` per GET (Seitenlink) – ein eingebettetes Cross-Site-`<img src="/logout">` könnte Nutzer ausloggen (Nuisance, keine Datenwirkung; SameSite=Lax mildert) | bewusst gelassen – alle Abmelde-Links müssten zu Formularen werden; Notiz für ein künftiges Audit |
| A3 | Niedrig | `request.referrer`-Redirect bei Routen-Bewertung – Referrer ist browsergesetzt, kein offener Redirect praktikabel | bewusst gelassen |
| A4 | Niedrig | `/api/location/update` ohne Rate-Limit – Aufzeichnung aber auf 1 Punkt/3 s je Person begrenzt, Rohpunkte nach 30 Tagen automatisch weg | bewusst gelassen |
| C7/C8 | Niedrig | CSRF (SameSite=Lax) und `HTTPS=true`/Secure-Cookie | weiterhin offen wie bisher (Betreiber-Aufgabe) |

## Bestätigt (ohne Handlungsbedarf)
- Neuer Cron-Endpunkt gleicher Schutz wie Backup-Trigger (HMAC-Vergleich, Token = SECRET_KEY[:20]),
  Selbst-Trigger wird durch den Cron-Aufruf nicht zusätzlich ausgelöst; Tagesflags verhindern Doppelsendung
- Foto-Upload: Magic-Byte-Prüfung, Duplikat-Schutz, Größen-Caps **vor** dem RAM-Einlesen (60 MB Foto/ZIP-Eintrag,
  20 MB Avatar, 500 MB Video), GPS vor Resize, ZIPs werden Eintrag für Eintrag aus dem Upload-Tempfile gelesen
- Live-Aufzeichnung: Genauigkeits-/Sprung-/Doppelsendungs-Filter, GPX-Download nur eigene bzw. Tourleitung,
  „übernehmen“ nur Tourleitung, Löschen passend beschränkt, GPX ohne Personenbezug
- Uploads (Logo/Musik): admin-only, Endungs-Whitelist, servergenerierte Dateinamen, öffentlich bleiben
  nur Gruppen-Logos/Ankündigungs-Bilder – wie im Audit 2 abgewogen

## Ideen für später (nicht umgesetzt, nach Priorität)
1. **📖 Vorlesen-Knopf** auf der Tourseite: Titel/Datum/Treffpunkt per Web Speech API vorlesen lassen –
   null Abhängigkeiten, genau richtig zur Großschrift-Zielgruppe (unterwegs oder für Sehschwache)
2. 🚻 **WC & Wasser unterwegs**: Trinkwasser-/Öffentliche-WC-Suche entlang des Tracks über die vorhandene
   Overpass-Anbindung (gleiches Muster wie die Gastro-Streckensuche)
3. ⏸️ **Pausen-Erkennung** aus den GPX-Zeitstempeln: „3 Pausen, 42 min“ als Kachel im Rückblick/Tour-Detail

## Testabdeckung
179 Smoke-Tests (`python -m unittest`) – **82 neu seit Audit 3** (28 ac + 17 af + 35 ag + 2 ah
+ 0 ah-Sonstige; Zählung je Build siehe CHANGELOG). Offene Lücken: Ankündigungs-Bild-Upload, Backup-Wiederherstellung per Weboberfläche,
Kalender-Abo mit echtem Token im Feed-Reader.

---

# Audit-Bericht – De jungen Olen, Audit 3 (Version 1.4.0, Build ab, 14.10.2026)

Drittes Komplett-Audit, Stand Build aa (Live-Karte). Die Berichte zu Audit 2 (1.4.0) und Audit 1 (1.2.0)
stehen darunter. Umsetzung aller drei Pakete: Build ab (siehe `CHANGELOG.md`).

## Vorgehen
- Statisches Review von `app.py` (~10 100 Zeilen), `models.py`, `backup.sh`, `static/sw.js`, allen Templates
- Dynamisch gegen eine temporäre SQLite-DB mit 2 Gruppen und 5 Rollen: XSS-Sweep (Nutzdaten in Titeln,
  Treffpunkten, Kommentaren, Gastro-Namen, Live-Namen → alle Seiten + JSON-APIs), Mandanten-Zugriffe
  (GET und POST auf fremde Touren/Fotos/Gastro/POI), Path Traversal, POST-Fuzzing aller Formular-Routen
  (0 Abstürze), SQL-Profiling je Seite (Abfragen/Seite), Speicherverbrauch des GPX-Caches, Seitengrößen
- Serverseitig durch den Betreiber geprüft: `.env`, `dejungen_olen.db`, `backups/`, `config.py` sind **nicht**
  über das Web erreichbar („Dateien werden nicht gefunden“) → kein Handlungsbedarf

## Ergebnis auf einen Blick
Positiv: XSS-Sweep sauber, Mandanten-Trennung sauber (Gastro/POI gruppenübergreifend ist gewollt), Traversal
→ 404, Fuzzing ohne 500er, Rate-Limits vorhanden, Migrationen vollständig, WAL aktiv, Security-Header gesetzt.

| Nr. | Schwere | Befund | Status (Build ab) |
|---|---|---|---|
| A1 | **Hoch** (Nutzen) | Tourtag-Erinnerung ohne Uhrzeit-Schranke: ging beim ersten Seitenaufruf nach Mitternacht raus – auch ausgelöst durch anonyme Aufrufe | behoben: ab 7 Uhr (einstellbar), `_run_tour_reminders` |
| A2 | **Hoch** (Nutzen) | Vorabend-Erinnerung nur als undokumentierter CLI-Befehl, nirgends eingerichtet | behoben: automatisch ab 18 Uhr, Telegram + Push, abschaltbar, Test-Knopf |
| A3 | **Hoch** (Nutzen) | Absagen nur per Admin-Status-Feld, keine Benachrichtigung bei Absage oder Terminänderung | behoben: Absagen mit Grund, Reaktivieren, „Änderung mitteilen“, Status-Whitelist |
| A4 | Mittel | „Angemeldet bleiben“ nicht vorausgewählt → Zielgruppe nach jedem Browserstart abgemeldet | behoben |
| A5 | Mittel | Bottom-Navigation .6 rem (≈ 9,6 px) | behoben: .75 rem |
| B6 | Mittel | Sind `.env`/DB/Backups über das Web erreichbar? | geprüft: nein – nichts zu tun |
| B7 | Mittel | Service-Worker-Cache `djo-v4` über alle Builds gleich, `style.css` ohne Versionsparameter → alte CSS/JS nach Deploy | behoben: Cache-Name je Build, `?v=` |
| B8 | Mittel | Backup synchron im Request (Seitenaufruf hängt), Videos immer dabei, 27 Generationen groß | behoben: Hintergrund-Thread, DB täglich + Komplett im Intervall, Videos optional, Rotation je Art |
| B9 | Mittel | `parse_gpx`-Cache bis ~170 MB je Prozess | behoben: 16 Einträge |
| B10 | Mittel | Kompletter GPX-Track im HTML der Tour-Seite (10 000 Punkte ≈ +0,7 MB) | behoben: ≤ 2 000 Punkte (3-D-Vereinfachung) |
| B11 | Mittel | N+1-Abfragen: `/mitglieder` 44 SQL (4 Mitglieder), `/profil` 96, `/rueckblick` 59 | behoben: Bulk-Statistik, `contains_eager` |
| B12 | Niedrig | `site_config` sammelt pro Tag neue Flag-Zeilen | behoben: `_set_day_flag` löscht ältere |
| B13 | Mittel | Telegram-Nachrichten ohne HTML-Escaping (7 Stellen) – „<3“ im Titel ließ den Versand scheitern | behoben: `_tg()` |
| B14 | Niedrig | Live-Karte: Statusleiste verdeckt OSM-Attribution | behoben: oben rechts |
| C1 | Mittel | Passwortwechsel im Profil ohne aktuelles Passwort | behoben |
| C2 | Niedrig | Mindestlänge 6/8 gemischt | behoben: überall 8 |
| C3 | Niedrig | `/admin/run-migration` mit Token = Anfang des `SECRET_KEY` | entfernt |
| C4 | Mittel | Video-Rendern ohne Sperre (Doppelklick = zwei ffmpeg-Läufe) | behoben: Sperrdatei je Tour |
| C5 | Mittel | Backup-Wiederherstellung `extractall` ungefiltert | behoben: `_safe_extractall` |
| C6 | Niedrig | `/api/backup/trigger`-Token aus `SECRET_KEY[:20]` | **bewusst gelassen** – in Plesk-Cron eingetragen |
| C7 | Niedrig | Kein CSRF-Schutz (SameSite=Lax-Cookies mindern) | offen, wie bisher |
| C8 | Niedrig | `HTTPS=true` in `.env` prüfen (Secure-Cookie) | Betreiber |
| D1 | Niedrig | RSVP auf abgesagten/abgeschlossenen Touren möglich | behoben |
| D2 | Niedrig | 8 `/proposals/…`-Stub-Routen | entfernt |
| D3 | Niedrig | Root-`.htaccess` nur `php_value` | gelassen |

## Neue Funktionen aus dem Audit (Paket 3)
- Notfallkontakt im Profil + druckbare Teilnehmerliste (nur Tourleitung/Admin)
- Fahrgemeinschaften je Tour
- Anmelde-Link per E-Mail (ohne Passwort), nur bei konfiguriertem SMTP

## Messwerte (vorher, 60 + 10 Touren, 4 Mitglieder)
`/gastro` 157 KB · `/archiv` 94 KB · Tour-Detail 186 KB / 25 SQL · `/` 33 SQL · `/touren` 22 SQL ·
Live 53 KB / 6 SQL. Nach Build ab (gemessen mit 11 Mitgliedern, 30 Touren): `/mitglieder` 8 SQL,
`/profil/<id>` 8 SQL, `/rueckblick` 12 SQL, `/rangliste` 6 SQL – unabhängig von der Mitglieder-/Tourenzahl.

## Testabdeckung
97 Smoke-Tests (`python -m unittest`), davon 27 neu in `tests/test_build_ab.py`. Offene Testlücken:
Registrierung/Einladung, Passwort-Reset-Formular, Kommentare, Foto-Upload, Zeitabstimmung, Vorlagen,
Ankündigungen.

---

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
1. **Toter Code:** `templates/touren/partials/*` war nirgends eingebunden – in Build d gelöscht. ✔
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
