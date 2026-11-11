# Runs the monthly trend_ensemble forward test on a home Windows PC and shows a toast with the
# one-line result. Started by the "SILVR Forward Test" task (install-forward-tasks.ps1). Expects
# .venv at the repo root. Run with PowerShell 7 (pwsh); Windows PowerShell 5.1 would write the
# log as UTF-16. The toast is shown by toast.ps1 under powershell.exe, which has the WinRT types.
# Output is appended to logs\forward-test.log line by line as it arrives. If the task's 12-hour
# limit kills the run, the log keeps what was written but no toast is shown.
# shortcut: logs\forward-test.log is not rotated; one run adds a few lines a month.
$Root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $Root
New-Item -ItemType Directory -Force logs | Out-Null
$log = 'logs\forward-test.log'
$crash = 'SILVR forward test error: the run crashed, see logs\forward-test.log'
function Show-Toast([string]$text) {
    powershell.exe -NoProfile -WindowStyle Hidden -File (Join-Path $PSScriptRoot 'toast.ps1') -Message $text
}
$python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    "$(Get-Date -Format o) missing $python; create the venv and pip install -e . first" | Add-Content $log
    Show-Toast $crash
    exit 1
}
"$(Get-Date -Format o) forward test start" | Add-Content $log
$lines = & $python -m silvr.backtest.trend_forward --download 2>&1 | ForEach-Object {
    $line = "$_"
    Add-Content $log $line
    $line
}
$code = if ($null -eq $LASTEXITCODE) { 1 } else { $LASTEXITCODE }
"$(Get-Date -Format o) forward test exited with code $code" | Add-Content $log
$toastLine = $lines | Where-Object { $_ -and $_.StartsWith('TOAST: ') } | Select-Object -Last 1
Show-Toast $(if ($toastLine) { $toastLine.Substring('TOAST: '.Length) } else { $crash })
# silvr-cr-006: refresh the hosted snapshot. It logs its own result and never changes $code.
& (Join-Path $PSScriptRoot 'publish-dashboard.ps1')
exit $code
