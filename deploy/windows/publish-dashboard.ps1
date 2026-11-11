# Publishes the read-only dashboard as a static snapshot (silvr-cr-006). Called at the end of
# forward-test.ps1 after each monthly run; can also be run by hand. Exports the same page the home
# dashboard serves to .tmp\silvr-dashboard, then deploys that folder to Vercel. The first deploy
# links the folder to a Vercel project named after it (.tmp\silvr-dashboard\.vercel keeps the link).
# Needs the Vercel CLI on PATH, signed in as the PC's user. Writes nothing outside .tmp and logs.
# Every outcome is appended to logs\forward-test.log; the exit code is 0 on success, 1 otherwise.
$Root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $Root
New-Item -ItemType Directory -Force logs | Out-Null
# Absolute: the deploy runs inside $site (Push-Location), where a relative path would not exist.
$log = Join-Path $Root 'logs\forward-test.log'
$site = Join-Path $Root '.tmp\silvr-dashboard'
function Write-Log([string]$text) { "$(Get-Date -Format o) publish: $text" | Add-Content $log }

$python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { Write-Log "skipped, missing $python"; exit 1 }
$vercel = Get-Command vercel -ErrorAction SilentlyContinue
if (-not $vercel) { Write-Log 'skipped, the Vercel CLI is not on PATH'; exit 1 }

& $python -m silvr.monitoring.dashboard_server --export $site 2>&1 | ForEach-Object { Write-Log "$_" }
if ($LASTEXITCODE -ne 0) { Write-Log "export failed with code $LASTEXITCODE"; exit 1 }

Push-Location $site
try {
    # Empty stdin: a signed-out CLI fails at once instead of waiting for a login until the task's 12-hour limit.
    $null | & $vercel.Source deploy --prod --yes 2>&1 | ForEach-Object { Write-Log "$_" }
    $code = if ($null -eq $LASTEXITCODE) { 1 } else { $LASTEXITCODE }
} finally {
    Pop-Location
}
Write-Log "vercel deploy exited with code $code"
exit $(if ($code -eq 0) { 0 } else { 1 })
