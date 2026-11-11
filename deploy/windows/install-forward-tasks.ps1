# Registers the two SILVR scheduled tasks on a home Windows PC, replacing same-named ones. It never
# touches any other task. Run once, with PowerShell 7 (pwsh), as the user who will be logged on:
#   pwsh -NoProfile -File deploy\windows\install-forward-tasks.ps1 -Root C:\SILVR-live
#   "SILVR Forward Test": day 1 of every month at 09:00 local time; StartWhenAvailable runs it at
#       the next logon if the PC was off; runs only while the user is logged on (Interactive).
#   "SILVR Dashboard": at logon of this user, the read-only dashboard on port 8765.
# Both actions run as conhost.exe --headless pwsh, so no console window flashes (as the bot task).
# The monthly task is registered from Task Scheduler XML: New-ScheduledTaskTrigger has no -Monthly,
# Windows rejects a CIM monthly trigger instance ("The parameter is incorrect", seen 2026-11-11), and
# schtasks.exe /SC MONTHLY cannot set StartWhenAvailable.
param([Parameter(Mandatory)][string]$Root)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path $Root).Path
$forwardName = 'SILVR Forward Test'
$dashboardName = 'SILVR Dashboard'
$pwsh = (Get-Command pwsh).Source
$conhost = Join-Path $env:SystemRoot 'System32\conhost.exe'
$user = "$env:USERDOMAIN\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
# The dashboard is a server: no time limit. (The forward task's 12-hour limit is in its XML below.)
$dashboardSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)

# Day 1 of every month at 09:00 local; StartWhenAvailable catches up after the PC was off; only while
# this user is logged on (InteractiveToken); stops after 12 hours (a hung download must not run
# forever; the verdict run re-simulates 2022-2027 once and needs headroom).
function X([string]$text) { [System.Security.SecurityElement]::Escape($text) }
$start = Get-Date -Hour 9 -Minute 0 -Second 0 -Format 's'
$months = (('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September',
    'October', 'November', 'December') | ForEach-Object { "<$_ />" }) -join ''
$userXml = X $user
$conhostXml = X $conhost
$argsXml = X ('--headless "{0}" -NoProfile -File "{1}"' -f $pwsh, (Join-Path $Root 'deploy\windows\forward-test.ps1'))
$rootXml = X $Root
$forwardXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>$start</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByMonth><DaysOfMonth><Day>1</Day></DaysOfMonth><Months>$months</Months></ScheduleByMonth>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author"><UserId>$userXml</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal>
  </Principals>
  <Settings>
    <StartWhenAvailable>true</StartWhenAvailable>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT12H</ExecutionTimeLimit>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
  </Settings>
  <Actions Context="Author">
    <Exec><Command>$conhostXml</Command><Arguments>$argsXml</Arguments><WorkingDirectory>$rootXml</WorkingDirectory></Exec>
  </Actions>
</Task>
"@
Register-ScheduledTask -TaskName $forwardName -Force -Xml $forwardXml | Out-Null

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
