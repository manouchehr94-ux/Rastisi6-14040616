<#
.SYNOPSIS  Stops the web server and worker of a QA run (data is kept; start again with Start-RastiSiQA.ps1 or inspect it).
#>
[CmdletBinding()]
param([string]$RunDir = '', [string]$QaRoot = '')
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_Common.ps1')
if (-not $QaRoot) { $QaRoot = Get-DefaultQaRoot }
if (-not $RunDir) { $RunDir = Find-LatestRun $QaRoot }
$run = Read-Run $RunDir
Stop-QaProcess ([int]$run.server_pid)
Stop-QaProcess ([int]$run.worker_pid)
$run.server_pid = 0; $run.worker_pid = 0
Save-Run $run
Write-Host "Stopped server and worker of $RunDir"
