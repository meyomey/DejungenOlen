#!/usr/bin/env python3
"""
Deploy-ZIPs für den FTP-Upload erstellen.

Erzeugt im Ordner deploy/ standardmäßig ZWEI Pakete:

  deploy_v<VERSION>_<BUILD>_komplett.zip     – das komplette Projekt (alle Dateien, die auf
                                                den Server gehören; ohne .env, Datenbank,
                                                Uploads, Backups, venv – und ohne die 80-MB-
                                                ffmpeg-Binärdatei, außer mit --with-ffmpeg)
  deploy_v<VERSION>_<BUILD>_aenderungen.zip  – nur die Dateien, die sich seit dem Stand
                                                geändert haben, der bestätigt auf dem Server
                                                liegt (deploy/LAST_DEPLOY.txt; oder --since)

Beide ZIPs haben die Ordnerstruktur des Projekts: auf dem PC entpacken und den Inhalt 1:1
per FTP in den App-Ordner (dejungen_olen/) kopieren. In jeder ZIP liegt eine
_DEPLOY_HINWEISE.txt mit Dateiliste und den Schritten nach dem Upload.

Aufruf (im Projektordner):
    python make_deploy_zip.py                       # beide ZIPs, Änderungen seit Server-Stand
    python make_deploy_zip.py --since origin/main   # Änderungen gegenüber einem Git-Stand
    python make_deploy_zip.py --only komplett       # nur das Komplettpaket
    python make_deploy_zip.py --only aenderungen    # nur das Änderungspaket
    python make_deploy_zip.py --with-ffmpeg         # Komplettpaket inkl. ffmpeg-Binärdatei
    python make_deploy_zip.py --deployed            # nach dem Upload: aktuellen Stand (HEAD)
                                                    # als Server-Stand merken (oder --deployed <Commit>)

deploy/LAST_DEPLOY.txt merkt sich den Git-Stand, der auf dem Server liegt; er wird nur mit
--deployed fortgeschrieben. Ältere ZIPs in deploy/ werden entfernt (das Komplettpaket enthält
immer alles), außer mit --keep-old.
Nur Standardbibliothek, läuft unter Python 3.9+ auf Linux/Windows.
"""
import argparse
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
FFMPEG = 'ffmpeg'  # 80-MB-Binärdatei, liegt bereits auf dem Server


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
    r = git('diff', '--name-status', ref, 'HEAD')
    if r.returncode != 0:
        sys.exit(f'git diff gegen {ref!r} fehlgeschlagen:\n{r.stderr}')
    for line in r.stdout.splitlines():
        parts = line.split('\t')
        status, path = parts[0][0], parts[-1]
        (deleted if status == 'D' else changed).add(path)
        if status == 'R' and len(parts) == 3:      # umbenannt/verschoben: alter Pfad muss weg
            deleted.add(parts[1])
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
    """Alle versionierten Dateien (Arbeitskopie-Stand), die auf den Server gehören."""
    tracked = set(git('ls-files').stdout.splitlines())
    # neue, noch nicht committete Dateien ebenfalls mitnehmen
    for line in git('status', '--porcelain', '--untracked-files=all').stdout.splitlines():
        if line.startswith('??'):
            tracked.add(line[3:])
    files = [p for p in tracked if wanted(p) and (ROOT / p).is_file()]
    if not include_ffmpeg:
        files = [p for p in files if p != FFMPEG]
    return sorted(files)


def hints(version, build, files, deleted, kind, mode):
    lines = [
        f'De jungen Olen – Deploy-Paket v{version} (Build {build})',
        f'Erstellt: {datetime.now().strftime("%d.%m.%Y %H:%M")} – {kind}',
        '',
        'UPLOAD',
        '  ZIP entpacken und den Inhalt mit gleicher Ordnerstruktur per FTP in den',
        '  App-Ordner (…/dejungen_olen/) kopieren, vorhandene Dateien überschreiben.',
    ]
    if kind == 'Komplettpaket':
        lines += [
            '  Enthält den vollständigen Projektstand – kann jederzeit über eine bestehende',
            '  Installation kopiert werden (.env, Datenbank, Uploads werden nicht berührt).',
            '  Neuinstallation: siehe docs/INSTALLATION_PLESK_FTP.md.',
        ]
    else:
        lines += [f'  Enthält nur die geänderten Dateien ({mode}).']
    lines += ['', f'DATEIEN ({len(files)}):'] + [f'  {f}' for f in files]
    if deleted:
        lines += ['', 'AUF DEM SERVER LÖSCHEN (im Projekt entfernt):'] + [f'  {f}' for f in deleted]
    lines += [
        '',
        'NACH DEM UPLOAD',
        '  1. Passenger neu starten: Plesk → Python → Restart (oder tmp/restart.txt anfassen).',
        '  2. ffmpeg (falls hochgeladen oder noch nie gesetzt): Rechte 755 (FTP-Client → Dateiberechtigungen).',
        f'  3. Einloggen, Footer prüfen: dort muss "Version {version} · {build}" stehen.',
        '  4. Admin → Tools → Pakete installieren: Kasten "Python-Umgebung" kontrollieren.',
        '',
        'Nicht enthalten (bleiben auf dem Server unverändert): .env, instance/*.db,',
        'static/uploads/, backups/, venv/' + ('' if FFMPEG in files else ', ffmpeg') + '.',
    ]
    return '\n'.join(lines) + '\n'


def write_zip(path, files, hint_text):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for rel in files:
            z.write(ROOT / rel, rel)
        z.writestr('_DEPLOY_HINWEISE.txt', hint_text)
    return path.stat().st_size / 1024


def resolve_base(since):
    if since:
        return since
    if MARKER.exists():
        ref = MARKER.read_text(encoding='utf-8').split()[0]
        if git('cat-file', '-e', f'{ref}^{{commit}}').returncode == 0:
            return ref
        print(f'Hinweis: gemerkter Server-Stand {ref[:12]} nicht gefunden – nutze origin/main')
    if git('rev-parse', '--verify', 'origin/main').returncode == 0:
        return 'origin/main'
    return 'HEAD~1'


def main():
    ap = argparse.ArgumentParser(description='Deploy-ZIPs erstellen')
    ap.add_argument('--since', help='Git-Stand (Commit/Branch/Tag), ab dem Änderungen gepackt werden')
    ap.add_argument('--only', choices=['komplett', 'aenderungen'], help='nur eines der beiden Pakete bauen')
    ap.add_argument('--with-ffmpeg', action='store_true', help='Komplettpaket inkl. ffmpeg-Binärdatei')
    ap.add_argument('--keep-old', action='store_true', help='ältere ZIPs in deploy/ behalten')
    ap.add_argument('--deployed', nargs='?', const='HEAD', metavar='COMMIT',
                    help='diesen Stand (Standard: HEAD) als auf dem Server liegend merken und beenden')
    args = ap.parse_args()

    version, build = app_version()
    DEPLOY_DIR.mkdir(exist_ok=True)

    if args.deployed:
        r = git('rev-parse', '--verify', f'{args.deployed}^{{commit}}')
        if r.returncode != 0:
            sys.exit(f'Unbekannter Git-Stand: {args.deployed}')
        head = r.stdout.strip()
        # Build-Kennung aus dem app.py DIESES Stands (nicht der Arbeitskopie)
        m = re.search(r"^APP_BUILD\s*=\s*'([^']+)'", git('show', f'{head}:app.py').stdout, re.M)
        dep_build = m.group(1) if m else '?'
        MARKER.write_text(f'{head}  Server-Stand (Build {dep_build})  {datetime.now().isoformat(timespec="minutes")}\n',
                          encoding='utf-8')
        print(f'Server-Stand gemerkt: {head[:12]} (Build {dep_build})')
        return
    stem = f'deploy_v{version}_{build.replace(" ", "")}'
    built = []

    if not args.keep_old:
        for old in DEPLOY_DIR.glob('deploy_*.zip'):
            old.unlink()

    if args.only != 'aenderungen':
        files = all_files(args.with_ffmpeg)
        out = DEPLOY_DIR / f'{stem}_komplett.zip'
        kb = write_zip(out, files, hints(version, build, files, [], 'Komplettpaket', ''))
        built.append((out, kb, len(files)))

    if args.only != 'komplett':
        ref = resolve_base(args.since)
        files, deleted = changed_since(ref)
        mode = f'Änderungen seit {ref[:12]}'
        if files or deleted:
            out = DEPLOY_DIR / f'{stem}_aenderungen.zip'
            kb = write_zip(out, files, hints(version, build, files, deleted, 'Änderungspaket', mode))
            built.append((out, kb, len(files)))
            print(f'Änderungspaket ({mode}):')
            for f in files:
                print('  ', f)
            if deleted:
                print('  Auf dem Server löschen:')
                for f in deleted:
                    print('    ', f)
        else:
            print(f'Keine geänderten Dateien seit {ref[:12]} – kein Änderungspaket erzeugt.')

    print()
    for out, kb, n in built:
        print(f'{out.relative_to(ROOT)}  ({kb:.0f} KB, {n} Dateien)')


if __name__ == '__main__':
    main()
