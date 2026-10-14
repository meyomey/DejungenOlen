# Projekt mit GitHub Desktop auf GitHub bringen

Schritt-für-Schritt mit der grafischen Oberfläche – keine Kommandozeile nötig.

---

## Schritt 1 – GitHub Desktop installieren

[desktop.github.com](https://desktop.github.com) → herunterladen und installieren.

Beim ersten Start: mit deinem GitHub-Account anmelden (falls noch keiner
vorhanden, auf [github.com](https://github.com) kostenlos erstellen).

---

## Schritt 2 – Alle Projektdateien lokal zusammenführen

Du brauchst eine vollständige, aktuelle Kopie aller Projektdateien auf deinem
PC (nicht nur die zuletzt aus dem Chat heruntergeladenen).

**Am einfachsten:** Per FTP das komplette `dejungen_olen/`-Verzeichnis vom
Server auf deinen PC herunterladen, z.B. nach:
```
C:\Projekte\dejungen_olen\          (Windows)
~/Projekte/dejungen_olen/            (Mac)
```

Dann die zuletzt aus diesem Chat heruntergeladenen Dateien (`app.py`,
`models.py`, Templates, `.gitignore`, `README.md`, `.env.example` etc.)
darüberkopieren, damit die lokale Kopie den neuesten Stand hat.

---

## Schritt 3 – `.env` Datei anlegen

Falls `config.py` bisher noch einen fest eingetragenen `SECRET_KEY` im Code
hat statt ihn aus einer Umgebungsvariable zu lesen: im Projektordner eine
neue Datei `.env` anlegen (z.B. mit Notepad/TextEdit) mit Inhalt:

```
SECRET_KEY=dein-bisheriger-schluessel
```

Diese Datei wird durch `.gitignore` automatisch von GitHub ferngehalten –
wichtig, damit der Schlüssel nicht öffentlich sichtbar wird.

---

## Schritt 4 – Neues Repository in GitHub Desktop erstellen

1. GitHub Desktop öffnen
2. **File → New Repository…** (oder **Add → Create New Repository** falls
   der Startbildschirm erscheint)
3. Ausfüllen:
   - **Name:** z.B. `dejungen-olen`
   - **Local Path:** hier den **übergeordneten** Ordner wählen (nicht den
     `dejungen_olen`-Ordner selbst), also z.B. `C:\Projekte\`
   - **Git Ignore:** auf `None` lassen (wir haben schon eine eigene `.gitignore`)
   - **License:** optional, kann leer bleiben
4. **Create Repository**

**Wichtig:** Falls GitHub Desktop einen neuen leeren Ordner `dejungen-olen`
anlegt statt den bestehenden zu nutzen – stattdessen **File → Add Local
Repository…** verwenden und direkt den bestehenden, bereits befüllten
`dejungen_olen`-Ordner auswählen.

---

## Schritt 5 – Dateien prüfen (Changes-Tab)

Nach dem Erstellen zeigt GitHub Desktop links eine Liste aller Dateien unter
**Changes**. Hier genau durchschauen:

✅ Sollten auftauchen: `app.py`, `models.py`, `templates/`, `static/`
(ohne Uploads), `README.md`, `.gitignore`, `.env.example`

❌ Sollten **nicht** auftauchen: `.env`, `*.db`-Dateien, Inhalte aus
`static/uploads/photos/`, `static/uploads/gpx/` etc., `venv/`

Falls doch etwas Falsches auftaucht: bedeutet meist, dass die `.gitignore`
nicht im richtigen Ordner liegt (muss im selben Ordner wie `app.py` sein)
oder GitHub Desktop neu gestartet werden muss, damit sie greift.

---

## Schritt 6 – Ersten Commit erstellen

Unten links im Fenster:
1. **Summary** (Pflichtfeld): z.B. `Initial commit`
2. **Description** (optional): z.B. `De jungen Olen Radgruppen-App`
3. Button **Commit to main** klicken

---

## Schritt 7 – Auf GitHub veröffentlichen

Oben in der Werkzeugleiste erscheint jetzt ein Button **Publish repository**.

1. Klicken
2. Name bestätigen oder anpassen
3. **„Keep this code private"** ankreuzen oder abwählen:
   - ✅ angehakt = privates Repo, nur du siehst den Code
   - ⬜ nicht angehakt = öffentlich sichtbar für alle
4. **Publish Repository**

Fertig – das Projekt liegt jetzt auf `github.com/DEIN_USERNAME/dejungen-olen`.

---

## Künftige Änderungen hochladen

Nach jeder Weiterentwicklung (egal ob hier im Chat oder direkt im Code):

1. Geänderte Dateien in den lokalen Projektordner kopieren
2. GitHub Desktop öffnen – die Änderungen erscheinen automatisch im
   **Changes**-Tab
3. Kurze **Summary** eingeben (z.B. „Wetter-Tagesverlauf hinzugefügt")
4. **Commit to main**
5. Button **Push origin** oben rechts klicken

---

## Nützliche Ansichten in GitHub Desktop

- **History-Tab** (oben, neben Changes): zeigt alle bisherigen Commits –
  gut um nachzuvollziehen, was wann geändert wurde
- **Diff-Ansicht:** Klick auf eine Datei im Changes-Tab zeigt genau, welche
  Zeilen sich geändert haben (grün = neu, rot = entfernt)
- **Repository → Show in Explorer/Finder:** öffnet den lokalen Ordner direkt

---

## Optional: GitHub Desktop mit VS Code verbinden

Falls du Änderungen auch mal direkt im Code machen möchtest:
**Repository → Open in Visual Studio Code** (falls VS Code installiert ist) –
öffnet den Projektordner direkt zum Bearbeiten, GitHub Desktop erkennt
Änderungen danach automatisch.
