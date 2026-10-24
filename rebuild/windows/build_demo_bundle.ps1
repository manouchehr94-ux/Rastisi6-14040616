<#
.SYNOPSIS
  Offline conversion of the two demo SQLite databases + media ZIPs into one validated bundle (Windows PowerShell).
.EXAMPLE
  .\rebuild\windows\build_demo_bundle.ps1 `
      -V5Sqlite D:\in\demo_v5.sqlite3 -V5MediaZip D:\in\demo_v5_media.zip `
      -Arch02Sqlite D:\in\demo_arch02.sqlite3 -Arch02MediaZip D:\in\demo_arch02_media.zip `
      -Out D:\out\rastisi-demo-bundle
.NOTES
  Needs Python 3.10+. Creates .venv inside the repository once. Exit code: 0 bundle written, 1 FAIL, 2 BLOCKED.
  Add -InspectOnly first to look at stores, ids, ZIP layout and unknown JSON keys without writing anything.
#>
param(
  [Parameter(Mandatory)][string]$V5Sqlite,   [Parameter(Mandatory)][string]$V5MediaZip,
  [Parameter(Mandatory)][string]$Arch02Sqlite, [Parameter(Mandatory)][string]$Arch02MediaZip,
  [Parameter(Mandatory)][string]$Out,
  [string]$V5Store, [string]$Arch02Store,
  [string]$WheelDir,
  [switch]$InspectOnly, [switch]$SkipFullCheck, [switch]$KeepWork,
  [string[]]$MapJsonKey, [string[]]$MapJsonListKey, [string[]]$IgnoreJsonKey,
  [string]$V5MediaPrefix, [string]$Arch02MediaPrefix
)
$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
# resolve user-supplied paths BEFORE changing the working directory
$V5Sqlite = (Resolve-Path -LiteralPath $V5Sqlite).Path;       $V5MediaZip = (Resolve-Path -LiteralPath $V5MediaZip).Path
$Arch02Sqlite = (Resolve-Path -LiteralPath $Arch02Sqlite).Path; $Arch02MediaZip = (Resolve-Path -LiteralPath $Arch02MediaZip).Path
$Out = [System.IO.Path]::GetFullPath($Out)
Set-Location (Join-Path $PSScriptRoot "..\..")
$hasPy = [bool](Get-Command py -ErrorAction SilentlyContinue)
$hasPython = [bool](Get-Command python -ErrorAction SilentlyContinue)
if (-not ($hasPy -or $hasPython)) { Write-Error "Python 3.10+ not found on PATH (https://www.python.org/downloads/)"; exit 9 }
$a = @("rebuild\tools\build_bundle_offline.py",
       "--v5-sqlite", $V5Sqlite, "--v5-media-zip", $V5MediaZip,
       "--arch02-sqlite", $Arch02Sqlite, "--arch02-media-zip", $Arch02MediaZip, "--out", $Out)
if ($V5Store)       { $a += @("--v5-store", $V5Store) }
if ($Arch02Store)   { $a += @("--arch02-store", $Arch02Store) }
if ($V5MediaPrefix)    { $a += @("--v5-media-prefix", $V5MediaPrefix) }
if ($Arch02MediaPrefix) { $a += @("--arch02-media-prefix", $Arch02MediaPrefix) }
if ($WheelDir)      { $a += @("--wheel-dir", $WheelDir) }
if ($InspectOnly)   { $a += "--inspect-only" }
if ($SkipFullCheck) { $a += "--no-full-check" }
if ($KeepWork)      { $a += "--keep-work" }
foreach ($k in $MapJsonKey)    { $a += @("--map-json-key", $k) }
foreach ($k in $MapJsonListKey) { $a += @("--map-json-list-key", $k) }
foreach ($k in $IgnoreJsonKey) { $a += @("--ignore-json-key", $k) }
if ($hasPy) { & py -3 @a } else { & python @a }
exit $LASTEXITCODE
