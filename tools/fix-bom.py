"""Add a UTF-8 BOM to every .ps1 that contains non-ASCII text.

Windows PowerShell 5.1 reads a .ps1 without a BOM using the system ANSI code
page, which turns Cyrillic inside string literals into mojibake and produces
parse errors. Editors that save as "UTF-8 without BOM" reintroduce the problem,
so this script exists to fix it in one command and the audit checks for it.

Run: python tools/fix-bom.py
"""
import os
import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOM = b'\xef\xbb\xbf'


def targets():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in {'.git', 'dist', 'node_modules'}]
        for name in sorted(filenames):
            if name.lower().endswith('.ps1'):
                yield os.path.join(dirpath, name)


fixed = 0
for path in targets():
    with open(path, 'rb') as fh:
        raw = fh.read()
    if raw.startswith(BOM):
        continue
    try:
        raw.decode('ascii')
        continue          # чистый ASCII — BOM не нужен
    except UnicodeDecodeError:
        pass
    with open(path, 'wb') as fh:
        fh.write(BOM + raw)
    print('BOM добавлен: ' + os.path.relpath(path, ROOT).replace(os.sep, '/'))
    fixed += 1

print(f'исправлено файлов: {fixed}')
