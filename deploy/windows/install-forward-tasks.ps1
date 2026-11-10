# Registers the two SILVR scheduled tasks on a home Windows PC, replacing same-named ones. It never
# touches any other task. Run once, with PowerShell 7 (pwsh), as the user who will be logged on:
#   pwsh -NoProfile -File deploy\windows\install-forward-tasks.ps1 -Root C:\SILVR-live
#   "SILVR Forward Test": day 1 of every month at 09:00 local time; StartWhenAvailable runs it at
#       the next logon if the PC was off; runs only while the user is logged on (Interactive).
#   "SILVR Dashboard": at logon of this user, the read-only dashboard on port 8765.
# Both actions run as conhost.exe --headless pwsh, so no console window flashes (as the bot task).
# shortcut: the monthly trigger is a CIM MSFT_TaskMonthlyTrigger, because New-ScheduledTaskTrigger
# has no -Monthly. schtasks.exe /SC MONTHLY was rejected: it cannot set StartWhenAvailable.
param([Parameter(Mandatory)][string]$Root)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path $Root).Path
$forwardName = 'SILVR Forward Test'
$dashboardName = 'SILVR Dashboard'
$pwsh = (Get-Command pwsh).Source
$conhost = Join-Path $env:SystemRoot 'System32\conhost.exe'
$user = "$env:USERDOMAIN\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
# The forward task stops after 12 hours (a hung download must not run forever; the verdict run
# re-simulates 2022-2027 once and needs headroom). The dashboard is a server: no limit.
$forwardSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 12)
$dashboardSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)

$monthly = Get-CimClass -Namespace Root/Microsoft/Windows/TaskScheduler -ClassName MSFT_TaskMonthlyTrigger
$forwardTrigger = New-CimInstance -CimClass $monthly -ClientOnly -Property @{
    DaysOfMonth   = [uint16]1                     # bit 0 = day 1
    MonthOfYear   = [uint16]4095                  # all twelve months
    StartBoundary = (Get-Date -Hour 9 -Minute 0 -Second 0 -Format 's')
    Enabled       = $true
}
$forwardAction = New-ScheduledTaskAction -Execute $conhost -WorkingDirectory $Root -Argument (
    '--headless "{0}" -NoProfile -File "{1}"' -f $pwsh, (Join-Path $Root 'deploy\windows\forward-test.ps1'))
Register-ScheduledTask -TaskName $forwardName -Force -Principal $principal -Settings $forwardSettings `
    -Trigger $forwardTrigger -Action $forwardAction | Out-Null

$python = Join-Path $Root '.venv\Scripts\python.exe'
$dashboardLog = Join-Path $Root 'logs\dashboard-console.log'
New-Item -ItemType Directory -Force (Join-Path $Root 'logs') | Out-Null
$dashboardAction = New-ScheduledTaskAction -Execute $conhost -WorkingDirectory $Root -Argument (
    "--headless `"{0}`" -NoProfile -Command `"& '{1}' -m silvr.monitoring.dashboard_server --port 8765 *>> '{2}'`"" -f $pwsh, $python, $dashboardLog)
Register-ScheduledTask -TaskName $dashboardName -Force -Principal $principal -Settings $dashboardSettings `
    -Trigger (New-ScheduledTaskTrigger -AtLogOn -User $user) -Action $dashboardAction | Out-Null

Write-Host "Registered '$forwardName' and '$dashboardName'. To remove both:"
Write-Host @'
Unregister-ScheduledTask -TaskName 'SILVR Forward Test','SILVR Dashboard' -Confirm:$false
'@
