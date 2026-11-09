# Keeps the paper bot running on a home Windows PC, like the server's systemd unit:
# restart 30 s after any exit (crash or lost market data is exit 1), stop for good on a
# configuration error (exit 2). Expects .env and .venv at the repo root. Run with PowerShell 7
# (pwsh); Windows PowerShell 5.1 would write the log as UTF-16 with wrapped stderr.
# shortcut: logs\bot-console.log is not rotated; trim it by hand if it grows past ~100 MB.
$Root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $Root
$python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw "missing $python; create the venv and pip install . first" }
New-Item -ItemType Directory -Force logs | Out-Null
while ($true) {
    & $python -m silvr *>> logs\bot-console.log
    $code = $LASTEXITCODE
    "$(Get-Date -Format o) bot exited with code $code" | Add-Content logs\bot-console.log
    if ($code -eq 2) { break }
    Start-Sleep -Seconds 30
}
