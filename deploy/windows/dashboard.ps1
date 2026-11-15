# Runs the read-only dashboard on port 8765 for the "SILVR Dashboard" logon task
# (install-forward-tasks.ps1) and shows a toast once the page answers, so the owner knows it started.
# Run with PowerShell 7 (pwsh); toasts go through toast.ps1 under powershell.exe (WinRT types).
# Server output is appended to logs\dashboard-console.log. A second toast says so if the server
# stops; none is shown when logoff or shutdown ends it.
$Root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $Root
New-Item -ItemType Directory -Force logs | Out-Null
$log = Join-Path $Root 'logs\dashboard-console.log'
$toast = Join-Path $PSScriptRoot 'toast.ps1'
function Show-Toast([string]$text) {
    powershell.exe -NoProfile -WindowStyle Hidden -File $toast -Message $text
}
$python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    "$(Get-Date -Format o) missing $python; create the venv and pip install -e . first" | Add-Content $log
    Show-Toast 'SILVR dashboard did not start: the venv is missing, see logs\dashboard-console.log'
    exit 1
}
# Another listener on the port would answer the poll below and fake the "running" toast.
$holder = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($holder) {
    "$(Get-Date -Format o) port 8765 is already in use by process $($holder.OwningProcess)" | Add-Content $log
    Show-Toast "SILVR dashboard did not start: port 8765 is already in use (process $($holder.OwningProcess))"
    exit 2
}
# A thread job polls the port for about a minute, so the toast means the page really answers.
$watch = Start-ThreadJob -ArgumentList $toast {
    param($toast)
    $up = $false
    foreach ($i in 1..60) {
        $client = [Net.Sockets.TcpClient]::new()
        try { $up = $client.ConnectAsync('127.0.0.1', 8765).Wait(1000) } catch { } finally { $client.Dispose() }
        if ($up) { break }
        Start-Sleep -Seconds 1
    }
    $text = if ($up) { 'SILVR dashboard is running: http://127.0.0.1:8765' }
        else { 'SILVR dashboard did not answer within a minute, see logs\dashboard-console.log' }
    powershell.exe -NoProfile -WindowStyle Hidden -File $toast -Message $text
}
"$(Get-Date -Format o) dashboard start" | Add-Content $log
& $python -m silvr.monitoring.dashboard_server --port 8765 *>> $log
$code = if ($null -eq $LASTEXITCODE) { 1 } else { $LASTEXITCODE }
"$(Get-Date -Format o) dashboard exited with code $code" | Add-Content $log
Stop-Job $watch
Show-Toast "SILVR dashboard stopped (exit $code), see logs\dashboard-console.log"
exit $code
