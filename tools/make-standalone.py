"""Build the single-file installer: `install-standalone.ps1`.

Some extractors flatten archives, which destroys `lib/` and `locales/ru/` and
leaves the package files loose. This sidesteps the problem: the four files the
runtime needs are embedded as base64 inside one .ps1, so there is nothing to
extract and nothing to lose.

`locales/` is deliberately not embedded — it is only needed to rebuild the
bundle, and embedding it would triple the file size.

Run: python tools/make-standalone.py
"""
import base64
import os
import sys

# Консоль Windows часто в cp866 или cp1251 — принудительный UTF-8, чтобы русский
# путь в выводе не валил скрипт.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'dist', 'install-standalone.ps1')

EMBED = [
    'package.json',
    'cordis.patch.yml',
    'lib/index.js',
    'lib/client.js',
]

files = {}
for rel in EMBED:
    with open(os.path.join(ROOT, rel.replace('/', os.sep)), 'rb') as fh:
        files[rel] = base64.b64encode(fh.read()).decode('ascii')

entries = '\n'.join(f"  '{rel}' = '{data}'" for rel, data in files.items())
sizes = ', '.join(f'{rel} {os.path.getsize(os.path.join(ROOT, rel.replace("/", os.sep)))} B'
                  for rel in EMBED)

TEMPLATE = r'''# ==========================================================================
#  dsh-locale-ru — русский язык для DeepSeek Harness
#
#  Установщик одним файлом: языковой пакет встроен внутрь, рядом ничего не
#  требуется и распаковывать нечего. Можно скопировать этот файл куда угодно
#  и запустить оттуда.
#
#     powershell -ExecutionPolicy Bypass -File install-standalone.ps1
#
#  Не запускайте от имени администратора: профиль ищется у текущего
#  пользователя. Перед запуском закройте приложение ПОЛНОСТЬЮ — правый клик
#  по значку в области уведомлений -> «Quit DeepSeek Harness».
#
#  Что делает скрипт: распаковывает четыре файла в профиль DeepSeek Harness,
#  добавляет пакет в dsh.profile.bundles и включает русский язык. Больше
#  ничего: ни сети, ни прав администратора, ни изменений в папке установки.
#  Полное удаление — uninstall.ps1 из репозитория.
# ==========================================================================

param(
  [string]$ProfileDir
)

$ErrorActionPreference = 'Stop'
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-Utf8NoBom([string]$Path, [string]$Text) {
  [System.IO.File]::WriteAllText($Path, $Text, $utf8NoBom)
}

# --- встроенный пакет (base64) -------------------------------------------
$FILES = @{
__ENTRIES__
}

# --- профиль --------------------------------------------------------------
$dshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE '.dsh' }
if (-not $ProfileDir) {
  $profilesRoot = Join-Path $dshHome 'profiles'
  if (-not (Test-Path $profilesRoot)) {
    throw "Не найдена папка профилей: $profilesRoot. Запустите DeepSeek Harness хотя бы раз, закройте его и повторите."
  }
  $available = @(Get-ChildItem $profilesRoot -Directory | Select-Object -ExpandProperty Name)
  if ($available -contains 'desktop') { $ProfileDir = Join-Path $profilesRoot 'desktop' }
  elseif ($available.Count -eq 1) { $ProfileDir = Join-Path $profilesRoot $available[0] }
  else { throw "Укажите профиль явно через -ProfileDir. Найдены: $($available -join ', ')" }
}
if (-not (Test-Path $ProfileDir)) { throw "Профиль не найден: $ProfileDir" }

Write-Host "Профиль : $ProfileDir"

# --- 1. распаковать пакет в профиль --------------------------------------
$pluginTarget = Join-Path $ProfileDir 'plugins\dsh-locale-ru'
if (Test-Path $pluginTarget) { Remove-Item $pluginTarget -Recurse -Force }
foreach ($rel in $FILES.Keys) {
  $path = Join-Path $pluginTarget ($rel -replace '/', '\')
  New-Item -ItemType Directory -Force -Path (Split-Path $path -Parent) | Out-Null
  [System.IO.File]::WriteAllBytes($path, [Convert]::FromBase64String($FILES[$rel]))
}
Write-Host "плагин  : распакован в $pluginTarget"

# --- 2. копия в node_modules (загрузчик ищет имя пакета здесь) -----------
$moduleTarget = Join-Path $ProfileDir 'node_modules\dsh-locale-ru'
if (Test-Path $moduleTarget) { Remove-Item $moduleTarget -Recurse -Force }
New-Item -ItemType Directory -Force -Path $moduleTarget | Out-Null
Copy-Item (Join-Path $pluginTarget '*') -Destination $moduleTarget -Recurse -Force
Write-Host "модуль  : разложен в $moduleTarget"

# --- 3. манифест профиля --------------------------------------------------
$pkgPath = Join-Path $ProfileDir 'package.json'
if (-not (Test-Path $pkgPath)) { throw "В профиле нет package.json: $pkgPath" }
$pkg = Get-Content $pkgPath -Raw -Encoding UTF8 | ConvertFrom-Json

if (-not $pkg.PSObject.Properties['dependencies']) {
  $pkg | Add-Member -NotePropertyName dependencies -NotePropertyValue ([pscustomobject]@{})
}
$pkg.dependencies | Add-Member -NotePropertyName 'dsh-locale-ru' `
  -NotePropertyValue 'file:plugins/dsh-locale-ru' -Force

$bundles = @($pkg.dsh.profile.bundles)
if ($bundles -notcontains 'dsh-locale-ru') { $bundles += 'dsh-locale-ru' }
$pkg.dsh.profile.bundles = $bundles

Write-Utf8NoBom $pkgPath ($pkg | ConvertTo-Json -Depth 20)
Write-Host "манифест: dsh-locale-ru добавлен в зависимости и в dsh.profile.bundles"

# --- 4. выбор языка -------------------------------------------------------
$patchPath = Join-Path $ProfileDir 'cordis.patch.yml'
if (-not (Test-Path $patchPath)) { Write-Utf8NoBom $patchPath "[]`n" }
$patch = Get-Content $patchPath -Raw -Encoding UTF8

if ($patch -match '(?m)^-\s*id:\s*locale\s*$') {
  Write-Host "язык    : строка locale уже есть — не трогаю"
}
else {
  $row = @(
    ''
    '# Русский язык интерфейса (языковой пакет dsh-locale-ru).'
    '# Это то же, что выбирает Настройки -> Общие -> Язык.'
    '- id: locale'
    '  name: "@deepseek-ai/dsh-client-locale"'
    '  config:'
    '    preference: ru'
  ) -join "`n"
  Write-Utf8NoBom $patchPath ($patch.TrimEnd() + "`n" + $row + "`n")
  Write-Host "язык    : в cordis.patch.yml добавлен preference: ru"
}

# --- 5. проверка и итог ---------------------------------------------------
$check = Join-Path $moduleTarget 'lib\client.js'
if (-not (Test-Path $check)) { throw "Файл бандла не записался: $check" }
$size = (Get-Item $check).Length
$hash = (Get-FileHash $check -Algorithm SHA256).Hash.ToLower()
Write-Host "проверка: lib\client.js на месте, $size байт"
Write-Host "          sha256 $hash"

Write-Host ""
Write-Host "Готово. Профиль сейчас:"
Write-Host ("  bundles: " + (@((Get-Content $pkgPath -Raw -Encoding UTF8 | ConvertFrom-Json).dsh.profile.bundles) -join ', '))
Write-Host ""
Write-Host "Осталось перезапустить приложение:"
Write-Host "  правый клик по значку DeepSeek Harness в области уведомлений ->"
Write-Host "  «Quit DeepSeek Harness», затем запустить заново."
Write-Host "Простое обновление страницы не поможет: хост читает плагин один раз при старте."
'''

script = TEMPLATE.replace('__ENTRIES__', entries)

# UTF-8 с BOM, иначе Windows PowerShell 5.1 прочитает кириллицу как ANSI.
with open(OUT, 'wb') as fh:
    fh.write(b'\xef\xbb\xbf')
    fh.write(script.encode('utf-8'))

print(f'embedded: {sizes}')
print(f'{OUT} = {os.path.getsize(OUT) / 1024:.0f} KB')
