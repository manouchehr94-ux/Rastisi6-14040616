<#
.SYNOPSIS
  OPTIONAL, EXPLICITLY CONFIRMED live Amazon SES smoke test. Default behaviour sends NOTHING.

.DESCRIPTION
  Uses the code of an existing QA run (same worktree + venv) but with the real SES provider and YOUR AWS credentials,
  which are read from your normal AWS environment/profile at run time. Credentials are never written to disk, never
  printed, never committed. Without -ConfirmLiveSend the script only does a read-only identity check.
  By default the recipient is the Amazon SES mailbox simulator (success@simulator.amazonses.com), which never reaches a person.

.PARAMETER FromAddress     Sender on a domain that is verified in SES, e.g. info@mybikestore.com   (required)
.PARAMETER Region          AWS region of the SES identity, e.g. eu-west-1                          (required)
.PARAMETER Scenario        success | bounce | complaint  (selects the simulator mailbox)
.PARAMETER To              A real recipient instead of the simulator (SES sandbox: must itself be verified)
.PARAMETER ConfigurationSet SES configuration set name (so delivery/bounce/complaint events reach your SNS topic)
.PARAMETER AwsProfile      Named AWS profile to use (otherwise the default credential chain)
.PARAMETER ConfirmLiveSend Actually send ONE real message through SES.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$FromAddress,
    [Parameter(Mandatory = $true)][string]$Region,
    [ValidateSet('success', 'bounce', 'complaint')][string]$Scenario = 'success',
    [string]$To = '',
    [string]$ConfigurationSet = '',
    [string]$AwsProfile = '',
    [switch]$ConfirmLiveSend,
    [string]$RunDir = '',
    [string]$QaRoot = ''
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_Common.ps1')
if (-not $QaRoot) { $QaRoot = Get-DefaultQaRoot }
if (-not $RunDir) { $RunDir = Find-LatestRun $QaRoot }
$run = Read-Run $RunDir

$envMap = Get-QaEnv $run
$envMap['RASTISI_QA_MODE'] = $null                  # QA seed/simulator commands must NOT be usable in this mode
$envMap['RASTISI_EMAIL_PROVIDER'] = 'ses'
$envMap['RASTISI_FAKE_EMAIL_STATE_FILE'] = $null
$envMap['RASTISI_FAKE_EMAIL_MAILBOX_DIR'] = $null
$envMap['RASTISI_SES_REGION'] = $Region
if ($ConfigurationSet) { $envMap['RASTISI_SES_CONFIGURATION_SET'] = $ConfigurationSet }
# AWS credentials: take whatever the caller's shell already has (never stored by this script)
foreach ($k in 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN', 'AWS_PROFILE') {
    $v = [Environment]::GetEnvironmentVariable($k, 'Process')
    if ($v) { $envMap[$k] = $v } else { $envMap.Remove($k) }
}
if ($AwsProfile) { $envMap['AWS_PROFILE'] = $AwsProfile }

$args2 = @('ses_smoke_test', '--from-address', $FromAddress, '--scenario', $Scenario)
if ($To) { $args2 += @('--to', $To) }
if ($ConfirmLiveSend) {
    Write-Warn2 'LIVE SEND CONFIRMED: one real message will be sent through Amazon SES.'
    $args2 += '--i-understand-this-sends-real-email'
} else {
    Write-Host 'Read-only mode: checking the SES identity only. Nothing will be sent (add -ConfirmLiveSend to send).'
    $args2 += '--check-only'
}
$py = Get-VenvPython $run.venv_dir
Invoke-WithEnv $envMap {
    Push-Location $run.src_dir
    try { Invoke-Native { & $py manage.py @args2 2>&1 | ForEach-Object { Write-Host "    $_" }; $script:__x = $LASTEXITCODE } } finally { Pop-Location }
}
if ($script:__x -ne 0) { Stop-Qa 'SES smoke test did not succeed (see the message above).' 'Typical causes: identity not verified yet, wrong region, sandbox recipient not verified, missing ses:SendEmail permission.' }
Write-Ok 'done'
