# Changelog – De jungen Olen

Neueste Version oben. Die Versionskennung steht in `app.py` (`APP_VERSION`, `APP_BUILD`) und im Footer jeder Seite.

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
