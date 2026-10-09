"""Подставить логин GitHub вместо заглушки OWNER.

Заглушка стоит в ссылках README, английского README и шаблона issue: без
настоящего логина они ведут в никуда. Скрипт заменяет её разом и заодно
проверяет, что логин вообще допустим на GitHub.

Run: python tools/set-owner.py --login andriano
"""
import argparse
import os
import re
import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLACEHOLDER = 'OWNER'

def text_files():
    """Все .md, .yml и .yaml репозитория — заглушка может быть в любом из них."""
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in {'.git', 'dist', 'node_modules'}]
        for name in sorted(filenames):
            if name.endswith(('.md', '.yml', '.yaml')):
                full = os.path.join(dirpath, name)
                yield full, os.path.relpath(full, ROOT).replace(os.sep, '/')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--login', required=True, help='логин GitHub, например andriano')
    parser.add_argument('--show', action='store_true', help='только показать, что найдено')
    args = parser.parse_args()

    login = args.login.strip().lstrip('@')

    # Правила GitHub: до 39 символов, буквы, цифры и дефис, без дефиса по краям.
    if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}', login):
        print(f'ОСТАНОВКА: "{login}" не похоже на логин GitHub '
              f'(до 39 символов, буквы, цифры и дефис, без дефиса по краям)', file=sys.stderr)
        sys.exit(1)

    total = 0
    for path, rel in text_files():
        with open(path, encoding='utf-8') as fh:
            text = fh.read()
        hits = text.count(PLACEHOLDER)
        if not hits:
            continue
        if args.show:
            print(f'{rel}: найдено {hits}')
            total += hits
            continue
        text = text.replace(PLACEHOLDER, login)
        with open(path, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(text)
        print(f'{rel}: заменено {hits}')
        total += hits

    if args.show:
        print(f'\nвсего заглушек: {total}')
        return

    print(f'\nвсего заменено: {total}')

    left = []
    for path, rel in text_files():
        with open(path, encoding='utf-8') as fh:
            if PLACEHOLDER in fh.read():
                left.append(rel)
    if left:
        print('Осталась заглушка в: ' + ', '.join(left))
    else:
        print('Заглушек больше нет в репозитории.')

    print()
    print('Адрес удалённого репозитория:')
    print(f'  git remote add origin https://github.com/{login}/dsh-locale-ru.git')


if __name__ == '__main__':
    main()
