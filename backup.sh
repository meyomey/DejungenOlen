#!/bin/bash
# De jungen Olen – Backup Script
# Täglich per Cron: 0 2 * * * /path/to/dejungen_olen/backup.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="${SCRIPT_DIR}/backups"
DATE=$(date +%Y-%m-%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/djo_backup_${DATE}.tar.gz"
MAX_BACKUPS=14  # Fallback-Sicherheitsnetz, falls die Python-Generationen-Rotation nicht läuft

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

# Archiv erstellen: DB + Uploads (ohne venv/Cache)
tar -czf "${BACKUP_FILE}" \
  -C "${SCRIPT_DIR}" \
  --exclude="static/uploads/photos/*.tmp" \
  --exclude="**/__pycache__" \
  --exclude="venv" \
  --exclude="backups" \
  static/uploads/ \
  -C /tmp "djo_backup_$$.sqlite" \
  2>/dev/null

rm -f "${TMPDB}"

if [ $? -eq 0 ] && [ -f "${BACKUP_FILE}" ]; then
  SIZE=$(du -sh "${BACKUP_FILE}" | cut -f1)
  echo "$(date): Backup OK – ${BACKUP_FILE} (${SIZE}) – DB-Datei: ${DB_FILE}"
else
  echo "$(date): Backup FEHLER"
  exit 1
fi

# Fallback-Rotation: nur die neuesten MAX_BACKUPS behalten (Sicherheitsnetz,
# falls die feinere Python-Generationen-Rotation aus der App nicht läuft)
ls -t "${BACKUP_DIR}"/djo_backup_*.tar.gz 2>/dev/null | \
  tail -n +$((MAX_BACKUPS + 1)) | xargs rm -f

echo "Backups gesamt: $(ls "${BACKUP_DIR}"/djo_backup_*.tar.gz 2>/dev/null | wc -l)"
