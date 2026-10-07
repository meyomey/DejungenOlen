# Audit-Bericht – De jungen Olen (Version 1.2.0, 07.10.2026)

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
