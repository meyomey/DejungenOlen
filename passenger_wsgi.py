"""Phusion Passenger entry point for Netcup / Plesk hosting."""
import os
import sys

# Projektverzeichnis
project_root = '/var/www/vhosts/hosting139268.a2e64.netcup.net/djo.wulmstorf.net/dejungen_olen'
vhost_home   = '/var/www/vhosts/hosting139268.a2e64.netcup.net'

# Python-Version des laufenden Interpreters, z. B. "python3.11". Nicht mehr fest
# verdrahtet: Nach dem Server-Update (3.9 → 3.11) zeigte der alte Pfad
# ".local/lib/python3.9/site-packages" auf Pakete, die für 3.9 kompiliert waren.
_pyver = 'python{}.{}'.format(sys.version_info.major, sys.version_info.minor)

# venv-Pfad – auf diesem Server: venv/Lib/site-packages (mit großem L);
# hierhin installieren Auto-Install und Admin → „Pakete installieren“ (pip --target).
venv_path   = os.path.join(project_root, 'venv', 'Lib', 'site-packages')

# Suchpfade in Prioritätsreihenfolge – nur vorhandene Ordner werden eingetragen.
# Der Altbestand für Python 3.9 steht bewusst ganz hinten: reine Python-Pakete von
# dort funktionieren weiter, frisch installierte Pakete gewinnen aber immer.
_candidates = [
    os.path.join(vhost_home, '.local', 'lib', _pyver, 'site-packages'),  # pip install --user (aktuelle Version)
    venv_path,
    os.path.join(project_root, 'venv', 'lib', _pyver, 'site-packages'),  # klassisches venv-Layout
    os.path.join(vhost_home, '.local', 'lib', 'python3.9', 'site-packages'),  # Altbestand vor dem Update
]
_paths = [p for p in _candidates if os.path.isdir(p)] + [project_root]
for _p in reversed(_paths):
    if _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)

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
        # --target umgeht die Debian-12-Sperre „externally-managed-environment“;
        # --upgrade ersetzt Reste, die noch für eine ältere Python-Version gebaut wurden.
        result = subprocess.run(
            _pip_cmd + ['install', '--quiet', '--upgrade', '--target', venv_path] + _missing,
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            logging.info(f'Auto-install success: {_missing}')
        else:
            logging.warning(f'Auto-install failed: {result.stderr[:200]}')
    except Exception as _e:
        logging.warning(f'Auto-install exception: {_e}')

# Arbeitsverzeichnis setzen (wichtig für SQLite-Pfad)
os.chdir(project_root)


def _startup_failed(text):
    """Build ae: Startfehler sichtbar machen. Bisher meldete Passenger bei einem Fehler in app.py
    nur „module 'passenger_wsgi' has no attribute 'application'“ – ohne SSH war die Ursache nicht
    zu sehen. Jetzt: Traceback in logs/startup_error.log (per FTP lesbar) und als Antwortseite."""
    try:
        import logging
        logging.error('De jungen Olen – Start fehlgeschlagen:\n%s', text)
    except Exception:
        pass
    try:
        import datetime
        os.makedirs(os.path.join(project_root, 'logs'), exist_ok=True)
        with open(os.path.join(project_root, 'logs', 'startup_error.log'), 'a', encoding='utf-8') as fh:
            fh.write('\n===== {} – Python {} =====\n{}\n'.format(
                datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), sys.version.split()[0], text))
    except Exception:
        pass

    def application(environ, start_response):
        body = ('De jungen Olen – die App konnte nicht starten.\n\n'
                'Fehler beim Laden von app.py (Python {}):\n\n{}\n\n'
                'Derselbe Text steht in logs/startup_error.log im App-Ordner.\n'
                'Nach dem Beheben: Plesk → Python → Restart (oder tmp/restart.txt anfassen).\n'
                ).format(sys.version.split()[0], text).encode('utf-8')
        start_response('500 Internal Server Error',
                       [('Content-Type', 'text/plain; charset=utf-8'),
                        ('Content-Length', str(len(body))),
                        ('Cache-Control', 'no-store')])
        return [body]
    return application


# App laden – jeder Fehler (auch SystemExit aus einer Bibliothek) wird angezeigt statt verschluckt
try:
    from app import app as application
    _app_file = getattr(sys.modules.get('app'), '__file__', '') or ''
    if not os.path.abspath(_app_file).startswith(os.path.abspath(project_root)):
        raise ImportError('Es wurde ein fremdes Modul "app" geladen: {} – erwartet wurde {}'.format(
            _app_file, os.path.join(project_root, 'app.py')))
    _startup_error = None
except BaseException:
    import traceback
    _startup_error = traceback.format_exc()
    application = _startup_failed(_startup_error)

# Datenbank + Schema-Migration beim Start
if _startup_error is None:
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
