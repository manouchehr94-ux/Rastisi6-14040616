<#
 RastiSi fast-delivery installer (read-only checks + ONE git branch switch). It never touches the database, media files, the old branch or
 any other folder. It does not start/stop services and does not push anything.
 Usage:
   .\install_fix.ps1 -Bundle D:\...\rastisi_fix_20261108.bundle -Sha256 <expected hash> -DatabaseUrl "postgres://user:pass@localhost:5433/rastisi_qa_..." [-Repo D:\Projects\RastiSi\QA_TRIAL_PURCHASE_20261107]
#>
param(
  [Parameter(Mandatory)] [string]$Bundle,
  [Parameter(Mandatory)] [string]$Sha256,
  [Parameter(Mandatory)] [string]$DatabaseUrl,
  [string]$Repo     = "D:\Projects\RastiSi\QA_TRIAL_PURCHASE_20261107",
  [string]$Python   = "D:\Projects\RastiSi\V5_VENV\Scripts\python.exe",
  [string]$Branch   = "fix/trial-buy-settings-tabs-20261108",
  [string]$BaseSha  = "b89f700f23db63ee19f804e700d5e198b45dce3f",
  [string]$TipSha   = "__TIP__",
  [int]$WebPort     = 18091
)
$ErrorActionPreference = "Stop"
function Step($m) { Write-Host "`n== $m" -ForegroundColor Cyan }
function Fail($m) { Write-Host "STOP: $m" -ForegroundColor Red; exit 1 }

Step "1/6 bundle checksum"
$h = (Get-FileHash $Bundle -Algorithm SHA256).Hash
if ($h -ne $Sha256.ToUpper() -and $h -ne $Sha256) { Fail "SHA-256 mismatch ($h)" }
Write-Host "ok  $h"

Step "2/6 repository state"
Set-Location $Repo
if (git status --porcelain) { Fail "working tree is not clean - nothing was changed" }
$head = (git rev-parse HEAD).Trim(); $cur = (git rev-parse --abbrev-ref HEAD).Trim()
if ($head -ne $BaseSha) { Fail "HEAD is $head, expected the installed base $BaseSha" }
Write-Host "ok  on '$cur' at $head (previous version - this is your rollback point)"

Step "3/6 bundle validity"
git bundle verify $Bundle | Out-Host
if ($LASTEXITCODE -ne 0) { Fail "git bundle verify failed" }

Step "4/6 QA connectivity (read-only)"
$u = [System.Uri]$DatabaseUrl
if (-not (Test-NetConnection $u.Host -Port $u.Port -WarningAction SilentlyContinue).TcpTestSucceeded) { Fail "PostgreSQL $($u.Host):$($u.Port) not reachable" }
Write-Host "ok  PostgreSQL port reachable"

Step "5/6 add the new branch and switch"
git fetch $Bundle "${Branch}:${Branch}" | Out-Host
$new = (git rev-parse $Branch).Trim()
if ($TipSha -ne "__TIP__" -and $new -ne $TipSha) { Fail "branch tip $new does not match $TipSha" }
git checkout $Branch | Out-Host
Write-Host "ok  now on $Branch @ $new"

Step "6/6 migration check (read-only; this fix adds NO migration)"
$env:DATABASE_URL = $DatabaseUrl
& $Python manage.py migrate --check
if ($LASTEXITCODE -ne 0) { Write-Host "WARNING: pending migrations exist (not from this fix) - do NOT run migrate until you reviewed them" -ForegroundColor Yellow }
else { Write-Host "ok  database schema is up to date; QA data untouched" }

Write-Host "`nDONE. Restart your QA server yourself:  & `"$Python`" manage.py runserver 127.0.0.1:$WebPort"
Write-Host "ROLLBACK (instant, no data change):  git -C `"$Repo`" checkout $cur   then restart the server" -ForegroundColor Green
