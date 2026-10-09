# Удаление русской локализации DeepSeek Harness из профиля.
#
#   powershell -ExecutionPolicy Bypass -File uninstall.ps1
#   powershell -ExecutionPolicy Bypass -File uninstall.ps1 -ProfileDir "..."
#
# Убирает плагин, его запись в манифесте и выбор языка. Приложение нужно
# закрыть перед запуском и открыть заново после.

param(
  [string]$ProfileDir
)

$ErrorActionPreference = 'Stop'
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-Utf8NoBom([string]$Path, [string]$Text) {
  [System.IO.File]::WriteAllText($Path, $Text, $utf8NoBom)
}

$dshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE '.dsh' }
if (-not $ProfileDir) {
  $candidate = Join-Path $dshHome 'profiles\desktop'
  if (Test-Path $candidate) { $ProfileDir = $candidate }
  else { throw "Укажите профиль явно через -ProfileDir" }
}
if (-not (Test-Path $ProfileDir)) { throw "Профиль не найден: $ProfileDir" }

Write-Host "Профиль : $ProfileDir"

# --- 1. файлы плагина -----------------------------------------------------
foreach ($p in @((Join-Path $ProfileDir 'plugins\dsh-locale-ru'),
                 (Join-Path $ProfileDir 'node_modules\dsh-locale-ru'))) {
  if (Test-Path $p) { Remove-Item $p -Recurse -Force; Write-Host "удалено : $p" }
}

# --- 2. манифест ----------------------------------------------------------
$pkgPath = Join-Path $ProfileDir 'package.json'
$pkg = Get-Content $pkgPath -Raw -Encoding UTF8 | ConvertFrom-Json

if ($pkg.PSObject.Properties['dependencies'] -and
    $pkg.dependencies.PSObject.Properties['dsh-locale-ru']) {
  $pkg.dependencies.PSObject.Properties.Remove('dsh-locale-ru')
}
$pkg.dsh.profile.bundles = @($pkg.dsh.profile.bundles | Where-Object { $_ -ne 'dsh-locale-ru' })
Write-Utf8NoBom $pkgPath ($pkg | ConvertTo-Json -Depth 20)
Write-Host "манифест: dsh-locale-ru убран"

# --- 3. выбор языка -------------------------------------------------------
# Работаем по структуре записи, а не по тексту комментариев: удаляем строку
# `- id: locale` вместе с её комментариями и телом, до следующей записи.
$patchPath = Join-Path $ProfileDir 'cordis.patch.yml'
if (Test-Path $patchPath) {
  $lines = @(Get-Content $patchPath -Encoding UTF8)

  $start = -1
  for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '^-\s*id:\s*locale\s*$') { $start = $i; break }
  }

  if ($start -lt 0) {
    Write-Host "язык    : записи locale нет — не трогаю"
  }
  else {
    $from = $start
    while ($from -gt 0 -and ($lines[$from - 1] -match '^\s*#' -or $lines[$from - 1].Trim() -eq '')) {
      $from--
    }
    $to = $lines.Count - 1
    for ($i = $start + 1; $i -lt $lines.Count; $i++) {
      if ($lines[$i] -match '^-\s*id:') { $to = $i - 1; break }
    }

    $kept = New-Object System.Collections.Generic.List[string]
    if ($from -gt 0) { $kept.AddRange([string[]]$lines[0..($from - 1)]) }
    if ($to + 1 -lt $lines.Count) { $kept.AddRange([string[]]$lines[($to + 1)..($lines.Count - 1)]) }

    Write-Utf8NoBom $patchPath (($kept -join "`n").TrimEnd() + "`n")
    Write-Host "язык    : запись locale удалена (строки $($from + 1)-$($to + 1))"
  }
}

Write-Host ""
Write-Host "Готово. Запустите приложение заново — интерфейс вернётся к прежнему языку."
