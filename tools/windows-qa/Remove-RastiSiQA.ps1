<#
.SYNOPSIS
  Stops a QA run and deletes its worktree, database and folder. Refuses to delete anything outside the QA root or without the QA marker file.
.PARAMETER KeepArtifacts  Copy logs, mailbox, QA-INFO.* to <QaRoot>\artifacts\<run> before deleting.
.PARAMETER All            Remove EVERY QA run (and the shared virtualenvs when -IncludeVenvs is also given).
#>
[CmdletBinding()]
param([string]$RunDir = '', [string]$QaRoot = '', [switch]$KeepArtifacts, [switch]$All, [switch]$IncludeVenvs)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_Common.ps1')
if (-not $QaRoot) { $QaRoot = Get-DefaultQaRoot }

function Remove-OneRun([string]$Dir) {
    if (-not (Test-InsideQaRoot $Dir $QaRoot)) { Stop-Qa "Refusing to delete a folder outside the QA root: $Dir" }
    if (-not (Test-Path -LiteralPath (Join-Path $Dir $script:QaMarker))) { Stop-Qa "Refusing to delete a folder without the $script:QaMarker marker: $Dir" }
    $run = $null
    try { $run = Read-Run $Dir } catch {}
    if ($run) {
        Stop-QaProcess ([int]$run.server_pid); Stop-QaProcess ([int]$run.worker_pid)
        Start-Sleep -Milliseconds 500
        if ($KeepArtifacts) {
            $dest = Join-Path $QaRoot ("artifacts\" + (Split-Path -Leaf $Dir))
            New-Item -ItemType Directory -Force -Path $dest | Out-Null
            foreach ($n in 'logs', 'mailbox') { if (Test-Path (Join-Path $Dir $n)) { Copy-Item -Recurse -Force (Join-Path $Dir $n) $dest } }
            foreach ($n in 'QA-INFO.json', 'QA-INFO.md', 'run.json') { if (Test-Path (Join-Path $Dir $n)) { Copy-Item -Force (Join-Path $Dir $n) $dest } }
            Write-Host "artifacts kept in $dest"
        }
        if ($run.repo -and (Test-Path -LiteralPath $run.src_dir)) {
            Invoke-Native { & git -C $run.repo worktree remove --force $run.src_dir 2>&1 | Out-Null }
            Invoke-Native { & git -C $run.repo worktree prune 2>&1 | Out-Null }
        }
    }
    Remove-Item -Recurse -Force -LiteralPath $Dir -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $Dir) { Write-Warn2 "Some files are still locked in $Dir - close programs using them and run this again." } else { Write-Ok "removed $Dir" }
}

if ($All) {
    $runs = Join-Path $QaRoot 'runs'
    if (Test-Path -LiteralPath $runs) { Get-ChildItem -LiteralPath $runs -Directory | ForEach-Object { Remove-OneRun $_.FullName } }
    if ($IncludeVenvs) { Get-ChildItem -LiteralPath $QaRoot -Directory -Filter 'venv-*' -ErrorAction SilentlyContinue | ForEach-Object { Remove-Item -Recurse -Force -LiteralPath $_.FullName; Write-Ok "removed $($_.FullName)" } }
} else {
    if (-not $RunDir) { $RunDir = Find-LatestRun $QaRoot }
    Remove-OneRun $RunDir
}
