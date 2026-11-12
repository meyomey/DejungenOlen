# Übergabe – Stand Build `cb`

> **Zweck:** Diese Datei ist der Einstieg für einen frischen Chat. Sie beschreibt, wie in
> diesem Projekt gearbeitet wird, was zuletzt passiert ist und was als Nächstes ansteht.
> **Bei jedem neuen Build aktuell halten** (Abschnitt 3 und 6).
>
> Stand: 2026-11-12, Build `2026-11-12 cb`, Branch `arena/cf89d938-dejungenolen` (Fortsetzung von `arena/9599fe55-dejungenolen`),
> HEAD siehe `git log -1`, Arbeitsbaum sauber.

---

## 1. So wird hier gearbeitet (die wichtigste Regel)

Der Nutzer meldet einen Fehler per **Screenshot + einem Satz**. Der Ablauf ist immer:

1. **Am echten Code nachmessen** – nicht raten. Die Ursache wird im Quelltext belegt.
2. **Mit echten Daten nachstellen** – ein kleines Skript, das den Fehler *vorher* zeigt
   und *nachher* nicht mehr. Erst wenn der Fehler reproduzierbar ist, wird er behoben.
3. **Beheben** – möglichst klein, an der Ursache, nicht am Symptom.
4. **Gegenprobe** – der Fix darf nichts anderes kaputt machen (Randfälle mitprüfen).
5. **Tests** – `tests/test_build_<buchstabe>.py` anlegen, volle Suite grün.
6. **Dokumentieren** – `CHANGELOG.md` mit Ursache, Nachstellung, Vorher/Nachher-Tabelle.
7. **Ausliefern** – Build-Buchstabe hochzählen, Deploy-ZIPs bauen, prüfen, committen, pushen.
8. **Antworten auf Deutsch**, mit Zahlen belegt, ruhig und knapp.

Wichtig: **Meldungen wörtlich zitieren** und die Akzeptanzkriterien im Code prüfen, nicht
„gefühlt erledigen". Wenn eine Meldung mehrdeutig ist, erst messen – meist zeigt sich
dann, dass hinter dem Symptom zwei Ursachen stecken (so war es bei Build `ca`).

### Fachliche Schutzregeln (aus Fehlern gelernt)

- **Breite CSS-Selektoren sind tabu.** Ein `<style>`-Block in einem Template gilt für die
  *ganze* Seite. Regeln immer an eine Container-Klasse binden (`.format-wahl`), nie an
  `.row .col-4`. Ein Test prüft das.
- **Inline-`display: …` neben `d-none` ist verboten** (zweimal passiert). Ebenso Inline-
  `bottom` am Hinweiskasten – das bricht das Vollbild-Layout.
- **Globale Lockerungen meiden.** `.btn { white-space: nowrap; }` in `static/css/style.css`
  wird an vielen Stellen als Container genutzt – nicht anfassen.
- **`word-break: break-word` ist veraltet** – stattdessen `overflow-wrap: anywhere`.
- **ZIPs nie von Hand bauen.** Immer `make_deploy_zip.py` benutzen, sonst greift die
  Datums-Warnung nicht und ein falscher Build-Stempel rutscht durch (ist passiert).
- **Build-Stempel = tatsächliches Datum des Baus.** Der Nutzer hat das ausdrücklich
  verlangt („Wir haben den 12.11."). `DatumTest` in `tests/test_build_bz.py` prüft:
  Build-Datum ≤ heute und ≥ heute − 2 Tage, Format `^\d{4}-\d{2}-\d{2} [a-z]{2}$`.
- **`AppTestCase` hat kein `self.app`** – `from tests.base import app` benutzen.
- **Nach Template-Änderungen** den Dev-Server neu starten (`stop_process` + `start_process`).

### Umgebung

```bash
cd /home/user/DejungenOlen
.venv/bin/python -m unittest discover -s tests -q      # volle Suite, ~115 s
.venv/bin/python -m unittest tests.test_build_cb -q    # nur ein Build
.venv/bin/python -m pyflakes app.py tests/             # Lint
```

- Python 3.11, Flask, Pillow, pyflakes im `.venv`; Node v22 (nur für jsdom-Proben).
- Tests importieren `tests.base`, das `DATABASE_URL` und alle Upload-Ordner auf ein
  Temp-Verzeichnis umbiegt – die echte DB wird **nie** angefasst.
- `ffmpeg` ist gitignored (77 MB) und liegt nur lokal/auf dem Server.

---

## 2. Was das Projekt ist

Selbst gehostete Web-App für eine Fahrradgruppe: Flask + SQLite + Leaflet, Multi-Tenancy
(mehrere Gruppen pro Installation). Live: `djo.wulmstorf.net`.

Kernbereiche: Touren (mit/ohne Termin, RSVP, Gäste, Einkehr-Stopps), GPX-Tracks,
Fotos, **Video-Export** (serverseitig mit ffmpeg – darum ging es zuletzt fast immer),
Live-Tracking, Gastronomie-Datenbank (mit OSM-Import), Rangliste/Badges, Push/Telegram.

**Der Video-Export ist der Schauplatz der letzten Builds.** `tour_video_render` in
`app.py` (ab Zeile ~3445) ist eine große Route, die viele verschachtelte Zeichen-Funktionen
enthält (`make_title_frame`, `_avatar_row_layer`, `build_gastro_frames`,
`build_track_frames`, `_draw_stats_canvas`, …). Diese Closures greifen auf lokale Variablen
der Route zu (`W`, `H`, `SAFE`, `photos`, `logo_rgba`, `tmpdir`, `fps`). Das erschwert das
isolierte Testen: Will man eine dieser Funktionen einzeln rendern, muss man sie per AST aus
`app.py` schneiden und die Closure-Variablen selbst bereitstellen. **Genau das ist der
schnellste Weg, Bilder zu prüfen** – siehe Rezept in Abschnitt 5.

---

## 3. Stand jetzt: Build `2026-11-12 cb` (fertig, ausgeliefert)

**Eine Meldung zum Video, am Code belegt, mit dem Nutzer abgestimmt, behoben.**

### 3.1 Fremdes Lokal auf der Einkehr-Folie ✅

> „Im Video erscheinen zwei Einkehrpunkte, wir waren aber nur im Asia Bistro. … Man könnte
> höchstens Einkehrstellen nahe der Strecke erwähnen, aber dann in einem eigenen Bereich oder
> ganz weglassen. Was meinst du?“

**Befund:** Keine Dublette (das war `ca`), sondern Design seit Build `j`: Die Folie mischte
eingetragene Einkehr + `gastro_near_track()` (alle Gastro-Einträge ≤ 150 m am Track).
„Bootshaus · 81 m neben der Route“ war so ein Streckenfund.

**Entscheidung:** Variante „weglassen“ (Empfehlung, vom Nutzer bestätigt). Die Streckenfunde
bleiben auf der Tour-Seite („Einkehr entlang der Strecke“, Build `u`).

**Fix:** `tour_video_render`: `_near_spots = _planned_einkehr_entries(tour, _gpx_points)` –
kein `gastro_near_track`, kein `_einkehr_merge_dedup` mehr in der Route (Funktion bleibt,
Tests in `test_build_ca.py` bleiben). Dieselbe Liste speist Folie und Kartenmarker.
Folie: Unterzeile „Unsere Einkehr auf dieser Tour“, Zusatz „· geplant“ entfällt.
Video-Seite: Häkchen „🍴 Einkehr-Folie (eingetragene Einkehr)“.
Ohne eingetragene Einkehr → keine Folie.

### 3.2 Stand `ca` (davor, ausgeliefert)

- Einkehr-Dublette (OSM-Import + Handanlage) → `_einkehr_merge_dedup`, durch `cb` in der
  Video-Route nicht mehr relevant.
- Gäste im Einstiegsbild: `_attending_users` = Mitglieder + Gäste, `make_title_frame`
  zeichnet Avatar-Zeile (`max_shown=12`, Umbruch ab 9).

### 3.3 Auslieferung

| | |
|---|---|
| `APP_VERSION` | `1.5.0` |
| `APP_BUILD` | `2026-11-12 cb` (app.py Z. 92) |
| Tests | `tests/test_build_cb.py` **11**, volle Suite **632 grün** (~115 s) |
| Pakete | `deploy/deploy_v1.5.0_2026-11-12cb_aenderungen.zip` · `…_komplett.zip` |
| Geprüft | Folie per AST gerendert (eine Kachel), ZIP-Probe siehe Commit-Text |

**Hinweis zur Paket-Probe:** Zwei Tests (`test_az_deploy_date_freshness`,
`test_n_ffmpeg_aus_git_aber_lokal_da`) schlagen im entpackten Paket an, weil sie
`make_deploy_zip.py` und `.gitignore` lesen – beides gehört nicht ins Serverpaket. Kein Fehler.

## 4. Offene Punkte (bewusst liegen gelassen)

Diese stehen im Kopf von `CHANGELOG.md` und wurden vom Nutzer **absichtlich** vertagt
(„erst fahren und schauen"):

- **Auto-Pause, Anfahren:** Die Aufzeichnung setzt erst ~27–30 m nach dem Losfahren wieder
  ein (18 km/h: 3 s · 11 km/h: 6 s · 7 km/h: 12 s · Schieben 4 km/h: 21 s). Kosmetik, kein
  Datenverlust. Fix wäre: Anker 25 → 10 m.
- **Auto-Pause, Stand-Punkte:** Im Stand werden weiter Punkte im 20-s-Takt gesendet → die
  Spur „knäuelt" bis ±20 m um den Pausenort. Kosmetik. Fix wäre: Stand-Punkte nur bei
  ≥ 5 m echter Bewegung.

Beides in `templates/…/live.html` (Pausen-Block), klein und unabhängig voneinander.
**Nur auf Zuruf machen** – der Nutzer wollte erst echte Fahrten abwarten.

---

## 5. Rezepte (sparen viel Zeit)

### Ein Video-Standbild prüfen, ohne ein Video zu rendern

Die Zeichen-Funktionen sind Closures in `tour_video_render`. Per AST herausschneiden und
mit den nötigen Variablen in einen eigenen Namensraum legen:

```python
import ast, textwrap
src = open('app.py', encoding='utf-8').read()
lines = src.splitlines(keepends=True)
tree = ast.parse(src)
want = ['_pil_font', '_centered_text', '_logo_scaled', 'paste_watermark',
        '_avatar_row_layer', '_cover_photo_bg', 'make_title_frame', '_draw_weather_icon']
found = {n.name: n for n in ast.walk(tree)
         if isinstance(n, ast.FunctionDef) and n.name in want}
body = '\n\n'.join(''.join(lines[found[w].lineno-1:found[w].end_lineno]) for w in want)

ns = dict(os=os, _PIL=_PIL, _ID_MOD=_ID_MOD, app=app, W=1080, H=1920, SAFE=40, PIL_OK=True,
          _IFO=__import__('PIL.ImageFont', fromlist=['x']),
          _ILF=__import__('PIL.ImageFilter', fromlist=['x']),
          photos=[], logo_rgba=None, _group_name='x',
          __file__='/home/user/DejungenOlen/app.py')
exec(compile('def _inner():\n' + textwrap.indent(textwrap.dedent(body), '    ')
             + '\n    return locals()\n', '<f>', 'exec'), ns)
loc = ns['_inner']()
# dann loc['make_title_frame']('/tmp/x.jpg') aufrufen, mit ns['tour'], ns['_weather'], …
```

Häufige Stolpersteine dabei: `__file__`, `_IFO`, `_ILF`, `logo_rgba`, `photos`, `fps`,
`tmpdir`, `GASTRO_NEAR_M` müssen im Namensraum liegen. Danach das JPEG mit dem
Bild-Betrachter ansehen – **nicht** mit Zeichenbreiten schätzen (das ging schon schief).

Zum Testen echter Datenmodelle: eigenes SQLite in `/tmp`, `db.create_all()` +
`migrate_db()`, `app.config.update(SERVER_NAME='localhost', TESTING=True)` – sonst
scheitert `url_for` außerhalb eines Request-Kontexts.

### Deploy-Paket bauen und prüfen

```bash
git add -A && git commit -m "Build <xx>: …"
.venv/bin/python make_deploy_zip.py --since <letzter-build-commit>
.venv/bin/python make_deploy_zip.py --deployed      # LAST_DEPLOY.txt setzen
git add -A && git commit -m "deploy: Server-Stand auf Build … gesetzt"
git push origin arena/cf89d938-dejungenolen
```

Vorher **immer** prüfen: `APP_BUILD` trägt das heutige Datum. `make_deploy_zip.py` warnt
sonst. Probe: ZIP nach `/tmp` entpacken, App starten, Footer prüfen.

---

## 6. Als Nächstes

Nichts Offenes aus Build `cb`. Der nächste Chat wartet auf die nächste Meldung des Nutzers.
Hinweis: `origin/main` auf GitHub steht noch auf Build `af` (15.10.) – alle neueren Builds
liegen nur auf den Arena-Branches; `main` nur auf Zuruf nachziehen.

Wenn eine neue Meldung kommt:
1. Wörtlich zitieren, Akzeptanz im Code prüfen.
2. Nachstellen (Skript, das den Fehler zeigt).
3. Beheben, Gegenprobe, Tests, CHANGELOG.
4. Buchstabe hochzählen: nach `cb` kommt `cc`, `cd`, … (immer Kleinbuchstaben, `z` → `aa`).
5. `APP_BUILD` auf das **heutige** Datum + neuen Buchstaben setzen.
6. Deploy-Pakete, Probe, Commit, Push.
7. **Diese Datei aktualisieren** (Abschnitt 3, 4 und 6).

---

## 7. Projekt-Landkarte (wo was liegt)

| Datei / Bereich | Inhalt |
|---|---|
| `app.py` (12.474 Zeilen) | fast alles: Routen, Video-Export, GPX, Gastro, Push |
| ↳ `tour_video_render` ~3445 | die große Video-Route mit allen Zeichen-Closures |
| ↳ `_avatar_row_layer` 3976 | Avatar-Zeile (Kreise + Namen), `max_shown`, Umbruch |
| ↳ `make_title_frame` 4082 | Einstiegsbild (Titel, Datum, Wetter, **Avatare**) |
| ↳ `build_gastro_frames` ~4341 | Folie „Einkehr unterwegs" – seit `cb` nur eingetragene Einkehren |
| ↳ `_attending_users` 4814 | Mitglieder **+ Gäste**, deutsch sortiert |
| ↳ `_planned_einkehr_entries` 8910 | geplante Stopps als Folien-Einträge (inkl. Freitext) |
| ↳ `_einkehr_merge_dedup` ~8958 | entdoppelt geplante Stopps ↔ Streckenfunde (seit `cb` von der Video-Route nicht mehr genutzt) |
| ↳ `gastro_near_track` 1990 | Gastro-Einträge ≤ `GASTRO_NEAR_M` neben dem Track |
| ↳ `_gastro_match_known` 6972 | Vorbild für die Duplikat-Regel (25 m / 100 m / osm_id) |
| ↳ `tour_headcount` 8279 | Mitglieder **+ Gäste** – die verbindliche Kopfzahl |
| ↳ `_de_name_key` 7260 | Telefonbuch-Sortierung (Ä→A, Ö→O, Ü→U, ß→ss) |
| `models.py` | `Tour` (inkl. `gastro_spot_id`, `einkehr2/3_*`), `TourGuest`, `TourParticipant`, `GastroSpot` |
| `templates/touren/video.html` | Video-Seite: Format-Auswahl (`.format-wahl`, Build bz) + JS-Vorschau |
| `static/css/style.css` | globales CSS – `.btn { white-space: nowrap; }` Z. 650 **nicht** anfassen |
| `tests/base.py` | `AppTestCase`, Seed-Daten, Attrappen für Netz-Zugriffe |
| `tests/test_build_*.py` | ein Testpaket pro Build; `test_build_ag.py` ist das große Sammelpaket |
| `make_deploy_zip.py` | baut beide ZIPs, warnt bei veraltetem Build-Datum, setzt `LAST_DEPLOY.txt` |
| `deploy/` | aktuelle ZIPs + `LAST_DEPLOY.txt` (nur der aktuelle Build bleibt liegen) |
| `CHANGELOG.md` | je Build: Meldung, Ursache, Nachstellung, Vorher/Nachher |

### Build-Historie (neueste zuerst)

| Build | Datum | Thema |
|---|---|---|
| `cb` | 2026-11-12 | Einkehr-Folie nur noch eingetragene Einkehr (keine Streckenfunde im Video) |
| `ca` | 2026-11-12 | Einkehr doppelt im Video · Gäste fehlen im Einstiegsbild |
| `bz` | 2026-11-12 | Format-Kacheln im Video-Export: Text lief in Nachbarkacheln |
| `by` | 2026-11-11 | (siehe CHANGELOG) |
| `bx` | 2026-11-11 | (siehe CHANGELOG) |
| `bw` | 2026-11-11 | (siehe CHANGELOG) |
| `bv` | 2026-11-11 | Auto-Pause untersucht → bewusst vertagt |
| `bk`–`bu` | 2026-11-09 | siehe CHANGELOG |

---

## 8. Text zum Einfügen in den neuen Chat

> Wir machen mit der App „DejungenOlen" weiter. Lies bitte zuerst `UEBERGABE.md` im
> Projektordner – dort steht der komplette Stand. Kurzfassung: Build `2026-11-12 cb` ist
> fertig und ausgeliefert (Einkehr-Folie nur noch eingetragene Einkehr), Arbeitsbaum
> sauber, alle 632 Tests grün. Arbeite weiter wie dort beschrieben: Meldung wörtlich
> nehmen, am echten Code nachmessen, mit echten Daten nachstellen, beheben, Gegenprobe,
> Tests, CHANGELOG, neuer Build-Buchstabe (`cc`), Deploy-Pakete, Push.
