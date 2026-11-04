<#
.SYNOPSIS
  Runs the automated acceptance walk-through (scenarios A-N, everything that does not need a human) against the RUNNING QA server.
  Real HTTP, real cookies, real host routing, real worker; fake e-mail provider. Writes ACCEPTANCE-REPORT.md into the run folder.
.EXAMPLE
  .\tools\windows-qa\Invoke-RastiSiAcceptanceCheck.ps1
  .\tools\windows-qa\Invoke-RastiSiAcceptanceCheck.ps1 -Only A,K
#>
[CmdletBinding()]
param([string]$RunDir = '', [string]$QaRoot = '', [string]$Only = '')
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_Common.ps1')
if (-not $QaRoot) { $QaRoot = Get-DefaultQaRoot }
if (-not $RunDir) { $RunDir = Find-LatestRun $QaRoot }
$run = Read-Run $RunDir
if (-not (Get-QaProcess $run.server_pid)) { Stop-Qa 'The QA web server is not running.' 'Start it with Start-RastiSiQA.ps1 (a new run).' }
$py = Get-VenvPython $run.venv_dir
$script = Join-Path $run.src_dir 'tools\windows-qa\qa_http_acceptance.py'
$argv = @($script, (Join-Path $run.run_dir 'run.json'))
if ($Only) { $argv += @('--only', $Only) }
$code = 0
Invoke-WithEnv (Get-QaEnv $run) {
    Push-Location $run.src_dir
    try { Invoke-Native { & $py @argv 2>&1 | ForEach-Object { Write-Host "$_" }; $script:__c = $LASTEXITCODE } } finally { Pop-Location }
}
Write-Host ""
Write-Host "Report: $(Join-Path $run.run_dir 'ACCEPTANCE-REPORT.md')"
if ($script:__c -ne 0) { Stop-Qa 'One or more automated acceptance checks failed.' 'Open ACCEPTANCE-REPORT.md for the failing rows.' }
Write-Ok 'all automated acceptance checks passed'
