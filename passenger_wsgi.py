"""Phusion Passenger entry point for Netcup / Plesk hosting."""
import os
import sys
import subprocess

# Projektverzeichnis
project_root = '/var/www/vhosts/hosting139268.a2e64.netcup.net/djo.wulmstorf.net/dejungen_olen'

# venv-Pfad – auf diesem Server: venv/Lib/site-packages (mit großem L)
venv_path   = os.path.join(project_root, 'venv', 'Lib', 'site-packages')
# User-installierte Pakete (pywebpush, cryptography etc.)
local_path  = '/var/www/vhosts/hosting139268.a2e64.netcup.net/.local/lib/python3.9/site-packages'

sys.path.insert(0, local_path)
sys.path.insert(1, venv_path)
sys.path.insert(2, project_root)

# Fehlende Pakete automatisch installieren
_required = ['pywebpush', 'cryptography']
_missing  = []
for _pkg in _required:
    try:
        __import__(_pkg.replace('-', '_').split('>=')[0])
    except ImportError:
        _missing.append(_pkg)

if _missing:
    import subprocess, logging
    # Mögliche pip-Pfade auf diesem Server
    _pip_candidates = [
        os.path.join(project_root, 'venv', 'bin', 'pip'),
        os.path.join(project_root, 'venv', 'bin', 'pip3'),
        os.path.join(project_root, 'venv', 'Scripts', 'pip.exe'),
        os.path.join(project_root, 'venv', 'Scripts', 'pip'),
        sys.executable.replace('python', 'pip').replace('python3', 'pip3'),
    ]
    _pip = next((p for p in _pip_candidates if os.path.isfile(p)), None)
    if not _pip:
        # Fallback: pip als Modul aufrufen
        _pip_cmd = [sys.executable, '-m', 'pip']
    else:
        _pip_cmd = [_pip]

    logging.info(f'Installing missing packages: {_missing} via {_pip_cmd}')
    try:
        result = subprocess.run(
            _pip_cmd + ['install', '--quiet', '--target', venv_path] + _missing,
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            logging.info(f'Auto-install success: {_missing}')
        else:
            logging.warning(f'Auto-install failed: {result.stderr[:200]}')
    except Exception as _e:
        logging.warning(f'Auto-install exception: {_e}')

sys.path.insert(0, venv_path)
sys.path.insert(1, project_root)

# Arbeitsverzeichnis setzen (wichtig für SQLite-Pfad)
os.chdir(project_root)

# App laden
from app import app as application

# Datenbank + Schema-Migration beim Start
with application.app_context():
    try:
        from models import db
        db.create_all()
        from app import migrate_db, init_site_config
        migrate_db()
        init_site_config()
    except Exception as _e:
        import logging
        logging.warning(f'Startup init: {_e}')
