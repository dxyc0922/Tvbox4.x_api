# 注册/卸载本机定时更新任务（Windows 任务计划程序）
#
# 默认：每周一 02:00 运行，使用当前登录用户（已登录即可，锁屏也能跑）。
# 需要「未登录也运行」时，用管理员 PowerShell 加 -RunWhenLoggedOff（会要求输入该用户密码）。
#
#   powershell -ExecutionPolicy Bypass -File scripts\register-task.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\register-task.ps1 -Time 03:30 -Day Monday
#   powershell -ExecutionPolicy Bypass -File scripts\register-task.ps1 -Unregister

[CmdletBinding()]
param(
    [string]$TaskName = "TVBox-UpdateApi",
    [string]$Time = "02:00",
    [ValidateSet("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")]
    [string]$Day = "Monday",
    [string]$Python = "",
    [switch]$Functional,
    [switch]$RunWhenLoggedOff,
    [switch]$Unregister
)

$ErrorActionPreference = "Stop"

if ($Unregister) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "已删除任务: $TaskName"
    } else {
        Write-Host "任务不存在: $TaskName"
    }
    return
}

$repo = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $repo "scripts\run_local.py"
if (-not (Test-Path $runner)) {
    throw "找不到 $runner"
}

if (-not $Python) {
    $candidates = @(
        (Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -First 1).Source,
        "C:\ProgramData\miniconda3\python.exe"
    ) | Where-Object { $_ -and (Test-Path $_) }
    if (-not $candidates) { throw "找不到 python.exe，请用 -Python 指定完整路径" }
    $Python = $candidates[0]
}
if (-not (Test-Path $Python)) { throw "Python 不存在: $Python" }

$arguments = "`"$runner`""
if ($Functional) { $arguments += " --functional" }

$action = New-ScheduledTaskAction -Execute $Python -Argument $arguments -WorkingDirectory $repo

$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Day -At $Time

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 15)

if ($RunWhenLoggedOff) {
    $user = "$env:USERDOMAIN\$env:USERNAME"
    $cred = Get-Credential -UserName $user -Message "输入 $user 的密码（仅本机任务计划使用）"
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Password -RunLevel Limited
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Settings $settings -Principal $principal -User $cred.UserName `
        -Password $cred.GetNetworkCredential().Password -Force | Out-Null
} else {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Settings $settings -Force | Out-Null
}

$info = Get-ScheduledTask -TaskName $TaskName
$next = ($info | Get-ScheduledTaskInfo).NextRunTime
Write-Host ""
Write-Host "已注册任务: $($info.TaskName)"
Write-Host "  运行时间: 每周 $Day $Time"
Write-Host "  Python  : $Python"
Write-Host "  参数    : $arguments"
Write-Host "  下次运行: $next"
Write-Host ""
Write-Host "立即测试: Start-ScheduledTask -TaskName $TaskName"
Write-Host "查看日志: Get-Content (Get-ChildItem '$repo\logs' | Sort-Object LastWriteTime | Select-Object -Last 1)"
Write-Host "删除任务: powershell -ExecutionPolicy Bypass -File scripts\register-task.ps1 -Unregister"
