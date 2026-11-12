# Changelog – De jungen Olen

> **Offen nach Build bv – bewusst nicht geändert (Nutzer: „erst fahren und schauen"):**
> Die Auto-Pause ist in besserem Zustand als zunächst vermutet. Gemessen mit dem echten
> Pausen-Block aus `live.html`:
> - **Anfahren:** Die Aufzeichnung setzt erst ~27–30 m nach dem Losfahren wieder ein
>   (18 km/h: 3 s · 11 km/h: 6 s · 7 km/h: 12 s · Schieben 4 km/h: 21 s). Kein Datenverlust,
>   sondern ein kleiner Schönheitsfehler – **nicht** die Ursache der fehlenden Kilometer.
> - **Stand-Punkte:** Die Pause wird bei jedem Rauschpegel (0 bis ±20 m) korrekt erkannt. Im
>   Stand werden aber trotzdem Punkte im 20-s-Takt gesendet, sodass die Spur mit starkem
>   GPS-Rauschen bis zu ±20 m um den Pausenort „knäuelt". Kosmetik.
>
> Falls nach der ersten bv-Fahrt gewünscht: Anker beim Anfahren 25 → 10 m, und Stand-Punkte nur
> bei ≥ 5 m echter Bewegung. Beides klein und voneinander unabhängig.

## 1.5.0 – 2026-11-12 (Build ce) – Wetter am Tourtag fehlte in Vorschau und MP4

> „Die Wetterinfo am Tourtag vermisse ich bei beiden, Vorschau und Video.“

**Ursache.** `_tour_day_weather(tour, lat, lng)` braucht einen Ort. Die Tour-Detailseite
(Build q) gibt ohne Treffpunkt den **GPX-Start** als Ersatz mit – die Video-Seite und der
Renderer riefen die Funktion aber **ohne** Ersatz-Koordinaten auf (`_tour_day_weather(tour)`).
Ohne `meeting_lat/lng` an der Tour bricht sie sofort mit `None` ab. Deshalb: Detailseite zeigt
Wetter, Vorschau und Video nicht – bei jeder Tour ohne eingetragenen Treffpunkt.

Nachgestellt (Open-Meteo-Attrappe: 9 °C, bewölkt; Tour ohne Treffpunkt, mit GPX):

| | vorher | nachher |
|---|---|---|
| Detailseite (Wetter-Kachel) | 9 °C ☁️ | 9 °C ☁️ |
| Video-Seite `const WEATHER` | `null` | `{temp_max: 9, kind: 'cloud', …}` |
| MP4-Titel / Statistik-Kachel „Wetter“ | – | 9 °C mit Symbol |

**Fix.** `_video_weather(tour, gpx_points, photos)` – ein Helfer für Seite und Renderer,
Ersatz-Reihenfolge: Treffpunkt → GPX-Startpunkt → erstes Foto mit GPS → Standard-Treffpunkt
der Gruppe (`default_meeting_lat/lng`). Im Renderer wird das Wetter jetzt **nach** dem
GPX-Parsen geholt (vorher davor, da gab es noch keine Punkte). Touren mit offenem Datum
bekommen weiterhin kein Wetter; der Cache in `tours.weather_json` greift wie bisher.

**Tests.** `tests/test_build_ce.py` (8), volle Suite **654 grün**.

## 1.5.0 – 2026-11-12 (Build cd) – Browser-Vorschau sieht aus wie das MP4

> „Die Vorschau sollte auch so aussehen wie das erzeugte Video.“

**Befund.** Vorschau (`templates/touren/video.html`, Canvas im Browser) und MP4
(`tour_video_render`, Pillow + ffmpeg) sind zwei getrennte Zeichenwege. Die Server-Seite hat
seit Build i/j/ca einiges dazubekommen, die Vorschau nicht – gemessen an den Folien:

| Folie | MP4 (Server) | Vorschau (vorher) |
|---|---|---|
| Titel | Gruppenlogo, Datum, „km · Hm“, Wetter, **Avatar-Zeile mit Namen (Mitglieder + Gäste)** | 🚴-Emoji, „👥 3 dabei“ – keine Avatare, kein Logo |
| Track | lila Einkehr-Marker mit Namensschild | keine Marker |
| Einkehr-Folie | nach dem Track, 2,5 s + 0,5 s je Zeile | **fehlte** („nur MP4“) |
| Statistik | Avatar-Zeile mit Profilbildern, Logo-Wasserzeichen | Namen nur als Textzeile, nur Mitglieder (`attending_names` ohne Gäste) |
| Outro | Logo über dem Dank | kein Logo |

**Fix.**
- **Eine Datenquelle:** `_video_attending_users(tour_id)` (Mitglieder + Gäste, deutsch
  sortiert) liefert jetzt die Liste für Seite **und** Renderer; `_video_page_einkehr()` gibt
  der Seite dieselben Einkehr-Einträge wie der Folie im MP4 (`_planned_einkehr_entries`,
  Build cb). Die Seite bekommt außerdem `logo_url`.
- **Titel:** Logo über dem Titel (ohne Logo weiterhin 🚴), „42.3 km · 120 Hm“, Wetterzeile,
  darunter die Avatar-Zeile (`drawAvatarRow`, bis 12 Gesichter, Umbruch ab 9, Initialen-Kreis
  ohne Profilbild – gleiche Palette/Größen wie `_avatar_row_layer`).
- **Einkehr-Folie** (`drawGastroFrame`): 1:1 nach `build_gastro_frames` – Überschrift,
  Unterzeile, Kacheln mit gestaffeltem Einblenden, „Geplante Einkehr · Imbiss“ ohne GPX, gleiche
  Dauer (`min(6, 2.5 + 0.5·n)`), Position nach dem Track. Häkchen gilt nun für beides; der
  Zusatz „(nur MP4)“ ist weg.
- **Track:** Einkehr-Marker (lila, Namensschild bis 6 Einträge) erscheinen, sobald der Track
  die Stelle erreicht hat.
- **Statistik:** Avatar-Zeile ab 55 % statt Textzeile; Logo-Wasserzeichen oben rechts;
  „42.3 km“ / „120 m“ mit Leerzeichen wie im MP4; Überschrift ohne Emoji.
- **Outro:** Logo über „Danke fürs Mitfahren!“.
- Standbild beim Öffnen wird nach dem Laden von Logo/Profilbildern noch einmal gezeichnet.

**Nachgestellt** (echte Seite aus dem Testclient, Skript in Node mit Stub-Canvas, Tour mit
1 Mitglied + 2 Gästen + 1 Einkehr):

| | vorher | nachher |
|---|---|---|
| Titel-Texte | `🚴, Titel, Datum, 📏 42.3 km ⛰️ 120 m, 👥 3 dabei` | `Titel, Datum, 42.3 km · 120 Hm, AH Axel, JK Jörg, O Orga` |
| Einkehr-Folie | – | `Einkehr unterwegs / Unsere Einkehr auf dieser Tour / Badener Asia Bistro / Geplante Einkehr · Imbiss` |
| Statistik-Teilnehmer | „Orga“ (Textzeile, ohne Gäste) | AH Axel · JK Jörg · O Orga |
| Gesamtdauer ohne GPX | 13 s | 16 s (+3 s Einkehr, wie MP4) |

Bleibende, bewusste Unterschiede: Die Vorschau rendert in 1280×720, das MP4 im gewählten
Format; Wettersymbol ist im Browser ein Emoji, im MP4 gezeichnet (kein Emoji-Font auf dem Server).

**Tests.** `tests/test_build_cd.py` (7, davon eine Node-Probe), volle Suite **646 grün**.

## 1.5.0 – 2026-11-12 (Build cc) – WhatsApp-Einladung: Karte wechselt mit dem Mitglied, am PC WhatsApp Web

> „Es bleibt immer das gleiche WhatsApp Fenster offen, auch wenn ich ein anderes Mitglied
> auswähle. Ich benutze auch Web WhatsApp. Der Link lässt sich nicht direkt darin öffnen
> sondern es kommt eine Meldung.“ (Windows-Dialog: „Der Datei ist keine App zum Ausführen
> dieser Aktion zugeordnet“, URL `whatsapp://send/?text=…`)

**Zwei Ursachen, beide in `templates/admin/dashboard.html`:**

1. **Karte wechselte nicht.** Die grüne Karte „Einladungstext für WhatsApp“ zeigte nur den
   Link aus dem URL-Parameter `?invite=<id>`, den die Weiterleitung nach „Link erstellen“
   setzt. Die „WhatsApp“-Links in der Liste „Einladungslinks“ sprangen direkt zu `wa.me`
   und änderten die Karte nie – oben blieb also immer das zuletzt erstellte Mitglied.
2. **Falscher Link am PC.** Alle Links zeigten auf `https://wa.me/?text=…`. Am PC leitet
   `wa.me` auf `whatsapp://send?…` weiter – das Protokoll der Desktop-App. Ohne installierte
   App zeigt Windows genau den gemeldeten Dialog. WhatsApp Web erwartet stattdessen
   `https://web.whatsapp.com/send?text=…`.

**Fix.**
- Klick auf „WhatsApp“ in der Liste lädt den Text **dieses** Mitglieds in die Karte (Name
  steht jetzt im Kartenkopf), Karte scrollt ins Bild. Ohne JavaScript führt der Link auf
  `/admin/?invite=<id>#einladung` – gleiches Ergebnis per Seitenaufruf. Die Karte ist
  vorhanden, sobald es offene Einladungen gibt (ohne Auswahl `d-none`, kein Inline-`display`).
- Der Senden-Button wählt per User-Agent: Handy (Android/iPhone/iPad) → `wa.me` (öffnet
  die App), PC → `web.whatsapp.com/send`. Gilt auch nach Textänderungen im Feld.
- Die Listen-Links stehen im DOM unterhalb des Skripts – deshalb Event-Delegation auf
  `document` statt direktem Binden (beim ersten Versuch griff der Klick darum nicht).

**Nachgestellt (jsdom, echte Seite aus dem Testclient mit zwei Einladungen):**

| | vorher | nachher |
|---|---|---|
| Karte nach Klick auf „Jörg Krüger“ in der Liste | Axel Hübner | **Jörg Krüger** (Text, Kopf, Link) |
| Senden-Link am PC (Windows-UA) | `wa.me` → `whatsapp://` → Fehlerdialog | `https://web.whatsapp.com/send?text=…` |
| Senden-Link am iPhone | `wa.me` | `wa.me` (unverändert) |
| Listen-Links direkt zu `wa.me` | 3 | 0 |

**Tests.** `tests/test_build_cc.py` (7), volle Suite **639 grün**.

## 1.5.0 – 2026-11-12 (Build cb) – Einkehr-Folie im Video zeigt nur noch die eingetragene Einkehr

> „Im Video erscheinen zwei Einkehrpunkte, wir waren aber nur im Asia Bistro. Bei der
> zweiten Stelle waren wir nicht. Das darf im Video nicht erscheinen, es ist auch nur die
> eine Einkehrstelle in der Tour eingetragen. Man könnte höchstens Einkehrstellen nahe der
> Strecke erwähnen, aber dann in einem eigenen Bereich oder ganz weglassen.“

**Befund.** Das war kein Rechenfehler und auch keine Dublette wie in Build `ca`. Die Folie
„Einkehr unterwegs“ war seit Build `j` als „Gastronomie direkt an der Strecke (bis 150 m)“
gebaut: Sie führte die **eingetragene Einkehr** (`_planned_einkehr_entries`) mit **allen**
Gastro-Einträgen zusammen, die ≤ 150 m neben dem GPX-Track liegen (`gastro_near_track`).
Das Bootshaus (81 m neben der Route) stand also berechtigt in dieser Liste – nur ist das
die falsche Aussage für ein Tour-Video: Jeder Zuschauer liest „Bootshaus · km 30,4“ als
„da waren wir auch“.

Nachgestellt mit zwei Datensätzen (Asia Bistro eingetragen, Bootshaus 80 m neben dem Track):

| | vorher (ca) | nachher (cb) |
|---|---|---|
| in der Tour eingetragen | 1 | 1 |
| Streckenfunde ≤ 150 m | 2 | 2 (unverändert, nur noch auf der Tour-Seite) |
| **Zeilen auf der Folie** | **2** | **1** |
| Kartenmarker auf der Track-Folie | 2 | 1 |
| keine Einkehr eingetragen | Folie mit fremden Lokalen | **keine Folie** |

**Entscheidung (Variante „ganz weglassen“, mit dem Nutzer abgestimmt).** Das Video erzählt,
wo wir waren. Was sonst an der Strecke liegt, ist eine Planungsinformation – die gibt es
weiterhin auf der Tour-Seite unter „Einkehr entlang der Strecke“ (Build `u`). Ein eigener
Video-Bereich dafür hätte 3–6 s gekostet und eine Frage beantwortet, die niemand stellt.

**Änderungen.**
- `tour_video_render`: `_near_spots = _planned_einkehr_entries(tour, _gpx_points)` – kein
  `gastro_near_track()`, keine Zusammenführung mehr. Dieselbe Liste speist Folie **und**
  Kartenmarker, also verschwinden fremde Lokale auch von der Karte.
- Folie: Unterzeile „Unsere Einkehr auf dieser Tour“ statt „Gastronomie direkt an der
  Strecke (bis 150 m)“; der Zusatz „· geplant“ entfällt (alles ist eingetragen). Freitext-
  Einkehren ohne Position erscheinen weiter als „Geplante Einkehr“ (Build `ca`).
- Video-Seite: Häkchen heißt „🍴 Einkehr-Folie (eingetragene Einkehr)“ statt „Einkehr nahe
  der Route“.
- `_einkehr_merge_dedup` (Build `ca`) bleibt als Funktion erhalten (mit Tests), wird von der
  Video-Route aber nicht mehr gebraucht.

**Gegenprobe.** Drei eingetragene Stopps (Build `bh`) erscheinen weiterhin alle drei; die
Tour-Seite ruft `gastro_near_track` unverändert auf; Folie per AST herausgeschnitten und
gerendert: eine Kachel, an der Stelle der früheren zweiten Zeile nur Hintergrund.

**Tests.** `tests/test_build_cb.py` (11), `test_build_ca.py` und `test_build_ag.py` auf den
neuen Stand angepasst – volle Suite **632 grün**.

## 1.5.0 – 2026-11-12 (Build ca) – Einkehr doppelt im Video, Gäste fehlen im Einstiegsbild

Zwei Meldungen zum Tour-Video, beide am echten Code nachgestellt.

### 1. „Im letzten Video sind wir nur einmal eingekehrt, im erzeugten Video stehen bei Einkehr zwei Positionen obwohl nur eine eingetragen ist."

**Ursache.** Die Folie bekommt ihre Zeilen aus zwei Quellen: den **geplanten** Stopps
(`_planned_einkehr_entries`) und den Gastro-Einträgen **neben der Strecke**
(`gastro_near_track`). Zusammengeführt wurden beide über genau eine Zeile:

```python
_planned_ids = {e['id'] for e in _planned_list}
_near_spots = _planned_list + [sp for sp in _near_spots if sp.get('id') not in _planned_ids]
```

Der Filter verglich **ausschließlich `id`-Werte**. Derselbe Ort kann aber zweimal in
`gastro_spots` stehen – einmal über den OpenStreetMap-Import, einmal von Hand angelegt.
Dann hat der geplante Stopp eine andere id als der Streckenfund, und der zweite Datensatz
rutschte durch. Nachgestellt mit zwei Datensätzen „Gasthof Adler" 15 m auseinander:

| | vorher | nachher |
|---|---|---|
| geplante Einkehr | 1 (`id` 1) | 1 (`id` 1) |
| Streckenfunde | 2 (`id` 1, `id` 2) | 2 |
| **Zeilen auf der Folie** | **2 Positionen** | **1 Position** |

**Behoben.** Neuer Helfer `_einkehr_merge_dedup(planned_list, near_spots)` neben
`_planned_einkehr_entries`. Er nutzt dieselbe Regel wie die Duplikat-Prüfung im
Gastro-Formular (`_gastro_match_known`): gleiche `id`, gleicher OpenStreetMap-Eintrag,
näher als **25 m** oder gleicher Name im Umkreis von **100 m** → dieselbe Einkehr. Beide
Quellen liefern dafür jetzt auch `osm_id` mit.

Bewusst *nicht* zusammengelegt werden geplante Stopps **untereinander** – zwei absichtlich
eingetragene Stopps (Build bh erlaubt drei) bleiben beide stehen.

**Zusatz.** Eine Einkehr, die nur als **Freitext** eingetragen ist (ohne Gastro-Eintrag),
fehlte auf der Folie bisher ganz. Sie erscheint jetzt als „Geplante Einkehr" ohne
Kilometerangabe. Auf der Karte bekommt sie keinen Marker (sie hat keine Position), und
die Marker-Schleife überspringt Einträge ohne Koordinaten, statt abzustürzen.

### 2. „Ich war dabei und zwei Leute waren als Gast dabei. Im Einstiegsbild des Videos sollen die Avatare mit Namen erscheinen auch für Gäste und nicht nur ‚3 dabei' stehen."

**Ursache.** Zwei Dinge kamen zusammen:
- `tour_headcount` zählt Mitglieder **und** Gäste (hier **3**), die Avatar-Liste enthielt
  aber nur die Mitglieder (hier **1**):
  ```python
  _attending_users = [(p.user.display_name, p.user.avatar) for p in
                      TourParticipant.query.filter_by(tour_id=tour_id, status='attending')…]
  ```
  `TourGuest` wurde nie abgefragt.
- Das Einstiegsbild (`make_title_frame`) malte **überhaupt keine** Avatare, sondern nur
  `f'{_attending_count} dabei'`. Selbst mit vollständiger Liste wäre dort ein Zähler
  gestanden.

**Behoben.**
- `_attending_users` enthält jetzt Mitglieder **und** Gäste, deutsch sortiert
  (`_de_name_key`, also Ä/Ö/Ü wie A/O/U). Gäste haben kein Konto und damit kein Bild –
  `avatar=None` lässt `_avatar_row_layer` den farbigen Initialen-Kreis zeichnen.
  Geprüft: Avatar-Anzahl == `tour_headcount`.
- Das Einstiegsbild zeichnet jetzt dieselbe Avatar-Zeile wie die Statistik-Folie
  (`_avatar_row_layer`), mit Namen darunter. Der Zähler „N dabei" ist nur noch der
  Notausgang, falls sich gar keine Zeile bauen lässt.
- `_avatar_row_layer` hat einen Parameter `max_shown` (Standard 8, wie bisher). Das
  Einstiegsbild nutzt 12. Bei mehr als 8 Gesichtern wird **umgebrochen**, statt sie zu
  verkleinern – sonst wären die Namen nicht mehr lesbar. Die Gesichtsgröße richtet sich
  nach höchstens 8 Kreisen pro Zeile, deshalb sieht die **Statistik-Folie unverändert
  aus** (nachgerechnet: 8 Leute → Gesicht 95 px, Zeilenhöhe 140 px, eine Zeile).

### Nachgestellt und geprüft
| Fall | Ergebnis |
|---|---|
| 1 Ort, 2 Datensätze (OSM + Handanlage) | vorher 2 Positionen → nachher **1** |
| 3 bewusst eingetragene Stopps | bleiben **3** |
| 2 echte Orte an der Strecke | bleiben **2** |
| gleicher Name, 300 m entfernt | bleibt **2** (eigener Ort) |
| Freitext-Einkehr ohne Gastro-Eintrag | erscheint (**1**), ohne km |
| keine Einkehr eingetragen | **0** (nichts erfunden) |
| 1 Mitglied + 2 Gäste | **3** Avatare mit Namen, kein „3 dabei" |
| 12 Anwesende | 12 Gesichter, **zwei Zeilen**, Namen lesbar |

Tests: `tests/test_build_ca.py` (14). Volle Suite **621 Tests grün** (vorher 607 + 14 neue).

---

## 1.5.0 – 2026-11-12 (Build bz) – Text in der Format-Auswahl läuft über die Begrenzungen
- **Meldung:** „Der Text läuft über die Begrenzungen." (Screenshot: Format-Auswahl beim
  Tour-Video, alle fünf Kacheln)

### Im Screenshot nachgemessen (500 px breit)
| | gemessen |
|---|---|
| Kachelbreite | **118 px**, innen nach Padding ~102 px |
| „Insta · TikTok · WhatsApp" | braucht **~143 px** |
| „Insta · Facebook 4:5" | braucht **~112 px** |
| „Facebook · Insta 1:1" | braucht **~112 px** |
| Container | 377 px (x 65..442), Kachelabstand 11 px |

### Ursache
`static/css/style.css` setzt global:

```css
.btn { white-space: nowrap; }
```

Die Regel stammt aus Build 11-06i und ist dort richtig – sie verhindert, dass „Anwenden"
mitten im Wort umbricht. Die Format-Kacheln tragen `btn` aber nur als **Optik**: Sie sind
`<div class="btn btn-outline-djo …">` mit zwei Textzeilen. Mit `nowrap` kann der Text
nirgends umbrechen und läuft in die Nachbarkachel. Im Bild deutlich zu sehen:
„Quadratisch" ragt in „Feed-Post", und „Insta · Facebook 4:5" überlappt mit
„Facebook · Insta 1:1".

### Behoben
**1. Umbruch nur hier.** `.format-btn` und alles darin darf umbrechen – das globale
Einzeilig-Gebot für echte Knöpfe bleibt unangetastet. Zusätzlich `overflow-wrap: anywhere`,
damit auch ein langes Wort wie „WhatsApp" getrennt wird statt herauszulaufen.

**2. Kacheln bleiben gleich hoch.** `height: 100%` auf Label und Kachel, damit eine Reihe
nicht „auf Lücke" steht, wenn eine Beschriftung zwei Zeilen braucht. Bewusst **ohne** eigenes
`display: flex`: Bootstrap-`.btn` ist bereits `inline-block` mit zentriertem Text, ein
Flex-Container würde die Zeilen anders verteilen als vorher.

**3. Unter 430 px zwei Spalten.** Nachgerechnet: Bei drei Spalten bleiben auf einem
360-px-Handy nur ~80 px Innenbreite – selbst umbrochene Wörter passen dort kaum. Mit zwei
Spalten sind die Kacheln 195 px breit und **alle** Beschriftungen einzeilig.

**4. Regeln sauber begrenzt.** Das `<style>` steht global im Dokument; ein `.row .col-4`
hätte auch andere Seiten getroffen. Alles hängt jetzt an `.format-wahl`.

### Getestet
`tests/test_build_bz.py` – 15 Tests: Umbruch erlaubt (auch für `small`), globales
Einzeilig-Gebot unverändert, kein veraltetes `word-break: break-word`, Regeln an
`.format-wahl` gebunden, gleiche Kachelhöhe, Media-Query für 2 Spalten, alle fünf Formate
und Beschriftungen unverändert. Nachgerechnet für 500/430/390/360 px: keine Überlappung mehr.
Volle Suite: **605 Tests, alle grün.**

---

## 1.5.0 – 2026-11-11 (Build by) – Tipp auf den Hinweis tat nichts
- **Meldung:** „Man klickt auf den Hinweis Bereich und nichts passiert, es bewegt sich nur ein
  bisschen nach oben." (Screenshot: Fahrt beendet, gelber Kasten mit „✓ Als Track übernehmen")

### Im Screenshot nachgemessen (1080×2340 = 360×780 CSS)
| Element | gemessen |
|---|---|
| Gelber Kasten | y 479..564 – **85 px** hoch |
| Grüner Knopf „✓ Als Track übernehmen" | bei y 564 **hart abgeschnitten** |
| Titel | endet mit **„sichern…"** – im Code steht „sichern" ohne Punkte |

Die drei Punkte sind die Signatur einer Textklemmung. In Build bo stand hier
`display: -webkit-box; -webkit-line-clamp: 2; overflow: hidden` – der Kasten durfte nur zwei
Zeilen hoch sein. Der Titel braucht bei 360 px schon zwei Zeilen, also war der Kasten voll und
die Knopfreihe fiel weg. Build bq hatte die Regel entfernt – die drei Punkte im Bild zeigen
aber, dass auf dem Server noch ein Stand davor lief.

### Und das „bewegt sich ein bisschen nach oben"
Der gelbe Kasten hatte **gar keinen Klick-Handler**. Getroffen wurde die Statuszeile darunter –
die ist auf `max-height: 3.1em` gekappt und klappt bei einem Tipp auf `12em` auf. Genau das
ist das kurze Nach-oben-Rucken. Der Satz darin war ebenfalls abgeschnitten („…Die Aufzeichnung
kannst du"), das Aufklappen hatte also einen Sinn – aber es sieht aus wie eine Schaltfläche,
die nicht funktioniert. Nachgemessen: Ein Tipp auf den Kasten löste **keine** Reaktion aus.

### Behoben
**1. Keine Klemmung mehr – mit Notaus.** Der Kasten trägt jetzt inline
`-webkit-line-clamp: unset !important` und `overflow-y: auto` mit `max-height`. Inline schlägt
jedes Stylesheet: Selbst wenn irgendwo noch ein altes Build mit der Klemmregel läuft, kann sie
nicht mehr durchschlagen. Wird der Platz knapp, scrollt der Inhalt – statt abgeschnitten zu
werden. (`display` bleibt bewusst außen vor: Ein `display: block !important` inline würde
`d-none` aushebeln und den Kasten dauerhaft zeigen.)

**2. Ein Tipp kann nie mehr wirkungslos sein.** Die ganze gelbe Fläche führt jetzt zur
Tourseite in den Abschnitt „Live-Aufzeichnung" – dort stehen Übernehmen, GPX-Download und
Löschen. Knöpfe, Links und das ⓘ machen weiter ihre eigene Sache. Die Fläche zeigt das auch
(cursor + Titel).

**3. Die Statuszeile zeigt bei Fahrtende den ganzen Satz** (`body.rec-hint-an` hebt die
Kappung auf) und führt bei einem Tipp ebenfalls zur Tourseite, statt nur aufzuklappen.
Während der Fahrt bleibt das Aufklappen wie gehabt.

### Getestet
`tests/test_build_by.py` – 13 Tests: keine echte Klemmregel mehr im Stylesheet, Notaus inline
vorhanden, `d-none` bleibt wirksam, Handler in beiden Zweigen (Vollbild/normal), Knöpfe nicht
geschluckt, kein doppelter Handler, Statuszeile bei Fahrtende offen und klickbar.
Nachgestellt im DOM: Tipp auf die Fläche → Tourseite, Tipp auf den grünen Knopf → eigene
Aktion, Tipp auf die Statuszeile bei Fahrtende → Tourseite, während der Fahrt → klappt auf.
Volle Suite: **590 Tests, alle grün.**

---

## 1.5.0 – 2026-11-11 (Build bx) – Hinweis „In Galerie sichern" war nicht zu sehen
- **Meldung:** „Habe ein Foto gemacht in der Live Karte, aber einen anschließenden Hinweis
  ‚In Galerie sichern' sehe ich nicht." (nach Build bw)

### Ursache – drei Fehler auf einmal, alle nachgemessen
Der Knopf aus Build bw war eingebaut, aber praktisch nicht erreichbar:

**1. Er war abgeschnitten.** Der Knopf stand mitten in `#live-status`. Diese Zeile ist auf
`max-height: 3.1em; overflow: hidden` gekappt. Auf 360 px Breite brauchen Satz + Knopf + Link
vier Zeilen – der Knopf saß in der dritten, und die war abgeschnitten. Ein Knopf, den niemand
sieht, ist kein Knopf.

**2. Sechs Sekunden später war er weg.** Der nächste Positions-Ping ruft
`setStatus('Du teilst deinen Standort seit …')` und überschreibt die Meldung. Beim Fahren kommt
alle 6 Sekunden ein Ping. Nachgemessen mit einer DOM-Nachbildung, die die echten Funktionen
ausführt: direkt nach dem Foto „Knopf DA", nach einem Ping „Knopf WEG". Auch der Satz „Foto
gespeichert" war damit fort.

**3. Auf iOS wurde er gar nicht erst gebaut.** Die Bedingung war `fotoId && navigator.canShare`.
`canShare()` **ohne Argumente** sagt nur, ob Teilen an sich möglich ist – nicht, ob Dateien
mitgehen. Auf iOS Safari ist `canShare` undefined, der Knopf fehlte dort also komplett.

### Behoben
**Eigener, dauerhafter Kasten `#foto-hinweis`** direkt über der Knopfleiste – dort, wo der
Daumen nach dem Foto ohnehin ist, an derselben Stelle wie `barHinweis`. Kein Positions-Ping
fasst ihn an; er bleibt, bis man ihn wegtippt, ein neues Foto macht oder 30 Minuten um sind.

- **Lage nachgemessen:** Der erste Entwurf saß bei `58 px + 8 px` – das ist *in* der Knopfleiste
  (58..116) und hätte „Fahren / Pause / Foto" verdeckt. (Rechnung für 360×800: Leiste
  684..742, Kasten 684..734.) Richtig ist `58 + 58 + 8`: Kasten 564..676, Leiste beginnt bei 684.
- **Über der Stromspar-Abdunklung** (`z-index 4100` gegen `#saver-dim` mit 4000). Wer mit
  Stromspar fährt und ein Foto macht, hat die Abdunklung offen – darunter wäre der Hinweis
  unsichtbar gewesen.
- **Knopf 44 px hoch** (übliche Mindestgröße für Touch-Ziele, im Fahren mit dem Daumen).
- **Prüfung mit einer echten Testdatei:** `_kannDateiTeilen()` legt ein `File` an und fragt
  `navigator.canShare({files: [datei]})`. Kann das Gerät es nicht, steht im Kasten ehrlich der
  Weg über die Tourseite (⬇) statt eines Knopfs, der nichts tut.
- **Dateiname aus dem Download** (`Content-Disposition`): Das Foto landet als
  `Fototour_2026-11-11_1817.jpg` in der Galerie, nicht als `foto_4711.jpg`.
- **Abbrechen ist kein Fehler:** Wer das Teilen-Menü wegtippt (`AbortError`/`NotAllowedError`),
  bekommt keine Warnung – der Hinweis bleibt einfach stehen.
- Die Meldung in der Statuszeile ist wieder kurz (nur „Foto gespeichert" + Link) und passt in
  die drei Zeilen.

### Getestet
`tests/test_build_bx.py` – 12 Tests. Darunter ein Test, der die echten Funktionen aus
`live.html` ausschneidet und in einem DOM ausführt: Hinweis erscheint, überlebt Positions-Ping
und Auto-Pause, übergibt die Datei mit lesbarem Namen, zeigt auf Geräten ohne Datei-Teilen den
Ersatzweg, schließt sich nach Erfolg und über ✕. Volle Suite: **577 Tests, alle grün.**

---

## 1.5.0 – 2026-11-11 (Build bw) – Foto aus der App landet nicht in der Handy-Galerie
- **Meldung:** „Habe ein Foto innerhalb der App gemacht, das erscheint auch auf der Tourkarte.
  Das Foto ist aber nicht in der Galerie des Handys zu finden. Dort hätte ich es auch gerne."

### Ursache – der Browser gibt die Aufnahme nie an die Galerie weiter
Das Foto entsteht über `<input type="file" accept="image/*" capture="environment">`:

```html
<input type="file" id="live-cam" accept="image/*" capture="environment">
```

Damit öffnet das Handy die Kamera und gibt die Aufnahme **an die Webseite** – der Weg endet dort.
Ein Browser kann nicht in die Galerie schreiben, dafür gibt es keine Schnittstelle. Im Download-
Ordner des Handys landete die Datei ebenfalls nicht, weil sie per `fetch` hochgeladen und nirgends
lokal abgelegt wird.

Zweiter Punkt: Der Server **verkleinerte jedes Foto und verwarf das Original**
(`_resize_photo_if_needed(max_px=1600, quality=85)`). Selbst wenn man an die Datei käme, wäre es
nicht das Foto, das das Handy gemacht hat. Gemessen: 3000×2000 (92 KB) → 1600×1066 (10 KB).
Und nicht einmal kleine Bilder blieben unangetastet – Pillow speichert **immer** neu:
ein 800×600-JPEG mit 8230 Bytes kam mit **3379 Bytes** zurück.

### Umgesetzt
**1. Das Original wird aufbewahrt.** Neue Spalte `TourPhoto.orig_filename` (Migration läuft beim
Start automatisch nach, bestehende Zeilen bleiben unverändert). Beim Upload wird das unveränderte
Handyfoto als `…_orig.<ext>` daneben gelegt, bevor verkleinert wird. Speicher: das Doppelte der
Web-Fassung – für eine Fahrrad-Gruppe unkritisch, und der einzige Weg zu einem echten Original.

**2. Download mit lesbarem Namen.** `/fotos/<id>/download` liefert das Original, sonst die
Web-Fassung (alte Fotos vor diesem Build). Der Dateiname ist sprechend, nicht der Hash:
`Fototour_2026-11-11_1817.jpg`.

**3. ⬇-Knopf an jedem Foto** auf der Tourseite – die Datei landet im Download-Ordner des Handys.

**4. „📥 In Galerie sichern“** direkt nach dem Foto in der Live-Karte. Der Knopf übergibt das
**Original vom Server** an das Teilen-Menü des Handys (`navigator.share({files})`), dort steht
„In Fotos sichern“ bzw. „In Galerie speichern“. Kein automatisches Aufpoppen – nur auf Tippen.
Kann das Gerät es nicht (z. B. Desktop-Firefox), sagt die App das ehrlich und verweist auf den
⬇-Knopf auf der Tourseite.

**5. Aufräumen.** Wird ein Foto gelöscht, geht das Original mit weg – sonst wären es Karteileichen
von mehreren MB pro Foto. Alle vier Löschstellen laufen jetzt über `_delete_photo_files()`.

### Gemessen (echter Upload über die Route, echte Dateien)
| | Quelle | Web-Fassung | Original / Download |
|---|---|---|---|
| großes Handyfoto 3000×2000 | 92 KB | 1600×1066, 10 KB | 92 KB, **byte-gleich** |
| kleines Bild 800×600 | 8230 B | 3379 B (Pillow, q85) | 8230 B, **byte-gleich** |

Download: HTTP 200, richtige Größe, Name `Fototour_2026-11-11_1817.jpg`.
Migration an einer DB ohne die Spalte geprüft: Spalte ergänzt, alte Zeilen unverändert.

### Tests
`tests/test_build_bw.py` – 15 Tests: Modell/Migration, Bildgrößen-Erkennung, die ganze Kette
Upload → DB → Download, Byte-Gleichheit des Originals, Rückfall auf die Web-Fassung bei alten
Fotos, Aufräumen beider Dateien, Vorhandensein der Knöpfe und des ehrlichen Hinweises.
Volle Suite: **565 Tests, alle grün.**

---

## 1.5.0 – 2026-11-11 (Build bv) – Nachgesendete Punkte gingen verloren (19,3 statt ~40 km)
- **Meldung:** nach Build bu: „Eigentlich war die Strecke heute ungefähr 40 km lang" – aufgezeichnet
  waren **19,3 km** bei 6:36 h. Dazu: „Größtenteils war der Stromsparmodus an und auch öfter
  Display aus."

### Ursache – der Zeitstempel fehlte beim Nachsenden
Der Client sichert jeden Punkt lokal (`gesichert`), damit das Display ausgehen darf. Beim
Nachsenden schickte er aber **keinen Zeitstempel** mit:

```js
body: {tour_id, lat, lng, accuracy, speed, heading, paused, resume, since}
```

Der Server setzte daraufhin die **Ankunftszeit** ein. Damit passierten drei Dinge gleichzeitig:

1. **Der 3-s-Filter warf fast alles weg.** Nachgesendete Punkte kommen im Rudel an – 200 Punkte
   innerhalb von 2 s. Nur der erste überlebte: gemessen **1 von 5**, bei 200 Punkten **1 von 200**.
2. **Die 90-km/h-Prüfung rechnete mit der falschen Zeit.** Ein Punkt von vor 3 Minuten wurde gegen
   „jetzt" geprüft: 5,5 km in 180 s = 110 km/h statt 5,5 km in 6 s = 3 300 km/h.
3. **Die Aufnahmezeiten waren verfälscht** – Zeitfenster, Fahrzeit und GPX-Zeitstempel.

Die fehlenden Punkte wurden auf der Karte mit **Geraden überbrückt**. Das Dreieck in Screenshot 18
waren also keine Kurven, sondern **fehlende Abschnitte**.

### Nachgestellt (echte HTTP-Route, 1500 Punkte, 40 km, zwei lange Aus-Fenster)
| | Punkte in der DB | Anteil |
|---|---|---|
| Build bu (Puffer 200, ohne `at`) | 800 von 1500 | **53,3 %** |
| Build bv (Puffer 1200, mit `at`) | **1500 von 1500** | **100 %** |

53,3 % entspricht fast genau den gemeldeten 19,3 von ~40 km (48 %).

### Behoben
1. **Aufnahmezeit wird mitgeschickt** (`at`, ms) – im Normalversand und beim Nachsenden. Der
   Server übernimmt sie, wenn sie plausibel ist (nicht aus der Zukunft, max. 2 min Vorlauf; nicht
   älter als 6 h). Alte Clients ohne `at` funktionieren unverändert.
2. **Nachsenden entkoppelt:** nur ein Lauf zur Zeit (`nachsendenLaeuft`), 60er-Blöcke, nach
   Aufnahmezeit sortiert. Vorher konnte es doppelt starten (Wächter + Sichtbarwerden) und
   schickte denselben Punkt zweimal.
3. **Puffer 200 → 1 200 Punkte** (2 h Sparmodus statt 20 min; ~72 KB localStorage).
4. **GPS-Aussetzer werden übersprungen** statt gespeichert: Fix mit > 120 km/h wird verworfen, die
   letzte Position bleibt erhalten (vorher blockierte der Aussetzer auch die nächste Sendung).
5. **8-Stunden-Grenze mit Vorwarnung:** 30 Minuten vorher ein deutlicher Hinweis, danach eine
   Erklärung mit Anleitung („Fahren" neu starten). Vorher stoppte die Aufzeichnung still.

### Gemessen
- Nachsenden von 200 Punkten (1 h Fahrt): vorher **1** gespeichert, jetzt **200** – Zeitfenster
  exakt 1 194 s (= 6 × 199), km-Anzeige 6,0 statt verfälscht.
- Aussetzer 200 m quer: wird in beiden Modi nicht mehr Teil der Spur und blockiert nicht mehr.
- JavaScript des Templates mit `node --check` geprüft.

### Tests
`tests/test_build_bv.py` (18 Tests): Aufnahmezeit in beiden Sendewegen, Plausibilitätsgrenzen,
Nachsende-Sperre und Sortierung, Puffergröße, Aussetzer-Filter (darf den Zustand **nicht**
verändern), 8-Stunden-Vorwarnung, und ein Syntax-Test des ganzen Template-JavaScripts.

## 1.5.0 – 2026-11-11 (Build bu) – Stromsparmodus zeichnete fast nur Geraden
- **Meldung:** „Das tracken im Stromsparmodus ist nicht brauchbar. Es sind fast nur Geraden
  sichtbar." (Bild 18: eine 6:36-h-Tour, 19,3 km – die Spur auf der Karte ist ein Dreieck mit
  schnurgeraden Kanten, kein Wegverlauf.)

### Ursache 1 – der Richtungs-Trigger war invertiert (Client)
Build 11-06o baute für den Stromsparmodus einen Richtungs-Trigger ein, der laut Kommentar
„Kurven sofort sichern" sollte (wie die Akku-Modi von Strava & Co.). Der Code tat das Gegenteil:

```js
if (turn < 25) return;        // bei Kursänderung UNTER 25° verwerfen
```

Damit flogen genau die Punkte **in den Kurven** raus, übrig blieben die **Geraden**. Dazu kam
die Reihenfolge: Der 20-s-Takt prüfte **zuerst** und warf den Punkt weg, bevor die Richtung
überhaupt gefragt wurde – der Trigger konnte nie etwas behalten, nur zusätzlich verwerfen.

### Ursache 2 – die Karten-Nutzlast dünnte blind aus (Server)
`LIVE_TRACK_PAGE_PTS = 400` und `pts[::step]` – gleichmäßig jeder n-te Punkt. Bei einer
4-h-Tour war das jeder 7.; die Verbindung zwischen zwei Punkten ist immer eine Gerade.

### Ursache 3 – derselbe Fehler im GPX-Pfad (nur der Form halber geprüft)
`_thin_points` (GPX-Routen) nutzt bereits Douglas-Peucker und war **nicht** betroffen – geprüft:
1 500 Punkte rein → 1 500 in der GPX-Datei → 1 500 auf der Tourseite.

### Behoben
| Stelle | vorher | nachher |
|---|---|---|
| `live.html` Richtungsregel | `if (turn < 25) return;` | Kursänderung ≥ 20° ⇒ **sofort senden** |
| `live.html` Takt (Sparmodus) | 20 s / Stand 45 s | 6 s / Stand 20 s, ab 6 m Bewegung |
| `live.html` Reihenfolge | Takt vor Richtung | erst Kurve, dann Takt |
| `LIVE_TRACK_PAGE_PTS` | 400 | 2 000 |
| Ausdünnen der Live-Spur | `pts[::step]` (blind) | Douglas-Peucker, Toleranz per Bisektion |

### Gemessen (echter Code aus dem Template, in Node gegen eine simulierte Runde)
Runde aus 400-m-Geraden und 90°-Bögen (r = 60 m), 18 km/h, GPS alle 3 s, 30 min = 601 Fixe:

| | gesendete Punkte | größte Lücke |
|---|---|---|
| Build bt (alt) | **36** von 601 | **329 m** |
| Build bu (neu) | **304** von 601 | **30 m** |
| ohne Stromsparmodus | 180 von 601 | 60 m |

Der Sparmodus ist damit **feiner** als der Normalmodus (6 s statt 10 s) – der Akku-Vorteil kommt
jetzt daher, dass das Display ausgehen darf, nicht mehr aus groben Punkten.

### Gemessen (Server, echte DB-Zeilen → was die Karte bekommt)
Abweichung der gezeichneten Spur von der tatsächlich gefahrenen Strecke:

| Tour | alt (400, blind) | neu (2 000, Douglas-Peucker) |
|---|---|---|
| 1 h | 301 Punkte, **7,4 m** daneben | 1 201 Punkte, **0,6 m** |
| 4 h | 370 Punkte, **541,3 m** daneben | 690 Punkte, **2,7 m** |

Bei 4 h wich die alte Spur also bis zu einem halben Kilometer ab – genau die gemeldeten Geraden.
Rechenzeit je Kartenaufruf: 48 ms (Bisektion mit Startwert 0,5 m statt 1 034 ms mit Start 0).

### Tests
`tests/test_build_bu.py` (11 Tests): Der Drossel-Block wird **aus dem Template gelesen** und in
Node gegen die simulierte Runde laufen gelassen – kein Nachbau. Dazu Formtreue von
`_thinned_track` (Gerade → 2 Punkte, Kurve bleibt auf der Kurve), die Punktgrenze und die
Meldung an den Nutzer. Der Test aus Build ag, der den **falschen** Code festhielt
(`if (turn < 25) return;`), ist umgeschrieben.

## 1.5.0 – 2026-11-09 (Build bt) – Desktop: Statuszeile verdeckte „Fahren" und „Pause"
- **Meldung:** „beim Desktop wird Fahren - Pause Knopf vom Hinweis überdeckt" (Bild 17:
  die grüne Zeile „Du teilst deinen Standort seit 22:05 Uhr …" lag über der Knopfleiste).

### Ursache
`#live-status` hatte auf dem Desktop `bottom: 8px`. Die Knopfleiste ist 58 px hoch und sitzt
bei `bottom: 0` – die Statuszeile lag also **genau darin**, mit `z-index: 1090` über der Leiste
(`z-index: 1000`). Build bm hatte beim Umbau nur den km-Chip und die Symbolspalte auf
`bottom: 66px` gehoben; die Statuszeile wurde dabei vergessen.

### Gemessen (Chromium, vorher → nachher)
| Breite | Status vorher | Status nachher | Leiste | Treffer auf „Pause" vorher → nachher |
|---|---|---|---|---|
| 1104×1070 | y 966..1011 | y 908..953 | 961..1019 | `live-status` → `btn-pause` |
| 1280×800 | y 696..741 | y 638..683 | 691..749 | `live-status` → `btn-pause` |
| 1440×900 | y 786..831 | y 728..773 | 781..839 | `live-status` → `btn-pause` |

`elementFromPoint` auf der Knopfmitte lieferte vorher `live-status` – die Knöpfe waren auf dem
Desktop **nicht antippbar**. Jetzt liegen Statuszeile (66..111), km-Chip (119..150) und
Sperr-Knopf (160..194) über der Leiste (0..58).

### Weitere geprüft
- **Kein Text-Abschneiden:** Lange Meldungen bleiben auf zwei Zeilen begrenzt und lassen sich
  antippen (`.open`, bis 12 em) – aufgeklappt wächst der Kasten **nach oben**, überlappt bei
  1104 und 1366 px weiterhin nichts
- **Vollbild:** Status y 959..1004, Pause 1020..1062 – ebenfalls frei
- **Schmale Desktops** 992/1024/1366 px: keine Überlappung, Treffer überall `btn-pause`
- Der zweite, widersprüchliche Desktop-Wert für den Sperr-Knopf (`bottom: 105px`) ist entfernt –
  er hätte die Pill in die Statuszeile geschoben
- 6 neue Tests in `tests/test_build_bt.py` (lesen die CSS-Werte, rechnen die Kette nach)

## 1.5.0 – 2026-11-09 (Build bs) – Audit 8: CSRF-Lücke geschlossen, Kommentar-Sperre nachgezogen
Achtes Komplett-Audit. Drei Befunde behoben, davon **einer mit Sicherheitswirkung**.

- **CSRF (Mittel, Sicherheit):** Es gab weder ein Token noch eine Herkunftsprüfung. Ein POST
  von einer fremden Seite wurde angenommen – gemessen: eine Teilnahme an einer Tour wurde
  ohne Zutun des Angreifers angelegt (`SameSite=Lax` schützt bei Top-Level-Formularen nicht).
  Jetzt weist `_csrf_herkunft()` POST/PUT/PATCH/DELETE mit fremdem `Origin`/`Referer` mit
  **403** ab. Der eigene Host ist erlaubt, `/api/` und die Anmeldung bleiben frei (Cron-Token,
  Login-Hilfsskripte). Fehlt beides (ältere Browser, curl, Cron), bleibt alles wie bisher –
  kein Formular musste angefasst werden.
- **Kommentar an fremder Tour löschbar (Niedrig, war seit Audit 7 offen):**
  `comment_delete` prüfte nur den Autor. Ein Mitglied konnte einen **eigenen** Kommentar
  löschen, dessen `tour_id` auf eine fremde Tour zeigt – Antwort 302 mit Umleitung auf
  `/touren/<fremde_id>` (dort 404). Jetzt: erst `_tour_or_404(tour_id)`, dann
  `comment.tour_id != tour_id → 404`. Es wird nichts geschrieben.
- **Hilfe widersprach dem Code (Niedrig, Doku):** Die Hilfe sagte beim 🔒-Knopf „auch im
  Vollbild"; Code (`guardWanted() → if (_fsAn()) return false`) und die gleiche Seite weiter
  oben sagen das Gegenteil. Der Text folgt jetzt dem Code: **im Vollbild gibt es kein 🔒,
  die Karte ist dort immer frei** (sonst beim Fahren nicht verschiebbar).

### Geprüft und in Ordnung (Auszug)
- Mandantentrennung: 8 Endpunkte gegen eine fremde Tour (GET und POST) → alle 404;
  kein fremder Titel in Start, Touren, Archiv, Karte, Rangliste, Mitglieder
- XSS: gespeicherte Payloads in Titel, Beschreibung, Treffpunkt → überall escaped
- Uploads: Endungs-Allowlist, Dateiname serverseitig (`token_hex`), kein Pfad-Traversal
  (8 Varianten), `.htaccess` sperrt Direktzugriff auf `gpx/photos/videos`
- Fuzzing: 1 656 Anfragen (GET/POST/Upload/JSON) → **kein 500er**
- Performance: 10–48 SQL je Seite, alle unter 13 ms, `EXPLAIN` durchweg `SEARCH … USING INDEX`
- Deploy-ZIPs: keine `.env`, keine Datenbank, keine Uploads, kein `__pycache__`
- **515 Tests** (vorher 500), 15 neue in `tests/test_build_bs.py`

## 1.5.0 – 2026-11-09 (Build br) – Stromspar-Balken rot statt gelb
- **Meldung:** „unten läuft ein gelber Balken" den man beim Fahren nicht so gut sehen,
  evtl. ist rot besser."

### Warum Gelb schlecht war
Gelb (`#ffc93c`) liegt auf den hellen Kartenkacheln fast auf demselben Farbton wie Straßen
und Wege — bei Sonne praktisch unsichtbar. Dazu war der Balken nur 4 px hoch.

### Jetzt
- **Rot in der Markenfarbe** `--djo-red` (`#C0392B`) — dieselbe Farbe wie „schwer" bei den
  Schwierigkeits-Badges. Rot liegt im Farbkreis am weitesten von Straßen-Gelb und Rasen-Grün
  entfernt und ist bei Tageslicht am auffälligsten.
- **6 statt 4 px hoch** — beim Fahren aus dem Augenwinkel erkennbar.
- **Weißer Rand oben** (1 px): grenzt den Balken auch über dunklen Flächen ab (Nachtmodus,
  schattierte Karte, dunkelblaue App-Navigation).

### Gemessen (Playwright, 461×934)
Berechnete Farbe `rgb(192, 57, 43)`, Höhe 6 px, weißer Rand vorhanden, Balken erscheint erst
in den letzten 10 Sekunden (Klasse `.rest-aktiv`). Keine Änderung an der 60-s-Frist.

- 497 Tests + **3 neue**: Balken ist rot (und nicht mehr gelb), ist 6 px hoch, hat den
  weißen Rand.

Geänderte Dateien: `static/css/style.css`, `app.py`, `CHANGELOG.md`, `tests/test_build_ad.py`,
`tests/test_build_ag.py`.

## 1.5.0 – 2026-11-09 (Build bq) – Gelber Hinweis im Vollbild wieder vollständig
- **Meldung:** „Der gelbe Hinweis ist abgeschnitten in der großen Karte."

### Ursache (selbst eingebaut)
Build bo setzte `-webkit-line-clamp: 2` auf `#rec-hint-fs`, damit der Kasten nicht auf die
senkrechte Symbolspalte läuft. Der Kasten enthält aber **Titel + drei Knöpfe + ⓘ-Zeile** —
gemessen bei 412×915 (deiner Gerätegröße): **77 px sichtbar von 183 px Inhalt**. Der grüne
Knopf „✓ Als Track übernehmen" war zur Hälfte weg, „⬇ GPX speichern" und „Später entscheiden"
ganz. Genau der Knopf, mit dem die Aufzeichnung gesichert wird.

### Jetzt
- **Keine Zeilenbegrenzung mehr** am gelben Kasten — er bekommt seine volle Höhe.
- Die Breite bleibt begrenzt (`max-width: calc(100% - 51px)`), damit er links der Symbolspalte
  bleibt. Der Abstand entsteht jetzt über die Breite statt über die Höhe.

### Gemessen (Vollbild, Hinweis offen)

| Fenster | Kasten | Inhalt sichtbar | Knöpfe |
|---|---|---|---|
| 412×915 | 578–763 (185 px) | 183 von 183 px | alle sichtbar |
| 461×934 | 619–782 (163 px) | 161 von 161 px | alle sichtbar |
| 390×844 | 468–692 (224 px) | vollständig | alle sichtbar |
| 360×740 | 364–588 (224 px) | 222 von 222 px | alle sichtbar |

Keine Überlappung mit Symbolspalte (13 px Abstand), Statuszeile oder km-Chip.

- 494 Tests + **3 neue**: keine Zeilenbegrenzung mehr, alle drei Knöpfe im HTML, Breite bleibt
  links der Spalte.

Geänderte Dateien: `templates/touren/live.html`, `app.py`, `CHANGELOG.md`,
`tests/test_build_ad.py`, `tests/test_build_ag.py`.

## 1.5.0 – 2026-11-09 (Build bp) – Stromspar: „dauerhaft hell" dunkelt nach 1 Minute selbst ab
- **Meldung:** „Im stromsparmodus soll der Screen nach einer gewissen Zeit automatisch wieder
  abdunkeln wenn er vorher durch zweimal tippen aktiviert wurde, falls man vergisst ihn
  auszuschalten. Was wäre eine gute bewährte Zeit?"

### Die Zeit: 60 Sekunden
- **Bewährter Standard ist 30 s** – iOS Auto-Sperre und Android Bildschirm-Timeout stehen
  ab Werk auf 30 Sekunden (iOS-Optionen: 30 s / 1 / 2 / 3 / 4 / 5 min; Android: 15 s bis
  30 min). 30 s sind beim Fahren aber zu kurz: eine Abfrage zu lesen, auf die Karte zu
  schauen, den Mitfahrer zu suchen – schon wäre es wieder dunkel.
- **Deshalb 60 s.** Lang genug für einen Blick, kurz genug, dass ein vergessener Bildschirm
  nicht minutenlang in der Sonne leuchtet. Und es ist derselbe Takt wie die vorhandene
  60-Sekunden-Nachprüfung des Wachhaltens – keine zweite, konkurrierende Zeit im Code.
- **Keine Überraschung:** In den letzten 10 Sekunden läuft unten am Fensterrand ein gelber
  Streifen ab. Ein Tipp auf die Fläche verlängert um volle 60 Sekunden.

### Jetzt
- **Nach 1 Minute dunkelt es von selbst ab**, ohne dass die Fahrt oder die Aufzeichnung
  endet – der Stromspar-Modus bleibt an, der Bildschirm darf wieder ausgehen.
- **Meldung danach:** „🌙 Nach 1 Minute wieder abgedunkelt."
- **Tippen verlängert** die Frist (vorher passierte im hellen Zustand nichts).
- **Sauber abgeräumt:** Timer und Streifen verschwinden beim Ausschalten des Sparmodus
  (✕), beim Zurückschalten per Doppeltipp und am Fahrtende.
- **Texte nennen die Frist:** „Hell für 1 Minute · tippen verlängert · zweimal tippen = sparen".

### Gemessen (Playwright, 461×934)
Sparmodus an → doppeltippen → hell: Timer gesetzt, Streifen vorhanden aber **noch nicht
sichtbar**. Frist künstlich auf 2,5 s verkürzt: nach 1,5 s **Streifen sichtbar**, nach
3,1 s **wieder dunkel**, Sparmodus weiter an, Streifen entfernt, Overlay dunkel.

- 488 Tests + **6 neue** für die Frist (Wert, Timer-Aufräumen, Rückfall, Verlängern,
  Streifen, Text).

Geänderte Dateien: `templates/touren/live.html`, `static/css/style.css`, `app.py`,
`CHANGELOG.md`, `tests/test_build_ad.py`, `tests/test_build_ag.py`.

## 1.5.0 – 2026-11-09 (Build bo) – Symbole auch im Vollbild senkrecht rechts
- **Meldung:** „Auch auf der großen Karte sollen die Symbole wie gehabt rechts untereinander
  dargestellt werden."

### Jetzt
- **Im Vollbild stehen die fünf Symbole wieder senkrecht untereinander** am rechten Rand –
  dieselbe Spalte wie im Normalbetrieb (5 × 35 + 4 × 5 = 195 px). Vorher lagen sie dort in
  einem 3×2-Raster (138 × 90 px) und wirkten wie ein Block statt wie eine Spalte.
- **Die Spalte steht über Chip und Statuszeile:** 113 (Chip) + 31 + 8 = **152**.
- **Der Zuschauer-Hinweis rückt nach rechts,** damit er nicht auf der Spalte liegt: rechts
  51 px Abstand (8 Rand + 35 Spalte + 8 Luft), höchstens zwei Zeilen.

### Gemessen (Vollbild, Playwright, Service Worker aus)
| Fenster | Spalte x | Spalte y | Überlappung |
|---|---|---|---|
| 461×934 | 418–453 | 587–782 | keine |
| 390×844 | 347–382 | 497–692 | keine |
| 360×740 | 317–352 | 393–588 | keine |
| 452×767 | 409–444 | 420–615 | keine |

Der weiße Hinweis hat in allen vier Größen **23 px** Luft zur Spalte. Im Normalbetrieb
(ohne Vollbild) ändert sich nichts.

- 488 Tests. Drei prüften das alte Raster (155/253) und wurden auf die Spalte umgestellt;
  sie schließen jetzt ausdrücklich aus, dass `grid-template-columns` zurückkommt.

Geänderte Dateien: `templates/touren/live.html`, `app.py`, `CHANGELOG.md`,
`tests/test_build_ag.py`, `tests/test_build_ay.py`.

## 1.5.0 – 2026-11-09 (Build bn) – Weißer Hinweis unten links am Kartenrand
- **Meldung:** „Der weiße Hinweis Bereich soll unten links am Rand der Karte erscheinen" (Bild 16).

### Jetzt
- **Der weiße Hinweis sitzt unten am Kartenrand:** 8 px über der Unterkante, 8 px vom linken
  Rand – auf derselben Linie wie Chip und Symbolspalte. Vorher stand er 89 px höher, mitten
  auf der Karte.
- **Pill und Chip rücken mit nach oben,** damit nichts übereinander liegt: von unten
  Hinweis 8–49 · „Zum Verschieben antippen" 57–91 · Zeit/km 99–130. Abstände 8 px.
- **Vollbild genauso, neu gestaffelt:** Leiste 0–56 · Hinweis 64–105 · Chip 113–144 ·
  Symbolspalte 155–245 · Zuschauer-Hinweis ab 253. Vorher lagen die Symbole (66–156) auf
  dem Hinweis (64–105).
- **Desktop:** Hinweis ebenfalls 8 px über der Kartenkante (vorher 147).

### Gemessen (Playwright, Service Worker aus)
461×934, 390×844, 360×740 und 1024×768: Hinweis jeweils **8 px** über dem Kartenende und
**8 px** vom linken Rand, keine Überlappung mit Chip, Pill oder Symbolen. Vollbild
461×934 und 390×844 ebenfalls ohne Überlappung.

- 488 Tests. 20 ältere prüften die Werte aus bm und wurden auf die neue Staffelung
  umgestellt (Hinweis 8, Pill 57, Chip 99; Vollbild 64/113/155/253).

Geänderte Dateien: `templates/touren/live.html`, `app.py`, `CHANGELOG.md`,
`tests/test_build_aa.py`, `tests/test_build_ad.py`, `tests/test_build_ag.py`,
`tests/test_build_ay.py`.

## 1.5.0 – 2026-11-09 (Build bm) – Seite passt ins Fenster, Bedienung am unteren Kartenrand
- **Meldung:** „immer noch nicht gut. immer noch zu hoch. Der Hinweis liegt so mittendrin."
- **Der Screenshot des Nutzers zeigte Build bj** (nachgerechnet: Chip 147 px und Schloss 186 px
  über der Kartenunterkante — das sind exakt die bj-Werte; bk/bl standen auf 98). Die letzten
  beiden Builds waren auf dem Gerät nie angekommen.

### Die eigentliche Ursache (gemessen)
Die Live-Seite war **höher als das Fenster**: bei 461×934 gemessen Dokument **1253 px** —
Karte 729 + „Unterwegs"-Kasten 118 + Fußzeile 69 + Seite-Padding 68 + untere App-Navigation 51.
Beim Scrollen wanderte die Karte nach oben; Chip, Hinweis und Symbole landeten mitten im Bild,
unten blieb ein leerer Kartenstreifen. Genau das zeigte der Screenshot (die Kartenoberkante war
abgeschnitten, die Kopfzeile „Live-Karte" fehlte).

### Jetzt
- **Die Seite passt ins Fenster:** Karte `max(300px, 100vh - 275px)`, Fußzeile auf der
  Live-Seite ausgeblendet, Seiten-Padding reduziert. Dokumenthöhe = Fensterhöhe → nichts
  scrollt mehr, die Lage bleibt.
- **Alles sitzt am unteren Kartenrand** (Kartenkoordinaten): Chip und Symbolspalte **8 px**,
  Verschiebe-Hinweis **47 px**, Statuszeile **89 px**.
- **Der Hinweis liegt nicht mehr mittendrin:** Bei 461×934 endet die Karte bei y 787, der
  Hinweis steht bei 706–740 — vorher (bj) lag er bei 499–536, also mitten im Bild.
- **Statuszeile hängt jetzt an der Karte** (`absolute` statt `fixed`): Vorher blieb sie beim
  Scrollen stehen und schob sich über den „Unterwegs"-Kasten — im Screenshot des Nutzers war
  das die grüne Zeile über der Kartenüberschrift.

### Damit kein alter Stand mehr angezeigt wird
- **Service Worker:** HTML-Seiten kamen aus dem Cache, wenn das Netz langsam war — nach einem
  Deploy sah man weiter die alte Seite. Jetzt Netz zuerst mit 4-s-Zeitlimit, Cache nur als
  Rückfall.
- **Selbst-Update:** Registriert sich ein neuer Service Worker, lädt die Seite einmal neu.
  So kann kein Build mehr „unsichtbar" bleiben.

### Drei Fehler, die beim Nachmessen auffielen
- **Die Knopfleiste lag über dem „Unterwegs"-Kasten.** Bei 461×934 deckte die feste Leiste
  (820–876) den Kasten (803–921) zu — sichtbar blieb nur ein 17-px-Streifen der blauen
  Überschrift, genau der Rest, der auf dem Screenshot über „Fahrt starten" stand.
  Jetzt ist die Karte 105 px kürzer (`100vh - 380px`): Karte endet bei 682, der Kasten liegt
  vollständig bei 698–816, die Leiste beginnt bei 820. Dokumenthöhe = Fensterhöhe.
- **Auf dem Desktop lagen Symbole und Leiste übereinander.** Die Regel für Chip und Symbole
  (`bottom: 66px`) stand im Stylesheet VOR der Basisregel (`bottom: 8px`) und wurde von ihr
  überschrieben — gleiche Spezifität, spätere Regel gewinnt. Gemessen: Symbole 498–693,
  Leiste 643–701. Die Regel steht jetzt nach der Basisregel: Symbole 440–635, Leiste 643–701.
- **Im Vollbild lagen Statuszeile und Symbole 9 px übereinander** (Statuszeile 147, Symbole
  bis 156). Die Statuszeile steht wieder auf 164, der Zuschauer-Hinweis auf 213.

### Gemessen
461×934 (Screenshot-Größe), 452×767, 390×844, 360×740 und 1024×768: keine Überlappung,
alle fünf Symbole treffbar, Chip/Hinweis/Symbole wandern mit der Karte. Im Vollbild
(461×934, 390×844, 360×740) ebenfalls keine Überlappung.

- 488 Tests. 17 ältere prüften die Werte aus bk/bl und wurden umgestellt.
  **Gegenprobe:** alte Anordnung zurück → Tests rot.

Geänderte Dateien: `templates/touren/live.html`, `templates/base.html`, `static/sw.js`,
`app.py`, `CHANGELOG.md`, `tests/test_build_ay.py`, `tests/test_build_ad.py`,
`tests/test_build_ag.py`, `tests/test_build_aa.py`.

## 1.5.0 – 2026-11-09 (Build bl) – Lücke geschlossen, Symbole zurück nach rechts
- **Meldung:** „Alles immer noch zu weit in der Mitte. **Großer Zwischenraum** zwischen
  ‚Zum verschieben antippen' und Zeit/km. Die Symbole waren schon gut vorher auf der rechten
  Seite, nur zu hoch."

### Ursache der Lücke (gemessen, nicht geschätzt)
Die Statuszeile wurde als **fester Posten zwischen Hinweis und Chip** mitgerechnet — 41 px
Höhe + 8 px Abstand. Sie steht während der Fahrt aber **gar nicht auf der Karte** (die Meldung
„Du teilst deinen Standort seit …" gehört zum „Unterwegs"-Kasten). Gemessen im Zustand
„Fahrt läuft" bei 452×767: Hinweis unten 161, Chip unten 122 → **62 px Leerraum**, davon
41 px unsichtbare Statuszeile.

### Jetzt
- **Statuszeile hängt an der Pill, nicht zwischen Pill und Chip** (203 statt 166). Fehlt sie,
  rücken Pill und Chip zusammen — der Abstand ist immer **8 px**.
- **Symbole wieder als Spalte rechts** (wie vorher), aber ganz unten und flacher:
  35 px statt 42 px, 5 px Abstand → **195 px** statt 234 px hoch. Gemessen 452×767:
  Spalte von y 450 bis 645, die Bildmitte (384) bleibt frei.
- **km/Zeit unten links** (98 in Kartenkoordinaten = 122 im Fenster, 8 px über der Leiste).
- Desktop: Chip/Symbole 66, Pill 105, Status 147. Vollbild: 66 / 105 / 147.

### Gemessen
452×767, 469×903 (Screenshot-Größe), 390×844, 360×740 — **je in beiden Zuständen**
(Zuschauer mit Meldung / Fahrt läuft ohne): keine Überlappung, alle fünf Symbole treffbar,
Lücke konstant 8 px, alles unterhalb der Bildmitte.

- 1 neuer Test („keine Lücke zwischen Hinweis und Chip"), 15 ältere auf die neuen Werte
  umgestellt. **Gegenprobe:** alte Anordnung zurück → 4 Tests rot. 487 gesamt.

Geänderte Dateien: `templates/touren/live.html`, `app.py`, `CHANGELOG.md`,
`tests/test_build_ay.py`, `tests/test_build_ad.py`, `tests/test_build_ag.py`,
`tests/test_build_aa.py`.

## 1.5.0 – 2026-11-09 (Build bk) – Symbole, Hinweis und km/Zeit ganz nach unten
- **Meldung:** „Symbole, Hinweis, Zeit/km befinden sich immer noch zu weit in der Mitte."
- **Nachgemessen am Screenshot (452 × 767):** Chip-Unterkante y = 534, Statuszeile erst bei
  y = 747 — dazwischen **213 px** leere Karte. Die Symbole begannen bei y = 287, also genau
  in der Bildmitte (384).

### Ursache
Nicht ein einzelner Wert, sondern die **Reihenfolge**. Unten sind zwei Balken fest vergeben
(Knopfleiste 56 px, Statuszeile 41 px = bis 114 px), also wurde alles darüber gestapelt:
Chip 147, Hinweis 186, Symbole als **234 px hohe Spalte** von 122 bis 356. Die Spalte allein
reichte damit bis in die Bildmitte — egal wie tief der Chip stand.

### Jetzt
- **Die fünf Symbole stehen in EINER Reihe** (36 px statt 42 px, 200 px breit) — Höhe
  **36 px statt 234 px**. Damit ist unten Platz.
- **Unterste Zeile (122 px):** links der km/Zeit-Chip, rechts die Symbolreihe.
- **Darüber:** Statuszeile (166) und Verschiebe-Hinweis (215).
- **km/Zeit ist das unterste der drei**, wie gewünscht („Zeit/km ist das unterste").
- Desktop: Chip und Symbole auf 66, Status 110, Hinweis 163. Vollbild: 66 / 110 / 205.
- **Gemessen** auf 452×767 (Screenshot-Größe), 460×972, 390×844, 360×740 und 1024×768:
  keine Überlappung, alle fünf Symbole treffbar, alles unterhalb der Bildmitte.
- **Scrollen** (452×767, 360×740): Chip, Hinweis und Symbole wandern **300 px** mit der
  Karte — die Statuszeile bleibt als Meldung am Fenster.
- 2 neue Tests („alles in der unteren Bildhälfte", „Symbolreihe flach"), 20 ältere prüften
  die Werte aus Build bj und wurden umgestellt. **Gegenprobe:** bj-Lage zurück → 5 Tests rot.

Geänderte Dateien: `templates/touren/live.html`, `app.py`, `CHANGELOG.md`,
`tests/test_build_ay.py`, `tests/test_build_ad.py`, `tests/test_build_ag.py`,
`tests/test_build_aa.py`.

## 1.5.0 – 2026-11-09 (Build bj) – km/Zeit nach unten, Symbole an die Karte
- **Meldung:** „zu weit oben. Zeit/km sollen im unteren Bereich positioniert werden."
- **Gemessen vorher:** Der Chip stand **206 px** (Handy) bzw. **166 px** (Desktop) über der
  Kartenunterkante — bei 676 px Kartenhöhe war das obere Drittel.

### Jetzt
- **km/Zeit sitzt unten:** 147 px über der Kartenunterkante (Desktop 137), direkt über der
  Statuszeile. Die Pill rückt dafür **darüber** (186 / Desktop 176) — die Reihenfolge ist
  jetzt gedreht: unten km/Zeit, darüber der Verschiebe-Hinweis.
- Nachgemessen auf 460×972, 390×844, 360×740 und 1024×768: keine Überlappung, Chip im
  unteren Bereich.

### Beim Messen gefunden: die Symbolspalte blieb am Fenster
`#live-tools` steckte **innerhalb** von `#live-bar` — und die ist auf dem Handy `fixed`.
Gemessen: beim Scrollen um 200 px verschob sich die Spalte um **0 px** und schwebte über dem
„Unterwegs"-Feld (im Screenshot über dem Kopfsymbol des Feldes zu sehen).

Jetzt ein eigenes Kind von `#live-wrap` (`absolute`): Verschiebung **200 px** wie die Karte,
auf allen vier Größen gemessen. Dabei fiel auf, dass sie mit `bottom: 66px` 8 px in die
Leiste ragte — sie steht jetzt bei 122 px, über der Leistenoberkante (114).

- 4 neue Tests. 8 ältere prüften die Werte aus Build bi und wurden umgestellt.
  **Gegenprobe:** alte Lage zurück → 5 Tests rot. 485 gesamt.

Geänderte Dateien: `templates/touren/live.html`, `app.py`, `CHANGELOG.md`,
`tests/test_build_ay.py`, `tests/test_build_ad.py`, `tests/test_build_ag.py`.

## 1.5.0 – 2026-11-09 (Build bi) – Kartenhinweise bleiben in der Karte
- **Meldung:** „Wenn ich scrolle, verschiebt sich die Karte, aber ‚Zum Verschieben antippen'
  bleibt unten. Die Zeitanzeige ist auch nicht optimal positioniert."
- **Gemessen** (460×972): Beim Scrollen um 200 px wanderte die Karte von oben 144 auf −56 —
  der Verschiebe-Hinweis blieb bei 774 stehen. Grund: `position: fixed` (am **Fenster**).
  Der km/Zeit-Chip hing an einer eigenen, fensterbezogenen Leiter (204 px) und riss dadurch
  von der Pill ab — in deinem Screenshot stand „5 min" deshalb oben am Kartenrand, der
  Hinweis unten.

### Jetzt (deine Wahl: beides wandert mit der Karte)
- Verschiebe-Hinweis und 🔒 hängen an **#live-wrap** (`absolute`), 164 px über der
  Kartenunterkante. Sie werden vom `overflow: hidden` der Karte beschnitten und können
  nicht über die Liste darunter rutschen.
- Der km/Zeit-Chip sitzt direkt darüber: 206 px = 164 + 34 (Pill) + 8. Gemessen exakt
  **8,00 px** Abstand.

**Nachgemessen auf 460×972, 390×844, 360×740:** Verschiebung beim Scrollen bei Karte und
Pill exakt **200 px** — beide wandern mit. Keine Überlappung mit Statuszeile, Leiste oder
Symbolspalte; Vollbild unverändert.

- 4 neue Tests. 5 ältere Tests prüften die alte Fensterlage und wurden auf den neuen Stand
  umgestellt. **Gegenprobe:** alte Lage zurück → 3 Tests rot. 481 gesamt.

Geänderte Dateien: `templates/touren/live.html`, `app.py`, `CHANGELOG.md`,
`tests/test_build_ay.py`, `tests/test_build_ad.py`, `tests/test_build_ag.py`.

## 1.5.0 – 2026-11-09 (Build bh) – Tour-Titel führt in die Details + Datum korrigiert
- **Wunsch:** „Wenn man auf den Titel klickt, soll man auch in die Details kommen."
- **Gemessen vorher** (`/touren`, 460×972): Der Titel war ein `<span class="fw-semibold">`
  **ohne Link** (`cursor: auto`) — ein Tipp änderte die URL nicht.
  **Nachher:** `a.tour-titel-link`, `cursor: pointer`, Klick führt auf `/touren/<id>`.
  Der Titel sieht aus wie vorher (keine Unterstreichung, gleiche Farbe).
- Verlinkt an **vier** Stellen: Karte mit Foto, Karte ohne Foto, Archiv-Karte, Übersicht der
  geplanten Touren.

### Datum korrigiert
Die Build-Kennung stand seit Build ax auf **2026-11-07**, obwohl die Commits vom **08.11.**
(ax–az) und **09.11.** (ba–bf) sind. Ursache: Ich hatte das Datum aus dem Sitzungs-Kontext
übernommen, statt die Uhr zu prüfen.

- `APP_BUILD` → **2026-11-09 bh** (Footer zeigt jetzt das richtige Datum).
- `CHANGELOG.md`: 12 Überschriften auf das echte Commit-Datum gesetzt
  (ax–az → 08.11., ba–bf → 09.11.). **Build `ao` bleibt auf 07.11.** — es gab im Oktober
  einen anderen Build mit demselben Kürzel (16.10., „Foto-Zoom ruhiger"), der nicht gemeint ist.
- Erstellungsdatum in den ZIPs kommt aus `APP_BUILD` und wandert automatisch mit.

- 3 neue Tests. **Gegenprobe:** Titel wieder als `<span>` → 2 Tests rot. 477 gesamt.

Geänderte Dateien: `templates/touren/list.html`, `templates/touren/geplant.html`, `app.py`,
`CHANGELOG.md`, `tests/test_build_ay.py`, `tests/test_build_ag.py`.

## 1.5.0 – 2026-11-09 (Build bf) – Erklärung hinter einem ⓘ
- **Wunsch:** Die lange Erklärung im Hinweis „Fahrt beendet" sollte nicht mehr offen dastehen,
  sondern hinter einem ⓘ, das erst auf Tippen aufklappt.
- **Gemessen vorher:** Der Hinweis war **328–367 px** hoch (460×972 / 390×844 / 360×740) und
  schob die Karte zusammen — bei 360 px blieben 572 px Karte.

### Was jetzt dasteht
Offen bleibt der Kern: *„Später heißt: nichts geht verloren – gespeichert bleibt sie 30 Tage,
danach wird sie gelöscht."* Darunter ein Knopf **ⓘ Wo finde ich sie wieder? ›**. Erst auf Tippen
erscheint der Weg (Tourseite → „Live-Aufzeichnung") samt Link **Zur Tourseite ›**.

**Gemessene Höhen (zugeklappt → aufgeklappt):**

| Bildschirm | vorher offen | jetzt zu | aufgeklappt |
|---|---|---|---|
| 460×972 normal | 328 | **298** | 383 |
| 390×844 normal | 328 | **357** | 461 |
| 360×740 normal | 367 | **418** | 541 |
| 460×972 Vollbild | 286 | **214** | 279 |
| 360×740 Vollbild | 286 | **224** | 348 |

*(Desktop 1024×768: 156 → 195 px.)* Im Vollbild ist die Fassung kürzer: Titel ohne „⏹", die
Zeile „nur 30 Tage" ist in den Aufklapp-Text gewandert — das sparte noch einmal rund 40 px.

### Beim Messen gefunden: die Symbolspalte lag auf dem Hinweis
Bei **360 px** Breite reichte der Hinweis bis x=348, die Symbolspalte steht bei 310–352.
Gemessen lag auf dem ⓘ also `btn-all` statt des Knopfes — die Symbole deckten den Text zu.
Die Karte selbst ist dort nur 336 px breit (Container-Padding), die Spalte hängt aber an der
fensterbreiten Leiste. Behoben über den rechten Rand des Hinweises (`margin-right: 48px`,
Text endet bei 300). Nachgemessen: ⓘ frei erreichbar, keine Überlappung auf 360/390/460/1024.

*Ein Versuch, stattdessen die Symbolspalte bei offenem Hinweis zweispaltig zu setzen, ist
verworfen: im Vollbild hat er die Überlappung erst erzeugt (138 px hoch, aber 90 px breit).*

- 6 neue Tests. **Gegenprobe:** Aufklapper aus → 1 Test rot; Breiten-Fix raus → 1 Test rot.
  474 gesamt.

Geänderte Dateien: `templates/touren/live.html`, `app.py`, `tests/test_build_ay.py`,
`tests/test_build_ag.py`, `CHANGELOG.md`.

## 1.5.0 – 2026-11-09 (Build be) – „Später" erklärt
- **Meldung:** „Man weiß gar nicht genau, was mit ‚Später' gemeint ist. Und wie man das, wie und
  wo aufruft."
- **Berechtigt.** Der Knopf hieß nur „Später" (gemessen: ohne `title`) und im Hinweis stand kein
  Wort darüber, dass die Aufzeichnung auf der Tourseite wartet. Den Abschnitt gibt es wirklich —
  gemessen auf der Tourseite: **„Live-Aufzeichnung"** mit „Als GPX-Track der Tour übernehmen",
  „⬇ GPX", „Meine Aufzeichnung löschen".

### Was jetzt dasteht
Unter den drei Knöpfen, in beiden Kopien (über der Karte und im Vollbild):

> **Später?** Nichts geht verloren: Die Aufzeichnung bleibt gespeichert und wartet auf der
> **Tourseite** im Abschnitt **„Live-Aufzeichnung"** — dort kannst du sie jederzeit übernehmen,
> als GPX herunterladen oder löschen. **Zur Tourseite ›**

- Der Knopf heißt jetzt **„Später entscheiden"** statt „Später" und hat einen `title`
  („Blendet diese Abfrage aus. Die Aufzeichnung bleibt gespeichert und wartet auf der Tourseite.").
- **Zur Tourseite ›** springt direkt in den Abschnitt (`#live-aufzeichnung`) und blendet die
  Abfrage dabei aus. Gemessen: landet auf `/touren/1#live-aufzeichnung`, der Abschnitt steht
  bei `top: 0` im Bild.
- Im Vollbild steht die Kurzfassung („Bleibt gespeichert — auf der Tourseite unter
  ‚Live-Aufzeichnung'"), weil die Karte der Platz ist.

Nachgemessen im Vollbild auf 460×972, 390×844 und 360×740: Hinweis und Link sichtbar und
klickbar, keine Überlappung (`ueber = {}`), passt jeweils ins Bild.

- 5 neue Tests. **Gegenprobe:** mit dem alten Zustand (nur „Später", ohne Erklärung)
  schlagen 3 Tests fehl. 468 gesamt.

Geänderte Dateien: `templates/touren/live.html`, `app.py`, `tests/test_build_ay.py`,
`tests/test_build_ag.py`, `CHANGELOG.md`.

## 1.5.0 – 2026-11-09 (Build bd) – Hinweis nicht mehr doppelt
- **Meldung:** „Die Abfrage 'Als Track übernehmen' erscheint doppelt in der normalen
  Kartenansicht in der Live Karte"
- **Ja, und das war ein Fehler aus Build ba.** `showRecHint()` nahm `d-none` von **beiden**
  Kopien. Die Kopie für das Vollbild liegt in `#live-wrap` und war außerhalb des Vollbilds
  ein normaler Block im Fluss — sie erschien unter der Karte ein zweites Mal.
  Am Bildschirm gemessen stand sie mit `un: -78` sogar **unter dem Fensterrand**.
- **Jetzt:** Sichtbar ist immer nur die zum Modus passende Kopie — draußen die über der Karte,
  im Vollbild die in der Karte. Die Kopie in der Karte ist außerhalb des Vollbilds per CSS
  ganz ausgeblendet (`display: none`).

### Zwei Folgefehler beim Umschalten, ebenfalls behoben
Beim Nachmessen der Übergänge fielen zwei Lücken auf, die es vorher auch schon gab:

1. Fahrt beenden, dann ins Vollbild: **keine** Kopie mehr sichtbar (der Hinweis war nur
   einmal gezeigt worden und hing am alten Modus).
2. Fahrt im Vollbild beenden, dann zurück: **keine** Kopie mehr sichtbar.

`toggleFs()` hängt die offene Rückfrage jetzt mit um (`recHintOffen`). Gemessen:

| Schritt | sichtbare „Als Track übernehmen"-Knöpfe |
|---|---|
| Normalbetrieb, Fahrt beendet | 1 (in `#rec-hint`) |
| ins Vollbild | 1 (in `#rec-hint-fs`) |
| zurück | 1 (in `#rec-hint`) |
| nach „Später" + Umschalten | 0, bleibt 0 |
| Fahrt im Vollbild beendet | 1 (in `#rec-hint-fs`) |

- 4 neue Tests. **Gegenprobe:** mit dem alten Zustand 2 Tests rot, mit der alten JS-Logik
  1 Fehler + 1 Fehlschlag. 463 gesamt.

Geänderte Dateien: `templates/touren/live.html`, `app.py`, `tests/test_build_ay.py`,
`tests/test_build_ag.py`, `CHANGELOG.md`.

## 1.5.0 – 2026-11-09 (Build bc) – km/Zeit im Vollbild nach unten
- **Wunsch:** „dann sollte die Zeit und km Anzeige auch mitwandern nach unten"
- **Berechtigt.** Der km-/Zeit-Chip hing im Vollbild noch an der Pill-Reihe: Seine Formel zählte
  Pill (34 px) und 🔒 (34 px) mit, obwohl beide im Vollbild gar nicht erscheinen. Gemessen stand
  er dadurch **155 px über** der Statuszeile (unten 188 statt 64).
- **Jetzt:** Chip direkt über der Statuszeile, 8 px Abstand. Gemessen bei 460×972:
  Statuszeile unten 64, Chip unten 113.

### Beim Nachmessen gefunden: der Hinweis lag auf dem Chip
`bottom: 128px` stand als **Inline-Style** am Hinweis. Ein Inline-Style schlägt jedes Stylesheet —
die Vollbild-Regel `bottom: 64px` konnte nie greifen. Sobald Fahrt-Ende-Hinweis **und** Chip
gleichzeitig da waren, lagen sie aufeinander (gemessene Überlappung `km/hint` bei 460×972,
390×844 und 360×740).

Behoben: Der Inline-Wert ist raus, die Lage kommt aus dem Stylesheet, und der Hinweis steht
**über** dem Chip. Der Stapel von unten nach oben:

```
Knopfleiste (0)  ·  Statuszeile (64)  ·  km/Zeit (113)  ·  Hinweis (157)
```

Nachgemessen auf drei Bildschirmgrößen: keine Überlappung mehr (`ueber = {}`).

- 4 neue Tests. **Gegenprobe:** mit der alten Formel und dem Inline-Style schlagen 3 Tests fehl.
  459 gesamt.

Geänderte Dateien: `templates/touren/live.html`, `app.py`, `tests/test_build_ay.py`,
`tests/test_build_ag.py`, `CHANGELOG.md`.

## 1.5.0 – 2026-11-09 (Build bb) – Vollbild: Knöpfe weiter nach unten
- **Wunsch:** „Könnte man die Symbole und Knöpfe bei der Vollkarte weiter nach unten bringen?"
- **Ja.** Im Vollbild liegt die Karte über der unteren App-Navigation. Gemessen: `bottom-nav`
  **nicht sichtbar**, `navUnten = 0`. Trotzdem hielten Knopfleiste, Statuszeile, Pill und 🔒
  die **58 px** für sie frei — unter der Leiste blieb ein leerer Streifen.

  Gemessen bei 460×900 im Vollbild:

  | | vorher | nachher |
  |---|---|---|
  | Knopfleiste (Abstand unten) | 58 px | **0 px** |
  | Statuszeile | 122 px | **64 px** |
  | Symbolspalte | 124 px | über der Statuszeile |

- **Was sich bewegt hat:** Im Vollbild rückt alles an den unteren Rand — die Knopfleiste direkt
  dorthin, die Statuszeile (Pausenmeldung, „Du schaust nur zu …") 64 px darüber, der
  Aufzeichnungs-Hinweis ebenfalls auf diese Kante. Pill und 🔒 folgen der Statuszeile.
  Die Symbolspalte steht direkt **über** der Statuszeile.
- **Beim Messen aufgefallen:** Mit „ganz nach unten" (8 px) stieß die 234 px hohe Symbolspalte
  an die Knopfleiste — gemessene Überlappung `tools/leiste = True`. Sie sitzt deshalb über der
  Statuszeile; danach ist keine Überlappung mehr messbar (`{}`).
- **Außerhalb des Vollbilds bleibt alles, wie es war** — dort liegt die App-Navigation unten,
  die 58 px sind also berechtigt.
- 5 neue Tests. **Gegenprobe:** ohne die Vollbild-Regeln schlagen 4 Tests fehl. 455 gesamt.

Geänderte Dateien: `templates/touren/live.html`, `app.py`, `tests/test_build_ay.py`,
`tests/test_build_ag.py`, `CHANGELOG.md`.

## 1.5.0 – 2026-11-09 (Build ba) – Hinweis fehlte im Vollbild
- **Meldung:** „Wenn in der Live Karte die große Kartendarstellung aktiv ist und die Fahrt beendet
  sieht man keinen Hinweis auf Track/GPX speichern."
- **Genau so war es.** Der Hinweis („⏹ Fahrt beendet – was passiert jetzt mit der Aufzeichnung?")
  stand **außerhalb** von `#live-wrap`. Im Vollbild ist `#live-wrap` aber `position: fixed;
  inset: 0` mit `z-index: 2000` — er deckte den Hinweis vollständig ab.

  Gemessen im Browser (Vollbild, Fahrt beendet):
  | | vorher | nachher |
  |---|---|---|
  | Hinweis im DOM | `display: block` | `display: block` |
  | was liegt darüber | **`live-map`** | Hinweis selbst |
  | „✓ Als Track übernehmen" sichtbar | **nein** | **ja** |
  | „⬇ GPX speichern" sichtbar | **nein** | **ja** |

- **Behoben:** Es gibt jetzt eine **zweite Kopie** des Hinweises **innerhalb** der Karte
  (`#rec-hint-fs`), fest über der Knopfleiste. Sichtbar ist immer nur eine:
  außerhalb des Vollbilds die normale, im Vollbild diese. „Später" räumt beide weg.
- **Beim Messen aufgefallen:** Mit `right: 8px` lag die Symbolspalte (🔒/🌗) auf dem dritten
  Knopf. Der Hinweis hat jetzt rechts 56 px Platz — alle drei Knöpfe sind frei.
- Im Vollbild entfällt das Scrollen zum Hinweis (`scrollIntoView` wäre sinnlos, die Karte deckt
  ohnehin alles ab).
- 5 neue Tests. **Gegenprobe:** ohne die Kopie schlagen 3 Tests fehl, mit ihr sind alle grün.
  450 gesamt.

Geänderte Dateien: `templates/touren/live.html`, `app.py`, `tests/test_build_ay.py`,
`tests/test_build_ag.py`, `CHANGELOG.md`.

## 1.5.0 – 2026-11-08 (Build az) – Nachtrag: „Ich hatte das als Admin gemacht"
- **Korrektur des Nutzers:** „Ich hatte das vorher als Admin gemacht, nicht als Mitglied."
  Damit war meine Erklärung aus Build ay nur die halbe Wahrheit. Ich habe den Admin-Weg in
  Build ax nachgestellt — und den Fehler dort gefunden:

  **Der Knopf, den ein Admin sah, hat nichts übernommen.** Er war ein reiner Link:

  ```html
  <a href="/touren/1#live-aufzeichnung">✓ Als GPX übernehmen</a>
  ```

  Ein Klick sprang nur auf die Tourseite. Die Strecke blieb weg; man musste dort ein
  **zweites Mal** „Als GPX-Track der Tour übernehmen" drücken. Wer nach dem ersten Klick
  nichts weiter tat, sah zu Recht keinen Track.

  In Build ax als Admin gemessen (45 Punkte, 1,9 km): nach dem Klick **0 Linien,
  `GPX_DATA = null`** — genau das Bild, das gemeldet wurde.

- **Behoben:** Es gibt jetzt **einen** Knopf für alle, die eine eigene Aufzeichnung haben –
  ein POST-Formular, das sofort übernimmt. Kein Seitenwechsel, kein zweiter Klick:
  „05 Als Track übernehmen". Danach landet man auf der Tourseite, die Strecke steht oben auf
  der Karte (gemessen: 2 Linien, 45 Punkte, Meldung „als GPX-Track übernommen: 1.9 km …").

- **Was aus Build ay bleibt:** Die Rechte-Änderung (Mitglieder dürfen ihre eigene Aufzeichnung
  übernehmen) und die Meldung statt der HTML-404 als `.gpx`. Beides war richtig, deckte den
  gemeldeten Fall aber nicht ab — als Admin kam man an eine andere Stelle.

- 3 neue Tests, die genau diesen Fehler festhalten (Formular statt Link, gleicher Knopf für
  Admin und Mitglied). **Gegenprobe:** mit dem alten Link-Knopf schlagen 4 Tests fehl,
  mit dem Fix sind alle grün. 445 gesamt.

Geänderte Dateien: `templates/touren/live.html`, `app.py`, `tests/test_build_ay.py`,
`tests/test_build_ag.py`, `CHANGELOG.md`.

## 1.5.0 – 2026-11-08 (Build ay) – „GPX speichern" ließ die Tour ohne Track
- **Meldung:** „Checke die Funktion ‚Als GPX speichern'. Irgendwie wird bei mir anschließend
  kein Track angezeigt."
- **Die Datei war in Ordnung — die Tour bekam sie nur nie.** Nachgefragt: Knopf auf der
  Live-Karte nach „Fahrt beenden", kurze Fahrt mit dem Handy. Genau da lag es:

  | Wer | Was passierte |
  |---|---|
  | Tourleitung | „✓ Als GPX übernehmen" → Track landet auf der Tour, Karte zeigt ihn |
  | **Mitglied** | nur „⬇ GPX speichern" → Datei aufs Handy, **Tour bleibt ohne Track** |

  `gpx_file` blieb `None`, `GPX_DATA` war `null`, die Karte hatte 0 Linien. Die Übernahme war
  hart auf `_can_manage_tour()` beschränkt — ein Mitglied kam nicht einmal an den Knopf.

- **Behoben:** Wer eine **eigene** Aufzeichnung hat, darf sie jetzt selbst als Track übernehmen.
  Auf der Live-Karte heißt der Knopf „✓ Als Track übernehmen" (ein Klick, kein Datei-Umweg),
  auf der Tourseite „Meine Aufzeichnung als Track übernehmen".
  Gemessen (Mitglied, 45 Punkte, 1,9 km): vorher 0 Linien → nachher **2 Linien, 45 Punkte,
  Zoom 14**, Kennzahlen 1,9 km und 0:10 h Fahrzeit.
- **Grenzen bleiben:** fremde Aufzeichnungen weiter nur für die Tourleitung (403), und einen
  **vorhandenen** Track darf ein Mitglied nicht ersetzen — dort kommt eine Meldung mit dem
  Hinweis, die Datei herunterzuladen.

### Zweiter Fehler, gleich mit behoben
Wer „GPX speichern" ohne brauchbare Aufzeichnung drückte, bekam **keine Fehlermeldung, sondern
eine Datei**: der Server antwortete mit der HTML-404-Seite, der Browser speicherte sie trotzdem
als `…_live_….gpx`. Diese Datei kann kein Programm lesen. Jetzt gibt es eine Meldung, die die
Ursache nennt — zu kurze Fahrt (unter 8 Punkte) oder ungenaues GPS (WLAN-Ortung, über 100 m).
- 11 neue Tests, 3 alte auf das neue Verhalten umgestellt (442 gesamt).

Geänderte Dateien: `app.py`, `templates/touren/live.html`, `templates/touren/detail.html`,
`tests/test_build_ay.py`, `tests/test_build_af.py`, `tests/test_build_ag.py`, `CHANGELOG.md`.

## 1.5.0 – 2026-11-08 (Build ax) – Hellere Hinweise, km + Fahrzeit unten links
- **Drei Wünsche auf einmal:** „die Meldungen ‚Zum verschieben tippen' sind mir zu dunkel,
  könnten irgendwie halbtransparent sein auf allen Karten. Die zurückgelegten Kilometer sollen
  auch lieber unten links angezeigt werden. Zusätzlich dazu auch noch die reine Fahrzeit ohne
  Pausen."

### 1. Hinweise halbtransparent
`rgba(20,30,60,.88)` → **`rgba(20,30,60,.54)`** plus `blur(3px)` und eine feine weiße Kante.
Die Karte scheint jetzt durch, die weiße Schrift bleibt kontrastreich. Gilt für **alle** Karten:

| Wo | Element |
|---|---|
| Live-Karte | „Zum Verschieben antippen", 🔒, km-/Zeit-Chip |
| Startseite, Tourseite, Karten-Seite, Gastro | „Karte zum Verschieben antippen" |
| Alle Karten | 🔒 unten links |

Im Browser auf allen vier Seiten gemessen: überall `rgba(20, 30, 60, 0.54)` + `blur(3px)`.

### 2. Kilometer nach unten links
Der Chip saß oben links unter dem Zoom, jetzt **unten links** — dort, wo auch Verschiebe-Hinweis
und Schloss sind, direkt darüber.

### 3. Reine Fahrzeit ohne Pausen
`addTrails()` verwarf die Zeitstempel der Spurpunkte; jetzt werden sie mitgeschrieben
(`trailPunkte`). Eine **Lücke von mehr als 2 Minuten** zwischen zwei Punkten gilt als Pause und
zählt nicht — gesendet wird alle 10–30 s, die Reihe reißt also nur, wenn man steht.

Gemessen im Browser: 20 Punkte im 20-s-Takt mit **einer 20-Minuten-Pause** dazwischen:

| | Wert |
|---|---|
| Gesamtspanne | 1580 s (26 min) |
| **angezeigte Fahrzeit** | **360 s (6 min)** ✅ |

Der Chip zeigt beides zusammen: **„1,7 km · 6 min"**. Unter 50 m und unter einer Minute bleibt
er weg („0,0 km · 3 s" beim Losfahren wäre nur Lärm). Uhr und Rad als Inline-SVG — Emojis
wurden auf Geräten ohne Emoji-Schrift zu leeren Kästchen.

- 8 neue Tests, 4 alte auf die neuen Werte umgestellt (431 gesamt).

Geänderte Dateien: `templates/touren/live.html`, `static/js/map-touch.js`, `app.py`,
`tests/test_build_ad.py`, `tests/test_build_ag.py`, `CHANGELOG.md`.

## 1.5.0 – 2026-11-08 (Build aw) – „Fahrt starten" tat nichts: Skript brach ab
- **Meldung:** „Der grüne Button ‚Fahrt starten' bleibt weiterhin grün nach Drücken. Es passiert
  nichts. Eine Meldung sehe ich auch nicht."
- **Es war diesmal kein Anzeigeproblem — das Skript brach ab.** Ursache ist ein Fehler, den
  **Build au** eingebaut hat (also meine eigene Änderung von vorhin):

  ```
  ReferenceError: Cannot access 'trailKm' before initialization
  ```

  `addTrails(TRAILS)` stand **vor** `const trailKm` / `const SVG_RAD`. `addTrails()` ruft
  `updateTrailKm()` auf, das beide Konstanten benutzt — bei `const` gilt die Temporal Dead
  Zone, der Zugriff wirft. Damit stand das **komplette** Skript: `toggleShare`, `startShare`,
  `setLiveGuard`, alle Klick-Handler wurden nie registriert. Deshalb blieb der Knopf grün,
  es kam keine Meldung, und der Stromspar-/Sperr-Knopf reagierte ebenfalls nicht.

  **Der Auslöser war eine vorhandene Aufzeichnung**: bei leerer Spur lief die Schleife in
  `addTrails()` nie, `updateTrailKm()` wurde nie erreicht — deshalb fiel es beim Testen mit
  frischer Datenbank nicht auf. Sobald Spurpunkte da waren (nach dem ersten Fahren oder wenn
  jemand anderes gefahren war), schlug es sofort zu.

- **Behoben:** Die km-Logik steht jetzt vor dem ersten `addTrails()`. Nachgemessen im Browser
  mit 10 echten Spurpunkten: **keine JS-Fehler**, Klick auf „Fahrt starten" → `sharing = true`,
  Knopf wird rot mit „⏹ Fahrt beenden", Statuszeile meldet „Du teilst deinen Standort seit
  10:26 Uhr". Zweiter Klick beendet die Fahrt.
- **Warum es durchgerutscht ist** (und was jetzt anders ist): mein Test rief `addTrails()` nur
  mit leerer Spur auf. Neu sind **4 Tests**, die genau diesen Fall abdecken:
  - `const`-Definitionen müssen **vor** `addTrails(TRAILS)` stehen (mit Kommentaren ausgefiltert)
  - die gerenderte Live-Seite **mit echten Spurpunkten** wird geprüft
  - Gegenprobe gemacht: mit absichtlich wieder eingebautem Fehler schlagen 2 Tests fehl,
  ohne ihn sind alle grün.
- 4 neue Tests (423 gesamt).

Geänderte Dateien: `templates/touren/live.html`, `app.py`, `tests/test_build_ad.py`,
`tests/test_live.py`, `tests/test_build_ag.py`, `CHANGELOG.md`.

## 1.5.0 – 2026-11-08 (Build av) – „Fahrt starten" sieht nicht mehr klickbar aus, wenn es gesperrt ist
- **Meldung:** „Jetzt kann ich bei Tour auf ‚Fahren' klicken, dann erscheint die Live Karte und
  dort ist der Button ‚Fahrt starten' weiter grün. Ein Draufklicken bringt keine Änderung.
  Irgendwo hakt es."
- **Es hakte nicht – der Knopf war absichtlich gesperrt, aber man sah es nicht.** Fahren ist nur
  vom Vortag bis einen Tag nach dem Tourtag erlaubt (Organisatoren jederzeit). Außerhalb dieses
  Fensters hatte der Knopf `disabled` — im Browser gemessen:

  | | gesperrt | aktiv |
  |---|---|---|
  | Hintergrund | **grün `rgb(25,135,84)`** | grün |
  | Deckkraft | 0,65 | 1,0 |
  | Cursor | **`pointer`** (Hand) | pointer |

  Nur 35 % Transparenz unterschieden ihn — auf dem Handy praktisch unsichtbar. Der erklärende
  Hinweis stand klein **über** der Karte, nicht am Knopf.
- **Jetzt:**
  - **Bernsteinfarben** `#D98E04` statt grün, mit **Schloss-Symbol** und dem Wort **„Fahren"**
    statt „Fahrt starten" — man sieht schon am Knopf, dass es nicht losgeht.
  - **`cursor: not-allowed`** statt Hand.
  - **Der Grund steht in der Statuszeile**, dort wo alle Live-Meldungen stehen:
    „🔒 Fahren ist ab dem Vortag der Tour möglich (Tourtag: 18.11.2026). Zuschauen geht jederzeit."
  - **Der alte Hinweisblock über der Karte ist weg** — er verdeckte beim Fahren genau den
    Bereich, den man anschaut.
- **Gegengeprüft, dass der erlaubte Knopf wirklich funktioniert:** Klick → `sharing = true`,
  Knopf wird rot mit „⏹ Fahrt beenden", Statuszeile meldet „Du teilst deinen Standort seit
  10:15 Uhr"; zweiter Klick beendet die Fahrt. Der gesperrte Knopf bleibt stumm, auch wenn man
  das `disabled` umgeht (`if (!CAN_SHARE) return;`).
- 7 neue Tests, 2 alte auf den neuen Knopf umgestellt (419 gesamt).

Geänderte Dateien: `templates/touren/live.html`, `app.py`, `tests/test_build_ad.py`,
`tests/test_build_ag.py`, `tests/test_live.py`, `CHANGELOG.md`.

2026-11-07 – Live-Karte zeigt die zurückgelegte Strecke
- **Frage:** „kann man die zurückgelegte Route auch schon in der Live Karte anzeigen lassen?"
- **Die Route war schon da:** Seit Build af zeichnet die Live-Karte die Spuren aller
  Teilnehmer (eigene Spur blau `#1E88E5`, jede weitere Person in einer eigenen Farbe) und
  wächst alle 15 s mit. Was fehlte: **wie viel** man geschafft hat. Die Kilometerzahl stand
  erst nach der Fahrt auf der Tourseite.
- **Neu:** Ein Chip auf der Karte, oben links unter dem Zoom – **„1,2 km gefahren"**.
  Er rechnet aus denselben Spurpunkten mit und aktualisiert sich bei jedem neuen Punkt.

  Gemessen im Browser: 10 Punkte → **1072 m** („1,2 km gefahren"); zwei weitere Punkte →
  **2156 m** („2,2 km"), ohne Neuladen.

- **Drei Details, die dabei wichtig waren:**
  - **Nicht in die Karte „Unterwegs":** Dort stand die Zahl zuerst – die Karte liegt auf dem
    Handy aber *unter* der Karte, man sähe sie beim Fahren also nie.
  - **Unter 50 m keine Zahl** – „0,0 km" beim Losfahren wäre nur Lärm.
  - **Inline-SVG statt 🚴:** im Testfeld erschien das Emoji als leeres Kästchen (fehlende
    Emoji-Schrift) – das SVG ist überall gleich.
- Im Stromsparmodus wird der Chip mit abgedunkelt (er gehört zur Karte), im hellen Zustand
  ist er sichtbar.
- 5 neue Tests (412 gesamt), `node --check` OK.

Geänderte Dateien: `templates/touren/live.html`, `app.py`, `tests/test_build_ad.py`,
`tests/test_build_ag.py`, `CHANGELOG.md`.

2026-11-07 – Der kurze Blick zeigt, wo man ist
- **Frage:** „Wenn man einmal tippt aus dem Stromspar kann man ja nichts bedienen, aber es
  sollte dann gezoomt werden auf einen selber um zu sehen wo man sich befindet, oder?"
  **Ja** – und genau das fehlte.
- **Vorher:** Ein Tipp im dunklen Sparmodus hellte den Bildschirm nur auf. Die Karte blieb
  stehen, wo sie war – nach dem Folgen-Abbruch oder nach dem Wegscrollen zeigte der kurze
  Blick also irgendwo ins Leere, statt die eine Frage zu beantworten, für die man aufhellt.
- **Jetzt:** Der kurze Blick holt die Karte auf die **eigene Position**, Zoom **mindestens 16**
  (dieselbe Stufe wie beim Folgen – Straßen und Wege lesbar).

  Gemessen im Browser (404 × 854):

  | | Zoom | Kartenmitte |
  |---|---|---|
  | vorher | 13 | 53.4661 / 9.7995 |
  | nach einem Tipp | **16** | **53.55 / 9.99** (eigene Position) |

- **Bewusst zurückhaltend, drei Bedingungen:**
  - nur beim **kurzen** Blick – nicht beim dauerhaften Hellschalten (dort will man die Karte
    bedienen, ein Sprung wäre störend),
  - nur wenn die **eigene Position bekannt** ist (sonst bleibt die Karte, wie sie ist),
  - nur wenn die Karte **wirklich woanders** steht – liegt der eigene Punkt schon im mittleren
    Bereich und der Zoom ist ausreichend, passiert nichts (kein Zappeln bei jedem Tipp).
- **Geprüft:** zweiter Blick bei bereits zentrierter Karte ändert nichts (`[16, 53.55]` →
  `[16, 53.55]`), dauerhaft hell lässt den Zoom bei 13, nach 4 s dunkelt es wieder ab.
- 5 neue Tests (407 gesamt), `node --check` OK.

Geänderte Dateien: `templates/touren/live.html`, `app.py`, `tests/test_build_ad.py`,
`tests/test_build_ag.py`, `CHANGELOG.md`.

2026-11-07 – Ein Schloss für alle Karten, unten statt oben rechts
- **Rückmeldung:** „Das Schloss sollte auch jetzt im unteren Bereich erscheinen und nicht weiter
  oben rechts sein. Die Darstellung des Schlosses sind momentan unterschiedlich Live-Karte und
  andere Karten. Das sollte einheitlich sein."
- **Zwei getrennte Umsetzungen, nebeneinander gewachsen** – das war der Kern des Problems:

  | | Live-Karte | andere Karten |
  |---|---|---|
  | Ecke | unten links | **oben rechts** |
  | Symbol | 🔒 (Emoji) | Icon-Font `bi-lock-fill` **vom CDN** |
  | Grund | dunkelblau | **schwarz** |
  | Form | Radius 20 px | **Radius 6 px, 32 × 32** |
  | Höhe | 30 px | 32 px |

- **Jetzt eine Darstellung, überall dieselbe:** unten links, **38 × 34 px**, Radius 20 px,
  Grund `rgba(20,30,60,.88)`, weisses Schloss als **Inline-SVG** (17 × 17).
  Im Browser auf allen fünf Karten nachgemessen: identische Werte.
- **Warum SVG statt Emoji und statt Icon-Font:** ein 🔒 sieht auf iOS, Android und Windows jedes
  Mal anders aus – und der Icon-Font kommt vom CDN, ist unterwegs ohne Netz also ein leerer
  Kasten. Das SVG ist auf jedem Gerät dasselbe und braucht kein Netz.
- **Kein Springen beim Umschalten:** Hinweis und Schloss tauschen sich an derselben Stelle aus
  (`left: 8px`, gleiche Unterkante, beide 34 px hoch) – gemessen: beide bei 9 px / 12 px.
- **Hinweis der übrigen Karten** sitzt jetzt ebenfalls unten **links** (vorher mittig): dort ist
  die einzige freie Ecke – oben links Zoom, oben rechts Kartenstil-Knopf, unten rechts die
  Quellenangabe. Damit deckt sich alles mit der Live-Karte.
- **Nebenbei behoben:** Der Kartenstil-Knopf wich immer nach links aus, sobald ein Schloss
  existierte – auch wenn es 600 px tiefer lag. Jetzt nur noch bei echter Überlappung.
- Desktop bleibt bewusst ohne Guard (Maus, keine Scroll-Falle) – unverändert.
- 6 neue Tests, 6 alte auf die einheitliche Darstellung umgestellt (402 gesamt).

Geänderte Dateien: `static/js/map-touch.js`, `templates/touren/live.html`, `app.py`,
`tests/test_build_ad.py`, `tests/test_build_ag.py`, `CHANGELOG.md`.

2026-11-07 – Hilfe sagt die richtige Ecke: unten links
- **Korrektur des Nutzers:** „Auf der Live Karte steht der Verschiebe-Hinweis unten links."
  Ich hatte in der letzten Antwort behauptet, er sitze oben links – **das war falsch.**
- **Nachgemessen** (404 × 854, Live-Karte): `#live-guard-pill` liegt bei **links 8 px,
  Unterkante 160 px über dem Fensterrand** – also unten links, 38 px über der Statuszeile.
  Das ist seit **Build an** die gewollte Lage („Der Sperrknopf soll lieber unten über dem
  grünen/orangen InfoBlock erscheinen"). An der Lage habe ich **nichts geändert**.
- **Falsch war nur der Text.** Die Hilfe sagte „Zum Verschieben **oben links**". Jetzt:
  „Unten links über dem Info-Block steht ‚Zum Verschieben antippen' – ein Tipp darauf gibt
  die Karte frei." (vorher stand dort doppelt „Zum Verschieben … Zum Verschieben antippen").
- Zwei Code-Kommentare in `live.html` behaupteten ebenfalls „oben links" – beide korrigiert
  und um den Stand ergänzt (seit Build an unten links). Warnung: Die Live-Karte und die
  übrigen Karten haben damit **zwei verschiedene Orte** für denselben Hinweis (Live: unten
  links über dem Info-Block · übrige: unten Mitte über der Quellenangabe) – gewollt, weil
  auf der Live-Karte unten die Bedienleiste sitzt.
- 3 neue Tests (396 gesamt): Hilfe sagt „unten links", Pill hängt an `left: 8px` + `bottom`,
  Kommentare behaupten nicht mehr „oben links".

Geänderte Dateien: `templates/hilfe.html`, `templates/touren/live.html`, `app.py`,
`tests/test_build_ad.py`, `tests/test_build_ag.py`, `CHANGELOG.md`.

2026-11-07 – Kartenhinweis sitzt unten, nicht mehr in der Kartenmitte
- **Rückmeldung:** „Bei den anderen Karten stört mich das ‚Karte zum Verschieben antippen' in der Mitte.
  Sollte vielleicht weiter unten liegen oder was meinst du?"
- **Zustimmung – und gemessen, wie störend es war:** Der Hinweis lag exakt mittig (`align-items: center`)
  und verdeckte die Kartenmitte, also genau die Stelle, auf die man beim Draufschauen zielt.
- **Geändert:** Hinweis **unten in der Mitte**, über der Quellenangabe. Das ist die einzige freie Ecke –
  oben links sitzt der Zoom, oben rechts der Kartenstil-Knopf, unten rechts die OSM-Quellenangabe.
- **Schrift passt sich der Kartenhöhe an**, weil die Karten sehr unterschiedlich hoch sind:

  | Karte | Höhe | Hinweis | Platz darunter |
  |---|---|---|---|
  | Startseite (Vorschau) | 100 px | 20 px, .72 rem | 28 px |
  | Tourenliste | 150/160 px | 25 px, .78 rem | 30 px |
  | Tourseite | 460 px | 28 px, .85 rem | 31 px |
  | Karten-Seite | 624 px | 28 px, .85 rem | 30 px |
  | Gastro | 360 px | 28 px, .85 rem | 30 px |

  Vorher war der Hinweis auf der 100-px-Vorschau **ein Drittel der Kartenhöhe**.
- **Geprüft:** auf allen fünf Karten kein Konflikt mit Zoom, Kartenstil-Knopf, 🔒 oder Quellenangabe;
  Antippen entsperrt weiterhin, 🔒 sperrt wieder; rechts bleiben 88 px frei für den Schloss-Knopf.
- 3 neue Tests (393 gesamt), `node --check` OK.

Geänderte Dateien: `static/js/map-touch.js`, `templates/hilfe.html`, `app.py`,
`tests/test_build_ad.py`, `tests/test_build_ag.py`, `CHANGELOG.md`.

2026-11-07 – Vollbild-Knopf zeigt keine ✕ mehr
- **Rückmeldung:** „Das X irritiert. Man denkt hier beendet man was komplett."
- **Geändert:** Im Vollbild ersetzte der Knopf sein Symbol durch ein großes **✕**. Jetzt ist es
  das übliche Gegenstück zum Auf-Symbol: **vier Pfeile nach innen** (⤡) – gleicher Platz,
  gleiche Größe (42 × 42), nur die Richtung zeigt, was der Knopf tut.
  - Auf-Symbol (Pfeile nach außen) = Vollbild öffnen
  - Pfeile nach innen = Vollbild verlassen
  - Titel und `aria-label` bleiben eindeutig: „Vollbild" / „Vollbild aus"
- Das ✕ gibt es weiterhin für den **Stromsparmodus** (oben rechts, dort heißt es wirklich
  „beenden") – im Vollbild war es aber doppeldeutig und ist dort verschwunden.
- Hilfe-Seite ergänzt: im Vollbild zeigen die Pfeile nach innen, ein ✕ gibt es dort bewusst nicht.
- 3 neue Tests, 2 alte auf das neue Symbolpaar umgestellt (390 gesamt); `node --check` OK.

Geänderte Dateien: `templates/touren/live.html`, `templates/hilfe.html`, `app.py`,
`tests/test_build_ad.py`, `tests/test_build_aa.py`, `tests/test_build_ag.py`, `CHANGELOG.md`.

## 1.5.0 – 2026-11-07 (Build ao) – Audit 7: zwei Fehler, ein Leck, toter Code
- **Komplett-Audit über 72 Commits seit Audit 6** (Build p, 04.11.) – vollständiger Bericht in
  `docs/AUDIT_BERICHT.md`. Ergebnis: **keine Sicherheitslücke**, aber vier echte Befunde.
- **B1 (Mittel, Bedienung) – Kartensperre nach dem Vollbild falsch.** `saverStufe()` schrieb den
  Frei-Zustand auch im Vollbild. Wer dort den Stromsparmodus beendete, fand die Karte beim
  Verlassen gesperrt vor, obwohl sie vorher frei war (gemessen: `drag` false statt true, Pill
  zurück). Jetzt fasst `saverStufe()` den Guard im Vollbild nicht mehr an.
- **B2 (Mittel, Ressourcen) – Kachel-Cache wuchs unbegrenzt.** Der Offline-Kachel-Cache ist
  bewusst von der Löschung bei Updates ausgenommen, wurde aber nie begrenzt: „Karte offline
  speichern" legt bis 500 Kacheln je Klick ab. Über Monate hunderte MB – irgendwann räumt der
  Browser alles auf, auch die offline gespeicherten Touren. Jetzt Obergrenze **1500 Kacheln**
  (FIFO, älteste zuerst), aufgeräumt bei jeder neuen Build-Version, nach dem Voraus-Cachen und
  gelegentlich beim Laden.
- **B3 (Niedrig, Performance) – fehlende Indizes.** `EXPLAIN QUERY PLAN` zeigte `SCAN tours`,
  `SCAN users`, `SCAN tour_videos`, obwohl nach `group_id`/`tour_id` bei jeder Anfrage gefiltert
  wird. Acht Indizes ergänzt (über das bestehende `CREATE INDEX IF NOT EXISTS`-Muster, greift
  also auch auf der laufenden Datenbank). Nachgemessen: `SCAN` → `SEARCH … USING INDEX`.
- **B5 (Niedrig, Wartbarkeit) – toter Code entfernt.** `saverTap()` (rund 40 Zeilen) lief seit
  Build ai nie mehr, dazu `const aufKarte`. Zwei Tests prüften den toten Code und hätten ihn
  festgehalten – sie zeigen jetzt auf die Stelle, die wirklich läuft.
- **B4 (Niedrig, Doku):** README beschrieb die Live-Karte auf dem Stand von Build p –
  Stromsparmodus, ehrliches „Bildschirm bleibt an" und die Sperre fehlten.
- **Nebenbei:** `.env.example` benennt jetzt die Folge eines nicht geänderten `SECRET_KEY`
  (die ersten 20 Zeichen sind der Cron-Token).
- **Geprüft und ohne Befund:** Mandantentrennung (8 Endpunkte gegen eine fremde Tour → 404/403,
  auch die Listen), XSS mit gespeicherten Payloads in Titel/Treffpunkt/Beschreibung, Uploads
  (Magic Bytes, serverseitige Dateinamen), Login-Links, Cron-Token (`compare_digest`),
  Deploy-ZIPs (keine `.env`/DB/Backups), 20 Fuzzing-Fälle (**kein 500er**), SQL-Zähler flach
  (9–29 je Seite), `node --check` über alle 36 Inline-Skript-Blöcke.

Geänderte Dateien: `templates/touren/live.html`, `static/sw.js`, `app.py`, `README.md`,
`.env.example`, `docs/AUDIT_BERICHT.md`, `tests/test_build_ad.py`, `tests/test_build_ag.py`,
`CHANGELOG.md`.

2026-11-07 – Kein Sperren im Vollbild, Sperrknopf über dem Info-Block
- **Rückmeldung:** „1. Beim Vollbild muss die Sperre nicht sein. 2. Der Sperrknopf soll lieber unten über dem grünen/orangen InfoBlock erscheinen."
- **(1) Vollbild:** `guardWanted()` gibt dort jetzt immer `false` zurück, der 🔒-Knopf wird gar nicht erst eingeblendet. Eine vor dem Vollbild gesetzte Sperre wird gemerkt und beim Verlassen wiederhergestellt; nach dem Vollbild startet die Karte frei.
- **(2) Lage:** Verschiebe-Hinweis und Sperrknopf sitzen nicht mehr oben links unter dem Zoom, sondern **unten direkt über dem Status-Chip**. Gemessen: Info-Block y 702–732, Knopf jetzt y 664–694 – also exakt 8 px darüber, links bündig.
  - Mobil hängt der Knopf am Fenster (wie der Info-Block): `bottom: calc(58px + 64px + 30px + 8px)`.
  - Desktop liegt der Info-Block in der Karte (`bottom: 84px`), der Knopf bei `bottom: 122px`.
  - Beide sind 30 px hoch, damit beim Umschalten zwischen Pill und 🔒 nichts springt.
- **Im Browser belegt** (404 × 854, echte Touch-Eingaben):

  | Prüfung | Ergebnis |
  |---|---|
  | 🔒 über dem grünen Info-Block | ja, Abstand exakt 8 px ✅ |
  | Pill über dem orangen Info-Block | ja ✅ |
  | Vollbild: kein 🔒, keine Pill | ja ✅ |
  | Vollbild: Karte frei | ja ✅ |
  | Vollbild aus: 🔒 wieder da, Sperren wirkt | ja ✅ |

- 3 neue Tests, 3 alte an die neue Lage angepasst, 381 gesamt; py_compile und JS-Syntax OK.

Geänderte Dateien: `templates/touren/live.html`, `templates/hilfe.html`, `app.py`, `tests/test_build_ad.py`,
`tests/test_build_ag.py`, `CHANGELOG.md`.

2026-11-07 – Live-Karte lässt sich immer sperren, dann scrollt die Seite
- **Rückmeldung:** „Bei der Live Karte kann man nicht so richtig scrollen, da man die Karte nicht sperren kann."
- **Nachgemessen** (acht Zustände, echter Ein-Finger-Wisch über die Karte):

  | Zustand | 🔒 sichtbar | Scrollweite |
  |---|---|---|
  | ohne Fahrt | ja | 338 px ✅ |
  | freigeschaltet | ja | 0 px (Karte frei) |
  | **Fahrt läuft** | **nein** ❌ | 0 px |
  | **Folgen an** | **nein** ❌ | 0 px |
  | **Vollbild** | **nein** ❌ | 0 px |
  | Sparmodus hell | ja | 0 px (Karte frei) |

- **Ursache:** Das 🔒 wurde nur angelegt, wenn `!sharing && !following && !_fsAn()` – also genau **nicht** während Fahrt, Folgen oder Vollbild. Wer dann scrollen wollte, fand keinen Sperr-Knopf, und die Karte fraß jedes Wischen.
- **Behoben:**
  - Neue eigene Sperre `guardLocked`, die jeden anderen Zustand schlägt. Fahrt, Folgen und Vollbild bestimmen nur noch, wie die Karte **startet** – nicht, ob man sie sperren darf.
  - Der 🔒-Knopf ist **immer** da, sobald die Karte frei ist.
  - Beim Sperren springt die Karte zurück auf den Ausschnitt, mit dem sie aufgebaut wurde – vorher blieb sie irgendwo verschoben stehen.
- **Im Browser belegt** (echte Touch-Eingaben):

  | Prüfung | Ergebnis |
  |---|---|
  | Fahrt läuft: 🔒 sichtbar | ja ✅ |
  | Fahrt läuft: nach 🔒 gesperrt, Seite scrollt | ja ✅ |
  | Folgen: 🔒 sichtbar, sperrbar, Seite scrollt | ja ✅ |
  | Normalfall: gesperrt → frei → gesperrt | ja ✅ |
  | Karte zurücksetzen beim Sperren | Mittelpunkt und Zoom wieder wie beim Aufbau ✅ |

- 4 neue Tests, 2 alte angepasst (die prüften die entfernte Einschränkung), 378 gesamt; py_compile und JS-Syntax OK.

Geänderte Dateien: `templates/touren/live.html`, `templates/hilfe.html`, `app.py`, `tests/test_build_ad.py`,
`tests/test_build_ag.py`, `CHANGELOG.md`.

2026-11-07 – Im Stromsparmodus zoomt nur die Karte, nicht der Bildschirm
- **Rückmeldung:** „Im Stromsparmodus zoomt der ganze Screen und nicht nur die Karte."
- **Nachgemessen** (echte Zwei-Finger-Touch-Events über CDP):

  | Zustand | `visualViewport.scale` | Kartenzoom |
  |---|---|---|
  | ohne Sparmodus | 1.0 | 12 → 14 ✅ |
  | Sparmodus, dunkel | **1 → 1.12** ❌ | 12 (steht) |
  | Sparmodus, hell | 1.0 | 12 → 14 ✅ |

- **Ursache:** Das Abdunklungs-Overlay hatte `touch-action: auto`. Leaflets `touch-action: none` liegt auf der Kartenfläche – die verdeckt das Overlay im dunklen Zustand, also zoomte der Browser die **Seite**.
- **Behoben:**
  - `#saver-dim` sperrt den Seiten-Zoom (`touch-action: none`). `manipulation` allein reicht **nicht** – getestet, die Seite zoomte weiter (1 → 1.14).
  - Neu `saverPinch`: Das Script misst den Fingerabstand und setzt den **Kartenzoom** selbst (Leaflet-Logik: doppelter Abstand = eine Stufe), zwei Finger verschieben die Karte mit. `passive: false`, damit `preventDefault` greift.
- **Im Browser belegt** (mit und ohne Vollbild, je 2 Durchläufe):

  | Prüfung | Ergebnis |
  |---|---|
  | Seitenskalierung beim Pinch | bleibt **1.0** ✅ |
  | Karte zoomt auf | 13 → 15 ✅ |
  | Karte zoomt zu | 15 → 13 ✅ |
  | Pinch im hellen Zustand | Karte zoomt, bleibt hell ✅ |
  | Sparmodus bleibt an, Stufe unverändert | ja ✅ |
  | Doppeltipp schaltet weiter ohne Zoom | ja, 0 Zoom-Ereignisse ✅ |
  | Einzeltipp | 4 s hell, kein Seiten-Zoom ✅ |
  | Drei-Finger-Wisch | Seite scrollt/zoomt nicht ✅ |
  | Pinch direkt nach einem Tipp | kein falscher Doppeltipp ✅ |

- 3 neue Tests (374 gesamt), py_compile und JS-Syntax OK.

Geänderte Dateien: `static/css/style.css`, `templates/touren/live.html`, `templates/hilfe.html`, `app.py`,
`tests/test_build_ad.py`, `tests/test_build_ag.py`, `CHANGELOG.md`.

2026-11-07 – Zweimal tippen zoomt die Karte nicht mehr
- **Rückmeldung:** „Blöd ist noch, dass die Karte gezoomt wird wenn man zweimal tippt und in Stromsparen geht."
- **Nachgemessen und reproduziert:** `zoom 15 → 16` beim Zurückschalten von hell auf dunkel. Im hellen Zustand ist die Karte bedienbar, also erreicht der Doppeltipp auch Leaflet – und Leaflet zoomt bei jedem `dblclick` eine Stufe hinein.
- **Behoben:** Solange der Sparmodus läuft, ist der **Doppeltipp-Zoom der Karte aus** (`map.doubleClickZoom`). Er wird beim Beenden des Sparmodus wieder eingeschaltet. Zoomen per **+ / −**, per **zwei Fingern** und per Mausrad bleibt unberührt.
- **Zweiter Fehler dabei gefunden und behoben:** Derselbe Doppeltipp schaltete zusätzlich das **Wachhalten** um. Wer nur zurück in den Stromsparmodus wollte, bekam ungefragt „Bildschirm an". Im Sparmodus gehört der Doppeltipp jetzt allein der Spar-Stufe; der **🔆-Knopf** ist für das Wachhalten zuständig.
- **Im Browser belegt** (Chromium, Smartphone-Profil, echte Touch-Tipps, **mit und ohne Vollbild**, je 3 Runden):

  | Prüfung | Ergebnis |
  |---|---|
  | Doppeltipp-Zoom im Sparmodus | aus ✅ |
  | 3× hin und zurück | hell/dunkel korrekt ✅ |
  | Zoom dabei | bleibt konstant (13), **0 Zoom-Ereignisse** ✅ |
  | Wachhalten beim Doppeltipp | bleibt unberührt ✅ |
  | Zoom-Knopf im hellen Zustand | funktioniert (13 → 14) ✅ |
  | Verschieben | bleibt hell ✅ |
  | Einzeltipp | kurz hell, nach 4,3 s dunkel ✅ |
  | Sparmodus beendet | Doppeltipp-Zoom wieder an ✅ |
  | Doppeltipp ohne Sparmodus | zoomt weiterhin (14 → 15) ✅ |

- 4 neue Tests (371 gesamt), py_compile und JS-Syntax OK.

Geänderte Dateien: `templates/touren/live.html`, `templates/hilfe.html`, `app.py`, `tests/test_build_ad.py`,
`tests/test_build_ag.py`, `CHANGELOG.md`.

2026-11-07 – Grüne Selbsttest-Boxen entfernt
- **Rückmeldung:** „Deine grünen Boxen mit test hinweisen können entfernt werden?"
- **Entfernt** (die Erfolgsmeldungen über den Hauptknöpfen):
  - „✅ Bildschirm bleibt an – vom Gerät bestätigt (40 s ohne Unterbrechung)"
  - „🔆 Eingerichtet (Browser-Freigabe / Video-Ersatz). Ob der Bildschirm wirklich anbleibt, zeigt sich in den nächsten 40 Sekunden – ich melde mich."
  - „🔆 Eingerichtet. Ob der Bildschirm anbleibt, zeigt sich in den nächsten 40 Sekunden." (Doppeltipp auf die Karte)
- **Geblieben ist der Nachweis selbst** – nur ohne Kasten:
  - Der Selbsttest läuft weiter: Erst nach 40 s ohne Unterbrechung gilt „bleibt an" als belegt; eine Lücke über 20 s widerlegt es sofort.
  - Der Stand steckt jetzt **im Knopf**: farbig, sobald es hält, mit `title`/`aria-label` „vom Gerät bestätigt" bzw. „noch nicht bestätigt".
- **Warnungen bleiben** (so gewünscht): „⚠️ Geht auf diesem Gerät nicht", „⚠️ Bildschirm wachhalten greift hier nicht", „⚠️ Der Bildschirm ging trotz ‚an' aus".
- „🔆 wird eingeschaltet …" (die halbe Sekunde bis zur Antwort) und „🌙 Bildschirm darf wieder ausgehen." bleiben – das sind keine Testergebnisse.
- **Im Browser belegt** (Chromium, Freigabe erteilt): nach 47 s `wachBeweis = {ok: true, geprueft: 40}`, Knopf „vom Gerät bestätigt", **keine sichtbare Box** im DOM. Ohne Freigabe: nur die rote Warnung, kein grüner Kasten.
- Hilfe-Seite an die neue Rückmeldung angepasst; 1 Test neu, 4 angepasst (367 gesamt).

Geänderte Dateien: `templates/touren/live.html`, `templates/hilfe.html`, `app.py`, `tests/test_build_ad.py`,
`tests/test_build_ag.py`, `CHANGELOG.md`.

2026-11-07 – Zweimal tippen funktioniert jetzt auch bei großgestellter Karte
- **Rückmeldung:** „Wenn die Karte auf groß gestellt ist, funktioniert zweimal tippen nicht mehr."
- **Der eigentliche Fehler hatte nichts mit dem Vollbild zu tun** – dort ist er nur aufgefallen, weil man die Karte dann wirklich bedient. Zwei Ursachen, beide von mir:
  1. **Seit Build ah hat das Overlay im hellen Zustand `pointer-events: none`** (damit die Karte bedienbar ist). Damit bekam der Tipp-Erkenner, der am Overlay hing, **keinen einzigen Tipp** mehr – „zweimal tippen" war tot.
  2. **Ein pauschales „es wurde bewegt"-Flag** blockierte den Doppeltipp zusätzlich: Jede Mausbewegung und jedes Finger-Wackeln setzte es.
- **Behoben:**
  - Die Tipp-Erkennung sitzt jetzt **am Dokument** statt am Overlay – sie zählt Tipps auf der Karte, auf Knöpfen und auf der Leiste gleichermaßen.
  - Das Bewegungs-Flag ist ersetzt durch einen **Vergleich des Kartenausschnitts** (`Zoom@Mittelpunkt`). Nur wenn sich die Karte zwischen den beiden Tipps **nicht** verändert hat, wird umgeschaltet – Zoomen und Verschieben lösen also nichts aus.
  - Echte Bedienelemente (Links, Knöpfe, Leaflet-Steuerung, Marker, Strecke) setzen die Messung zurück und zählen nie als Tipp.
  - Im hellen Zustand gibt es keinen Hinweis-Streifen mehr, der etwas verdecken könnte; der Mond-Knopf bleibt zum Abschalten erreichbar.
- **Im Browser belegt** (Chromium, Smartphone-Profil, **mit und ohne Vollbild** – beide Läufe identisch):
  - dunkel → 2× tippen → hell ✅
  - 2× **zoomen** → bleibt hell (Zoom 12 → 13) ✅
  - 2× **verschieben** → bleibt hell ✅
  - Knopf „Alle" → bleibt hell ✅
  - 2× tippen → zurück auf dunkel ✅
  - 1× tippen → kurz hell, nach 4,2 s wieder dunkel ✅
- 4 neue Tests (366 gesamt), py_compile und JS-Syntax OK.

Geänderte Dateien: `templates/touren/live.html`, `static/css/style.css`, `templates/hilfe.html`, `app.py`,
`templates/base.html`, `tests/test_build_ad.py`, `tests/test_build_ag.py`, `CHANGELOG.md`.

2026-11-07 – Im hellen Stromspar-Zustand ist die Karte wieder bedienbar
- **Rückmeldung:** „man kann nur schauen und nicht bedienen oder zoomen nach einem Doppelklick aus dem Stromsparen?"
- **Ursache (mein Fehler in Build af):** `background: transparent` machte das Overlay im dauerhaft hellen Zustand nur **unsichtbar**. Es lag weiterhin über der ganzen Seite und fing jeden Tipp ab – man konnte zusehen, aber nichts bedienen. Zwei weitere Sperren kamen dazu:
  - `body.saver-on #live-tools { visibility: hidden; }` blendete die Symbolspalte in **jedem** Sparzustand aus, auch im hellen.
  - Der Karten-Wächter („Zum Verschieben antippen") blieb aktiv, solange keine Fahrt lief.
- **Behoben:**
  - Im hellen Zustand lässt das Overlay **alle Tipps durch** (`pointer-events: none`). Nur der ✕-Knopf und der kleine Hinweis-Streifen bleiben anklickbar – sonst käme man nicht mehr heraus.
  - Symbolspalte, Statuszeile und Verschiebe-Hinweis sind im hellen Zustand wieder da; im dunklen bleiben sie ausgeblendet (die Regel hängt jetzt an `body.saver-on:not(.saver-hell)`).
  - Die Karte ist im hellen Zustand **verschiebbar**, ohne vorher „Zum Verschieben antippen" drücken zu müssen; beim Zurückschalten wird sie wieder geschützt.
- **Im Browser belegt** (Chromium, Smartphone-Profil):
  - hell: `pointer-events = none`, `map.dragging = true`, Symbolspalte `visible`.
  - **Zoom 12 → 13** per Klick auf „+", **Karte verschoben** (53,4595 → 53,4457), „Alle"-Knopf reagiert, Fahrt-Knopf reagiert.
  - zurück auf dunkel: `pointer-events = auto`, Symbolspalte `hidden` – die Sperre greift wieder.
- 4 neue Tests (362 gesamt), py_compile und JS-Syntax OK.

Geänderte Dateien: `templates/touren/live.html`, `static/css/style.css`, `templates/hilfe.html`, `app.py`,
`templates/base.html`, `tests/test_build_ad.py`, `tests/test_build_ag.py`, `CHANGELOG.md`.

2026-11-07 – Einmal tippen dunkelt jetzt jedes Mal wieder ab
- **Rückmeldung:** „Einmal tippen funktioniert nur einmal. Wenn man erneut nach einer längeren Zeit auf den abgedunkelten Screen einmal tippt, bleibt er immer an."
- **Ursache (klarer Fehler in Build af):** `saverTap()` hellte direkt auf (`classList.add('saver-peek')`), setzte aber **keinen Zeitgeber zum Zurückdunkeln**. Der 4-Sekunden-Timer lebte nur in `saverStufe()` und lief einmal beim Einschalten des Sparmodus. Nach der ersten Aufhellung blieb deshalb jeder weitere Einzeltipp für immer hell.
- **Behoben:** Es gibt jetzt genau **eine** Stelle, die den kurzen Blick steuert – `saverBlick()`. Sie setzt bei **jedem** Tipp beide Timer neu: Abdunkeln nach 4 s, Hinweis weg nach 2 s. `saverStufe()` macht nur noch den Zustandswechsel dunkel ↔ dauerhaft hell.
- **Zweiter Fehler gleich mit behoben:** Im dauerhaft hellen Zustand setzte der Einzeltipp keinen Warte-Timer. Dadurch wurde der nächste Tipp wieder als „erster" gezählt – **das Zurückschalten per Doppeltipp ging verloren**. Die 300-ms-Erkennung ist jetzt in beiden Zuständen gleich scharf.
- **Im Browser belegt** (Chromium, Smartphone-Profil, echte Tap-Ereignisse):
  - Drei Runden hintereinander: Tipp → hell (`0.18`), nach 9 s Wartezeit → wieder dunkel (`0.86`). Alle drei „OK".
  - Doppeltipp (120 ms Abstand) → dauerhaft hell, bleibt auch nach 6 s offen.
  - Einzeltipp im hellen Zustand → bleibt hell (kein versehentliches Abdunkeln).
  - Doppeltipp → zurück auf dunkel (`0.86`).
  - Erneuter Einzeltipp nach 6 s → hell, nach 4,5 s wieder dunkel. **Genau der gemeldete Fall.**
- 4 neue Tests (358 gesamt), py_compile und JS-Syntax OK.

Geänderte Dateien: `templates/touren/live.html`, `app.py`, `templates/base.html`,
`tests/test_build_ad.py`, `tests/test_build_ag.py`, `CHANGELOG.md`.

2026-11-07 – Stromspar mit zwei Stufen, Hinweis versperrt die Karte nicht mehr
- **Gute Nachricht vom Gerät:** „Der Bildschirm bleibt 40 s an, vom Gerät bestätigt." Der Selbsttest aus Build ae funktioniert also – das Wachhalten hält auf dem S23 und die Meldung ist belegt statt behauptet.
- **Wunsch:** „Wenn der Stromsparen aktiv ist, soll bei einmal tippen das Display kurz angehen um kurz schauen zu können und bei zweimal tippen soll das Display anbleiben. Wenn man erneut zweimal tippt, wieder in Stromsparen gehen."
  - **Einmal tippen** → 4 Sekunden hell, dann wieder dunkel (wie bisher, aber jetzt sauber getrennt).
  - **Zweimal tippen** → dauerhaft hell: Die Abdunklung ist vollständig weg, die Karte also wirklich frei.
  - **Nochmals zweimal tippen** → zurück in den Sparmodus.
  - **✕** beendet den Modus weiterhin ganz.
  - Unterscheidung: Der zweite Tipp innerhalb von 300 ms zählt als Doppeltipp; ein Einzeltipp hellt sofort auf, damit man nicht ins Leere tippt.
- **Fehler:** „Aktuell wird die Sicht auf die Karte versperrt mit dem großen Stromspar-an-Hinweis, auch wenn es hell ist." Zu Recht – der Kasten stand mittig im Bild und blieb auch im hellen Zustand stehen.
  - Der Hinweis ist jetzt ein **schmaler Streifen** statt eines Kastens, sitzt **über der Knopfleiste** (verdeckt weder Karte noch App-Navigation) und wird **beim Aufwachen nach 2 Sekunden ausgeblendet**.
  - Im dauerhaft hellen Zustand ist er nur so lange zu sehen, bis man die neue Stufe wahrgenommen hat.
- **Im Browser belegt** (Chromium, Smartphone-Profil):
  - frisch an → dunkel (`rgba(5,9,20,0.86)`), Hinweis sichtbar.
  - 1× tippen → `saver-peek saver-tipp`, Hintergrund `0.18`, Hinweis nach 2 s auf `opacity 0`; nach 4,5 s wieder `0.86`.
  - 2× tippen → `saver-off`, Hintergrund `transparent`, Text „Dauerhaft hell · zweimal tippen = wieder Stromsparen".
  - erneut 2× → wieder dunkel.
  - ✕ → `saverOn = false`, Overlay `d-none`.
  - Hinweis-Lage: `[682, 732]` – unterhalb der Karte, oberhalb von Leiste und Navigation.
- 4 neue Tests (354 gesamt), py_compile und JS-Syntax OK.

Geänderte Dateien: `templates/touren/live.html`, `static/css/style.css`, `templates/hilfe.html`, `app.py`,
`templates/base.html`, `tests/test_build_ad.py`, `tests/test_build_ag.py`, `CHANGELOG.md`.

2026-11-07 – „Grün, aber wirkungslos" abgeschafft + Abdunklung wirklich ganzflächig
- **Rückmeldung:** „Es geht nicht, obwohl nur grüne Meldungen kommen. Es wird auch nicht der ganze Bildschirm abgedunkelt."
- **Der eigentliche Konstruktionsfehler (meiner):** Ich habe gemeldet, dass *meine Mittel* laufen (Video spielt, Wake-Lock erteilt), und das als Beweis ausgegeben, dass der Bildschirm anbleibt. Das ist es nicht. Verweigert das Betriebssystem den Bildschirm-Wächter – Samsungs Akkusparmodus tut genau das –, laufen Video und Schnittstelle „fehlerfrei" weiter, nur ohne Wirkung. Das Grün war also ehrlich gemeint und trotzdem falsch.
  - **Neu: ein echter Selbsttest mit Zeitmessung.** Wenn der Bildschirm ausgeht, friert Android die Seite ein. `wachTick()` läuft alle 5 Sekunden und merkt sich die Zeit; bleibt ein Loch von mehr als 20 Sekunden, war es **kein** Wachhalten – dann kommt sofort eine rote, konkrete Meldung: „Der Bildschirm ging trotz ‚an' aus (34 s Stillstand)." Der gemessene Gegenbeweis schlägt jede technische Freigabe (`f.ok = false`).
  - **„Bleibt an" nur noch nach 40 Sekunden ohne Unterbrechung** – vorher steht dort „Eingerichtet … ob der Bildschirm wirklich anbleibt, zeigt sich in den nächsten 40 Sekunden". Auch der Knopf-Tooltip und das aria-label folgen dieser Regel.
  - `wakeVerify()` behauptet nichts mehr. Es prüft nur noch, ob Video/API technisch laufen – und schweigt, wenn ja, statt Grün zu fahren.
- **Abdunklung war nicht ganzflächig** – zu Recht gemeldet. Drei Ursachen, alle behoben:
  - Das Overlay endete per `bottom: var(--saver-frei)` **oberhalb** der Knopfleiste → unten blieb ein heller Streifen.
  - Build ad hatte die Knopfleiste mit `z-index: 4100` **über** die Abdunklung gehoben → Leiste und App-Navigation blieben hell.
  - Die Symbolspalte lag ebenfalls darüber.
  - Neu: `inset: 0` ohne Verkürzung, die Abdunklung liegt über **allem** – nachgemessen an neun Punkten (Ecken, Navigation, Leiste, Symbolspalte): alle treffen das Overlay. Aufgehellt wird durch Tippen (4 s), beendet mit ✕ oben rechts. Der Spar-Hinweis ist größer und mittig.
- **Im Browser belegt** (Chromium, Smartphone-Profil):
  - Deckung: `vollflaeche = true`, alle neun Testpunkte treffen `saver-dim` (bzw. den Spar-Chip in der Mitte).
  - Selbsttest negativ: 34 s Stillstand → `wachBeweis = {ok: false, luecke: 34}`, roter Balken, `wakeFacts().ok = false`.
  - Selbsttest positiv: 41 s ohne Stillstand → `{ok: true, geprueft: 40}`, grüner Balken „vom Gerät bestätigt".
- 6 neue Tests (350 gesamt), py_compile und JS-Syntax OK.

Geänderte Dateien: `templates/touren/live.html`, `static/css/style.css`, `templates/hilfe.html`, `app.py`,
`templates/base.html`, `tests/test_build_ad.py`, `tests/test_build_ag.py`, `CHANGELOG.md`.

2026-11-07 – „Bildschirm bleibt an" endlich wirksam + Stromspar neu gedacht
- **Rückmeldung:** „es geht nicht. Wenn ich länger auf den Button tippe, wird auch nichts angezeigt. Vielleicht sollte man den Stromsparmode nochmal neu denken." Zwei echte Fehler, ein Design-Fehler.
- **Fehler 1 – das Video war zu klein.** Ich hatte die Regel falsch im Kopf. Im Chromium-Quelltext (`video_wake_lock.cc`) steht sie wörtlich: ein Video hält den Bildschirm nur, wenn es **hörbar** läuft **oder** zu **mindestens 20 % des Fensters** zählt **und** zu **mindestens 75 % sichtbar** ist (`kSizeThreshold = 0.2`, `kStrictVisibilityThreshold = 0.75`). Mein 2×2-Pixel-Video aus Build ac erfüllte beides **nie** – es konnte auf dem S23 gar nicht wirken.
  - **Neu:** Das Ersatz-Video ist **bildschirmfüllend** (`inset: 0`, `object-fit: cover`), liegt **hinter** der Seite und ist mit **1 % Deckkraft** unsichtbar. Es zählt damit als 100 % Fläche und 100 % sichtbar. Echtes Clip 320×180 mit Vorbis-Tonspur, 5,8 KB, eingebettet.
- **Fehler 2 – die App schaltete den funktionierenden Weg selbst ab.** Sobald die Wake-Lock-Schnittstelle „erteilt" meldete, wurde das Video gestoppt („spart Akku"). Verweigert das **Betriebssystem** den Lock still – im Akkusparmodus bei Samsung üblich –, ist das für JavaScript **nicht unterscheidbar** von einer echten Freigabe. Ergebnis: Die App behauptete „bleibt an", während nichts mehr hielt.
  - **Neu:** Beide Wege laufen **gleichzeitig**, das Video wird nicht mehr abgeschaltet.
- **Statt Hoffnung: Nachprüfung.** `wakeFacts()` misst Fläche, Sichtbarkeit und Laufzeit des Videos und prüft, ob der API-Lock noch da ist. `wakeVerify()` meldet nach 1,2 s das **geprüfte** Ergebnis. Nur wenn beides scheitert, kommt die ehrliche Warnung mit Grund („Video zu klein oder verdeckt" / „Video startet nicht").
- **Rückmeldung am Knopf** (der zweite Teil der Meldung): Bisher erschien die Antwort nur als 2,5-s-Toast **oben auf der Karte** – wer unten auf ein Symbol tippt, sah nichts. Neu: eine **Hinweisleiste direkt über den Hauptknöpfen**, 4 s, farbig (grün = hält, rot = hält nicht), dort wo der Daumen ist. Die Statuszeile weicht so lange.
- **Stromspar neu gedacht – das Display darf jetzt ausgehen.** Bisher verlangte der Sparmodus zusätzlich „Display bleibt an": das Gegenteil von Stromsparen und vom Betriebssystem ohnehin nicht erzwingbar. Neu:
  - Display **darf aus**; entscheidend ist, dass kein Messpunkt verloren geht.
  - Jeder Punkt wird **vor** dem Senden lokal gesichert (`localStorage`, bis 200 Punkte) und nach dem Aufwachen **nachgesendet** – auch nach einem Neustart der Seite. Beim Fahrtstart wird die Sicherung sofort geleert.
  - Bildschirm-an (🔆) und Stromspar (🌙) sind jetzt **unabhängige Schalter**.
- **Nebenbei behoben:** Im Stromsparmodus fing das dunkle Overlay **jeden Tipp ab** – die Fahrt ließ sich auf dem Rad nicht beenden. Jetzt bleiben Knopfleiste und Symbolspalte über der Abdunklung bedienbar; der Spar-Hinweis sitzt oben und überdeckt sie nicht.
- **Im Browser belegt** (Chromium, Smartphone-Profil, ohne Autoplay-Sonderflag): Video **100 % Fläche / 100 % sichtbar**, `paused = false`, `muted = false`, Ton dekodiert (`92`), Chromium-Bedingung **erfüllt**, Knopf „an", Hinweis „🔆 Bildschirm bleibt an – Video-Ersatz, geprüft."
  - Sicherung: 3 offene Punkte überleben das Einfrieren (`document.hidden`) und werden beim Aufwachen **in Reihenfolge** nachgesendet, `localStorage` danach leer.
  - Stromspar: Leiste bleibt klickbar (`elementFromPoint` → `btn-share`), keine Überlappung mit der Symbolspalte.
- 12 neue Tests (344 gesamt), py_compile und JS-Syntax OK.

Geänderte Dateien: `templates/touren/live.html`, `static/css/style.css`, `templates/hilfe.html`, `app.py`,
`templates/base.html`, `tests/test_build_ad.py` (neu), `tests/test_build_aa.py`, `tests/test_build_ag.py`, `CHANGELOG.md`.

2026-11-07 – „Bildschirm bleibt an": der Fehler lag im Video (es war stumm)
- **Rückmeldung:** „Leider funktioniert Bildschirm bleibt an nicht." Zu Recht – mein Ersatz-Weg aus Build ab war **wirkungslos**.
- **Die Regel, die ich übersehen hatte:** Ein Video hält den Bildschirm nur wach, wenn es **nicht stumm** ist. Es braucht eine **Tonspur** und darf nicht `muted` sein. Das Video aus Build ab hatte gar keine Tonspur (nur ein schwarzes Bild) und war zusätzlich stummgeschaltet – der Browser hatte damit keinen Grund, das Display anzulassen.
  - Nachgeprüft am Vorbild **NoSleep.js**: dessen WebM hat eine **Vorbis**-, das MP4 eine **AAC**-Tonspur, und es wird nirgends stummgeschaltet.
- **Neues Video:** 2×2 Pixel, schwarz, 1 s, Endlosschleife, **mit unhörbarer Vorbis-Tonspur** (Lautstärke 0,02 – nicht stumm), 5,5 KB, direkt im HTML eingebettet. Kein Netz, keine Datei.
- **Zweiter echter Fehler gefunden:** `wakeActive()` fragte nur ein Flag ab. Stand das Video (Autoplay-Sperre, Energiesparmodus), behauptete die Seite trotzdem „Bildschirm bleibt an". Jetzt zählt nur ein **nachweislich laufendes** Video (`!paused && readyState >= 2`); sonst kommt eine ehrliche Warnung: „greift auf diesem Gerät nicht – bitte Bildschirmsperre im Gerät abschalten."
- **Fehlertexte nennen jetzt den Video-Grund**: „das Ersatz-Video startet nicht (Autoplay gesperrt)" bzw. „wird blockiert (Code …)" statt allgemein „abgelehnt".
- **Im Browser belegt** (Chromium, Smartphone-Simulation):
  - Wake-Lock-Berechtigung erteilt → API hält (`api = true`), Video bleibt aus.
  - Berechtigung fehlt → Video läuft (`paused = false`, `muted = false`, `duration 1,06 s`), Knopf „an".
  - Abspielen künstlich blockiert → Knopf **orange**, ehrliche Warnung, kein falsches „bleibt an".
- 3 neue Tests (332 gesamt), py_compile und JS-Syntax OK.

Geänderte Dateien: `templates/touren/live.html`, `app.py`, `tests/test_build_aa.py`, `tests/test_build_ag.py`, `CHANGELOG.md`.

2026-11-07 – „Bildschirm bleibt an" hält jetzt wirklich (zweiter Weg) + feinere Leiste
- **Fehler:** „Bildschirm bleibt an funktioniert nicht, zumindest nicht auf meinem Galaxy S23 und auch nicht im Browser bei der Smartphone-Simulation." Ursache: Der Wake-Lock ist eine **Berechtigung** des Browsers. Verweigert er sie (Energiesparmodus, schwacher Akku, Browser-Richtlinie, Seite nicht über https), blieb bisher nur eine ehrliche Fehlermeldung – der Bildschirm ging aus.
- **Zweiter Weg – stilles Endlos-Video:** Ein 641 Byte kleines, unsichtbares Video (16×16, schwarz, 1 s, Endlosschleife, direkt im HTML eingebettet, kein Netz nötig) hält den Bildschirm genauso wach. Das ist der klassische Ausweg, den auch NoSleep.js geht.
  - Läuft die Wake-Lock-Schnittstelle, wird sie genommen (sauberer, sparsamer) – das Video bleibt aus.
  - Scheitert sie (oder fehlt sie ganz), springt das Video ein; der Knopf zeigt dann trotzdem „an" und der Titel nennt den Weg.
  - Fällt der Lock später weg (Tab-Wechsel, Sperren, Energiesparmodus), startet das Video automatisch; der 20-s-Wächter prüft beide Wege und startet ein pausiertes Video neu.
  - Aus-Knopf und Fahrtende schalten **beide** Wege ab.
- **Im Browser nachgemessen** (Chromium, Smartphone-Simulation): mit erteilter Wake-Lock-Berechtigung hält die API; **ohne** Berechtigung übernimmt das Video (läuft, `wakeActive() = true`, Knopf „an", kein „greift nicht" mehr). Nach Pause des Videos startet es über den Wächter wieder.
- **Kartenstil-Knopf höher:** Auf der Live-Karte sitzt er jetzt ganz oben rechts (6 px) als 42-px-Symbol; der Lizenzhinweis rückt dafür 50 px nach links. Auf allen anderen Karten bleibt er der Textknopf.
- **Hauptknöpfe kleiner:** Fahrt beenden/starten · Pause · Foto von 58 px auf **46 px** (Schrift .97rem) – die Leiste ist damit nur noch 56 px hoch (vorher 70). Der Laufraum darunter sinkt auf 106 px, Status-Chip und Symbolspalte rücken entsprechend nach.
- 7 neue Tests (Video-Ersatz), 329 gesamt, py_compile und JS-Syntax OK.

Geänderte Dateien: `templates/touren/live.html`, `static/js/map-touch.js`, `app.py`, `tests/test_build_aa.py`,
`tests/test_build_ag.py`, `tests/test_build_z.py`, `CHANGELOG.md`, `templates/hilfe.html`.

2026-11-07 – Live-Karte: die Karte bekommt den Bildschirm
- **Wunsch:** „Vom Wichtigsten, der Karte, kann man fast nichts mehr sehen. Die Knöpfe nehmen viel zu viel Platz ein."
- **Oben: eine Titelzeile statt vier Blöcke.** Zurück-Pfeil · Titel · ℹ️ in einer Zeile (≈ 38 px statt über 300 px). Datum, Startzeit und Treffpunkt sowie der ganze Hinweise-Block stecken im ℹ️-Aufklapper; die Statusmeldung ist ein kleiner Chip **auf** der Karte (zwei Zeilen, antippen klappt die ganze Meldung auf – die Links nach Fahrtende bleiben erreichbar).
- **Unten: drei große Knöpfe statt fünf Reihen.** Fahrt beenden/starten · Pause · Foto sind jetzt **58 px hoch** (vorher 50) und der Fahrt-Knopf bekommt am meisten Breite – der Rest der Leiste ist weg (≈ 70 px statt ≈ 200 px).
- **Nebenfunktionen als Symbole auf der Karte:** Folgen · Alle · Vollbild · Bildschirm an · Stromspar sitzen als 42-px-Symbole unten rechts über der Leiste. Aktive Funktionen sind eingefärbt (Bildschirm: orange, wenn gewünscht, aber nicht greifend), jeder Knopf nennt beim Antippen kurz seinen Namen.
- **Symbole als Inline-SVG statt Icon-Schrift:** Unterwegs ohne Netz lädt Bootstrap Icons nicht vom CDN – die Knöpfe wären leere Kästchen. Die Symbole stecken jetzt direkt im HTML (auch der Verschiebe-Hinweis und der ℹ️-Knopf kommen ohne Icon-Font aus).
- **Messung im Browser** (390×844): Karte 676 px hoch, beginnt bei y = 232 statt 318, Kopfzeile 38 px, Leiste 70 px; bei 360×640 bleibt die Karte 472 px hoch, kein Symbol liegt auf Leiste oder Karte-Chip.
- 12 neue Tests (`tests/test_build_aa.py`), 322 gesamt, py_compile OK.

Geänderte Dateien: `templates/touren/live.html`, `app.py`, `tests/test_build_aa.py`, `tests/test_build_ag.py`,
`tests/test_live.py`, `CHANGELOG.md`, `templates/hilfe.html`.

2026-11-06 – Radkarte (CyclOSM) auf jeder Karte
- **Wunsch:** „CyclOSM soll auch auf jeder Karte auswählbar sein." Bisher gab es den Radkarten-Stil nur auf der Live-Karte (🚵 Wege, Build 11-06u), auf der Tour-Seite nur als einer von mehreren Knöpfen.
- **Eine Lösung statt 17 Kopien:** Der Umschalter steckt in `static/js/map-touch.js` – die Datei wird über `base.html` auf jeder Seite geladen. Ein kleiner Knopf auf der Karte schaltet zyklisch **Standard → Radkarte (CyclOSM) → Luftbild**; er erkennt „unsere" Karten an den OSM-Kacheln, tauscht nur den Grund-Kachelsatz (Marker, Track, Overlays bleiben oben) und zieht alle anderen Karten der Seite mit.
- **Gilt für die ganze Sitzung:** Die Wahl liegt in `sessionStorage` (`djo_map_style`) und wird auf jeder Seite sofort angewandt – einmal Radkarte, überall Radkarte. Die alte Merke der Live-Karte (`localStorage djo_live_tiles`) wird übernommen, damit niemand nach dem Update plötzlich wieder die Standardkarte bekommt.
- **Live-Karte:** Der eigene 🚵-Kachelknopf ist aus der Leiste verschwunden (dort war ohnehin kein Platz); das Umschalten macht der Knopf auf der Karte. Die Leiste behält alle übrigen Funktionen.
- **Tour-Seite:** 🗺️ · 🚵 · 🛰️ bleiben im Kartenkopf – sie lesen und schreiben denselben Speicher, der aktive Knopf leuchtet auch nach einem Neuladen richtig. Das GPS-Modal übernimmt den Stil der Tour (eigener Kachelsatz, aber **kein** zweiter Knopf im kleinen Fenster).
- **Kein Gedränge auf der Karte:** Der Knopf startet oben rechts und weicht automatisch nach unten aus, bis er wirklich frei liegt (Prüfung gegen Leaflet-Bedienelemente und per Trefferprobe). Auf der Live-Karte sitzt er unter dem OSM-Hinweis, mobil nie auf dem 🔒-Knopf des Karten-Guards.
- **Mini-Karten** (Startseite, Tourenliste) zeigen nur das Symbol – Text würde dort den halben Kartenausschnitt verdecken. Opt-out per `data-map-style="off"` (Druckansicht) bzw. `"own"` (Karten mit eigenem Umschalter).
- **Geländekarte bleibt draußen** – Build f hat sie auf Wunsch entfernt (kaum nutzbar, lud langsam); sie kommt hier nicht durch die Hintertür zurück.
- 310 Tests (22 neue in `tests/test_build_z.py`), py_compile OK.

Geänderte Dateien: `static/js/map-touch.js`, `templates/touren/detail.html`, `templates/touren/live.html`,
`templates/touren/print.html`, `app.py`, `tests/test_build_z.py`, `tests/test_build_ag.py`,
`CHANGELOG.md`, `templates/hilfe.html`.

2026-11-06 – „Bildschirm bleibt an“ hält jetzt wirklich an
- **Fehler:** Nach dem Doppeltipp stand „🔆 Bildschirm bleibt an“, der Bildschirm ging aber trotzdem aus – auch in der Handy-Simulation des Browsers, also kein Geräteproblem. Ursache: Der Wake-Lock wurde **einmal** angefordert und nie wieder. Lässt der Browser ihn fallen (Tab verlassen, Display gesperrt, App-Wechsel, Akkusparmodus – bei jeder Aufnahme des Handys fällt er weg), blieb die Erfolgsmeldung stehen, aber nichts hielt den Bildschirm mehr. Der 60-s-Wächter griff nur bei laufender Fahrt/Folgen/Stromspar – nicht beim reinen Doppeltipp.
- **Jetzt:** Die Seite merkt sich den **Wunsch** (`wakeWanted`) und holt den Lock bei jeder Rückkehr neu: bei `visibilitychange` (zurück im Tab, entsperrt), bei jedem normalen Tipp und über einen **20-s-Wächter** (vorher 60 s und nur bei Fahrt). Genau so verlangt es der Browser: eine neue Anforderung ist nur bei sichtbarer Seite erlaubt.
- **Doppeltipp schaltet um:** einmal an, nochmal aus („🌙 Bildschirm darf wieder aus“) – vorher war ein zweiter Doppeltipp wirkungslos.
- **Ehrliche Rückmeldung:** Der Erfolgstext kommt nur, wenn der Lock wirklich greift. Sonst nennt die Meldung den Grund (kein https, Energiesparmodus/Akku, Browser ohne Unterstützung).
- **Neuer Knopf „🔆 Bildschirm an“** in der Leiste (dritte Reihe, volle Breite): setzt das Wachhalten ohne laufende Fahrt und zeigt den echten Zustand – „Bildschirm bleibt an“, wenn er gerade hält, sonst „Bildschirm an (greift nicht)“.
- **Nebenbei:** Ein bestehender Test (`/fahren`) rechnete mit dem UTC-Datum des Servers statt mit Berliner Zeit und war zwischen 22 und 24 Uhr UTC rot – jetzt `_berlin_today()` wie in der App.
- 288 Tests, py_compile OK.

2026-11-06 – Live-Karte auf dem Handy lesbar: Guard unter dem Zoom, volle Knopf-Beschriftungen
- **„Zum Verschieben antippen“ und 🔒 lagen auf dem „−“**: Das Zoom-Bedienfeld von Leaflet beginnt bei 10 px, ist mit zwei Knöpfen ≈ 70 px hoch – die Pill begann bei 56 px und nahm das Herauszoomen weg. Beide sitzen jetzt bei `top: 80px; left: 10px`, also **unter** dem Zoom und bündig mit ihm; der Karten-Toast rutscht mit auf 124 px.
- **Abgeschnittene Knöpfe („Fol…“, „Voll…“, „Sta…“, „Str…“)**: Die fünf Sekundär-Knöpfe quetschten sich in eine Zeile und wurden mit Ellipse gekürzt. Jetzt ein 3+2-Raster (Folgen · Alle · Vollbild / Standard · Stromspar) mit voller Beschriftung und Umbruch statt Ellipse – die Höhe der Leiste bleibt bei ≈ 155 px.
- **Beschriftung bleibt beim Umschalten**: Vollbild und Kartenstil tauschen nur noch den Text im Knopf (eigene Spans), das Icon bleibt stehen – vorher wurde der Vollbild-Knopf zum nackten „⛶“.
- **Nebenbefund, mitbehoben:** Der Laufraum unter der Daumenleiste war wirkungslos – `base.html` setzt sein `body { padding-bottom: 58px }` später im Dokument und gewann bei gleicher Spezifität (58 px statt 174 px), die letzten Inhalte lagen hinter der Leiste. Jetzt `html body { padding-bottom: 222px }` (0,0,2), passend zur neuen Leistenhöhe.
- 284 Tests, py_compile OK.

2026-11-06 – Live-Karte wieder sperrbar: 🔒-Knopf nach dem Freischalten
- Nach dem Freischalten des Ecken-Guards (Pill „Zum Verschieben antippen“ oben links) ließ sich die Karte nicht wieder sperren – die Pill war weg und die Seite scrollte fortan nicht mehr normal. Jetzt erscheint beim Freischalten an derselben Ecke der **🔒-Knopf**: Er sperrt die Karte wieder (Seite scrollt normal, Pill kommt zurück).
- Der Guard liest seinen Zustand **selbst** (`setLiveGuard()` ohne Argumente, `guardArmed = true` als Startwert): gesperrt = kein Fahrt/Folgen/Vollbild **und** nicht freigetippt. Damit bleibt der Zustand auch nach Fahrtende, Folgen-Aus oder Drehen des Geräts konsistent (Neu-Bewertung zusätzlich bei `resize` und nach dem Ziehen der Karte).
- Während **Fahrt, Folgen und Vollbild** sind Pill und 🔒 ausgeblendet – dort muss Verschieben sofort gehen (wie seit Build u).
- Hilfe-Seite erklärt das Sperren auf der Live-Karte.
- 280 Tests, py_compile OK.

2026-11-06 – Live-Karte-Nachjustieren: Scrollen, Knopf-Zustand, ehrlicher Doppeltipp
- Scrollen wieder leicht: Der Antipp-Schutz kehrt auf der Live-Karte zurück – aber als dezente Pill OBEN LINKS statt als Overlay mitten auf der Karte. Ohne laufende Fahrt scrollt die Seite normal, die Pill schaltet die Karte zum Verschieben frei; sobald Fahrt/Folgen/Vollbild aktiv sind, schaltet der Schutz automatisch ab (sofortiges Verschieben) und kehrt danach zurück.
- Der 🚵-Knopf zeigt jetzt sichtbar den aktiven Kartenstil („🚵 Standard“ hell / „🚵 Radkarte“ gelb) – vorher blieb die Hell-Färbung drauf und überdeckte die Gelb-Markierung.
- Doppeltipp-Rückmeldung erscheint als Toast AUF der Karte (vorher nur Statuszeile darüber); unterstützt das Gerät das Bildschirm-Wachhalten nicht (älteres iOS, Akkusparmodus), kommt ein ehrlicher ⚠️-Hinweis statt der Erfolgsmeldung.
- 277 Tests, py_compile OK.
2026-11-06 – Fahrmodus der Live-Karte
- Kein „Karte zum Verschieben antippen“ mehr auf der Live-Karte: Der Antipp-Schutz bleibt auf allen eingebetteten Karten aktiv, ist auf der Live-Seite aber aus – beim Fahren verschiebt ein Finger SOFORT, nichts überlagert die Kartenmitte.
- Karte größer auf dem Handy (höhere Mindesthöhe, mehr Bildschirmanteil auf schmalen Displays).
- 🚵 Wege-Knopf: Kartenstil umschaltbar zwischen Standard-OSM und CyclOSM (Radkarten-Stil, Feldwege/Tracks kräftig) – die Wahl wird gemerkt.
- 👠 Folgen zoomt jetzt auf Fahrzoom 16 (Straßen/Wege deutlich lesbar).
- Doppeltipp auf der Karte frischt das Bildschirm-Wachhalten auf („🔱 Bildschirm bleibt an“), dazu ein Wächter, der den Wake-Lock alle 60 s zurückholt – das Display hält so den ganzen Fahrttag durch.
- 274 Tests, py_compile OK.
2026-11-06 – Eine rote Anzeige statt zweier
- Läuft die EIGENE Fahrt, ist die „Fahrt läuft“-Pill unten rechts DIE eine Anzeige – sie zeigt jetzt auch, wie viele unterwegs sind und ob die Aufzeichnung läuft (vorher standen Navbar-Pille „N unterwegs“ und Pill gleichzeitig herum). Die Navbar bleibt bei eigener Fahrt frei; fährt jemand anderes, zeigt weiterhin die Navbar-Pille die Gruppe an. Tourseiten regelt wie seit Build p die Aktionsleiste.
- 271 Tests, py_compile OK.
2026-11-06 – „Ende gilt“-Siegel gegen Zombie-Fahrten
- Fix für „Fahrt läuft immer noch, obwohl ich sie mehrfach beendet habe“: Ein vergessenes Gerät (Tab oder Handy mit offener Live-Karte bzw. aktivem Fahren-Status) sendete im Hintergrund weiter und riss die soeben gelöschte Anwesenheit alle ~30 Sekunden neu ein – die rote Anzeige kam also immer wieder.
- Beim Beenden setzt der Server jetzt ein Siegel (live_stops): Weitere Hintergrund-Updates werden abgewiesen (HTTP 409), die Sender räumen sich selbst ab. Eine frisch geladene Live-Karte meldet resume und startet unbeschwert neu; die Aufzeichnung bleibt von der Änderung unberührt (weiter übernehmen/löschen auf der Tourseite).
- 269 Tests, py_compile OK.
2026-11-06 – Navbar bei mittlerer Größe gerade gezogen
- Bei mittlerer Fenstergroße (992–1199 px) standen die Menü-Einträge versetzt: Icon über, Beschriftung unter – Ursache war Bootstraps .container, der dort nur 960 px breit ist und die Links zum Umbrechen zwang. Die Navbar nutzt jetzt die volle Breite (container-fluid), Beschriftungen sind grundsätzlich einzeilig, und im Mittelbereich sind Abstände/Logo/Brand etwas kompakter.
- 267 Tests, py_compile OK.
2026-11-06 – Karten-Overlay eindeutig benannt
- Der Karten-Schutz auf Handys hieß „☝ Tippen zum Aktivieren“ und wurde mehrfach so verstanden, als ließe sich hier die TOUR starten/aktivieren – gemeint war die Karte (erst antippen, dann mit einem Finger verschieben). Neu: „☝ Karte zum Verschieben antippen“; die vier Positions-Picker (Treffpunkt, Orte, Gastro, GPS-Korrektur) bekamen ebenfalls eindeutige Hinweise („Karte antippen – Klick setzt danach …“).
- 266 Tests, py_compile OK.
2026-11-06 – Eine Live-Anzeige statt dreier, „Abschließen“ entschärft
- Konsolidiert: Auf der Tourseite zeigt jetzt die Aktionsleiste den Lauf-Status an – die rote „Fahrt läuft“-Pill unten rechts erscheint dort nicht mehr (Navbar-Punkt bleibt app-weit). Läuft die EIGENE Fahrt, wird der Knopf zum aktiven „⏺ Fahrt beenden“ (stoppt die eigene Aufzeichnung, ohne die Tourseite zu verlassen; danach steht wieder „Fahren“ da). Fremde Fahrten bleiben reiner Status.
- „Abschließen“ tritt bei laufender Fahrt einen Schritt zurück (weicher Tint statt Vollgrün) und fragt beim Klick nach: „Es läuft noch eine Fahrt – Abschließen stoppt sie NICHT“. Bisher wirkte das grüne „Abschließen“ wie der Knopf zum Fahrt-Beenden.
- 264 Tests, py_compile OK.
2026-11-06 – Stromspar-Modus Stufe 2: gröber senden, Kurven-Trigger
- Im Stromspar-Modus sendet die Aufzeichnung gröber: alle 20 s statt 10 s (im Stand alle 45 s statt 30 s) – spürbar weniger Funk-Aktivität auf langen Geraden.
- Neuer Richtungs-Trigger (über 25° Kursänderung, wie in den Akku-Modi von Strava & Co.): Kurven werden auch im gröberen Takt sofort gesichert – Ecken bleiben rund, nur Geraden werden ausged¼nnt. Außerhalb des Sparmodus ändert sich nichts.
- 261 Tests, py_compile OK.
2026-11-06 – Video-Fehler inline, ffmpeg aus Git, Stromspar-Modus
- Video-Seite: Schlägt die MP4-Erstellung serverseitig fehl, erscheint die Meldung jetzt direkt im Fortschritts-Kasten (mit Grund, Button bleibt bedienbar für erneuten Versuch) – vorher lud die Seite sich still neu und der Formularstand war weg.
- ffmpeg-Binärdatei (77 MB) aus der Git-Verwaltung genommen („sanftes Slimming“): Der Verlauf wächst nicht weiter, die Datei bleibt lokal und auf dem Server; Deploy-ZIPs enthielten sie schon immer nicht. Bei Serverumzug aus der Historie holen (git checkout f32448c -- ffmpeg).
- Stromspar-Modus auf der Live-Karte (Schalter „🌙 Stromspar“): Bildschirm bleibt AN (Wake Lock), wird aber dunkel überzogen – kein Entsperren nötig; Tippen hellt 4 s lang auf, ✕ beendet, mit Fahrtende endet der Modus automatisch. Die Aufzeichnung läuft unverändert weiter.
- 260 Tests, py_compile OK.
2026-11-06 – Footer-Link heißt jetzt „Monatsrückblick“
- Der Footer-Link „Newsletter“ heißt jetzt „Monatsrückblick“ – so nennt sich die Zielseite selbst (Kopf: „Monatsrückblick MM/JJJJ“); auch der Browser-Titel der Seite wurde von „Newsletter MM/JJJJ“ auf „Monatsrückblick MM/JJJJ“ angeglichen. Die Adresse (/newsletter) bleibt unverändert, alte Links/Bookmarks funktionieren weiter.
- 257 Tests, py_compile OK.
2026-11-06 – Footer zentriert
- Die Footer-Zeile (Gruppenname · Newsletter · Datenschutz) ist jetzt zentriert statt im Breitband-Layout nach links/rechts verteilt – auf schmalen Screens stand bisher alles links, nur die Versionszeile mittig.
- 255 Tests, py_compile OK.
2026-11-06 – Text-Überlauf behoben & Versionssprung 1.4.0 → 1.5.0
- Aufklapp-Hinweise (z. B. „Noch keine GPX-Datei?“ beim Tour-Anlegen) brechen wieder um: Das globale Einzeilig-Gebot für Buttons aus Build i ließ den langen Hinweistext über den rechten Rand laufen; Aufklapp-Buttons (data-bs-toggle="collapse") sind jetzt ausgenommen, normale Buttons bleiben einzeilig.
- Versionsnummer erstmals seit Build af wieder angehoben (1.4.0 → 1.5.0) – seitdem kamen u. a.: WhatsApp-Verwaltung, Kopf-/Aktionsleisten, eine Button-Familie app-weit, OSM-Direktsuche mit Circuit-Breaker, Rückblick-Extras. Footer und Deploy-ZIPs führen künftig 1.5.0.
- 254 Tests, py_compile OK.
## 1.4.0 – 2026-11-06 (Build j) – Ein Gelbton für alle Plus-Akzente
- Die getönte Plus-Kachel der mobilen Kopfzeile nutzt jetzt das App-Amber #f0a500 (wie der runde Plus-Button der Bottom-Nav und der aktive Menüpunkt) statt Bootstrap-Gelb #ffc107 – vorher trafen sich auf einem Handy-Screen zwei verschiedene Gelbtöne.
- 252 Tests, py_compile OK.
## 1.4.0 – 2026-11-06 (Build i) – Kopfzeilen- & Filter-Buttons in die Familie
- Mobile Schnell-Buttons (Touren, Suche, Neue Tour, Profil) sind jetzt eine visuelle Familie: gleich große weiche Kacheln mit Rahmen statt drei gemischter Stile (weiße Outline / knallgelb / nackter Avatar); der Plus-CTA bleibt als einziger gelb, aber getönt.
- Gastro-Filter: „Anwenden“ bricht nicht mehr mitten im Wort um (Button größt nach Inhalt, Buttons grundsätzlich einzeilig); Sortier-Chips umbrechen statt rechts abgeschnitten zu werden.
- 251 Tests, py_compile OK.

## 1.4.0 – 2026-11-06 (Build h) – OSM-Suche: sofort direkt suchen, wenn der Server-Kanal tot ist

- Diagnose bestätigt: Der Hosting-Server erreicht **keinen** Overpass-Server (Zeitüberschreitung über alle vier hinweg – zuletzt maps.mail.ru), während der Browser direkt problemlos sucht. Es handelt sich um eine Ausgangs-Sperre/-Drossel des Hosters.
- **Circuit-Breaker:** Nach einem Total-Ausfall des Server-Kanals wartet die App bei den nächsten Suchen **10 Minuten lang nicht mehr** auf den sterbenden Server-Versuch, sondern übergibt sofort an die Browser-Direktsuche (gleiche Ergebnisse). Nach 10 Minuten wird der Server-Kanal wieder einmal probiert; ein Erfolg räumt die Sperre ab. Gecachte Suchen laufen weiterhin über den Server.
- 249 Tests, py_compile OK.

## 1.4.0 – 2026-11-06 (Build g) – OSM-Suche: Ursache sichtbar, Server wartet fair

- Bei „Gaststätten im Kartenbereich suchen“ (und der Strecken-Suche auf der Tour) springt bei Server-Problemen die Direktsuche im Browser ein – das ist als Sicherheitsnetz gebaut. Jetzt wird aber **sichtbar, warum** ausgewichen wurde (z. B. „Zeitüberschreitung bei overpass-api.de“, „zu viele Anfragen (429)“) – sowohl im Hinweis als auch klein neben dem Ergebnis.
- Serverseitig wartet die App jetzt **18 s** statt 12 s pro Overpass-Server: Overpass bekommt intern 15 s Zeit – bei der ersten, ungecachten Suche brach die App vorher ab, deshalb sprang praktisch immer die Direktsuche ein. Nach einem erfolgreichen Server-Treffer antwortet die Suche für 10 Minuten aus dem Cache ohne erneute Overpass-Anfrage.
- 248 Tests, py_compile OK.

## 1.4.0 – 2026-11-06 (Build f) – Buttons app-weit eine Familie

- Globaler Button-Feinschliff: Gleiche Ecken für alle Buttons, und die Outline-Varianten (grau/grün/rot) haben jetzt überall die weiche Tint-Optik aus der Aktionsleiste – vorher nackte Bootstrap-Kacheln, besonders auf Gastro-, Archiv- und Admin-Seiten auffällig. Dark Mode mit eigenen Tönen.
- Die Navigations-Buttons auf der Tour-Seite (Komoot, OsmAnd/Maps-App, Apple Maps, OpenStreetMap) nutzen jetzt Icons statt Emojis und passen zum Rest.
- 247 Tests, py_compile OK.

## 1.4.0 – 2026-11-06 (Build e) – Aktionsleiste auf der Tour-Seite gestylt

- Die Aktions-Buttons (Vorlesen, Bearbeiten, Vorlage, Nochmal, Löschen, Rückblick & Video, Drucken, iCal, Teilen …) sehen jetzt ruhig und einheitlich aus: gleiche Höhe und Ecken, weiche getönte Flächen statt nackter Outline-Kacheln, dezenter Hub beim Berühren. Grün (Nochmal) und Rot (Löschen) bleiben als Bedeutung erkennbar, „Rückblick & Video“ bleibt der goldene Hingucker – zusammen deutlich ruhiger.
- Dark Mode berücksichtigt (eigene Töne), die kompakte Handy-Darstellung bleibt unverändert. Der Teilen-Button nutzt jetzt ein passendes Icon statt des ✈️-Emojis.
- 246 Tests, py_compile OK.

## 1.4.0 – 2026-11-06 (Build d) – Kopf-Buttons auf der Touren-Seite einheitlich

- WhatsApp / Kalender / Neue Tour sahen nebeneinander unruhig aus (Icon-Quadrat, umbruchendes „Kalender-Abo“, unterschiedliche Höhen). Die drei Buttons sind jetzt eine einheitliche Reihe: gleiche Höhe, sanft abgerundete Ecken, dezenten Schatten, zentriertes Icon + Text, kein Umbruch. Auf sehr schmalen Handy-Breiten erscheinen nur die Icons (Beschriftung ab 576 px). „Kalender-Abo“ heißt im Kopf jetzt kurz „Kalender“ (Erklärung wie gehabt im Tooltip bzw. Profil).
- 245 Tests, py_compile OK.

## 1.4.0 – 2026-11-06 (Build c) – WhatsApp-Link: ein System, klar verwaltet

- Es gab zwei WhatsApp-Anlaufstellen (die globale Einstellung unter Admin → Einstellungen und den Gruppen-Link aus Build b, der sich versteckt hinter dem Stift-Aufmacher verbarg). Jetzt ist es ein System mit klarer Rolle: **Gruppen-Link (Admin → Gruppen) hat Vorrang, sonst gilt die globale Einstellung (Admin → Einstellungen, dort wo auch Telegram steht)**. Touren-Button und Account-Menü nutzen dieselbe Quelle – kein Doppel-Eintrag mehr.
- **Der Gruppen-Link ist jetzt direkt auf der Gruppenkarte sichtbar** (eigenes Feld mit Speichern/🗑 statt im Bearbeiten-Formular versteckt) – mit Status-Anzeige „Aktiv“.
- 244 Tests, py_compile OK.

## 1.4.0 – 2026-11-06 (Build b) – WhatsApp-Gruppe aus der App erreichen

- Die eigene WhatsApp-Gruppe ist jetzt direkt aus der App erreichbar: Auf der **Touren-Seite** gibt es einen grünen **WhatsApp-Button** (offizielles Logo, auf dem Handy als Icon), im **„Mehr“-Menü** einen Eintrag „WhatsApp-Gruppe“. Beide öffnen die Gruppe in neuem Tab.
- Der **Einladungslink wird pro Gruppe** in der Admin-Gruppenverwaltung hinterlegt (Feld „WhatsApp-Gruppe (Einladungslink)“, leer = Button nicht anzeigen). Zur Sicherheit werden nur echte WhatsApp-Links akzeptiert (`https://` mit `chat.whatsapp.com`, `wa.me` oder `whatsapp.com`) – alles andere wird abgelehnt.
- 244 Tests, py_compile OK.

## 1.4.0 – 2026-11-06 (Build a) – Rückblick-Diagramm pulsiert auf dem Handy nicht mehr

- „Touren pro Monat“: Das Diagramm wurde auf Smartphones ständig kleiner/größer (Chart.js kämpfte mit der CSS-Begrenzung `max-height` am Zeichenfeld – jeder Adressleisten-Ein-/Ausblend-Stoß löste eine Größenänderung aus). Jetzt steht das Zeichenfeld in einem festen 220-px-Rahmen, das Seitenverhältnis ist fix und Größenänderungen werden 200 ms entprellt.
- 243 Tests, py_compile OK.

## 1.4.0 – 2026-11-05 (Build o) – Lieblings-Einkehr: alle Stopps, Top 3

- Die Einkehr-Bilanz im Jahresrückblick zählte nur den 1. Stopp und zeigte bei Gleichstand einen zufälligen Einstieg. Jetzt zählen **alle Stopps einer Tour** (1.–3. Stopp, Gastro-Verknüpfung oder Freitext), und die Karte zeigt die **Top 3** mit Zähler – Gleichstände (z. B. dreimal 2×) sind jetzt alle sichtbar. Freitext-Namen werden groß-/kleinschreibungsunabhängig zusammengezogen; wer denselben Stopp als Freitext und Verknüpfung einträgt, wird nicht doppelt gezählt.
- 242 Tests, py_compile OK.

## 1.4.0 – 2026-11-05 (Build n) – Jahresrückblick: Wetter, Lieblings-Einkehr, Fotograf:innen

- **Wetter-Bilanz:** Wie viele Touren waren Regen-/Schneetouren, wie war die wärmste Tour (mit Link), Ø-Temperatur und Sonnenstunden. Wird ausschließlich aus dem gespeicherten Wetter-Cache gelesen (keine API-Aufrufe) – die Karte erscheint, sobald Touren Wetterdaten haben.
- **Lieblings-Einkehr:** Die meist angesteuerte Gaststätte des Jahres (Einkehr-Feld der Touren); ohne verknüpfte Gaststätte zählt der Einkehr-Text.
- **Fotograf:innen des Jahres:** Top 3 nach hochgeladenen Tour-Fotos mit Mini-Vorschauen der Aufnahmen.
- 241 Tests, py_compile OK.

## 1.4.0 – 2026-11-05 (Build m) – Doppelte „Längste Tour“ entfernt

- Im Jahresrückblick gab es die „Längste Tour“ zweimal: als Banner oben und als Karte in der rechten Spalte. Die rechte Karte ist entfernt – das Banner oben zeigt Titel, km, Anstieg, Datum und Details-Button.
- 240 Tests, py_compile OK.

## 1.4.0 – 2026-11-05 (Build l) – Rückblick: Sortieren ohne Sprung nach oben

- Die Sortier-Buttons („↑ Älteste zuerst“ / „↓ Neueste zuerst“) im Jahresrückblick sind keine Links mehr, die die Seite neu laden (Sprung nach oben). Sie drehen die Liste jetzt direkt im Browser um – sofort, ohne Reload, die Scrollposition bleibt.
- 239 Tests, py_compile OK.

## 1.4.0 – 2026-11-05 (Build k) – Jahresrückblick: Sortierung + fünf Aktivste

- **Touren sortierbar:** Im Karten-Kopf „Alle N Touren“ gibt es jetzt „↑ Älteste zuerst“ / „↓ Neueste zuerst“ (Standard wie gehabt: älteste zuerst).
- **Aktivste Mitglieder:** Es erscheinen (bis zu) **fünf** – vorher zählte die Box nur **bestätigte** Mitglieder, dadurch wurden oft weniger angezeigt. Jetzt zählt „angemeldet“, wie die Kopfzahlen überall in der App; Gleichstand wird alphabetisch sortiert.
- 239 Tests, py_compile OK.

## 1.4.0 – 2026-11-05 (Build j) – Rangliste sortiert richtig, Gästeverzeichnis aufräumbar, Gast → Mitglied

- **Ranglisten-Sortierung korrigiert:** Gäste wurden erst NACH dem Sortieren in die Liste gehängt – sie klebten dadurch immer am Ende der Gesamt-Liste (konnten nie aufs Podium) und fehlten im Tab „Dieses Jahr“ komplett. Jetzt werden sie vor dem Sortieren mitgemischt und erscheinen überall an ihrem richtigen Platz.
- **Gästeverzeichnis aufräumen:** Auf der Tour-Seite gibt es unter „Wieder dabei“ jetzt „Gästeverzeichnis (N) verwalten“ – Tippfehler lassen sich per 🗑 aus der Vorschlagsliste entfernen (nur Tourleitung; vergangene Tour-Einträge bleiben unverändert).
- **Gast ist jetzt Mitglied:** Meldet sich ein ehemaliger Gast mit dem gleichen Namen als Mitglied an, sieht die Tourleitung auf seinem Profil einen Hinweis („fuhr früher als Gast mit …“) und kann die Gast-Einträge per Klick übernehmen: Die Touren zählen künftig fürs Mitglied (inkl. Bestätigung, Kilometer und Badges), die Gast-Zeile in der Rangliste und die Verzeichnis-Vorschläge verschwinden. Namensgleichheit (Groß-/Kleinschreibung egal) innerhalb der Gruppe ist die Bedingung.
- 238 Tests, py_compile OK.

## 1.4.0 – 2026-11-05 (Build i) – Bestätigt-Badge zählt Gäste mit

- Das Badge neben „Anwesenheit bestätigen“ zählte nur die bestätigten **Mitglieder** – die Häkchen-Liste darunter führt aber Mitglieder **und** Gäste. Beispiel: 1 Mitglied + 1 Gast bestätigt → Badge zeigte „1 ✓“, obwohl zwei Häkchen gesetzt waren. Das Badge zählt jetzt beide (grüner Wert = Anzahl bestätigter Häkchen).
- „offen“-Badge und automatisch aufgeklappte Bestätigungs-Box berücksichtigen jetzt auch reine Gäste-Touren.
- 237 Tests, py_compile OK.

## 1.4.0 – 2026-11-05 (Build h) – Archiv zählt Personen richtig

- **Archiv-Liste (Tabelle, Karten und Suche):** Die Personen-Spalte 👥 zählte vorher nur die **bestätigten Mitglieder** – Gäste fehlten komplett, angemeldete (aber nicht bestätigte) Mitglieder auch. Jetzt zählt das Archiv exakt wie die Tour-Seite: **angemeldete Mitglieder + Gäste**.
- Die Zähllogik liegt einmalig im neuen Helfer `tour_headcounts()` (Mehrfach-Variante von `tour_headcount()` aus Build g) und wird von Archiv, Archiv-Suche und Jahresrückblick genutzt.
- 236 Tests, py_compile OK.

## 1.4.0 – 2026-11-05 (Build g) – Gäste zählen überall mit

- **Teilnehmer-Liste auf der Tour-Seite:** Gäste stehen jetzt MIT in der „Dabei“-Liste (mit „Gast“-Badge und Telefon-Hinweis) und die Kopfzahl zählt sie mit: „Dabei (Mitglieder + Gäste)“. Der separate Gäste-Block darunter ist damit überflüssig und entfällt. Entfernen geht wie bisher per × direkt an der Zeile.
- **Überall dieselbe Kopfzahl:** Auch Jahresrückblick („👥 N“), Video-Statistik („Dabei gewesen“ / „N dabei“), druckbare Teilnehmerliste (Fußzeile „… zugesagt, … Gäste“) und der Admin-CSV-Export zählen Gäste jetzt mit – vorher zeigten diese Stellen nur die Mitgliederzahl. (Touren-Liste, Startseite und die „Dabei“-Kachel zählten bereits korrekt.)
- 235 Tests, py_compile OK.

## 1.4.0 – 2026-11-05 (Build f) – Gruppen immer getrennt, keine km-Summen über Gruppen

- **Gruppen bleiben garantiert getrennt:** Kilometer- und Tourzahlen werden nirgends mehr über Gruppen hinweg summiert. Die Rangliste (Mitglieder wie Gäste) war schon gruppenscharf – jetzt sind es auch die **Profil-Statistik**, das **Logbuch**, die **Badges** (inkl. Mitgliederliste). Wer (z. B. durch frühere Daten oder Admin-Gruppenwechsel) in zwei Gruppen gefahren ist, sieht pro Gruppe nur die Werte dieser Gruppe.
- Neuer Helfer `_stats_group_id()` (eigene Gruppe, sonst aktive Gruppe); `badge_stats_bulk()` hat einen optionalen Gruppenfilter.
- 234 Tests, py_compile OK.

Neueste Version oben. Die Versionskennung steht in `app.py` (`APP_VERSION`, `APP_BUILD`) und im Footer jeder Seite.

## 1.4.0 – 2026-11-05 (Build e) – Gäste in der Rangliste

- **Gäste als eigene Einträge:** Bestätigte Gäste erscheinen jetzt in allen drei Ranglisten-Tabs (Gesamt, Kilometer, Dieses Jahr) als eigene Zeile mit grauem Avatar, Name und „Gast“-Badge – aggregiert über alle bestätigten Touren (Anzahl, Kilometer, Jahre). Sie können damit auch das Podest erreichen; auf Profilen verlinkt wird bei Gästen natürlich nicht.
- Die Summenzeile aus Build c („Dazu kamen N Gäste …“) ist damit überflüssig und entfällt.
- 233 Tests, py_compile OK.


## 1.4.0 – 2026-11-05 (Build d) – Gästeverzeichnis: Wiederkehrer ohne App-Konto nicht neu tippen

- **Einmal erfassen, immer wieder wählbar:** Beim Anlegen eines Gastes wird er automatisch im Gruppen-**Gästeverzeichnis** gespeichert. Auf jeder anderen Tour erscheint er in der Auswahl „Wieder dabei (bekannter Gast)…“ und wird mit Name und gespeicherter Telefonnummer eingetragen – ein Klick genügt.
- Bestehende Tour-Gäste wurden einmalig ins Verzeichnis übernommen (beim Server-Start); wer schon auf der Tour steht, taucht in der Auswahl nicht erneut auf. Verzeichnis ist gruppenscharf.
- 233 Tests, py_compile OK.


## 1.4.0 – 2026-11-05 (Build c) – Gast-Teilnehmer: Mitfahrer ohne App-Konto abbilden

- **Wer ohne App mitfährt, ist jetzt abgebildet:** Tourleitung/Orga/Admin tragen pro Tour **Gäste** ein (Name + optionale Telefonnummer, Knopf „+ Gast“ unter dem Teilnehmer-Hinzufügen). Gäste erscheinen mit „Gast“-Marke in der Teilnehmer-Liste, zählen zur Kopfzahl („Dabei“), werden bei der **Anwesenheit** mit abgehakt und stehen auf der **druckbaren Teilnehmerliste** samt Telefon.
- **Rangliste:** Die Rangliste bleibt pro App-Mitglied; darüber steht jetzt, wie viele Gäste insgesamt auf den Touren dabei waren („Dazu kamen N Gäste ohne App-Konto“).
- 232 Tests, py_compile OK.


## 1.4.0 – 2026-11-05 (Build b) – Auch die manuelle Pause setzt beim Weiterfahren automatisch fort

- **Nichts mehr zum Weiterdrücken:** Vorher galt: manuell pausiert = bleibt pausiert, bis man „▶ Weiter“ tippt (vergessene Pausen ließen Track-Lücken). Jetzt merkt sich die App den Pausenort – entfernt man sich beim Weiterfahren rund 100 m, geht die Aufzeichnung von selbst wieder an. Die automatische Pause (3 min Stillstand) setzt wie bisher schon ab 25 m fort.
- Der ℹ️-Hinweis „Pause“ erklärt beide Wege.
- 231 Tests, py_compile OK.


## 1.4.0 – 2026-11-05 (Build a) – Tourenliste: Löschen auf Termin-losen Karten + kompakte Leere

- **Löschen fehlte:** Termin-lose Tour-Karten hatten nur Details/Uhr/Bearbeiten – Löschen gab es dort nicht. Jetzt wie bei geplanten Touren ein 🗑-Knopf (Admin/Ersteller) mit Rückfrage.
- **Zwischenraum weg:** Der Leer-Zustand („Keine Touren geplant.“) war mit riesigem Icon und viel Polsterung mehrere Bildzeilen hoch – jetzt kompakt in einer Zeile, klarer formuliert („Keine Touren **mit Termin** geplant.“) mit „Tour erstellen“-Knopf direkt daneben.
- 230 Tests, py_compile OK.


## 1.4.0 – 2026-11-04 (Build q) – Nach dem Beenden direkt nach der Aufzeichnung fragen

- **Kein Vergessen mehr:** Nach „⏹ Fahrt beenden“ erscheint sofort eine deutliche gelbe Rückfrage „Was passiert jetzt mit der Aufzeichnung?“ – mit Knöpfen direkt auf der Live-Karte (und sanftem Scrollen dorthin). Tourleitung/Orga: „✓ Als GPX übernehmen“ (springt zur Übernahme auf der Tourseite); Mitglieder: „⬇ GPX speichern“ (lädt die eigene Aufzeichnung als GPX-Datei) plus Hinweis auf die Tourleitung. „Später“ blendet die Rückfrage weg.
- **Rollen-passend:** Auch der Text in der Status-Leiste passt sich jetzt der Rolle an (Übernehmen vs. GPX speichern). Fehlerfälle ohne Fahrt (Zeitfenster abgelaufen, GPS verweigert) zeigen die Rückfrage nicht.
- 229 Tests, py_compile OK.

## 1.4.0 – 2026-11-04 (Build p) – Audit 6: Live-Status gruppenscharf, 500er-Fix, Doku

- **Audit 6** (Komplett-Audit über die 34 Commits seit Audit 5): Zwei selbst gefundene Befunde behoben –
  ① Der zentrale Live-Status (roter Navbar-Punkt, `/api/live/now`) zeigte auch Mitgliedern **fremder
  Gruppen** Aktivität und Titelanfang; er ist jetzt gruppenscharf wie alle Live-Seiten (Admins sehen alle).
  ② Ein Extremwert als Tour-ID (1e309) lieferte HTTP 500 statt einer sauberen 400-Antwort.
- **Doku:** README + Hilfe beschreiben jetzt Fahrmodus, Auto-Pause, Blitzstart `/fahren` und den
  app-weiten „Fahrt läuft“-Zustand; die veraltete Aussage „endet beim Schließen der Seite“ ist korrigiert.
- 228 Tests, py_compile OK. Vollständiger Bericht: `docs/AUDIT_BERICHT.md` (Audit 6).

## 1.4.0 – 2026-11-04 (Build o) – „Fahrt läuft“/„Fahren“ auf der Tourseite aktualisiert sich selbst

- **Kein Widerspruch mehr nach dem Fahr-Ende:** Blieb die Tourseite offen, zeigte sie weiter „Fahrt läuft“, während die Live-Karte längst „Fahrt starten“ zeigte – die Tourseite musste neu geladen werden. Jetzt schaltet das 30-Sekunden-Polling (wie beim roten Navbar-Punkt) den Knopf selbst um.
- **Technik:** Beide Zustände werden serverseitig gerendert (einer versteckt), der Hook `djoLiveNowUpdate` blendet beim Poll alle 30 s den passenden ein – inklusive frischer Zahlen im Tooltip.
- 227 Tests, py_compile OK.


## 1.4.0 – 2026-11-04 (Build n) – Fix: „Fahrt beenden“ wirklich nicht mehr abgeschnitten

- **Build m war wirkungslos (CSS-Spezifität):** Die Zweizeilig-Regel `#btn-share { white-space: normal }` verlor gegen `#live-bar .btn { white-space: nowrap }` (ID + Klasse schlägt bloße ID) – der Knopf blieb abgeschnitten. Der Selektor heißt jetzt `#live-bar #btn-share` und gewinnt.
- 226 Tests, py_compile OK.


## 1.4.0 – 2026-11-04 (Build m) – „Fahrt beenden“ wieder komplett lesbar

- **Kein „Fahrt bee…“ mehr:** Der rote Knopf darf in der Daumenleiste zweizeilig werden, statt abgeschnitten zu werden (schmale Displays, Großschrift-Modus). Bei sehr schmalen Screens wird die Schrift der Fahrt-Knöpfe zusätzlich leicht verkleinert.
- 226 Tests, py_compile OK.


## 1.4.0 – 2026-11-04 (Build l) – „Als GPX übernehmen“ in der Beenden-Meldung klickbar

- **Direkt zum Sichern:** Die Status-Leiste nach „⏹ Fahrt beenden“ verlinkt jetzt ebenfalls – „Als GPX übernehmen“ springt direkt zum Aufzeichnungs-Bereich (#live-aufzeichnung) der Tourseite.
- **Nachzieher zu Build j:** Auch der Aufzeichnungs-Kasten auf der Tourseite heißt jetzt „(„Fahren“ auf der Live-Karte)“ statt „(„Standort teilen“ …)“.
- **Begriffs-Reste:** Auch Datenschutz-Seite, Hilfe, Tour-Seite (Tooltips/Foto-Hinweis) und das App-Manifest sagen jetzt „Fahrt starten“/„Fahren“ statt „Standort teilen“.
- 225 Tests, py_compile OK.


## 1.4.0 – 2026-11-04 (Build k) – Foto-Meldung mit direktem Fotos-Link

- **„Zur Tour → Fotos“ ist klickbar:** Nach „📷 Foto gespeichert …“ verlinkt die Status-Leiste jetzt direkt zum Fotos-Bereich der Tourseite (#fotos) – kein Umweg mehr über „Zur Tour“ und Scrollen. Der gleiche Link steht auch im ℹ️-Hinweis „Foto“.
- 224 Tests, py_compile OK.


## 1.4.0 – 2026-11-04 (Build j) – Einheitliche Begriffe: „Fahrt starten“ statt „Standort teilen“

- **Ein Knopf, ein Begriff:** „Fahren“ (Tourseite/Navigation) und der grüne Live-Knopf sind dasselbe – er heißt jetzt **„▶ Fahrt starten“** (statt „📍 Standort teilen“) und passt damit zum roten **„⏹ Fahrt beenden“**. Der Tooltip erklärt: Dabei wird der Standort für alle geteilt und der Weg aufgezeichnet.
- **Alle Texte im gleichen Wortlaut:** ℹ️-Hinweise, Zeitfenster-Meldungen („Fahren ist ab dem Vortag der Tour möglich …“) und die 8-Stunden-Meldung nutzen denselben Begriff.
- 223 Tests, py_compile OK.


## 1.4.0 – 2026-11-04 (Build i) – Stopp-Knopf auf der Live-Karte eindeutig benannt

- **„⏹ Fahrt beenden“ statt „Teilen beenden“:** Der rote Knopf unten links auf der Live-Karte heißt jetzt so, wie man denkt – vorher hieß er „Teilen beenden“ und war in der Daumenleiste abgeschnitten („Teilen be…“), sodass man ihn als Fahrt-Stopp nicht erkannt hat.
- **Knopf breiter:** Die Daumenleiste gibt dem Knopf mehr Platz – die Beschriftung passt ganz hinein.
- **Hilfestellung nach dem Beenden:** Die Status-Leiste erinnert danach daran, die Aufzeichnung auf der Tourseite mit „Als GPX übernehmen“ zu sichern; auch der Hinweise-Block nennt den Knopf beim Namen.
- 222 Tests, py_compile OK.


## 1.4.0 – 2026-11-04 (Build h) – Live-Status ohne Seitenwechsel, eine Anzeige statt zweier

- **Live-Punkt aktualisiert sich selbst:** Der rote Navbar-Punkt („N unterwegs · ⏺“) frischt sich jetzt per JS alle 30 Sekunden auf (neuer Endpunkt `/api/live/now`) – er erscheint, während die Fahrt läuft, **ohne** dass man die Seite wechseln muss.
- **Eine Anzeige statt zweier:** Der zusätzliche rote Hinweis neben „Fahren“ auf der Tour-Seite ist entfernt – der zentrale Navbar-Punkt ist die eine Live-Anzeige (die „Fahrt läuft“-Pill unten rechts bleibt als Fernbedienung auf anderen Seiten).
- **„Fahren“ deaktiviert während der Fahrt:** Läuft auf der angeschauten Tour gerade eine Fahrt, zeigt die Tour-Seite statt des grünen „Fahren“-Knopfes einen deaktivierten roten Knopf **„⏺ Fahrt läuft“**.
- 221 Tests, py_compile OK.

## 1.4.0 – 2026-11-04 (Build g) – Fahrt bleibt über Seitenwechsel aktiv

- **Vorher:** Ein Tipp auf einen anderen Menüpunkt beendete „Fahren“ still (die Live-Seite schickte beim Verlassen ein „Teilen beenden“).
- **Jetzt:** Die Fahrt läuft **app-weit weiter** – auf jeder Seite sitzt unten rechts ein roter Punkt **„⏺ Fahrt läuft · Zur Karte · ✕“**: Damit standortet das Handy weiter (alle 30 s), ✕ beendet die Fahrt von überall, „Zur Karte“ springt zurück (die Live-Seite erkennt die laufende Fahrt und macht automatisch weiter). Auf der Live-Seite selbst hat wie gehabt die volle Steuerung Vorrang. Beendet wird nur noch per Knopf (oder automatisch nach 8 Stunden).
- **Speichern:** Die Aufzeichnung läuft automatisch in der Datenbank weiter (auch bei Seitenwechsel, inkl. Auto-Pause). Zum **Festschreiben als Tour-Track** wählt die Tourleitung auf der Tourseite „Als GPX übernehmen“ – bewusst manuell, damit ein geplanter GPX-Track nicht versehentlich überschrieben wird. Unübernommene Aufzeichnungen löschen sich nach 30 Tagen automatisch.
- 220 Tests, py_compile OK, Tracker- und Live-JS per node --check geprüft.

## 1.4.0 – 2026-11-04 (Build f) – Zentraler Live-Punkt + Topo-Karte entfernt

- **Zentraler Live-Punkt:** Läuft gerade eine Fahrt, zeigt die **Navbar auf JEDER Seite** einen roten, pulsierenden Punkt **„N unterwegs · ⏺“** – ein Klick öffnet die Live-Karte. „Unterwegs“ = wer in den letzten 3 Minuten seinen Standort geteilt hat (pausiert zählt mit), **⏺** = es wird gerade aufgezeichnet. Zusätzlich steht auf der betreffenden Tour-Seite neben „Fahren“ ein roter Hinweis **„🔴 N unterwegs · Aufzeichnung läuft“**. Nach 3 Minuten ohne Signal verschwindet der Punkt.
- **Topographische Karte entfernt:** Die Karten-Auswahl auf der Tour-Seite hat nur noch **🗺️ Karte** und **🛰️ Satellit** (der 📐-Knopf war kaum nutzbar und lud langsam).
- 219 Tests, py_compile OK.

## 1.4.0 – 2026-11-04 (Build e) – Live-Karte: EIN Hinweis-Block + Lücke endgültig geschlossen

- **Ein Block statt zwei:** „ℹ️ Info“ oben und „ℹ️ Hinweise“ unten sind zusammengelegt zu **einem** einklappbaren Block direkt unter dem Titel – „Hinweise – Zuschauen · Pause · Aufzeichnung · Foto“ – mit vier klar getrennten, benannten Absätzen (auf dem Desktop zweispaltig). Die Karte ist damit der erste Inhalt auf der Seite.
- **Lücke endgültig weg:** Der Überstand unter der Karte ist entfernt (er erzeugte den leeren Bereich zwischen Karte und „Unterwegs“). Die Daumenleiste liegt jetzt nur noch beim Scrollen über dem Inhalt; am Seitenende sorgt ein Laufraum dafür, dass nichts hinter der Leiste versteckt bleibt.
- 218 Tests, py_compile OK.

## 1.4.0 – 2026-11-04 (Build d) – Live-Karte: Lücke geschlossen, Hinweise als ein Einklapp-Block

- **Lücke gefixt:** Der große Zwischenraum zwischen Karte und „Unterwegs“-Karte auf dem Handy ist weg – der Abstand ist jetzt exakt auf die Daumenleiste bemessen.
- **Hinweise strukturiert:** Die beiden Textblöcke unterhalb der Karte sind jetzt **ein** einklappbarer Block „ℹ️ Hinweise“ mit zwei klaren Absätzen: „Standorte & Teilen“ und „Aufzeichnung & Foto“ (zusammenhängend, wie gewünscht).
- **Oben kompakt:** Die Kopf-Beschreibung heißt jetzt nur noch „ℹ️ Info“ (eingeklappt).
- 218 Tests, py_compile OK.

## 1.4.0 – 2026-11-04 (Build c) – Aufgeräumte Live-Karte + Fahrgemeinschaften eingeklappt

- **Live-Karte:** Der Erklärtext („Was macht die Live-Karte?“) ist jetzt **eingeklappt** und öffnet sich per Tipp – die Seite startet kompakt mit Karte und Knöpfen.
- **Statusmeldungen deutlich sichtbar:** Die Status-Zeile ist keine Mini-Schrift mehr, sondern eine **farbige Leiste** – grau-blau (Info), **grün** (Teilen läuft/Aufzeichnung), **gelb** (Pause/Warnung), **rot** (Fehler). Zustand sofort erkennbar.
- **Tour-Seite:** Der Bereich **Fahrgemeinschaften** steht jetzt **eingeklappt** – auf-/zuklappen per Tipp auf die Überschrift (Anzahl-Ernennung als Punkt rechts bleibt sichtbar).
- 218 Tests, py_compile OK.

## 1.4.0 – 2026-11-04 (Build b) – Smartphone-Bedienung: Daumenleiste + Blitzstart „/fahren“

- **Daumenleiste (Live-Karte, Handy):** Die Knöpfe sind jetzt **unten fest** in der Daumenzone – unten (groß): **📍 Standort teilen · ⏸ Pause/▶ Weiter · 📷 Foto**; darüber eine schmale Reihe mit 🎯 Folgen · 👥 Alle · ⛶ Vollbild. Desktop unverändert.
- **Blitzstart `/fahren`:** Neue Adresse, die automatisch die passende Tour findet (heute zuerst – mit „Dabei“-Anmeldung, sonst die nächste geplante) und die Live-Karte mit direkt startendem Teilen + Aufzeichnung öffnet. Vom Tourenabend an nutzbar, Organisatoren jederzeit.
- **App-Verknüpfungen („Art Widget“):** Android: App-Icon **lange drücken** → **„Fahren starten“**. iPhone: App-Icon lange drücken → Schnellaktion. Damit ist eine Fahrt von jedem Bildschirm aus mit 2–3 Tippens startbar.
- 217 Tests, py_compile OK.

## 1.4.0 – 2026-11-04 (Build a) – Nur Build-Datum korrigiert

- Der letzte Deploy war am 29.10.; `APP_BUILD` jetzt auf den heutigen Stand **2026-11-04 a** (Nutzer-Hinweis: heute ist der 04.11.2026). Neuer Tag → Buchstabe wieder ab „a“. Keine Funktionsänderung.

## 1.4.0 – 2026-10-29 (Build b) – Fahren-Modus: Direktstart + Pause (auto & manuell)

Gemeinsam fahren, von der Tourseite aus:

- **🚴 „Fahren“-Knopf** auf der Tour-Seite (Aktions-Reihe, bei geplanten Touren): öffnet die Live-Karte und startet **Standort teilen + Aufzeichnung automatisch** (Link `?share=1`).
- **Auto-Pause:** Steht man ≈ 3 Minuten an derselben Stelle (Bewegung < 25 m – Einkehr, Pause, Schienenaufpassen), pausiert die Aufzeichnung automatisch und setzt beim Weiterfahren automatisch fort. Statuszeile zeigt „⏸ Pause erkannt …“ bzw. „▶ Weiter geht’s …“.
- **Manueller Pause-Knopf** „⏸ Pause“ / „▶ Weiter“ neben „Standort teilen“ – überschreibt die Auto-Erkennung.
- Wichtig: In der Pause bleibt der Standort für die anderen **sichtbar**, es werden nur keine Spurpunkte mehr gespeichert (der später übernommene GPX-Track enthält die Pause nicht).
- Fotos unterwegs: weiterhin der „📷 Foto“-Knopf auf der Live-Karte (sofort mit Standort in der Tour).
- 216 Tests, py_compile OK.

## 1.4.0 – 2026-10-29 (Build a) – Nur Build-Datum korrigiert

- Die Deploy-Builds bc–bk trugen noch das Datum des Vortags (2026-10-28) – die Session lief über Mitternacht. `APP_BUILD` jetzt auf **2026-10-29 a**, Fußzeile entsprechend. Keine Funktionsänderung.

## 1.4.0 – 2026-10-28 (Build bk) – Video-Startbild: Logik-Invertierung aus bj korrigiert

- **Build bj war wirkungslos** (sorry!): Die Aufruf-Stellen übergaben `fade_in=not wrote_any` – für das erste Segment ergab das **doch** `fade_in=True`, also weiterhin Einblendung aus Schwarz. Der bj-Test prüfte nur die Filterfunktion, nicht die Aufruf-Polarität.
- **Jetzt richtig:** Alle 9 Segment-Stellen übergeben `fade_in=wrote_any` → das erste Segment startet **sichtbar ab Frame 1** (Titelbild), alle folgenden behalten den kurzen Schwarz-Dip als Übergang.
- Der Test prüft jetzt zusätzlich die Polarität der Aufruf-Stellen und die Logik-Semantik.
- 215 Tests, py_compile OK.

## 1.4.0 – 2026-10-28 (Build bj) – WhatsApp-Vorschau: Startbild statt Schwarz

- **Fehler:** Beim Teilen des Videos (z. B. in WhatsApp) zeigte die Chat-Vorschau nur ein schwarzes Bild. Ursache: Das Video blendete mit der allerersten Einstellung aus Schwarz ein – WhatsApp baut die Vorschau aber aus den ersten Videobildern, und Bild 1 war schwarz.
- **Fix:** Das **erste Segment** (Titelfolie) startet jetzt **ohne Schwarz-Einblendung** – Bild 1 zeigt sofort das Titelbild. Alle übergänge zwischen den Folien (dip to black) und das Ausblenden am Ende bleiben unverändert. Die Regel greift robust an allen 9 Segment-Stellen (Titel, Karte, Einkehr, Statistik, Fotos inkl. Fallback, Höhenprofil, Outro): welches Segment auch immer zuerst kommt, es startet sichtbar.
- 215 Tests, py_compile OK.

## 1.4.0 – 2026-10-28 (Build bi) – Fotolöschen repariert (Papierkorb tat nichts)

- **Fehler:** Auf der Tour-Seite löschte der Papierkorb-Knopf (🗑) am Foto nichts – ebenso das GPS-✕. Ursache: Das Sammel-Löschen-Formular („Löschen (n)“) umschloss das gesamte Foto-Raster; die Einzel-Formulare steckten dadurch **verschachtelt** darin. HTML erlaubt das nicht – der Browser verwirft die inneren Formulare stillschweigend, die Knöpfe hingen in keinem Formular mehr.
- **Fix:** Das Bulk-Formular ist jetzt ein leeres Formular über der Liste; Foto-Checkboxen und der Sammel-Löschen-Knopf sind über `form="bulk-form"` damit verknüpft (Standard-HTML-Mechanismus). Die Einzel-Knöpfe 🗑 / GPS-✕ liegen in ihren eigenen, nicht mehr verschachtelten Formularen. Zwei alte doppelte Restzeilen im Template entfernt. Sammel-Löschen und Auswahl („Alle/Keine“) funktionieren unverändert.
- 214 Tests, py_compile OK.

## 1.4.0 – 2026-10-28 (Build bh) – Bis zu drei Einkehr-Stopps pro Tour

Bisher konnte eine Tour nur EINE geplante Einkehr haben. Jetzt:

- **Tour anlegen/bearbeiten:** Nach der ersten Einkehr-Zeile erscheint der Knopf **„➕ Weiteren Stopp hinzufügen“** – bis zu **drei Stopps**, jeder wahlweise aus der Gastro-Liste oder als Freitext.
- **Anzeige überall in Reihenfolge:** Tour-Kopf („Einkehr: … · 2. Stopp: … · 3. Stopp: …“ mit allen Warnungen je Stopp), Druckansicht, Tourtag-Erinnerung, Kalender-Eintrag und Vorlesen („Einkehr bei …, später außerdem Einkehr bei …“).
- **Video:** Alle Gastro-Stopps mit Streckenkilometer in der Einkehr-Folie (Freitext-Stopps ohne Position erscheinen dort nicht).
- **Tour „nochmal fahren“** übernimmt alle drei Stopps. Die Karte („Als Einkehr festlegen“) setzt weiterhin die Haupt-Einkehr; Stopps 2/3 ändern sich im Formular.
- 213 Tests, py_compile OK, Template-Checks OK.

## 1.4.0 – 2026-10-28 (Build bg) – Einkehr-Auswahl alphabetisch (Ä/Ö/Ü richtig)

- Das Dropdown **„Geplante Einkehr“** in den Tour-Formularen (Anlegen/Bearbeiten) nutzt jetzt dieselbe menschliche A–Z-Sortierung wie die Gastroliste (Build bf) – vorher hingen Namen mit Ä/Ö/Ü hinten.
- 212 Tests, py_compile OK.

## 1.4.0 – 2026-10-28 (Build bf) – Gastroliste: echte A–Z-Sortierung + Sortierung auswählbar

Die Liste war technisch, nicht menschlich sortiert: SQLite hängt Namen mit Ä/Ö/Ü am Anfang (und Kleinbuchstaben) hinter „Z“ – deshalb wirkte sie nicht mehr alphabetisch. Jetzt:

- **A–Z wie im Telefonbuch:** Ä wie A, Ö wie O, Ü wie U, ß wie ss, Groß-/Kleinschreibung egal (Standard, auch ohne JavaScript).
- **Sortierung auswählbar** über Knöpfe über der Liste (aktiver Knopf ist dunkel): 🔤 **A–Z** · ⭐ **Bewertung** (beste zuerst, ohne Wert hinten) · 🆕 **Neueste** (zuletzt hinzugefügt zuerst) · 📍 **Nähe zu mir** · 🏁 **Nähe zum Treffpunkt** (wie bisher).
- 212 Tests, py_compile OK, Sortier-JS mit Runtime-Smoke geprüft.

## 1.4.0 – 2026-10-28 (Build be) – Fahrzeit manuell nachtragen

Touren, deren GPX keine Zeitstempel hat (z. B. gezeichnete/geplante Route oder aufgenommener Track ohne Uhrzeit), zeigten bei ⏱ nur „–“ – Fahrzeit und Ø-Tempo waren nicht nachträglich korrigierbar. Jetzt:

- **Tour bearbeiten** hat ein Feld **„Fahrzeit (manuell)“** (Stunden:Minuten, z. B. 3:30). Die App trägt die Fahrzeit ein und rechnet das **Ø-Tempo** automatisch aus der Strecke.
- Zeigt die Formular-Hilfe den aktuell automatisch ermittelten Wert an (falls vorhanden). Feld **leeren** = Wert wird automatisch neu aus dem GPX ermittelt.
- Das Admin-„GPX-Kennzahlen nachrechnen“ überschreibt manuelle Zeiten nicht mehr.
- 211 Tests, py_compile OK.

## 1.4.0 – 2026-10-28 (Build bd) – Orte-Formular mobil: Karte zuerst

- Wie beim Gastro-Formular: Auf dem Smartphone erscheint die **Position auf Karte** zuerst, die Eingabe-Felder danach. Desktop unverändert (Details links, Karte rechts).
- 209 Tests, py_compile OK.

## 1.4.0 – 2026-10-28 (Build bc) – Gastro-Formular mobil: Karte + Suche zuerst

- Auf dem Smartphone erscheinen jetzt **Position auf Karte** und **Eintrag suchen & importieren** zuerst, die manuelle Eingabe danach – passend zum Ablauf „Position/Import → Formular prüfen → Speichern“ (und die Suche nutzt den Kartenausschnitt). Der Übernehmen-Hinweis scrollt zum Formular. Desktop unverändert (Formular links, Karte rechts).
- 209 Tests, py_compile OK.

## 1.4.0 – 2026-10-28 (Build bb) – Einheitlicher mobiler Kartenschutz auf allen Seiten

- **Problem:** Sofort aktive Karten fingen auf dem Handy das Wischen ab (ein Finger = Karte ziehen statt Seite scrollen). Nur Touren und Gruppen-Karte hatten einen Schutz – Gastro, Orte, Startseite, Live und Formulare nicht.
- **Lösung (Standard-Muster, wie Google-Maps-Embeds/Leaflet.GestureHandling):** Neues zentrales `static/js/map-touch.js`, das sich automatisch in **jede** Leaflet-Karte einklinkt: Karte startet mobil ohne Ein-Finger-Ziehen mit Overlay „Tippen zum Aktivieren“, 🔒-Knopf sperrt wieder, **zwei Finger funktionieren jederzeit**. Desktop unverändert.
- Die beiden bisherigen Inline-Umsetzungen (Tourseite, Gruppen-Karte) entfernt – ein Code für alle: Touren-Detail, Start-/Touren-/Archiv-Mini-Karten, Gruppen-Karte, Erkundung, Gastro (Liste/Detail/Formular), Orte, Tour-Formular, Live, Admin, GPX-Modal. Positionierer-Formulare zeigen einen eigenen Hinweis („Tippen aktivieren – dann klicken setzt die Position“); die Druckansicht ist ausgenommen.
- 209 Tests, py_compile OK.

## 1.4.0 – 2026-10-28 (Build ba) – Gastro-Suchkarte: doppelte Lupe, richtige Weg-Beschreibung

- **Doppelte Lupe behoben:** Der Karten-Kopf trug dieselbe Such-Lupe wie der Suchknopf darunter – der Kopf hat jetzt ein „Import“-Symbol (Wolke mit Pfeil), die Lupe gehört allein zum Suchknopf.
- **Anleitung korrigiert:** „links auf die Karte klicken“ stimmte in keinem Layout – die Karte liegt (Handy wie Desktop) **direkt über der Suchkarte**; der Hinweis sagt das jetzt korrekt.
- 208 Tests, py_compile OK.

## 1.4.0 – 2026-10-28 (Build az) – Deploy-Datum aktuell halten

- Die Deploy-ZIPs und der Footer trugen weiter das Datum alter Builds (2026-10-15), weil `APP_BUILD` bei neueren Auslieferungen nicht mitgezogen hatte. Das Datum ist jetzt aktuell (2026-10-28), und `make_deploy_zip.py` **warnt künftig**, wenn das Build-Datum nicht dem heutigen Tag entspricht – so bleibt jedes Paket sofort am Namen als „frisch“ erkennbar. README-Abschnitt „Auslieferung per FTP“ um den Hinweis ergänzt (neuer Tag = wieder bei „a“ beginnen).
- 208 Tests, py_compile OK.

## 1.4.0 – 2026-10-17 (Build ay) – Gastro-Formular: Umlaut-Fehler und Führung

- **Fehler behoben:** Die Suchkarte zeigte „Eintrag suchen &amp;amp; importieren“ – ein `&amp;` im Jinja-Ausdruck wurde doppelt maskiert. Jetzt korrekt „Eintrag suchen & importieren“.
- **Bedienung intuitiver:** Die Suchkarte erklärt den Ablauf in drei Schritten (suchen oder Karte klicken → Felder werden übernommen → prüfen & speichern). Nach dem Übernehmen eines Treffers erscheint die Erfolgsmeldung jetzt auch direkt über dem Speichern-Knopf, auf dem Handy scrollt die Seite automatisch zum Formular und das Namensfeld grünt kurz.
- 207 Tests, py_compile OK.

## 1.4.0 – 2026-10-17 (Build ax) – Vorschau-Abbruch nach der Statistikfolie behoben

- **Fehler behoben (Build-aw-Nachzieher):** Die neue Uhrzeit-Leiste nutzte die Variable `mmSide` (Mini-Karten-Breite), bevor sie deklariert wurde – JavaScript wirft dafür einen Referenzfehler, die Browser-Vorschau frozte daraufhin nach der Statistikfolie (direkt vor den Fotos), die Musik lief weiter. Die Deklaration steht jetzt vor der ersten Nutzung.
- **Sicherheitsnetz:** Echte Vorschau-Fehler werden jetzt als „Vorschau-Fehler: …“ im Status angezeigt (Musik stoppt, Knöpfe kehren zurück), statt die Vorschau stumm einfrieren zu lassen. `node --check` erkennt solche Laufzeit-Fehler nicht – deshalb der neue Test, der Deklarations-Reihenfolge prüft.
- 206 Tests, py_compile OK.

## 1.4.0 – 2026-10-17 (Build aw) – Vorschau zeigt die Foto-Uhrzeit wie das MP4

- Die **Browser-Vorschau** der Video-Seite zeichnet in der Unterschrift-Leiste jetzt dieselbe **gelbe Uhrzeit über dem Text** wie der fertige MP4-Export (bislang zeigte sie nur Text bzw. Datum – deshalb wirkte die Uhrzeit im MP4-Abgleich als „verschwunden“; das MP4 selbst war zu jeder Zeit korrekt).
- Der Gruppenname rechts unten weicht der Mini-Karte aus, statt von ihr überdeckt zu werden.
- 205 Tests, py_compile OK.

## 1.4.0 – 2026-10-17 (Build av) – Audit 5: Lock-Race behoben, Video-Doku ergänzt

Fünftes Komplett-Audit (Zuwachs aj–au), Bericht in `docs/AUDIT_BERICHT.md`. Umgesetzt aus dem Audit:

- **Lock-Race bei langen Video-Renders behoben (B1):** Seit ar gilt eine Render-Sperre nach 4 min als verwaist – ein legitimer langer Render erneuerte sie aber nicht, ein zweiter Klick hätte einen parallelen ffmpeg gestartet. Die Sperre wird jetzt während des Renderns regelmäßig „angefasst“ (je Foto + vor dem Final-Render); nur wirklich tote Sperren verfallen nach 4 min.
- **Doku-Lücke geschlossen (B2):** Hilfe → Fotos um „🎬 Videos zur Tour“ ergänzt (die Video-Seite ist für alle Mitglieder), README-Foto-Kapitel um die Video-Erstellung ergänzt. Pakete-Admin/Python-3.11-Themen waren bereits in README + INSTALLATION dokumentiert.
- 204 Tests, py_compile OK.

## 1.4.0 – 2026-10-15 (Build au) – Doku: Pakete-Admin im README

- README (Deployment-Kurzfassung) um einen Absatz ergänzt: Admin → „Pakete installieren“ prüft und repariert Python-Pakete ohne SSH – inkl. Hinweis auf den funktionalen Pillow-Test, der nach Python-Updates des Hostings (3.9 → 3.11) alte, nicht mehr ladende Paket-Builds zuverlässig erkennt. Reine Dokumentation, keine Code-Änderung.
- 203 Tests, py_compile OK.

## 1.4.0 – 2026-10-15 (Build at) – Mini-Karte auf Höhe von Uhrzeit und Text

- Die 🗺️-Mini-Karte auf den Fotos hat jetzt dieselbe Unterkante wie die Unterschrift-Leiste – sie liegt also genau auf Höhe von Uhrzeit und Text (vorher schwebte sie eine Kartenhöhe darüber). Gilt für MP4 und Vorschau.
- Die Unterschrift-Leiste weicht dem Karten-Kasten rechts aus (Text-Umbruch und Leistenbreite passend), damit kein Text unter der Karte liegt.
- 203 Tests, py_compile OK.

## 1.4.0 – 2026-10-15 (Build as) – Mini-Karte tiefer, Fahrten wieder ruhiger

- **Mini-Karte auf Fotos weiter unten:** Der 🗺️-Kartenausschnitt saß zu weit im Bild – jetzt liegt er knapp über der Unterschrift-Leiste (bzw. nah an der Unterkante), im MP4 und in der Vorschau.
- **Fahrten wieder ruhiger, ohne den Server zu überfordern:** Das Bewegungsfenster ist zurück auf 1,5-fach (feineres End-Downscaling verschmilzt die Pixel-Schritte), und wenn FFmpeg `tmix` beherrscht, bekommt jede Foto-Fahrt einen hauchfeinen Motion-Blur (Ein-Bild-Glättung) – Schritte werden vom Auge als ruhige Bewegung wahrgenommen. Unterschriften/Logo bleiben scharf, sie werden erst danach aufgelegt. Die 2-fach-Überhöhung bleibt (Ressourcen!), der Filter wird vorher geprüft und sonst einfach weggelassen.
- 202 Tests, py_compile OK.

## 1.4.0 – 2026-10-15 (Build ar) – Video-Render schonender gerechnet

Nach Meldung „kein Video mehr erstellen“ (Abbruch nach 2–3 s ohne Meldung): Der Server bricht den Auftrag offensichtlich früh ab – die Rechenlast der letzten Optimierungen (3-fach überhöhter Zoom, 30 fps) übersteigt vermutlich die Ressourcen des Shared Hostings. Gegenmaßnahmen:

- **Zoom-Rechnung entlastet:** 2-fach Überhöhung mit 1,25-fachem Bewegungsfenster statt 3-fach/1,5-fach – deutlich weniger RAM und Rechenzeit, die Bewegung bleibt glatt (Schrittweite weiter unter 1 Ausgabepixel).
- **Verwaiste Videosperren** werden schon nach 4 min statt 15 min abgebaut; **Überreste abgestürzter Renders** in /tmp räumt der nächste Render automatisch weg (schützt vor vollem /tmp).
- 201 Tests, py_compile OK.

## 1.4.0 – 2026-10-15 (Build aq) – Kein Foto mehr ohne Bewegung, Effekte kräftiger

- **Fehler behoben:** Bei bündig containeden Fotos (z. B. Hochkant-Foto im Hochkant-Video) blieben Panorama-Fahrten in der Vorschau nichtig bzw. bewegten im MP4 nur die schwarzen Balken. Jetzt arbeiten Vorschau und MP4 mit demselben Fenster-Modell wie FFmpeg (Ausschnitt über das komplette Bild inkl. Balken) – jeder Effekt bewegt sich auf jedem Foto sichtbar.
- **Kräftigere Bewegungen:** Zoom 9 % → 13 %, Panorama-Fahrten 9 % → 16 % Bildschirm-Einzug, Diagonalen bis 20 %, Drift stärker. Die Effekt-Helfer logieren auf Modulebene – Vorschau, MP4-Export und Tests lesen dieselben Verläufe.
- 200 Tests, py_compile OK.

## 1.4.0 – 2026-10-15 (Build ap) – Ken-Burns-Effekt-Vielfalt

Bisher wechselten sich beim Foto-Video nur Zoom rein / Zoom raus ab. Jetzt 10 Varianten:

- **Zoom rein / raus** (bisher), **Panorama-Fahrten** links→rechts, rechts→links, oben→unten, unten→oben (Kamera fährt über das Foto, leicht eingezoomt), **Diagonalen** (Fahrt über Eck plus sanfter Zoom, hin und zurück) und **Drift** für Hochkant-Fotos (Zoom mit seitlicher Drift).
- Hochkant-Fotos bekommen keine vertikalen Fahrten – sonst würden die schwarzen Safe-Area-Balken mitschieben. Die Effekt-Reihenfolge ist pro Tour versetzt, nicht jede Tour gleich.
- Die Browser-Vorschau auf der Video-Seite zeigt dieselben Effekte wie der fertige MP4-Export (gleiche Namen und Verläufe).
- 199 Tests, py_compile OK.

## 1.4.0 – 2026-10-15 (Build ao) – Foto-Zoom noch ruhiger

Nachlegen beim Ken-Burns-Zoom der Fotos:

- **30 fps statt 25:** 25 Bilder/s laufen auf 60-Hz-Handy-/PC-Displays in ungleichem Takt (2-3-2-3-Bilder) – genau das fühlt sich bei langsamen Zoomfahrten wie Ruckeln an. 30 fps teilen durch 60 genau, die Bewegung ist gleichmäßig.
- **Höherwertige Zwischen-Segmente:** Die Einzel-Segmente werden jetzt mit CRF 18 statt Werkseinstellung encodiert (Codec-Erkennung einmalig am Anfang) – der finale Zusammenbau verstärkt weniger Artefakte, Himmel/Feinstruktur schimmern nicht.
- 196 Tests, py_compile OK.

## 1.4.0 – 2026-10-15 (Build an) – Flüssigere Video-Bewegungseffekte

Das leichte Ruckeln bei der Video-Erstellung hatte drei Ursachen, alle behoben:

- **Ken-Burns-Zoom (Fotos):** FFmpeg `zoompan` rundet den Bildausschnitt auf ganze Pixel – bei nur 2-facher Überhöhung sichtbar als feines Zittern. Jetzt wird 3-fach überhöht gerechnet, das Zoomfenster auf 1,5-facher Größe ausgewertet und erst danach per Lanczos aufs Zielmaß verkleinert (subpixelgenaue Bewegung). Zusätzlich Sanftanlauf aus (Cosinus) statt konstanter Zoom-Fahrt.
- **Karten-Animation:** Der Track baute sich bisher in nur 16 sichtbaren Sprüngen auf. Jetzt entsteht ein Kartenaufbau-Bild pro Video-Bild (25/s) – flüssiges Wachstum wie in der Browser-Vorschau.
- **Statistik-/Einkehr-/Höhenprofil-Folien:** Bisher 15 Einzelbilder/s, die auf die 25-fps-Ausgabe umgetaktet wurden (unglemäßige Bildfolge). Jetzt mit voller Framerate und exakter Bild-Taktung.
- Render-Timeouts für die jetzt größeren Segmente erhöht (60 → 180 s je Segment). 196 Tests, py_compile OK.

## 1.4.0 – 2026-10-15 (Build am) – Video-Anzahlen neben den Foto-Anzahlen

- **Archiv:** Die Listen zeigen jetzt auch die Anzahl der Videos – in der Tabelle neben der Foto-Spalte (Kopf „📷 🎬") und in den Handy-Karten („🎬 N" neben „📷 N"). Die Zahl kommt aus je einer Sammel-Abfrage (kein N+1), sowohl in der Liste als auch in der Archiv-Suche.
- **Tourseite:** Der Fotos-Karten-Kopf zeigt neben dem Foto-Zähler ein 🎬-Badge mit der Video-Anzahl (bislang stand die Zahl nur ganz unten in der Video-Karte).
- 193 Tests, py_compile OK.

## 1.4.0 – 2026-10-15 (Build al) – Doppelten Video-Knopf entfernt

- Auf fertigen Touren mit Fotos standen zwei Knöpfe mit demselben Ziel („Rückblick & Video“ und „Video“ – beides öffnete die Foto-Video-Seite). Jetzt gibt es nur noch **einen** Knopf: fertige Touren zeigen den gelben „Rückblick & Video“-Knopf, geplante Touren mit Fotos weiterhin den schlichten „Video“-Knopf.
- 189 Tests, py_compile OK.

## 1.4.0 – 2026-10-15 (Build ak) – Tourseite kompakter

Screenshot-Feedback zur Tourseite auf dem Handy umgesetzt:

- **Aktions-Knöpfe:** Der Vorlesen-Knopf steht jetzt als erster Knopf in der normalen Aktions-Leiste (statt eigener Zeile) und ist für alle da; die Orga-Knöpfe folgen danach.
- **Handy-Kurzschrift:** Unter 576 px zeigen die Knöpfe Kurzwörter (z. B. „Vorlage", „Nochmal", „Löschen") – alles passt in eine Umbrech-Zeile. Mit Großer Schrift bleiben die vollen Texte aktiv; bei Fensterbreiten-Wechsel schaltet die Beschriftung automatisch um.
- **Kennzahlen-Kacheln:** Auf dem Handy rast die Kachel-Reihe in einem 3-spaltigen Raster ein (Wetter/Wind-Kacheln breiter), Texte laufen nicht mehr aus der Kachel. Die Pausen-Kachel zeigt platzsparend „X min", den vollen Text beim Tippen (Titel).
- 188 Tests, py_compile, node --check OK.

## 1.4.0 – 2026-10-15 (Build aj) – Vorlesen-Knopf und Pausen-Erkennung

Die beiden Wünsche aus dem Audit-4-Gespräch („Ideen für später", Platz 1 und 3):

**🔊 Vorlesen-Knopf (Tourseite, für alle)**
- Neuer Knopf **„Vorlesen"** unter der Datumszeile liest die Tourdetails per **Web Speech API** vor –
  ohne neue Pakete, auf Handy und Desktop. Vorgelesen werden: Titel, Wochentag/Datum/Uhrzeit,
  Schwierigkeit, abgesagt/abgeschlossen (bei Absage mit Grund), Treffpunkt, Kilometer, Höhenmeter,
  Fahrzeit, Ø-Tempo, Pausen, angemeldete Fahrer und die geplante Einkehr – als kurze, natürliche
  Sätze („3 Stunden 47 Minuten", Komma statt Punkt). Knopf wechselt bei laufender Vorlesung auf
  **„Stoppen"**, endet automatisch, stoppt beim Verlassen der Seite/Tab-Wechsel. Browser ohne
  Sprachausgabe blenden den Knopf aus. Funktion `toggleReadAloud()` global (onclick-Regel).

**⏸️ Pausen-Erkennung (GPX-Zeitstempel)**
- Neue Helfer `_gpx_pauses()` / `_pauses_summary()`: Als Pause zählt Stehen unter 3,6 km/h oder eine
  Lücke (Gerät aus), sobald sie **≥ 3 Minuten** andauert; Bewegung unterbricht. Gleiches Schwellen-
  wert-Prinzip wie die gpxpy-Fahrzeit.
- Zwei neue Spalten `tours.gpx_pauses_n` / `gpx_pauses_s` (Migration automatisch). Berechnet beim
  GPX-Upload, beim „Live-Aufzeichnung übernehmen" und beim Admin-Nachrechnen; ältere Touren mit
  Fahrzeit bekommen die Pausen einmalig beim ersten Aufruf der Tourseite nachgetragen.
- Neue Kachel **„n · Pausen · x min"** in der Kennzahlen-Zeile der Tourseite (nur bei Zeitstempeln;
  im mobilen Kompaktmodus und Großschrift-Modus korrekt eingebunden). Der Vorlesetext nennt die
  Pausen mit („3 Pausen, insgesamt 42 Minuten").
- 7 neue Tests (187 gesamt).

Geänderte Dateien: `app.py`, `models.py`, `templates/touren/detail.html`, `templates/hilfe.html`,
`tests/test_build_ag.py`, `README.md`, `CHANGELOG.md`.

## 1.4.0 – 2026-10-15 (Build ai) – Komplett-Audit 4: sauber, ein Verhärtungspunkt

Viertes Komplett-Audit (Bericht: `docs/AUDIT_BERICHT.md`, Abschnitt oben): statisches Review des
Zuwachses seit Audit 3 + dynamischer Lauf (XSS-Sweep über ~40 Seiten × 3 Rollen mit scharfen
Nutzdaten, 36 Mandanten-Proben, Path Traversal, 104 POST-Routen gefuzzt, Rate-Limits, Header,
Cookie-Flags, JS-Syntaxcheck, CVE-Scan, SQL-Profiling). **Keine Sicherheits- oder Stabilitätslücke.**
SQL-Zählungen 6–16 je Seite, Seitengrößen 26–50 KB.

- **Fotos/Videos im Service-Worker jetzt network-first** (Befund A1, Mittel/Datenschutz): Bisher
  cache-first – ein ausgeloggter Browser auf einem geteilten Gerät bekam bereits gesehene Fotos
  weiter aus dem Cache, obwohl der Server 404 liefert. Jetzt gilt der Server-404; offline
  (Radtour ohne Netz) springt weiterhin der Cache ein.
- Dokumentiert als bewusst gelassen: Logout per GET (Nuisance-CSRF), Referrer-Redirect bei der
  Routenbewertung, kein Rate-Limit am Live-Standort (dort ohnehin 1 Punkt/3 s begrenzt), Gastro
  gruppenübergreifend (Design Audit 3).
- 1 neuer Test (180 gesamt).

Geänderte Dateien: `static/sw.js`, `app.py` (Build-Kennung), `tests/test_build_ag.py`,
`docs/AUDIT_BERICHT.md`, `CHANGELOG.md`.

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
