# Local preview only. Does not checkout/reset Git or touch an existing database.
param([ValidateRange(1024, 65535)][int]$Port = 8013)
$ErrorActionPreference = 'Stop'
$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if ($env:DATABASE_URL -or $env:DJANGO_SECRET_KEY) {
    throw 'Use a fresh local shell without DATABASE_URL/DJANGO_SECRET_KEY. No value was printed or changed.'
}
if (!(Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker Desktop must be installed and running for the dedicated local Redis.' }
if (!(Get-Command py -ErrorAction SilentlyContinue)) { throw 'Install Python 3.12 with the Windows py launcher.' }
$Name = 'rastisi-altcha-qa'
$Existing = & docker ps -a --filter "name=^/$Name`$" --format '{{.Names}}'
if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop is not available.' }
if ($Existing) {
    $Info = @(& docker inspect $Name | ConvertFrom-Json)[0]
    $Label = $Info.Config.Labels.'io.rastisi.qa'
    if ($Label -ne 'altcha') { throw 'Container name is already owned by another setup; nothing changed.' }
    $Binding = @($Info.HostConfig.PortBindings.'6379/tcp')[0]
    if ($Binding.HostIp -ne '127.0.0.1' -or $Binding.HostPort -ne '6394') { throw 'Existing preview Redis has unexpected port bindings; nothing changed.' }
    & docker start $Name | Out-Null
} else {
    & docker run -d --name $Name --label io.rastisi.qa=altcha -p 127.0.0.1:6394:6379 redis:7.4-alpine redis-server --appendonly no --requirepass local-test-altcha | Out-Null
}
if ($LASTEXITCODE -ne 0) { throw 'Could not start the isolated Redis.' }
$Names = @('DJANGO_DEBUG', 'RASTISI_RATE_LIMIT_CACHE_URL', 'RASTISI_CAPTCHA_ENABLED')
$Previous = @{}
foreach ($Name in $Names) { $Previous[$Name] = [Environment]::GetEnvironmentVariable($Name, 'Process') }
Push-Location $Repo
try {
    $env:DJANGO_DEBUG = 'true'
    $env:RASTISI_RATE_LIMIT_CACHE_URL = 'redis://:local-test-altcha@127.0.0.1:6394/14'
    $env:RASTISI_CAPTCHA_ENABLED = 'true'
    $Python = Join-Path $Repo '.altcha-qa\venv\Scripts\python.exe'
    if (!(Test-Path $Python)) {
        & py -3.12 -m venv (Join-Path $Repo '.altcha-qa\venv')
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 virtual environment creation failed.' }
    }
    & $Python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    & $Python manage.py migrate --noinput --settings=tools.altcha_qa.settings
    if ($LASTEXITCODE -ne 0) { throw 'Isolated preview database setup failed.' }
    & $Python manage.py ensure_industry_registry --apply --settings=tools.altcha_qa.settings
    if ($LASTEXITCODE -ne 0) { throw 'Local preview reference data setup failed.' }
    Write-Host "Open http://rastisi.localhost:$Port/login/ (local preview; development OTP is 123456). Ctrl+C stops the server."
    & $Python manage.py runserver "127.0.0.1:$Port" --settings=tools.altcha_qa.settings
} finally {
    Pop-Location
    foreach ($Name in $Names) { [Environment]::SetEnvironmentVariable($Name, $Previous[$Name], 'Process') }
}
