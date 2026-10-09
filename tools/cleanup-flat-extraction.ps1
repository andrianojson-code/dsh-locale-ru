# Уборка россыпи, оставшейся после распаковки архива «плоским» способом.
#
#   powershell -ExecutionPolicy Bypass -File cleanup-flat-extraction.ps1
#   powershell -ExecutionPolicy Bypass -File cleanup-flat-extraction.ps1 -Folder "C:\Temp" -WhatIfOnly
#
# Удаляет файлы ТОЛЬКО если их содержимое совпадает с файлом из дистрибутива
# (сравнение по SHA256) или если файл — наш README по первой строке. Ничего
# чужого в папке не трогается: файлы с теми же именами, но другим содержимым,
# остаются на месте и попадают в отчёт.

param(
  [string]$Folder = $env:TEMP,
  [switch]$WhatIfOnly
)

$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $PSCommandPath
$pack = Join-Path $here 'dsh-locale-ru'
if (-not (Test-Path $pack)) { throw "Не найден дистрибутив рядом со скриптом: $pack" }
if (-not (Test-Path $Folder)) { throw "Папка не найдена: $Folder" }

# эталонные хэши: всё содержимое пакета + скрипты дистрибутива
$known = @{}
foreach ($f in Get-ChildItem $pack -Recurse -File) {
  $known[(Get-FileHash $f.FullName -Algorithm SHA256).Hash] = $f.Name
}
foreach ($f in Get-ChildItem $here -File -Include *.ps1, *.md -Recurse -Depth 0) {
  $known[(Get-FileHash $f.FullName -Algorithm SHA256).Hash] = $f.Name
}

$marker = '# Русификация DeepSeek Harness'

Write-Host "Папка   : $Folder"
Write-Host "Эталонов: $($known.Count)"
if ($WhatIfOnly) { Write-Host "Режим   : только показать, ничего не удаляю" }
Write-Host ""

$deleted = 0; $kept = 0; $skipped = 0; $locked = 0

foreach ($f in Get-ChildItem $Folder -File) {
  # Файлы в TEMP бывают заняты другими процессами — такие просто пропускаем.
  $hash = $null
  try { $hash = (Get-FileHash $f.FullName -Algorithm SHA256 -ErrorAction Stop).Hash }
  catch { Write-Host "  ПРОПУЩЕН  : $($f.Name)  — занят другим процессом"; $locked++; continue }
  $byHash = $known.ContainsKey($hash)

  $byMarker = $false
  if (-not $byHash -and $f.Extension -in @('.md', '.ps1') -and $f.Length -lt 200000) {
    $head = Get-Content $f.FullName -TotalCount 1 -Encoding UTF8 -ErrorAction SilentlyContinue
    if ($head -and $head.StartsWith($marker)) { $byMarker = $true }
  }

  if ($byHash -or $byMarker) {
    $why = if ($byHash) { "совпадает с «$($known[$hash])»" } else { 'наш файл по заголовку' }
    if ($WhatIfOnly) {
      Write-Host "  удалил бы : $($f.Name)  ($why)"
    } else {
      Remove-Item $f.FullName -Force
      Write-Host "  удалено   : $($f.Name)  ($why)"
    }
    $deleted++
  }
  elseif ($f.Name -match '^(README.*\.md|install.*\.ps1|uninstall.*\.ps1|build\.js|verify\.js|deploy\.ps1|client\.js|index\.js|package\.json|cordis\.patch\.yml)$') {
    Write-Host "  ОСТАВЛЕНО : $($f.Name)  — имя наше, содержимое другое"
    $kept++
  }
  else {
    $skipped++
  }
}

Write-Host ""
Write-Host "Итог: удалено $deleted, оставлено чужих с нашими именами $kept, пропущено занятых $locked, не тронуто остальных $skipped"
if ($WhatIfOnly) { Write-Host "Это была примерка. Запустите без -WhatIfOnly, чтобы удалить." }
