# Установка русской локализации DeepSeek Harness в профиль.
#
#   powershell -ExecutionPolicy Bypass -File install.ps1
#   powershell -ExecutionPolicy Bypass -File install.ps1 -ProfileDir "$env:USERPROFILE\.dsh\profiles\desktop"
#
# Скрипт лежит в корне пакета и берёт файлы оттуда же. Ничего не скачивает и не
# требует Node или pnpm: он копирует готовый плагин, прописывает его в профиль и
# включает русский язык.
# После установки приложение нужно ПОЛНОСТЬЮ закрыть (трей -> Quit DeepSeek
# Harness) и открыть заново.

param(
  [string]$ProfileDir
)

$ErrorActionPreference = 'Stop'

$pack = Split-Path -Parent $PSCommandPath
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-Utf8NoBom([string]$Path, [string]$Text) {
  [System.IO.File]::WriteAllText($Path, $Text, $utf8NoBom)
}

# Ровно те файлы, которые читает загрузчик. Копируется именно этот список, а не
# «всё, что лежит рядом»: так в профиль не попадает ничего лишнего.
$PAYLOAD = @('package.json', 'cordis.patch.yml', 'lib\index.js', 'lib\client.js')

foreach ($rel in $PAYLOAD) {
  if (-not (Test-Path (Join-Path $pack $rel))) {
    throw "В пакете нет файла $rel. Возьмите готовый архив целиком или воспользуйтесь install-standalone.ps1."
  }
}

function Copy-Payload([string]$From, [string]$To) {
  if (Test-Path $To) { Remove-Item $To -Recurse -Force }
  foreach ($rel in $PAYLOAD) {
    $dst = Join-Path $To $rel
    New-Item -ItemType Directory -Force -Path (Split-Path $dst -Parent) | Out-Null
    Copy-Item (Join-Path $From $rel) -Destination $dst -Force
  }
}

# --- профиль --------------------------------------------------------------
$dshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE '.dsh' }
if (-not $ProfileDir) {
  $profilesRoot = Join-Path $dshHome 'profiles'
  if (-not (Test-Path $profilesRoot)) { throw "Не найдена папка профилей: $profilesRoot" }
  $available = Get-ChildItem $profilesRoot -Directory | Select-Object -ExpandProperty Name
  if ($available -contains 'desktop') { $ProfileDir = Join-Path $profilesRoot 'desktop' }
  elseif ($available.Count -eq 1) { $ProfileDir = Join-Path $profilesRoot $available[0] }
  else { throw "Укажите профиль явно через -ProfileDir. Найдены: $($available -join ', ')" }
}
if (-not (Test-Path $ProfileDir)) { throw "Профиль не найден: $ProfileDir" }

Write-Host "Профиль : $ProfileDir"

# --- 1. сам плагин --------------------------------------------------------
$pluginTarget = Join-Path $ProfileDir 'plugins\dsh-locale-ru'
Copy-Payload $pack $pluginTarget
Write-Host "плагин  : скопирован в $pluginTarget"

# --- 2. node_modules ------------------------------------------------------
# Копии достаточно: загрузчик разрешает имя пакета обычным поиском по
# node_modules. pnpm здесь не нужен.
$moduleTarget = Join-Path $ProfileDir 'node_modules\dsh-locale-ru'
Copy-Payload $pack $moduleTarget
Write-Host "модуль  : скопирован в $moduleTarget"

# --- 3. package.json профиля ---------------------------------------------
$pkgPath = Join-Path $ProfileDir 'package.json'
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
  Write-Host "язык    : строка locale уже есть в cordis.patch.yml — не трогаю"
} else {
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

# --- 5. итог --------------------------------------------------------------
$check = Get-Content $pkgPath -Raw -Encoding UTF8 | ConvertFrom-Json
Write-Host ""
Write-Host "Готово. Профиль сейчас:"
Write-Host ("  bundles: " + ($check.dsh.profile.bundles -join ', '))
Write-Host ""
Write-Host "Осталось перезапустить приложение:"
Write-Host "  правый клик по значку DeepSeek Harness в области уведомлений ->"
Write-Host "  «Quit DeepSeek Harness», затем запустить заново."
Write-Host "Простое обновление страницы не поможет: хост читает плагин один раз при старте."
