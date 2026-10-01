# Backup wiederherstellen

Anleitung für Netcup/Plesk per FTP – ohne SSH-Zugang.

---

## ⚠️ Wichtiger Hinweis vorab

`backup.sh` hatte bisher einen Fehler: es sicherte eine Datei namens
`djo.sqlite`, die tatsächliche App-Datenbank heißt aber standardmäßig
`dejungen_olen.db`. Das wurde jetzt behoben (`backup.sh` aktualisiert,
siehe separates Update).

**Bitte vor dem ersten Restore-Versuch prüfen:**
1. Per FTP in den Projektordner schauen, welche `.db`- bzw. `.sqlite`-Datei
   dort tatsächlich liegt und aktuell (Änderungsdatum = heute/kürzlich) ist
2. Die vorhandenen Dateien in `backups/*.tar.gz` herunterladen und stichprobenartig
   prüfen, ob sie überhaupt eine `.sqlite`-Datei mit sinnvoller Dateigröße enthalten
   (nicht nur wenige KB – das wäre ein Hinweis auf eine leere/fehlgeschlagene Sicherung)

Falls die bisherigen Backups tatsächlich leer/falsch waren: das aktualisierte
`backup.sh` hochladen, damit ab sofort wieder korrekt gesichert wird. Ältere,
fehlerhafte Backups sind dann leider nicht mehr nutzbar – ab dem nächsten
Lauf sind neue, korrekte Backups vorhanden.

---

## Schritt 1 – Backup-Datei herunterladen

1. Per FTP in `backups/` navigieren
2. Die gewünschte `djo_backup_JJJJ-MM-TT_HHMMSS.tar.gz` auf den PC herunterladen
3. Lokal entpacken:
   - **Windows:** 7-Zip oder WinRAR (Rechtsklick → Extrahieren)
   - **Mac:** Doppelklick öffnet es automatisch, oder Terminal: `tar -xzf dateiname.tar.gz`

Im entpackten Ordner findest du:
```
djo_backup_12345.sqlite      ← die Datenbank
static/uploads/               ← alle Fotos, GPX-Tracks, Avatare, Logos
```

---

## Schritt 2 – Sicherheitskopie der aktuellen Daten anlegen

**Bevor irgendetwas überschrieben wird:** aktuellen Stand vom Server sichern,
falls der Restore rückgängig gemacht werden muss.

Per FTP im Projektordner:
1. `dejungen_olen.db` → herunterladen und lokal als `dejungen_olen.db.vor-restore` speichern
2. Falls vorhanden: `dejungen_olen.db-wal` und `dejungen_olen.db-shm` ebenfalls herunterladen
   (SQLite-Zusatzdateien im WAL-Modus – siehe Hinweis unten)

---

## Schritt 3 – Datenbank zurückspielen

1. Auf dem Server im Projektordner die Datei `dejungen_olen.db` **löschen**
2. Falls vorhanden, auch `dejungen_olen.db-wal` und `dejungen_olen.db-shm`
   **löschen** (wichtig! Diese enthalten nicht-übertragene Änderungen der
   *alten* Datenbank und dürfen nicht mit der wiederhergestellten Version
   vermischt werden – sonst drohen Inkonsistenzen)
3. Die entpackte `djo_backup_XXXXX.sqlite` aus dem Backup per FTP hochladen
4. Direkt beim Hochladen (oder danach) umbenennen zu genau: `dejungen_olen.db`

---

## Schritt 4 – Uploads (Fotos, GPX, Logos) zurückspielen

**Wichtige Entscheidung:** Möchtest du die Uploads komplett ersetzen (alles was
seit dem Backup neu hochgeladen wurde geht verloren) oder nur ergänzen?

**Meistens sinnvoller – zusammenführen statt ersetzen:**
1. Den Ordner `static/uploads/` aus dem entpackten Backup öffnen
2. Die Unterordner (`photos/`, `gpx/`, `avatars/`, `group_logos/`, `group_music/`, `videos/`)
   einzeln durchgehen
3. Per FTP nur die Dateien hochladen, die auf dem Server **fehlen** (die meisten
   FTP-Clients wie FileZilla zeigen beim Hochladen einen Vergleich an, oder nutze
   „Nur neuere Dateien hochladen")

**Alternative – komplett ersetzen** (nur wenn du sicher bist, dass seit dem
Backup nichts Neues mehr hochgeladen wurde): den kompletten `static/uploads/`-
Ordner auf dem Server löschen und durch den aus dem Backup ersetzen.

---

## Schritt 5 – Passenger neu starten

Wie gewohnt: in Plesk → Python-App → **Restart**, oder eine leere/aktualisierte
Datei in `tmp/restart.txt` hochladen.

---

## Schritt 6 – Prüfen

1. Seite aufrufen, einloggen
2. Stichprobenartig eine bekannte Tour/ein bekanntes Foto öffnen, das im
   Backup-Zeitpunkt vorhanden war
3. Admin → Dashboard → Mitgliederzahl mit dem erwarteten Stand vergleichen

---

## Hinweis: SQLite WAL-Modus

Die App nutzt SQLite im **WAL-Modus** (Write-Ahead Logging) für bessere
Performance bei parallelen Zugriffen. Das bedeutet: neben `dejungen_olen.db`
können zur Laufzeit zusätzlich `dejungen_olen.db-wal` und `dejungen_olen.db-shm`
existieren, die noch nicht in die Hauptdatei geschriebene Änderungen enthalten.

`backup.sh` selbst nutzt `sqlite3 ... .backup` – das erstellt einen sauberen,
konsistenten Snapshot **inklusive** aller WAL-Daten in einer einzigen Datei.
Das im Backup enthaltene `.sqlite` ist daher bereits vollständig und
in sich konsistent – du musst dir beim eigentlichen Restore-Vorgang keine
Gedanken um WAL-Dateien *aus dem Backup* machen, nur um die *aktuellen*
WAL-Dateien auf dem Server (die zur alten DB gehören und vor dem Ersetzen
gelöscht werden müssen, siehe Schritt 3).

---

## Künftig: Backups vor Restore testen

Um genau dieses Problem (defekte/leere Backups die erst beim Restore auffallen)
künftig zu vermeiden: gelegentlich stichprobenartig ein Backup herunterladen,
entpacken und die `.sqlite`-Datei lokal mit einem SQLite-Browser (z.B.
[DB Browser for SQLite](https://sqlitebrowser.org/), kostenlos) öffnen um zu
prüfen, ob echte Daten (Mitglieder, Touren) drin sind.
