# Keeps the paper bot running on a home Windows PC, like the server's systemd unit:
# restart 30 s after a crash or lost market data (exit 1), stop for good on a configuration
# error (exit 2). Run from the repo root's copy that holds .env, .venv, data, logs and reports.
# shortcut: logs\bot-console.log is not rotated; trim it by hand if it grows past ~100 MB.
$Root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $Root
$python = Join-Path $Root '.venv\Scripts\python.exe'
New-Item -ItemType Directory -Force logs | Out-Null
while ($true) {
    & $python -m silver_bot *>> logs\bot-console.log
    $code = $LASTEXITCODE
    "$(Get-Date -Format o) bot exited with code $code" | Add-Content logs\bot-console.log
    if ($code -eq 2) { break }
    Start-Sleep -Seconds 30
}
