"""Build the release artifacts into `dist/`.

Produces:
  dist/install-standalone.ps1        — installer as one self-contained file
  dist/dsh-locale-ru-<version>.zip   — the whole package plus that installer
  dist/SHA256SUMS                    — checksums for both

Checks run first and abort the release on any failure: a release whose artifact
does not match the sources must never be published.

Run: python tools/make-release.py [--version 1.0.0]
"""
import argparse
import hashlib
import os
import re
import subprocess
import sys
import zipfile

# Консоль Windows часто работает в cp866 или cp1251, где русского текста в
# выводе может не оказаться. Принудительный UTF-8 с заменой непечатаемых
# символов избавляет от падений на ровном месте.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, 'tools')
DIST = os.path.join(ROOT, 'dist')

# Каталоги, которые не попадают в архив.
EXCLUDE_DIRS = {'.git', 'dist', 'node_modules', '__pycache__', '.github'}
# Точечные исключения внутри включаемых каталогов.
EXCLUDE_PATHS = {'.github'}


def run(script, label):
    print(f'--- {label} ---')
    result = subprocess.run([sys.executable, os.path.join(TOOLS, script)],
                            cwd=ROOT, capture_output=True, text=False)
    out = (result.stdout or b'').decode('utf-8', 'replace').strip()
    err = (result.stderr or b'').decode('utf-8', 'replace').strip()
    if out:
        print(out)
    if err:
        print(err, file=sys.stderr)
    if result.returncode != 0:
        print(f'\nОСТАНОВКА: {script} завершился с кодом {result.returncode}', file=sys.stderr)
        sys.exit(1)


def run_node(script, label):
    print(f'--- {label} ---')
    result = subprocess.run(['node', os.path.join(TOOLS, script)],
                            cwd=ROOT, capture_output=True, text=False)
    out = (result.stdout or b'').decode('utf-8', 'replace').strip()
    err = (result.stderr or b'').decode('utf-8', 'replace').strip()
    if out:
        print(out)
    if err:
        print(err, file=sys.stderr)
    if result.returncode != 0:
        print(f'\nОСТАНОВКА: {script} завершился с кодом {result.returncode}', file=sys.stderr)
        sys.exit(1)


def collect_files():
    files = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel_dir = os.path.relpath(dirpath, ROOT)
        parts = [] if rel_dir == '.' else rel_dir.split(os.sep)
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        if any(p in EXCLUDE_DIRS for p in parts):
            continue
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, ROOT).replace(os.sep, '/')
            if rel.startswith('.'):
                continue
            files.append(rel)
    return sorted(files)


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', default=None,
                        help='версия релиза; по умолчанию берётся из CHANGELOG.md')
    args = parser.parse_args()

    version = args.version
    if not version:
        with open(os.path.join(ROOT, 'CHANGELOG.md'), encoding='utf-8') as fh:
            m = re.search(r'^##\s*\[(\d+\.\d+\.\d+)\]', fh.read(), re.M)
        version = m.group(1) if m else '0.0.0'

    # 1. Артефакт должен совпадать с исходниками — иначе релиз не собираем.
    run_node('build.js', 'сборка бандла из исходников')
    run_node('verify.js', 'контракт локали')
    run_node('audit-bundle.js', 'аудит безопасности')

    # 2. Установщик одним файлом.
    run('make-standalone.py', 'установщик одним файлом')

    os.makedirs(DIST, exist_ok=True)
    standalone = os.path.join(DIST, 'install-standalone.ps1')
    if not os.path.exists(standalone):
        print('ОСТАНОВКА: install-standalone.ps1 не собрался', file=sys.stderr)
        sys.exit(1)

    # 3. Архив с исходниками.
    top = f'dsh-locale-ru-{version}'
    zip_path = os.path.join(DIST, f'{top}.zip')
    files = collect_files()
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel in files:
            z.write(os.path.join(ROOT, rel.replace('/', os.sep)), f'{top}/{rel}')
        # установщик одним файлом кладём и в корень архива
        z.write(standalone, f'{top}/install-standalone.ps1')

    # 4. Контрольные суммы.
    sums_path = os.path.join(DIST, 'SHA256SUMS')
    entries = [(os.path.basename(standalone), standalone), (os.path.basename(zip_path), zip_path)]
    with open(sums_path, 'w', encoding='utf-8', newline='\n') as fh:
        for name, path in entries:
            fh.write(f'{sha256(path)}  {name}\n')

    print()
    print(f'версия  : {version}')
    print(f'файлов в архиве: {len(files) + 1}')
    for name, path in entries:
        print(f'{name}  {os.path.getsize(path) / 1024:.0f} KB')
    print(f'SHA256SUMS  {os.path.getsize(sums_path)} B')
    print()
    print('SHA256SUMS:')
    with open(sums_path, encoding='utf-8') as fh:
        print(fh.read().rstrip())


if __name__ == '__main__':
    main()
