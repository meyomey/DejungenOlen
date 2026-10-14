#!/bin/bash
# De jungen Olen – Backup Script
# Aufruf:  backup.sh [full|db]
#   full (Standard) = Datenbank + Fotos/GPX/Avatare  → backups/djo_backup_<datum>.tar.gz
#   db              = nur die Datenbank (klein)       → backups/djo_db_<datum>.tar.gz
# Videos (static/uploads/videos) kommen nur mit INCLUDE_VIDEOS=1 ins Komplett-Backup –
# die App setzt das aus der Admin-Einstellung „Videos einschließen“ (Build ab).
# Täglich per Cron: 0 2 * * * /path/to/dejungen_olen/backup.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="${SCRIPT_DIR}/backups"
DATE=$(date +%Y-%m-%d_%H%M%S)
MODE="${1:-full}"
INCLUDE_VIDEOS="${INCLUDE_VIDEOS:-0}"
if [ "$MODE" = "db" ]; then
  BACKUP_FILE="${BACKUP_DIR}/djo_db_${DATE}.tar.gz"
else
  MODE="full"
  BACKUP_FILE="${BACKUP_DIR}/djo_backup_${DATE}.tar.gz"
fi
# Fallback-Sicherheitsnetz, falls die Python-Generationen-Rotation (7 Tage + 8 Wochen
# + 12 Monate = max. 27 Dateien) nicht läuft. Muss darüber liegen, sonst löscht dieses
# Skript die Wochen-/Monats-Generationen wieder (Audit 1.4.0: vorher 14).
MAX_BACKUPS=40

mkdir -p "${BACKUP_DIR}"

# ── Datenbankdatei automatisch ermitteln ────────────────────────────────────
# WICHTIG: Flask-SQLAlchemy legt relative sqlite:///-Pfade standardmäßig im
# instance/-Unterordner ab (Flask-Standardverhalten), NICHT im Projekt-
# Hauptordner! Hier werden daher beide Orte geprüft, instance/ zuerst.
DB_FILE=""
if [ -f "${SCRIPT_DIR}/.env" ]; then
  DB_URL=$(grep -E '^DATABASE_URL=' "${SCRIPT_DIR}/.env" | head -1 | cut -d'=' -f2-)
  if [ -n "$DB_URL" ]; then
    DB_FILE=$(echo "$DB_URL" | sed 's#^sqlite:///##')
  fi
fi
if [ -z "$DB_FILE" ]; then
  DB_FILE="dejungen_olen.db"  # App-Standard aus config.py
fi

# Kandidaten in Prioritätsreihenfolge prüfen: instance/ zuerst (Flask-Standard)
DB_PATH=""
for candidate in \
  "${SCRIPT_DIR}/instance/${DB_FILE}" \
  "${SCRIPT_DIR}/${DB_FILE}"
do
  if [ -f "$candidate" ]; then
    DB_PATH="$candidate"
    break
  fi
done

if [ -z "$DB_PATH" ]; then
  echo "$(date): FEHLER – Datenbankdatei nicht gefunden."
  echo "$(date): Geprüfte Orte: ${SCRIPT_DIR}/instance/${DB_FILE} und ${SCRIPT_DIR}/${DB_FILE}"
  echo "$(date): Prüfe DATABASE_URL in .env oder passe DB_FILE in backup.sh manuell an."
  exit 1
fi

# SQLite zuerst in eine saubere Kopie exportieren (inkl. WAL-Daten konsistent)
TMPDB="/tmp/djo_backup_$$.sqlite"
sqlite3 "${DB_PATH}" ".backup '${TMPDB}'" 2>/dev/null || cp "${DB_PATH}" "${TMPDB}"

if [ ! -f "$TMPDB" ]; then
  echo "$(date): FEHLER – Datenbank-Export fehlgeschlagen."
  exit 1
fi

if [ "$MODE" = "db" ]; then
  # Nur die Datenbank
  tar -czf "${BACKUP_FILE}" -C /tmp "djo_backup_$$.sqlite" 2>/dev/null
  TAR_RC=$?
else
  # Archiv erstellen: DB + Uploads (ohne venv/Cache; Videos nur auf Wunsch)
  VIDEO_EXCLUDE=()
  if [ "$INCLUDE_VIDEOS" != "1" ]; then
    VIDEO_EXCLUDE=(--exclude="static/uploads/videos")
  fi
  tar -czf "${BACKUP_FILE}" \
    -C "${SCRIPT_DIR}" \
    --exclude="static/uploads/photos/*.tmp" \
    --exclude="**/__pycache__" \
    --exclude="venv" \
    --exclude="backups" \
    "${VIDEO_EXCLUDE[@]}" \
    static/uploads/ \
    -C /tmp "djo_backup_$$.sqlite" \
    2>/dev/null
  TAR_RC=$?   # Audit 1.4.0: Exit-Code von tar sichern – vorher wurde der von rm geprüft
fi

rm -f "${TMPDB}"

if [ $TAR_RC -eq 0 ] && [ -f "${BACKUP_FILE}" ]; then
  SIZE=$(du -sh "${BACKUP_FILE}" | cut -f1)
  if [ "$MODE" = "db" ]; then
    echo "$(date): Datenbank-Backup OK – ${BACKUP_FILE} (${SIZE}) – DB-Datei: ${DB_FILE}"
  else
    echo "$(date): Komplett-Backup OK – ${BACKUP_FILE} (${SIZE}) – DB-Datei: ${DB_FILE} – Videos: $([ "$INCLUDE_VIDEOS" = "1" ] && echo ja || echo nein)"
  fi
else
  echo "$(date): Backup FEHLER"
  exit 1
fi

# Fallback-Rotation je Art: nur die neuesten MAX_BACKUPS behalten (Sicherheitsnetz,
# falls die feinere Python-Generationen-Rotation aus der App nicht läuft)
for PREFIX in djo_backup_ djo_db_; do
  ls -t "${BACKUP_DIR}"/${PREFIX}*.tar.gz 2>/dev/null | \
    tail -n +$((MAX_BACKUPS + 1)) | xargs rm -f
done

echo "Backups gesamt: $(ls "${BACKUP_DIR}"/djo_backup_*.tar.gz 2>/dev/null | wc -l) komplett, $(ls "${BACKUP_DIR}"/djo_db_*.tar.gz 2>/dev/null | wc -l) nur Datenbank"
