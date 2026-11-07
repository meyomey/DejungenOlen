# Changelog – De jungen Olen
## 1.5.0 – 2026-11-07 (Build an) – Kein Sperren im Vollbild, Sperrknopf über dem Info-Block
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

## 1.5.0 – 2026-11-07 (Build am) – Live-Karte lässt sich immer sperren, dann scrollt die Seite
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

## 1.5.0 – 2026-11-07 (Build al) – Im Stromsparmodus zoomt nur die Karte, nicht der Bildschirm
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

## 1.5.0 – 2026-11-07 (Build ak) – Zweimal tippen zoomt die Karte nicht mehr
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

## 1.5.0 – 2026-11-07 (Build aj) – Grüne Selbsttest-Boxen entfernt
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

## 1.5.0 – 2026-11-07 (Build ai) – Zweimal tippen funktioniert jetzt auch bei großgestellter Karte
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

## 1.5.0 – 2026-11-07 (Build ah) – Im hellen Stromspar-Zustand ist die Karte wieder bedienbar
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

## 1.5.0 – 2026-11-07 (Build ag) – Einmal tippen dunkelt jetzt jedes Mal wieder ab
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

## 1.5.0 – 2026-11-07 (Build af) – Stromspar mit zwei Stufen, Hinweis versperrt die Karte nicht mehr
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

## 1.5.0 – 2026-11-07 (Build ae) – „Grün, aber wirkungslos" abgeschafft + Abdunklung wirklich ganzflächig
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

## 1.5.0 – 2026-11-07 (Build ad) – „Bildschirm bleibt an" endlich wirksam + Stromspar neu gedacht
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

## 1.5.0 – 2026-11-07 (Build ac) – „Bildschirm bleibt an": der Fehler lag im Video (es war stumm)
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

## 1.5.0 – 2026-11-07 (Build ab) – „Bildschirm bleibt an" hält jetzt wirklich (zweiter Weg) + feinere Leiste
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

## 1.5.0 – 2026-11-07 (Build aa) – Live-Karte: die Karte bekommt den Bildschirm
- **Wunsch:** „Vom Wichtigsten, der Karte, kann man fast nichts mehr sehen. Die Knöpfe nehmen viel zu viel Platz ein."
- **Oben: eine Titelzeile statt vier Blöcke.** Zurück-Pfeil · Titel · ℹ️ in einer Zeile (≈ 38 px statt über 300 px). Datum, Startzeit und Treffpunkt sowie der ganze Hinweise-Block stecken im ℹ️-Aufklapper; die Statusmeldung ist ein kleiner Chip **auf** der Karte (zwei Zeilen, antippen klappt die ganze Meldung auf – die Links nach Fahrtende bleiben erreichbar).
- **Unten: drei große Knöpfe statt fünf Reihen.** Fahrt beenden/starten · Pause · Foto sind jetzt **58 px hoch** (vorher 50) und der Fahrt-Knopf bekommt am meisten Breite – der Rest der Leiste ist weg (≈ 70 px statt ≈ 200 px).
- **Nebenfunktionen als Symbole auf der Karte:** Folgen · Alle · Vollbild · Bildschirm an · Stromspar sitzen als 42-px-Symbole unten rechts über der Leiste. Aktive Funktionen sind eingefärbt (Bildschirm: orange, wenn gewünscht, aber nicht greifend), jeder Knopf nennt beim Antippen kurz seinen Namen.
- **Symbole als Inline-SVG statt Icon-Schrift:** Unterwegs ohne Netz lädt Bootstrap Icons nicht vom CDN – die Knöpfe wären leere Kästchen. Die Symbole stecken jetzt direkt im HTML (auch der Verschiebe-Hinweis und der ℹ️-Knopf kommen ohne Icon-Font aus).
- **Messung im Browser** (390×844): Karte 676 px hoch, beginnt bei y = 232 statt 318, Kopfzeile 38 px, Leiste 70 px; bei 360×640 bleibt die Karte 472 px hoch, kein Symbol liegt auf Leiste oder Karte-Chip.
- 12 neue Tests (`tests/test_build_aa.py`), 322 gesamt, py_compile OK.

Geänderte Dateien: `templates/touren/live.html`, `app.py`, `tests/test_build_aa.py`, `tests/test_build_ag.py`,
`tests/test_live.py`, `CHANGELOG.md`, `templates/hilfe.html`.

## 1.5.0 – 2026-11-06 (Build z) – Radkarte (CyclOSM) auf jeder Karte
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

## 1.5.0 – 2026-11-06 (Build y) – „Bildschirm bleibt an“ hält jetzt wirklich an
- **Fehler:** Nach dem Doppeltipp stand „🔆 Bildschirm bleibt an“, der Bildschirm ging aber trotzdem aus – auch in der Handy-Simulation des Browsers, also kein Geräteproblem. Ursache: Der Wake-Lock wurde **einmal** angefordert und nie wieder. Lässt der Browser ihn fallen (Tab verlassen, Display gesperrt, App-Wechsel, Akkusparmodus – bei jeder Aufnahme des Handys fällt er weg), blieb die Erfolgsmeldung stehen, aber nichts hielt den Bildschirm mehr. Der 60-s-Wächter griff nur bei laufender Fahrt/Folgen/Stromspar – nicht beim reinen Doppeltipp.
- **Jetzt:** Die Seite merkt sich den **Wunsch** (`wakeWanted`) und holt den Lock bei jeder Rückkehr neu: bei `visibilitychange` (zurück im Tab, entsperrt), bei jedem normalen Tipp und über einen **20-s-Wächter** (vorher 60 s und nur bei Fahrt). Genau so verlangt es der Browser: eine neue Anforderung ist nur bei sichtbarer Seite erlaubt.
- **Doppeltipp schaltet um:** einmal an, nochmal aus („🌙 Bildschirm darf wieder aus“) – vorher war ein zweiter Doppeltipp wirkungslos.
- **Ehrliche Rückmeldung:** Der Erfolgstext kommt nur, wenn der Lock wirklich greift. Sonst nennt die Meldung den Grund (kein https, Energiesparmodus/Akku, Browser ohne Unterstützung).
- **Neuer Knopf „🔆 Bildschirm an“** in der Leiste (dritte Reihe, volle Breite): setzt das Wachhalten ohne laufende Fahrt und zeigt den echten Zustand – „Bildschirm bleibt an“, wenn er gerade hält, sonst „Bildschirm an (greift nicht)“.
- **Nebenbei:** Ein bestehender Test (`/fahren`) rechnete mit dem UTC-Datum des Servers statt mit Berliner Zeit und war zwischen 22 und 24 Uhr UTC rot – jetzt `_berlin_today()` wie in der App.
- 288 Tests, py_compile OK.

## 1.5.0 – 2026-11-06 (Build x) – Live-Karte auf dem Handy lesbar: Guard unter dem Zoom, volle Knopf-Beschriftungen
- **„Zum Verschieben antippen“ und 🔒 lagen auf dem „−“**: Das Zoom-Bedienfeld von Leaflet beginnt bei 10 px, ist mit zwei Knöpfen ≈ 70 px hoch – die Pill begann bei 56 px und nahm das Herauszoomen weg. Beide sitzen jetzt bei `top: 80px; left: 10px`, also **unter** dem Zoom und bündig mit ihm; der Karten-Toast rutscht mit auf 124 px.
- **Abgeschnittene Knöpfe („Fol…“, „Voll…“, „Sta…“, „Str…“)**: Die fünf Sekundär-Knöpfe quetschten sich in eine Zeile und wurden mit Ellipse gekürzt. Jetzt ein 3+2-Raster (Folgen · Alle · Vollbild / Standard · Stromspar) mit voller Beschriftung und Umbruch statt Ellipse – die Höhe der Leiste bleibt bei ≈ 155 px.
- **Beschriftung bleibt beim Umschalten**: Vollbild und Kartenstil tauschen nur noch den Text im Knopf (eigene Spans), das Icon bleibt stehen – vorher wurde der Vollbild-Knopf zum nackten „⛶“.
- **Nebenbefund, mitbehoben:** Der Laufraum unter der Daumenleiste war wirkungslos – `base.html` setzt sein `body { padding-bottom: 58px }` später im Dokument und gewann bei gleicher Spezifität (58 px statt 174 px), die letzten Inhalte lagen hinter der Leiste. Jetzt `html body { padding-bottom: 222px }` (0,0,2), passend zur neuen Leistenhöhe.
- 284 Tests, py_compile OK.

## 1.5.0 – 2026-11-06 (Build w) – Live-Karte wieder sperrbar: 🔒-Knopf nach dem Freischalten
- Nach dem Freischalten des Ecken-Guards (Pill „Zum Verschieben antippen“ oben links) ließ sich die Karte nicht wieder sperren – die Pill war weg und die Seite scrollte fortan nicht mehr normal. Jetzt erscheint beim Freischalten an derselben Ecke der **🔒-Knopf**: Er sperrt die Karte wieder (Seite scrollt normal, Pill kommt zurück).
- Der Guard liest seinen Zustand **selbst** (`setLiveGuard()` ohne Argumente, `guardArmed = true` als Startwert): gesperrt = kein Fahrt/Folgen/Vollbild **und** nicht freigetippt. Damit bleibt der Zustand auch nach Fahrtende, Folgen-Aus oder Drehen des Geräts konsistent (Neu-Bewertung zusätzlich bei `resize` und nach dem Ziehen der Karte).
- Während **Fahrt, Folgen und Vollbild** sind Pill und 🔒 ausgeblendet – dort muss Verschieben sofort gehen (wie seit Build u).
- Hilfe-Seite erklärt das Sperren auf der Live-Karte.
- 280 Tests, py_compile OK.

## 1.5.0 – 2026-11-06 (Build v) – Live-Karte-Nachjustieren: Scrollen, Knopf-Zustand, ehrlicher Doppeltipp
- Scrollen wieder leicht: Der Antipp-Schutz kehrt auf der Live-Karte zurück – aber als dezente Pill OBEN LINKS statt als Overlay mitten auf der Karte. Ohne laufende Fahrt scrollt die Seite normal, die Pill schaltet die Karte zum Verschieben frei; sobald Fahrt/Folgen/Vollbild aktiv sind, schaltet der Schutz automatisch ab (sofortiges Verschieben) und kehrt danach zurück.
- Der 🚵-Knopf zeigt jetzt sichtbar den aktiven Kartenstil („🚵 Standard“ hell / „🚵 Radkarte“ gelb) – vorher blieb die Hell-Färbung drauf und überdeckte die Gelb-Markierung.
- Doppeltipp-Rückmeldung erscheint als Toast AUF der Karte (vorher nur Statuszeile darüber); unterstützt das Gerät das Bildschirm-Wachhalten nicht (älteres iOS, Akkusparmodus), kommt ein ehrlicher ⚠️-Hinweis statt der Erfolgsmeldung.
- 277 Tests, py_compile OK.
## 1.5.0 – 2026-11-06 (Build u) – Fahrmodus der Live-Karte
- Kein „Karte zum Verschieben antippen“ mehr auf der Live-Karte: Der Antipp-Schutz bleibt auf allen eingebetteten Karten aktiv, ist auf der Live-Seite aber aus – beim Fahren verschiebt ein Finger SOFORT, nichts überlagert die Kartenmitte.
- Karte größer auf dem Handy (höhere Mindesthöhe, mehr Bildschirmanteil auf schmalen Displays).
- 🚵 Wege-Knopf: Kartenstil umschaltbar zwischen Standard-OSM und CyclOSM (Radkarten-Stil, Feldwege/Tracks kräftig) – die Wahl wird gemerkt.
- 👠 Folgen zoomt jetzt auf Fahrzoom 16 (Straßen/Wege deutlich lesbar).
- Doppeltipp auf der Karte frischt das Bildschirm-Wachhalten auf („🔱 Bildschirm bleibt an“), dazu ein Wächter, der den Wake-Lock alle 60 s zurückholt – das Display hält so den ganzen Fahrttag durch.
- 274 Tests, py_compile OK.
## 1.5.0 – 2026-11-06 (Build t) – Eine rote Anzeige statt zweier
- Läuft die EIGENE Fahrt, ist die „Fahrt läuft“-Pill unten rechts DIE eine Anzeige – sie zeigt jetzt auch, wie viele unterwegs sind und ob die Aufzeichnung läuft (vorher standen Navbar-Pille „N unterwegs“ und Pill gleichzeitig herum). Die Navbar bleibt bei eigener Fahrt frei; fährt jemand anderes, zeigt weiterhin die Navbar-Pille die Gruppe an. Tourseiten regelt wie seit Build p die Aktionsleiste.
- 271 Tests, py_compile OK.
## 1.5.0 – 2026-11-06 (Build s) – „Ende gilt“-Siegel gegen Zombie-Fahrten
- Fix für „Fahrt läuft immer noch, obwohl ich sie mehrfach beendet habe“: Ein vergessenes Gerät (Tab oder Handy mit offener Live-Karte bzw. aktivem Fahren-Status) sendete im Hintergrund weiter und riss die soeben gelöschte Anwesenheit alle ~30 Sekunden neu ein – die rote Anzeige kam also immer wieder.
- Beim Beenden setzt der Server jetzt ein Siegel (live_stops): Weitere Hintergrund-Updates werden abgewiesen (HTTP 409), die Sender räumen sich selbst ab. Eine frisch geladene Live-Karte meldet resume und startet unbeschwert neu; die Aufzeichnung bleibt von der Änderung unberührt (weiter übernehmen/löschen auf der Tourseite).
- 269 Tests, py_compile OK.
## 1.5.0 – 2026-11-06 (Build r) – Navbar bei mittlerer Größe gerade gezogen
- Bei mittlerer Fenstergroße (992–1199 px) standen die Menü-Einträge versetzt: Icon über, Beschriftung unter – Ursache war Bootstraps .container, der dort nur 960 px breit ist und die Links zum Umbrechen zwang. Die Navbar nutzt jetzt die volle Breite (container-fluid), Beschriftungen sind grundsätzlich einzeilig, und im Mittelbereich sind Abstände/Logo/Brand etwas kompakter.
- 267 Tests, py_compile OK.
## 1.5.0 – 2026-11-06 (Build q) – Karten-Overlay eindeutig benannt
- Der Karten-Schutz auf Handys hieß „☝ Tippen zum Aktivieren“ und wurde mehrfach so verstanden, als ließe sich hier die TOUR starten/aktivieren – gemeint war die Karte (erst antippen, dann mit einem Finger verschieben). Neu: „☝ Karte zum Verschieben antippen“; die vier Positions-Picker (Treffpunkt, Orte, Gastro, GPS-Korrektur) bekamen ebenfalls eindeutige Hinweise („Karte antippen – Klick setzt danach …“).
- 266 Tests, py_compile OK.
## 1.5.0 – 2026-11-06 (Build p) – Eine Live-Anzeige statt dreier, „Abschließen“ entschärft
- Konsolidiert: Auf der Tourseite zeigt jetzt die Aktionsleiste den Lauf-Status an – die rote „Fahrt läuft“-Pill unten rechts erscheint dort nicht mehr (Navbar-Punkt bleibt app-weit). Läuft die EIGENE Fahrt, wird der Knopf zum aktiven „⏺ Fahrt beenden“ (stoppt die eigene Aufzeichnung, ohne die Tourseite zu verlassen; danach steht wieder „Fahren“ da). Fremde Fahrten bleiben reiner Status.
- „Abschließen“ tritt bei laufender Fahrt einen Schritt zurück (weicher Tint statt Vollgrün) und fragt beim Klick nach: „Es läuft noch eine Fahrt – Abschließen stoppt sie NICHT“. Bisher wirkte das grüne „Abschließen“ wie der Knopf zum Fahrt-Beenden.
- 264 Tests, py_compile OK.
## 1.5.0 – 2026-11-06 (Build o) – Stromspar-Modus Stufe 2: gröber senden, Kurven-Trigger
- Im Stromspar-Modus sendet die Aufzeichnung gröber: alle 20 s statt 10 s (im Stand alle 45 s statt 30 s) – spürbar weniger Funk-Aktivität auf langen Geraden.
- Neuer Richtungs-Trigger (über 25° Kursänderung, wie in den Akku-Modi von Strava & Co.): Kurven werden auch im gröberen Takt sofort gesichert – Ecken bleiben rund, nur Geraden werden ausged¼nnt. Außerhalb des Sparmodus ändert sich nichts.
- 261 Tests, py_compile OK.
## 1.5.0 – 2026-11-06 (Build n) – Video-Fehler inline, ffmpeg aus Git, Stromspar-Modus
- Video-Seite: Schlägt die MP4-Erstellung serverseitig fehl, erscheint die Meldung jetzt direkt im Fortschritts-Kasten (mit Grund, Button bleibt bedienbar für erneuten Versuch) – vorher lud die Seite sich still neu und der Formularstand war weg.
- ffmpeg-Binärdatei (77 MB) aus der Git-Verwaltung genommen („sanftes Slimming“): Der Verlauf wächst nicht weiter, die Datei bleibt lokal und auf dem Server; Deploy-ZIPs enthielten sie schon immer nicht. Bei Serverumzug aus der Historie holen (git checkout f32448c -- ffmpeg).
- Stromspar-Modus auf der Live-Karte (Schalter „🌙 Stromspar“): Bildschirm bleibt AN (Wake Lock), wird aber dunkel überzogen – kein Entsperren nötig; Tippen hellt 4 s lang auf, ✕ beendet, mit Fahrtende endet der Modus automatisch. Die Aufzeichnung läuft unverändert weiter.
- 260 Tests, py_compile OK.
## 1.5.0 – 2026-11-06 (Build m) – Footer-Link heißt jetzt „Monatsrückblick“
- Der Footer-Link „Newsletter“ heißt jetzt „Monatsrückblick“ – so nennt sich die Zielseite selbst (Kopf: „Monatsrückblick MM/JJJJ“); auch der Browser-Titel der Seite wurde von „Newsletter MM/JJJJ“ auf „Monatsrückblick MM/JJJJ“ angeglichen. Die Adresse (/newsletter) bleibt unverändert, alte Links/Bookmarks funktionieren weiter.
- 257 Tests, py_compile OK.
## 1.5.0 – 2026-11-06 (Build l) – Footer zentriert
- Die Footer-Zeile (Gruppenname · Newsletter · Datenschutz) ist jetzt zentriert statt im Breitband-Layout nach links/rechts verteilt – auf schmalen Screens stand bisher alles links, nur die Versionszeile mittig.
- 255 Tests, py_compile OK.
## 1.5.0 – 2026-11-06 (Build k) – Text-Überlauf behoben & Versionssprung 1.4.0 → 1.5.0
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
