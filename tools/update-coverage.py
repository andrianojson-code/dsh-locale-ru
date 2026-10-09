"""Обновить числа покрытия по всему репозиторию.

Перевод вырос с 57 пространств имён и 2603 строк до 58 и 2615 — выяснилось,
что выгрузка словарей пропускала `settings.permission`. Скрипт приводит все
упоминания в документации, бейджах и генераторе баннера к новым значениям.

Себя скрипт из обработки исключает: иначе он правит собственные шаблоны замен
и превращает их в пустышки.

Запуск: python tools/update-coverage.py
"""
import os
import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SELF = os.path.abspath(__file__)

OLD_NS, NEW_NS = '57', '58'
OLD_KEYS, NEW_KEYS = '2603', '2615'

REPLACEMENTS = [
    (f'keys-{OLD_KEYS}-', f'keys-{NEW_KEYS}-'),
    (f'coverage-{OLD_NS}%2F{OLD_NS}', f'coverage-{NEW_NS}%2F{NEW_NS}'),
    (f'{OLD_NS} из {OLD_NS}', f'{NEW_NS} из {NEW_NS}'),
    (f'{OLD_NS} of {OLD_NS}', f'{NEW_NS} of {NEW_NS}'),
    (f'{OLD_NS} пространств имён', f'{NEW_NS} пространств имён'),
    (f'{OLD_KEYS} из {OLD_KEYS}', f'{NEW_KEYS} из {NEW_KEYS}'),
    (f'{OLD_KEYS} of {OLD_KEYS}', f'{NEW_KEYS} of {NEW_KEYS}'),
    (f'{OLD_KEYS} строки', f'{NEW_KEYS} строк'),
    (f'{OLD_KEYS} строк', f'{NEW_KEYS} строк'),
    (f'{OLD_KEYS} strings', f'{NEW_KEYS} strings'),
    ('ещё 47 пространств имён', 'ещё 48 пространств имён'),
    (f'{OLD_NS} пространств имён · {OLD_KEYS} строки · MIT',
     f'{NEW_NS} пространств имён · {NEW_KEYS} строк · MIT'),
]

STALE = (OLD_KEYS, f'{OLD_NS} из {OLD_NS}', f'{OLD_NS} of {OLD_NS}', f'coverage-{OLD_NS}')

TEXT_EXT = ('.md', '.yml', '.yaml', '.py')


def targets():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in {'.git', 'dist', 'node_modules'}]
        for name in sorted(filenames):
            if not name.endswith(TEXT_EXT):
                continue
            path = os.path.join(dirpath, name)
            if os.path.abspath(path) == SELF:
                continue
            yield path, os.path.relpath(path, ROOT).replace(os.sep, '/')


changed = 0
for path, rel in targets():
    with open(path, encoding='utf-8') as fh:
        text = fh.read()
    original = text
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    if text != original:
        with open(path, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(text)
        print(f'обновлено: {rel}')
        changed += 1

print(f'\nфайлов изменено: {changed}')

left = []
for path, rel in targets():
    with open(path, encoding='utf-8') as fh:
        for i, line in enumerate(fh, 1):
            if any(s in line for s in STALE):
                left.append(f'{rel}:{i}')
if left:
    print('ОСТАЛОСЬ: ' + ', '.join(left))
else:
    print('старых значений не осталось')
