#!/bin/bash
# De jungen Olen – Backup Script
# Taeglich per Cron: 0 2 * * * /path/to/dejungen_olen/backup.sh >> /path/to/dejungen_olen/backups/backup.log 2>&1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="${SCRIPT_DIR}/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/djo_backup_${DATE}.tar.gz"
MAX_BACKUPS=10

mkdir -p "${BACKUP_DIR}"

# SQLite-Datei finden
DB_FILE=""
for candidate in \
    "${SCRIPT_DIR}/djo.sqlite" \
    "${SCRIPT_DIR}/instance/djo.sqlite" \
    "${SCRIPT_DIR}/dejungen_olen.db" \
    "${SCRIPT_DIR}/instance/dejungen_olen.db"; do
    if [ -f "$candidate" ]; then
        DB_FILE="$candidate"
        break
    fi
done

if [ -z "$DB_FILE" ]; then
    echo "$(date): FEHLER – SQLite-Datenbankdatei nicht gefunden in ${SCRIPT_DIR}"
    exit 1
fi

# SQLite sauber sichern (kein Lock-Problem)
TMPDB="/tmp/djo_backup_$$.sqlite"
if command -v sqlite3 &>/dev/null; then
    sqlite3 "${DB_FILE}" ".backup '${TMPDB}'"
else
    cp "${DB_FILE}" "${TMPDB}"
fi

if [ ! -f "${TMPDB}" ]; then
    echo "$(date): FEHLER – DB-Backup fehlgeschlagen"
    exit 1
fi

# Archiv erstellen
tar -czf "${BACKUP_FILE}" \
  -C "${SCRIPT_DIR}" \
  --exclude="venv" \
  --exclude="backups" \
  --exclude="__pycache__" \
  --exclude="*.pyc" \
  --exclude="*.tmp" \
  static/uploads/ \
  -C /tmp "djo_backup_$$.sqlite" \
  2>/dev/null

rm -f "${TMPDB}"

if [ $? -eq 0 ] && [ -f "${BACKUP_FILE}" ]; then
    SIZE=$(du -sh "${BACKUP_FILE}" | cut -f1)
    COUNT=$(ls "${BACKUP_DIR}"/djo_backup_*.tar.gz 2>/dev/null | wc -l)
    echo "$(date): OK – ${BACKUP_FILE} (${SIZE}), ${COUNT} Backups gesamt"
else
    echo "$(date): FEHLER beim Erstellen des Archivs"
    rm -f "${BACKUP_FILE}"
    exit 1
fi

# Alte Backups loeschen
ls -t "${BACKUP_DIR}"/djo_backup_*.tar.gz 2>/dev/null | \
    tail -n +$((MAX_BACKUPS + 1)) | xargs -r rm -f

exit 0
