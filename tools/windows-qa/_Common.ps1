# Shared helpers for the RastiSi Windows QA package. Dot-sourced by the other scripts. ASCII-only on purpose
# (Windows PowerShell 5.1 reads BOM-less files as ANSI). Works on Windows PowerShell 5.1 and PowerShell 7+.

Set-StrictMode -Version 2.0

$script:QaMarker = '.rastisi-qa'

function Test-IsWindows {
    if ($PSVersionTable.PSEdition -eq 'Desktop') { return $true }
    return [bool]$IsWindows
}

function Write-Step([string]$Message) { Write-Host ""; Write-Host "==> $Message" -ForegroundColor Cyan }
function Write-Ok([string]$Message)   { Write-Host "    [OK]   $Message" -ForegroundColor Green }
function Write-Warn2([string]$Message){ Write-Host "    [WARN] $Message" -ForegroundColor Yellow }
function Write-Fail([string]$Message) { Write-Host "    [FAIL] $Message" -ForegroundColor Red }

function Stop-Qa([string]$Message, [string]$Hint = '') {
    Write-Fail $Message
    if ($Hint) { Write-Host "           $Hint" -ForegroundColor Yellow }
    throw "RastiSi QA stopped: $Message"
}

function Get-DefaultQaRoot {
    if (Test-IsWindows) {
        $base = $env:LOCALAPPDATA
        if (-not $base) { $base = Join-Path $env:USERPROFILE 'AppData\Local' }
        return (Join-Path $base 'RastiSiQA')
    }
    return (Join-Path $HOME '.rastisi-qa')
}

function Get-VenvPython([string]$VenvDir) {
    if (Test-IsWindows) { return (Join-Path $VenvDir 'Scripts\python.exe') }
    return (Join-Path $VenvDir 'bin/python')
}

function Resolve-RepoRoot([string]$RepoPath) {
    if (-not $RepoPath) { $RepoPath = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path }
    if (-not (Test-Path -LiteralPath $RepoPath)) { Stop-Qa "Repository path not found: $RepoPath" }
    $top = $null
    Invoke-Native { $script:__top = (& git -C $RepoPath rev-parse --show-toplevel 2>$null) }
    $top = $script:__top
    if ($LASTEXITCODE -ne 0 -or -not $top) { Stop-Qa "Not a Git repository: $RepoPath" 'Pass -RepoPath <your RastiSi clone>.' }
    return (Resolve-Path $top).Path
}

function Test-PythonCandidate([string]$Exe, [string[]]$PrefixArgs) {
    # Returns the real interpreter path when it is Python >= 3.10, else $null.
    try {
        $out = $null
        Invoke-Native { $script:__pyout = & $Exe @PrefixArgs -c "import sys; print(sys.executable); print('%d.%d' % sys.version_info[:2])" 2>$null }
        $out = $script:__pyout
        if ($LASTEXITCODE -ne 0 -or -not $out -or @($out).Count -lt 2) { return $null }
        $ver = [version](@($out)[1])
        if ($ver -lt [version]'3.10') { return $null }
        return @($out)[0]
    } catch { return $null }
}

function Find-Python([string]$Explicit) {
    if ($Explicit) {
        $only = Test-PythonCandidate $Explicit @()
        if (-not $only) { Stop-Qa "The Python you passed (-PythonPath $Explicit) is not a working Python 3.10+." 'Fix the path, or omit -PythonPath to auto-discover.' }
        return $only
    }
    $candidates = New-Object System.Collections.ArrayList
    if ($env:RASTISI_QA_PYTHON) { [void]$candidates.Add(@($env:RASTISI_QA_PYTHON, @())) }
    if (Test-IsWindows) { [void]$candidates.Add(@('py', @('-3'))) }
    [void]$candidates.Add(@('python', @()))
    [void]$candidates.Add(@('python3', @()))
    foreach ($c in $candidates) {
        $found = Test-PythonCandidate $c[0] $c[1]
        if ($found) { return $found }
    }
    Stop-Qa 'No usable Python 3.10+ found.' 'Install Python 3.11 from python.org (tick "Add python.exe to PATH"), or pass -PythonPath C:\Path\To\python.exe.'
}

function Get-FreePort([int]$Preferred) {
    $port = $Preferred
    while ($port -lt ($Preferred + 200)) {
        $listener = $null
        try {
            $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $port)
            $listener.Start(); $listener.Stop()
            return $port
        } catch { $port++ } finally { if ($listener) { try { $listener.Stop() } catch {} } }
    }
    Stop-Qa "No free local TCP port between $Preferred and $($Preferred + 199)."
}

function New-RandomSecret([int]$Bytes = 32) {
    $buf = New-Object byte[] $Bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($buf); $rng.Dispose()
    return ([Convert]::ToBase64String($buf) -replace '[^A-Za-z0-9]', 'x')
}

function Get-RequirementsHash([string]$File) {
    $bytes = [System.IO.File]::ReadAllBytes($File)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $hash = ($sha.ComputeHash($bytes) | ForEach-Object { $_.ToString('x2') }) -join ''
    $sha.Dispose()
    return $hash.Substring(0, 16)
}

function Invoke-Native([scriptblock]$Block) {
    # Windows PowerShell 5.1 turns ANY native-command stderr line into a terminating error under
    # $ErrorActionPreference='Stop'. Native tools (git, pip, python) legitimately write progress/warnings to stderr,
    # so run them with 'Continue' and judge success by $LASTEXITCODE only.
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $Block } finally { $ErrorActionPreference = $old }
}

function Add-LogLine([string]$Path, [string]$Line) {
    if ($Path) { Add-Content -LiteralPath $Path -Value $Line -Encoding UTF8 }
}

function Invoke-WithEnv([hashtable]$Vars, [scriptblock]$Block) {
    # Sets process-scope environment variables for the duration of $Block, then restores the caller's values.
    # $null removes the variable. Nothing is ever written to the user's machine/user environment.
    $saved = @{}
    foreach ($k in $Vars.Keys) {
        $saved[$k] = [Environment]::GetEnvironmentVariable($k, 'Process')
        [Environment]::SetEnvironmentVariable($k, $Vars[$k], 'Process')
    }
    try { & $Block } finally {
        foreach ($k in $saved.Keys) { [Environment]::SetEnvironmentVariable($k, $saved[$k], 'Process') }
    }
}

function Get-QaEnv($Run) {
    # The ONLY environment the Django QA process sees. Live-send/AWS settings are explicitly cleared.
    return @{
        DJANGO_SETTINGS_MODULE            = 'shop_core.settings'
        DJANGO_DEBUG                      = 'True'
        DJANGO_SECRET_KEY                 = $Run.secret_key
        DJANGO_ALLOWED_HOSTS              = 'localhost,127.0.0.1,.rastisi.localhost'
        RASTISI_PLATFORM_HOSTS            = 'rastisi.localhost,www.rastisi.localhost'
        RASTISI_PLATFORM_ADMIN_HOSTS      = 'platformadmins.rastisi.localhost'
        RASTISI_QA_MODE                   = '1'
        RASTISI_EMAIL_PROVIDER            = 'fake'
        RASTISI_FAKE_EMAIL_STATE_FILE     = (Join-Path $Run.data_dir 'fake-email-state.json')
        RASTISI_FAKE_EMAIL_MAILBOX_DIR    = (Join-Path $Run.run_dir 'mailbox')
        RASTISI_EMAIL_DNS_ADVISORY_LOOKUP = 'False'
        DATABASE_URL                      = $null
        RASTISI_SES_REGION                = $null
        RASTISI_SES_ACCESS_KEY_ID         = $null
        RASTISI_SES_SECRET_ACCESS_KEY     = $null
        RASTISI_SES_CONFIGURATION_SET     = $null
        RASTISI_SES_SNS_TOPIC_ARNS        = $null
        AWS_ACCESS_KEY_ID                 = $null
        AWS_SECRET_ACCESS_KEY             = $null
        AWS_SESSION_TOKEN                 = $null
        AWS_PROFILE                       = $null
        PYTHONUTF8                        = '1'
        PYTHONIOENCODING                  = 'utf-8'
        PYTHONDONTWRITEBYTECODE           = '1'
    }
}

function Invoke-Manage($Run, [string[]]$ManageArgs, [string]$LogName = '', [switch]$AllowFailure) {
    $py = Get-VenvPython $Run.venv_dir
    $log = ''
    if ($LogName) { $log = Join-Path $Run.logs_dir $LogName; Set-Content -LiteralPath $log -Value '' -Encoding UTF8 }
    $script:__exit = 0
    Invoke-WithEnv (Get-QaEnv $Run) {
        Push-Location $Run.src_dir
        try {
            Invoke-Native {
                & $py manage.py @ManageArgs 2>&1 | ForEach-Object { $line = "$_"; Add-LogLine $log $line; Write-Host "    $line" }
                $script:__exit = $LASTEXITCODE
            }
        } finally { Pop-Location }
    }
    if ($script:__exit -ne 0 -and -not $AllowFailure) {
        Stop-Qa "manage.py $($ManageArgs -join ' ') failed (exit $($script:__exit))." "See $log"
    }
    return $script:__exit
}

function Read-Run([string]$RunDir) {
    $file = Join-Path $RunDir 'run.json'
    if (-not (Test-Path -LiteralPath $file)) { Stop-Qa "Not a RastiSi QA run folder (run.json missing): $RunDir" }
    return (Get-Content -LiteralPath $file -Raw -Encoding UTF8 | ConvertFrom-Json)
}

function Save-Run($Run) {
    $Run | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $Run.run_dir 'run.json') -Encoding UTF8
}

function Find-LatestRun([string]$QaRoot) {
    $runsDir = Join-Path $QaRoot 'runs'
    if (-not (Test-Path -LiteralPath $runsDir)) { Stop-Qa "No QA runs found under $runsDir" 'Run Start-RastiSiQA.ps1 first.' }
    $latest = Get-ChildItem -LiteralPath $runsDir -Directory | Where-Object { Test-Path (Join-Path $_.FullName $script:QaMarker) } |
        Sort-Object Name -Descending | Select-Object -First 1
    if (-not $latest) { Stop-Qa "No QA runs found under $runsDir" 'Run Start-RastiSiQA.ps1 first.' }
    return $latest.FullName
}

function Test-InsideQaRoot([string]$Path, [string]$QaRoot) {
    $p = [System.IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
    $r = [System.IO.Path]::GetFullPath($QaRoot).TrimEnd('\', '/')
    return ($p.Length -gt $r.Length -and $p.StartsWith($r + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase))
}

function Get-QaProcess($ProcId) {
    # PID 0 / negative are never ours (PID 0 is the idle process on Windows and Linux).
    if (-not $ProcId -or [int]$ProcId -le 4) { return $null }
    return (Get-Process -Id ([int]$ProcId) -ErrorAction SilentlyContinue)
}

function Stop-QaProcess($ProcId) {
    if (-not $ProcId -or [int]$ProcId -le 4) { return }
    try {
        $p = Get-Process -Id $ProcId -ErrorAction SilentlyContinue
        if ($p) { Stop-Process -Id $ProcId -Force -ErrorAction SilentlyContinue }
    } catch {}
}

function Test-HttpUp([string]$Url) {
    # True when ANY HTTP response (even 404/302/500) is received; false only on connection failure.
    try {
        $req = [System.Net.HttpWebRequest]::Create($Url)
        $req.AllowAutoRedirect = $false; $req.Timeout = 5000
        $resp = $req.GetResponse(); $resp.Close(); return $true
    } catch [System.Net.WebException] {
        return ($null -ne $_.Exception.Response)
    } catch { return $false }
}

function Get-HttpStatus([string]$Url, [string]$HostHeader = '') {
    try {
        $req = [System.Net.HttpWebRequest]::Create($Url)
        $req.AllowAutoRedirect = $false; $req.Timeout = 15000
        if ($HostHeader) { $req.Host = $HostHeader }
        $resp = $req.GetResponse(); $code = [int]$resp.StatusCode; $resp.Close(); return $code
    } catch [System.Net.WebException] {
        if ($_.Exception.Response) { return [int]$_.Exception.Response.StatusCode }
        return 0
    } catch { return 0 }
}

function Test-LocalhostSubdomainResolves([string]$HostName) {
    try { $a = [System.Net.Dns]::GetHostAddresses($HostName); return ($a.Count -gt 0) } catch { return $false }
}
