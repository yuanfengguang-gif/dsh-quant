# scripts/_register_task.ps1 -- register daily paper-trade task
# ASCII-only + derive paths from $PSScriptRoot (no Chinese literals -> no encoding issues)
$ErrorActionPreference = 'Stop'

$scriptsDir = $PSScriptRoot
if (-not $scriptsDir) { $scriptsDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
$proj = Split-Path -Parent $scriptsDir
$bat  = Join-Path $scriptsDir '_run_paper.bat'

Write-Output ("project : " + $proj)
Write-Output ("bat     : " + $bat)
if (-not (Test-Path $bat)) { Write-Output 'FAIL: bat not found'; exit 1 }

$action    = New-ScheduledTaskAction -Execute $bat
$trigger   = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At '16:30'
$settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$principal = New-ScheduledTaskPrincipal -UserId ("$env:USERDOMAIN\" + $env:USERNAME) -LogonType Interactive -RunLevel Limited

try {
    Register-ScheduledTask -TaskName 'DSH_PaperTrade' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Pension paper trading daily update (weekdays 16:30, catches up if missed)' -Force | Out-Null
    Write-Output 'OK: registered via Register-ScheduledTask'
} catch {
    Write-Output ("Register-ScheduledTask failed: " + $_.Exception.Message)
    $tr  = '"' + $bat + '"'
    $cmd = 'schtasks /Create /TN "DSH_PaperTrade" /TR ' + $tr + ' /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 16:30 /F'
    Write-Output ("trying: " + $cmd)
    $r = & cmd.exe /c $cmd 2>&1
    Write-Output ("result: " + ($r -join ' | '))
}

Write-Output ''
Write-Output '=== verify ==='
$t = Get-ScheduledTask -TaskName 'DSH_PaperTrade' -ErrorAction SilentlyContinue
if ($t) {
    Write-Output ("task : " + $t.TaskName + "   state: " + $t.State)
    Write-Output ("exec : " + ($t.Actions | ForEach-Object { $_.Execute }))
    $i = Get-ScheduledTaskInfo -TaskName 'DSH_PaperTrade' -ErrorAction SilentlyContinue
    if ($i) {
        Write-Output ("next : " + $i.NextRunTime)
        Write-Output ("last : " + $i.LastRunTime)
    }
    Write-Output 'RESULT: TASK_EXISTS'
} else {
    Write-Output 'RESULT: NO_TASK'
}
