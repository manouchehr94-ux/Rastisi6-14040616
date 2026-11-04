<#
.SYNOPSIS
  QA helper actions against the most recent (or a named) RastiSi QA run. Fake provider only.

.PARAMETER Action
  Status        - server/worker state, port, URLs, sender state of every store
  VerifyDomain  - pretend the (fake) e-mail provider confirmed DKIM for -Domain   (then click "retry" in the store panel)
  FailDomain    - pretend the provider reported a permanent verification failure for -Domain
  TempFailDomain- pretend the provider had a temporary error for -Domain
  RefreshSenders- run the sender revalidation job once (same as the hourly production job)
  RunWorkers    - process the e-mail/SMS outbox once
  PlaceOrder    - place a cash-on-delivery order through the real order service (scenario L)
  Event         - inject a delivery|bounce|complaint event for the latest sent e-mail (-EventType)
  ShowMailbox   - list the e-mails the fake provider accepted (From / To / Subject / provider message id)
  OpenMailbox   - open the mailbox folder in Explorer
.EXAMPLE
  .\Invoke-RastiSiQATool.ps1 -Action VerifyDomain -Domain pendingstore.test
  .\Invoke-RastiSiQATool.ps1 -Action Event -EventType bounce
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Status', 'VerifyDomain', 'FailDomain', 'TempFailDomain', 'RefreshSenders', 'RunWorkers', 'PlaceOrder', 'Event', 'ShowMailbox', 'OpenMailbox')]
    [string]$Action,
    [string]$Domain = '',
    [ValidateSet('delivery', 'bounce', 'complaint')][string]$EventType = 'delivery',
    [string]$EventId = '',
    [string]$Store = 'qa-bike',
    [string]$RunDir = '',
    [string]$QaRoot = ''
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_Common.ps1')
if (-not $QaRoot) { $QaRoot = Get-DefaultQaRoot }
if (-not $RunDir) { $RunDir = Find-LatestRun $QaRoot }
$run = Read-Run $RunDir
$run.venv_dir = [string]$run.venv_dir

switch ($Action) {
    'Status' {
        $s = Get-QaProcess $run.server_pid
        $w = Get-QaProcess $run.worker_pid
        Write-Host "run: $($run.run_dir)  commit: $($run.commit)"
        Write-Host ("server : {0} (port {1})" -f $(if ($s) { 'RUNNING pid ' + $s.Id } else { 'stopped' }), $run.port)
        Write-Host ("worker : {0}" -f $(if ($w) { 'RUNNING pid ' + $w.Id } else { 'stopped' }))
        Invoke-Manage $run @('shell', '-c', "from apps.notifications.models import EmailSenderIdentity as E; [print(e.store.slug, e.status, e.from_address or '-', e.reason_code or '-') for e in E.objects.select_related('store').order_by('store__slug')]") | Out-Null
        Invoke-Manage $run @('qa_email_domain', 'show') | Out-Null
    }
    'VerifyDomain'   { if (-not $Domain) { Stop-Qa '-Domain is required (e.g. pendingstore.test)' }; Invoke-Manage $run @('qa_email_domain', 'verify', $Domain) | Out-Null }
    'FailDomain'     { if (-not $Domain) { Stop-Qa '-Domain is required' }; Invoke-Manage $run @('qa_email_domain', 'fail', $Domain) | Out-Null }
    'TempFailDomain' { if (-not $Domain) { Stop-Qa '-Domain is required' }; Invoke-Manage $run @('qa_email_domain', 'temp-fail', $Domain) | Out-Null }
    'RefreshSenders' { Invoke-Manage $run @('refresh_email_identities') | Out-Null }
    'RunWorkers'     { Invoke-Manage $run @('process_notification_outbox') | Out-Null }
    'PlaceOrder'     { Invoke-Manage $run @('qa_place_order', '--store', $Store) | Out-Null }
    'Event' {
        $a = @('qa_simulate_email_event', $EventType)
        if ($EventId) { $a += @('--event-id', $EventId) }
        Invoke-Manage $run $a | Out-Null
    }
    'ShowMailbox' {
        $box = Join-Path $run.run_dir 'mailbox'
        $files = @(Get-ChildItem -LiteralPath $box -Filter '*.json' -ErrorAction SilentlyContinue | Sort-Object Name)
        if ($files.Count -eq 0) { Write-Host 'mailbox is empty (nothing has been sent yet - run the worker or place an order)'; break }
        foreach ($f in $files) {
            $m = Get-Content -LiteralPath $f.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
            Write-Host ("{0}`n    From   : {1}`n    To     : {2}`n    Subject: {3}`n    HTML   : {4}" -f $m.message_id, $m.from_address, $m.to, $m.subject, ($f.FullName -replace '\.json$', '.html'))
        }
    }
    'OpenMailbox' { Start-Process (Join-Path $run.run_dir 'mailbox') }
}
