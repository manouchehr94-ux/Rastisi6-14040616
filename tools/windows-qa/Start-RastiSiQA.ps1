<#
.SYNOPSIS
  Creates an ISOLATED RastiSi notification QA environment on this computer and starts it. Fake e-mail transport only.

.DESCRIPTION
  * adds a NEW detached Git worktree of the branch under the QA root (your main / Claude / Kiro / finance worktrees are never touched)
  * uses its own SQLite database inside that worktree (DATABASE_URL is cleared)
  * creates (or reuses) a QA-only Python venv outside the worktrees and installs requirements.txt into it
  * runs `manage.py check`, `makemigrations --check`, `migrate`, then seeds four demo stores and two platform accounts
  * starts a local web server on a free port + a background worker, and prints the exact URLs and logins
  * NO AWS credentials are read, NO e-mail leaves your computer: the "fake" provider writes every message to a local mailbox folder.
  Real Amazon SES testing is a separate, explicitly confirmed script: Invoke-RastiSiLiveSesSmoke.ps1.

.PARAMETER RepoPath   Your local RastiSi clone (default: the clone this script lives in).
.PARAMETER Branch     Branch to test (default: kiro/notifications-email-engine-20261104).
.PARAMETER Ref        Exact Git ref/commit to check out instead of origin/<Branch> (advanced).
.PARAMETER NoFetch    Do not run `git fetch` (use what is already in the clone).
.PARAMETER QaRoot     Where QA runs live (default: %LOCALAPPDATA%\RastiSiQA).
.PARAMETER Port       First port to try (default 8765); the first free one is used.
.PARAMETER PythonPath Explicit python.exe (default: auto-discovery incl. the `py -3` launcher).
.PARAMETER Password   Password for ALL seeded QA accounts (default: a random one, shown at the end).
.PARAMETER RunTests   Also run the targeted Notifications test suites inside the QA worktree.
.PARAMETER NoServer   Prepare + seed only; do not start the web server/worker.
.PARAMETER NoWorker   Start the web server without the background outbox worker.
.PARAMETER OpenBrowser Open the platform admin page in the default browser when ready.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\tools\windows-qa\Start-RastiSiQA.ps1 -OpenBrowser
#>
[CmdletBinding()]
param(
    [string]$RepoPath = '',
    [string]$Branch = 'kiro/notifications-email-engine-20261104',
    [string]$Ref = '',
    [switch]$NoFetch,
    [string]$QaRoot = '',
    [int]$Port = 8765,
    [string]$PythonPath = '',
    [string]$Password = '',
    [switch]$RunTests,
    [switch]$NoServer,
    [switch]$NoWorker,
    [switch]$OpenBrowser
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_Common.ps1')

Write-Host "RastiSi notification QA - isolated environment (FAKE e-mail transport; no AWS, no real e-mail)" -ForegroundColor White

# ---------------------------------------------------------------- 1. preflight
Write-Step '1/9  Preflight'
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Stop-Qa 'git is not installed or not on PATH.' 'Install Git for Windows from https://git-scm.com/download/win and re-open PowerShell.' }
$repo = Resolve-RepoRoot $RepoPath
Write-Ok "repository: $repo"
if (-not $QaRoot) { $QaRoot = Get-DefaultQaRoot }
$python = Find-Python $PythonPath
Write-Ok "python: $python"
if (-not $Password) { $Password = 'Qa-' + (New-RandomSecret 9) + '-1' }

# ---------------------------------------------------------------- 2. run folder + worktree
Write-Step '2/9  Creating an isolated Git worktree'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$runDir = Join-Path $QaRoot "runs\$stamp"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null
Set-Content -LiteralPath (Join-Path $runDir $script:QaMarker) -Value 'RastiSi QA run - safe to delete with Remove-RastiSiQA.ps1' -Encoding ASCII
$srcDir = Join-Path $runDir 'src'; $dataDir = Join-Path $runDir 'data'; $logsDir = Join-Path $runDir 'logs'
New-Item -ItemType Directory -Force -Path $dataDir, $logsDir, (Join-Path $runDir 'mailbox') | Out-Null

if (-not $NoFetch) {
    Invoke-Native { & git -C $repo fetch --quiet origin $Branch 2>&1 | ForEach-Object { Write-Host "    $_" } }
    if ($LASTEXITCODE -ne 0) { Stop-Qa "git fetch origin $Branch failed." 'Check your network / GitHub access, or re-run with -NoFetch to use what is already in the clone.' }
}
$checkout = $Ref
if (-not $checkout) { $checkout = "origin/$Branch" }
Invoke-Native { & git -C $repo rev-parse --verify --quiet "$checkout^{commit}" 2>&1 | Out-Null }
if ($LASTEXITCODE -ne 0) { Stop-Qa "Git ref '$checkout' does not exist in $repo." 'Run without -NoFetch, or pass -Ref <commit>.' }
Invoke-Native { $script:__sha = (& git -C $repo rev-parse $checkout 2>$null) }
$sha = ("$script:__sha").Trim()
Invoke-Native { & git -C $repo worktree add --detach $srcDir $sha 2>&1 | ForEach-Object { Write-Host "    $_" } }
if ($LASTEXITCODE -ne 0) { Stop-Qa 'git worktree add failed.' }
Write-Ok "worktree: $srcDir  @ $sha (detached; your branches are untouched)"

$run = [pscustomobject]@{
    run_dir = $runDir; src_dir = $srcDir; data_dir = $dataDir; logs_dir = $logsDir; qa_root = $QaRoot; repo = $repo
    branch = $Branch; commit = $sha; venv_dir = ''; python = $python; port = 0; password = $Password
    secret_key = (New-RandomSecret 48); server_pid = 0; worker_pid = 0; started_at = (Get-Date).ToString('s')
}

# ---------------------------------------------------------------- 3. venv + dependencies
Write-Step '3/9  Python environment (QA-only virtualenv, outside every worktree)'
$req = Join-Path $srcDir 'requirements.txt'
if (-not (Test-Path -LiteralPath $req)) { Stop-Qa 'requirements.txt not found in the worktree.' }
$venvDir = Join-Path $QaRoot ("venv-" + (Get-RequirementsHash $req))
$venvPy = Get-VenvPython $venvDir
$ready = Join-Path $venvDir '.deps-installed'
if (-not (Test-Path -LiteralPath $ready)) {
    Write-Host "    creating $venvDir and installing dependencies (first run takes a few minutes)..."
    Invoke-Native { & $python -m venv $venvDir 2>&1 | ForEach-Object { Write-Host "    $_" } }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPy)) { Stop-Qa 'Could not create the virtualenv.' 'Make sure the Python "venv" module is installed (python.org installer includes it).' }
    $pipLog = Join-Path $logsDir 'pip-install.log'
    Invoke-Native { & $venvPy -m pip install --disable-pip-version-check --quiet --upgrade pip 2>&1 | Out-Null }
    Invoke-Native { & $venvPy -m pip install --disable-pip-version-check -r $req 2>&1 | ForEach-Object { $l = "$_"; Add-LogLine $pipLog $l; if ($l -match 'ERROR|error:') { Write-Host "    $l" } } }
    if ($LASTEXITCODE -ne 0) { Stop-Qa 'pip install -r requirements.txt failed.' "See $(Join-Path $logsDir 'pip-install.log')" }
    Set-Content -LiteralPath $ready -Value (Get-Date).ToString('s') -Encoding ASCII
} else { Write-Ok "reusing $venvDir" }
$run.venv_dir = $venvDir
Invoke-Native { $script:__missing = & $venvPy -c "import importlib.util as u; print(','.join(m for m in ('django','boto3','dns','PIL','jdatetime','openpyxl','cryptography') if u.find_spec(m) is None))" 2>$null }
$missing = ("$script:__missing").Trim()
if ($missing) { Stop-Qa "Dependencies missing in the QA venv: $missing" "Delete $venvDir and run again." }
Write-Ok 'dependencies verified (django, boto3, dnspython, Pillow, jdatetime, openpyxl, cryptography)'
Save-Run $run

# ---------------------------------------------------------------- 4. isolation proof
Write-Step '4/9  Proving the database is isolated'
$dbName = (Invoke-WithEnv (Get-QaEnv $run) { Push-Location $srcDir; try { Invoke-Native { & $venvPy -c "import os,django;os.environ.setdefault('DJANGO_SETTINGS_MODULE','shop_core.settings');django.setup();from django.conf import settings;print(settings.DATABASES['default']['NAME'])" 2>$null } } finally { Pop-Location } })
$dbName = ("$dbName").Trim()
if (-not $dbName.StartsWith($runDir, [System.StringComparison]::OrdinalIgnoreCase)) { Stop-Qa "Database path is not inside the QA run folder: $dbName" 'Refusing to continue - this would not be isolated.' }
Write-Ok "database: $dbName"

# ---------------------------------------------------------------- 5. checks
Write-Step '5/9  Django system check + migration consistency'
Invoke-Manage $run @('check') 'check.log' | Out-Null
Write-Ok 'manage.py check passed'
$mm = Invoke-Manage $run @('makemigrations', '--check', '--dry-run') 'makemigrations-check.log' -AllowFailure
if ($mm -ne 0) { Stop-Qa 'Model changes are missing a migration (makemigrations --check failed).' "See $(Join-Path $logsDir 'makemigrations-check.log')" }
Write-Ok 'no missing migrations'
Invoke-Manage $run @('migrate', '--noinput', '-v', '0') 'migrate.log' | Out-Null
Write-Ok 'migrations applied to the isolated database'

# ---------------------------------------------------------------- 6. port + seed
Write-Step '6/9  Choosing a port and seeding demo data'
$port = Get-FreePort $Port
$run.port = $port
$info = Join-Path $runDir 'QA-INFO.json'
Invoke-Manage $run @('seed_qa_notifications', '--password', $Password, '--port', "$port", '--json', $info) 'seed.log' | Out-Null
Write-Ok 'seeded 4 stores + platform accounts'
Save-Run $run

# ---------------------------------------------------------------- 7. tests (optional)
if ($RunTests) {
    Write-Step '7/9  Targeted automated tests (inside the worktree, fake provider)'
    $labels = @('apps.notifications', 'apps.sms', 'apps.dashboard.tests.test_notification_admin', 'apps.portal.tests.test_platform_notification_admin')
    $code = Invoke-Manage $run (@('test') + $labels + @('--parallel', '1', '--noinput')) 'tests.log' -AllowFailure
    if ($code -ne 0) { Write-Warn2 "some tests failed - see $(Join-Path $logsDir 'tests.log')" } else { Write-Ok 'targeted tests passed' }
} else { Write-Step '7/9  Targeted automated tests'; Write-Host '    skipped (add -RunTests to run them here)' }

# ---------------------------------------------------------------- 8. processes
$py = Get-VenvPython $venvDir
function Start-QaBackground([string]$Name, [string[]]$ProcArgs) {
    $out = Join-Path $logsDir "$Name.out.log"; $err = Join-Path $logsDir "$Name.err.log"
    $sp = @{ FilePath = $py; ArgumentList = $ProcArgs; WorkingDirectory = $srcDir; RedirectStandardOutput = $out; RedirectStandardError = $err; PassThru = $true }
    if (Test-IsWindows) { $sp['WindowStyle'] = 'Hidden' }
    $p = $null
    Invoke-WithEnv (Get-QaEnv $run) { $script:__p = Start-Process @sp }
    return $script:__p
}
if (-not $NoServer) {
    Write-Step "8/9  Starting the web server on port $port"
    $srv = Start-QaBackground 'server' @('manage.py', 'runserver', "127.0.0.1:$port", '--noreload')
    $run.server_pid = $srv.Id
    if (-not $NoWorker) {
        $wrk = Start-QaBackground 'worker' @('manage.py', 'qa_worker', '--interval', '5')
        $run.worker_pid = $wrk.Id
        Write-Ok "background worker started (pid $($wrk.Id)); sends queued e-mail every 5 seconds"
    }
    Save-Run $run
    $up = $false
    for ($i = 0; $i -lt 40; $i++) {
        if ($srv.HasExited) { break }
        if (Test-HttpUp "http://127.0.0.1:$port/") { $up = $true; break }
        Start-Sleep -Milliseconds 750
    }
    if (-not $up) { Stop-Qa 'The web server did not become ready.' "See $(Join-Path $logsDir 'server.err.log')" }
    Write-Ok "server ready (pid $($srv.Id))"
} else { Write-Step '8/9  Web server'; Write-Host '    skipped (-NoServer)' }

# ---------------------------------------------------------------- 9. report
Write-Step '9/9  Ready'
$data = Get-Content -LiteralPath $info -Raw -Encoding UTF8 | ConvertFrom-Json
$md = New-Object System.Collections.ArrayList
[void]$md.Add("# RastiSi notification QA - run $stamp")
[void]$md.Add("")
[void]$md.Add("* Commit under test: ``$sha`` (branch ``$Branch``)")
[void]$md.Add("* Mode: FAKE e-mail transport (no AWS, no real e-mail). Mailbox folder: ``$(Join-Path $runDir 'mailbox')``")
[void]$md.Add("* Database: ``$dbName``")
[void]$md.Add("* Platform admin: $($data.platform_admin_url)  (login: ``$($data.platform_owner)`` / password below)")
[void]$md.Add("* Central login (store owners): $($data.login_url)")
[void]$md.Add("* Password for every QA account: ``$Password``")
[void]$md.Add("* Limited platform member (can only VIEW the event catalog): ``$($data.platform_limited_member)``")
[void]$md.Add("")
[void]$md.Add("| store | owner login | store admin URL | e-mail sender state |")
[void]$md.Add("|---|---|---|---|")
foreach ($s in $data.stores) { [void]$md.Add("| $($s.slug) | $($s.owner_login) | $($s.store_admin_url) | $($s.sender_status) $($s.sender_address) |") }
$mdPath = Join-Path $runDir 'QA-INFO.md'
$md -join "`r`n" | Set-Content -LiteralPath $mdPath -Encoding UTF8

Write-Host ""
Write-Host "  Platform admin : $($data.platform_admin_url)" -ForegroundColor Green
Write-Host "      login      : $($data.platform_owner)   password: $Password"
Write-Host "  Central login  : $($data.login_url)  (store owners sign in here, then land in their store admin)"
foreach ($s in $data.stores) {
    Write-Host ("  Store admin    : {0}" -f $s.store_admin_url) -ForegroundColor Green
    Write-Host ("      store {0,-13} login: {1}   sender: {2} {3}" -f $s.slug, $s.owner_login, $s.sender_status, $s.sender_address)
}
Write-Host ""
Write-Host "  Fake mailbox   : $(Join-Path $runDir 'mailbox')   (every 'sent' e-mail appears here as .html/.txt/.json)"
Write-Host "  Run folder     : $runDir"
Write-Host "  Details        : $mdPath"
Write-Host ""
$resolvable = Test-LocalhostSubdomainResolves 'platformadmins.rastisi.localhost'
if (-not $resolvable) {
    Write-Warn2 'Windows itself does not resolve *.rastisi.localhost (Edge/Chrome/Firefox usually still do). If a URL below does not open, add this line to C:\Windows\System32\drivers\etc\hosts (Notepad as Administrator):'
    Write-Host '        127.0.0.1 rastisi.localhost platformadmins.rastisi.localhost qa-a.rastisi.localhost qa-b.rastisi.localhost qa-bike.rastisi.localhost qa-other.rastisi.localhost'
}
Write-Host "  Next: follow tools\windows-qa\README-WINDOWS-QA.md (scenarios A-N). Helper: .\tools\windows-qa\Invoke-RastiSiQATool.ps1 -Action Status"
Write-Host "  Stop: .\tools\windows-qa\Stop-RastiSiQA.ps1     Remove everything: .\tools\windows-qa\Remove-RastiSiQA.ps1"
if ($OpenBrowser -and -not $NoServer) { Start-Process $data.platform_admin_url }
