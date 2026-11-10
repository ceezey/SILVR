# Runs the monthly trend_ensemble forward test on a home Windows PC and shows a toast with the
# one-line result. Started by the "SILVR Forward Test" task (install-forward-tasks.ps1). Expects
# .venv at the repo root. Run with PowerShell 7 (pwsh); Windows PowerShell 5.1 would write the
# log as UTF-16. The toast is shown by toast.ps1 under powershell.exe, which has the WinRT types.
# shortcut: logs\forward-test.log is not rotated; one run adds a few lines a month.
$Root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $Root
$python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw "missing $python; create the venv and pip install . first" }
New-Item -ItemType Directory -Force logs | Out-Null
"$(Get-Date -Format o) forward test start" | Add-Content logs\forward-test.log
$lines = & $python -m silvr.backtest.trend_forward --download 2>&1 | ForEach-Object { "$_" }
$code = $LASTEXITCODE
$lines | Add-Content logs\forward-test.log
"$(Get-Date -Format o) forward test exited with code $code" | Add-Content logs\forward-test.log
$toastLine = $lines | Where-Object { $_.StartsWith('TOAST: ') } | Select-Object -Last 1
if ($toastLine) { $message = $toastLine.Substring('TOAST: '.Length) }
else { $message = 'SILVR forward test error: the run crashed, see logs\forward-test.log' }
powershell.exe -NoProfile -WindowStyle Hidden -File (Join-Path $PSScriptRoot 'toast.ps1') -Message $message
exit $code
