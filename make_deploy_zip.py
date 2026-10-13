#!/usr/bin/env python3
"""
Deploy-ZIP für den FTP-Upload erstellen.

Packt alle Dateien, die sich seit dem letzten Deploy (bzw. seit einem Git-Stand) geändert
haben, in deploy/deploy_v<VERSION>_<BUILD>.zip – mit Ordnerstruktur wie im Projekt, so dass
die ZIP auf dem PC entpackt und 1:1 per FTP in den App-Ordner (dejungen_olen/) kopiert
werden kann. Zusätzlich liegt in der ZIP eine _DEPLOY_HINWEISE.txt mit Dateiliste und den
Schritten nach dem Upload.

Aufruf (im Projektordner):
    python make_deploy_zip.py                 # Änderungen seit dem letzten Deploy-ZIP
    python make_deploy_zip.py --since origin/main   # Änderungen gegenüber einem Git-Stand
    python make_deploy_zip.py --full          # komplettes Projekt (Neuinstallation)

Nach dem Erstellen wird der aktuelle Git-Stand in deploy/LAST_DEPLOY.txt gemerkt;
der nächste Lauf ohne --since packt dann nur, was seitdem dazukam.
Nur Standardbibliothek, läuft unter Python 3.9+ auf Linux/Windows.
"""
import argparse
import os
import re
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEPLOY_DIR = ROOT / 'deploy'
MARKER = DEPLOY_DIR / 'LAST_DEPLOY.txt'

# Dateien/Ordner, die nie auf den Server gehören
EXCLUDE_PREFIXES = ('deploy/', '.git/', '.github/', 'venv/', '.venv/', 'backups/', 'instance/',
                    'static/uploads/', '__pycache__/', 'node_modules/')
EXCLUDE_FILES = {'.gitignore', '.gitattributes', 'make_deploy_zip.py', 'LAST_DEPLOY.txt'}
EXCLUDE_SUFFIXES = ('.pyc', '.db', '.db-wal', '.db-shm', '.log', '.zip')
# Große Binärdatei: nur bei --full und auch dann nur auf Wunsch
FFMPEG = 'ffmpeg'


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True,
                          encoding='utf-8', errors='replace')


def app_version():
    src = (ROOT / 'app.py').read_text(encoding='utf-8')
    v = re.search(r"^APP_VERSION\s*=\s*'([^']+)'", src, re.M)
    b = re.search(r"^APP_BUILD\s*=\s*'([^']+)'", src, re.M)
    return (v.group(1) if v else '0.0.0'), (b.group(1) if b else datetime.now().strftime('%Y-%m-%d'))


def wanted(rel):
    rel = rel.replace('\\', '/')
    if rel.startswith(EXCLUDE_PREFIXES) or rel in EXCLUDE_FILES or rel.endswith(EXCLUDE_SUFFIXES):
        return False
    if '/__pycache__/' in rel:
        return False
    return True


def changed_since(ref):
    """Geänderte/neue Dateien seit `ref` (committet) + alles Uncommittete; gelöschte separat."""
    changed, deleted = set(), set()
    r = git('diff', '--name-status', f'{ref}', 'HEAD')
    if r.returncode != 0:
        sys.exit(f'git diff gegen {ref!r} fehlgeschlagen:\n{r.stderr}')
    for line in r.stdout.splitlines():
        parts = line.split('\t')
        status, path = parts[0][0], parts[-1]
        (deleted if status == 'D' else changed).add(path)
    # Uncommittete Änderungen (modifiziert, neu, unversioniert)
    r = git('status', '--porcelain', '--untracked-files=all')
    for line in r.stdout.splitlines():
        status, path = line[:2], line[3:]
        if ' -> ' in path:
            path = path.split(' -> ')[-1]
        if 'D' in status:
            deleted.add(path)
        else:
            changed.add(path)
    changed = {p for p in changed if wanted(p) and (ROOT / p).is_file()}
    deleted = {p for p in deleted if wanted(p) and not (ROOT / p).exists()}
    return sorted(changed), sorted(deleted)


def all_files(include_ffmpeg):
    r = git('ls-files')
    files = [p for p in r.stdout.splitlines() if wanted(p) and (ROOT / p).is_file()]
    if not include_ffmpeg:
        files = [p for p in files if p != FFMPEG]
    return sorted(files), []


def hints(version, build, files, deleted, mode):
    lines = [
        f'De jungen Olen – Deploy-Paket v{version} (Build {build})',
        f'Erstellt: {datetime.now().strftime("%d.%m.%Y %H:%M")} – Modus: {mode}',
        '',
        'UPLOAD',
        '  ZIP entpacken und den Inhalt mit gleicher Ordnerstruktur per FTP in den',
        '  App-Ordner (…/dejungen_olen/) kopieren, vorhandene Dateien überschreiben.',
        '',
        f'DATEIEN ({len(files)}):',
    ] + [f'  {f}' for f in files]
    if deleted:
        lines += ['', 'AUF DEM SERVER LÖSCHEN (im Projekt entfernt):'] + [f'  {f}' for f in deleted]
    lines += [
        '',
        'NACH DEM UPLOAD',
        '  1. Passenger neu starten: Plesk → Python → Restart (oder tmp/restart.txt anfassen).',
        '  2. Falls ffmpeg dabei war: Rechte 755 setzen (FTP-Client → Dateiberechtigungen).',
        '  3. Einloggen, Footer prüfen: dort muss "Version {v} · {b}" stehen.'.format(v=version, b=build),
        '  4. Admin → Tools → Pakete installieren: Kasten "Python-Umgebung" kontrollieren.',
        '',
        'Nicht enthalten (bleiben auf dem Server unverändert): .env, instance/*.db,',
        'static/uploads/, backups/, venv/.',
    ]
    return '\n'.join(lines) + '\n'


def main():
    ap = argparse.ArgumentParser(description='Deploy-ZIP erstellen')
    ap.add_argument('--since', help='Git-Stand (Commit/Branch/Tag), ab dem Änderungen gepackt werden')
    ap.add_argument('--full', action='store_true', help='komplettes Projekt packen')
    ap.add_argument('--with-ffmpeg', action='store_true', help='bei --full auch die ffmpeg-Binärdatei packen')
    ap.add_argument('--no-marker', action='store_true', help='LAST_DEPLOY.txt nicht aktualisieren')
    args = ap.parse_args()

    version, build = app_version()
    DEPLOY_DIR.mkdir(exist_ok=True)

    if args.full:
        files, deleted = all_files(args.with_ffmpeg)
        mode = 'komplett'
    else:
        ref = args.since
        if not ref and MARKER.exists():
            ref = MARKER.read_text(encoding='utf-8').split()[0]
            if git('cat-file', '-e', f'{ref}^{{commit}}').returncode != 0:
                print(f'Hinweis: gemerkter Stand {ref} nicht gefunden – nutze origin/main')
                ref = None
        if not ref:
            ref = 'origin/main' if git('rev-parse', '--verify', 'origin/main').returncode == 0 else 'HEAD~1'
        files, deleted = changed_since(ref)
        mode = f'Änderungen seit {ref[:12]}'
        if not files and not deleted:
            print(f'Keine Änderungen seit {ref} – nichts zu packen.')
            return

    safe_build = build.replace(' ', '')
    out = DEPLOY_DIR / f'deploy_v{version}_{safe_build}.zip'
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for rel in files:
            z.write(ROOT / rel, rel)
        z.writestr('_DEPLOY_HINWEISE.txt', hints(version, build, files, deleted, mode))

    if not args.no_marker:
        head = git('rev-parse', 'HEAD').stdout.strip()
        MARKER.write_text(f'{head}  {out.name}  {datetime.now().isoformat(timespec="minutes")}\n',
                          encoding='utf-8')

    size_kb = out.stat().st_size / 1024
    print(f'{out.relative_to(ROOT)}  ({size_kb:.0f} KB, {len(files)} Dateien, Modus: {mode})')
    for f in files:
        print('  ', f)
    if deleted:
        print('Auf dem Server löschen:')
        for f in deleted:
            print('  ', f)


if __name__ == '__main__':
    main()
