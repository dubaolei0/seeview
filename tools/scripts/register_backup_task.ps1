# 注册「数学组工作区备份」定时任务（每天 18:30 自动 git push）
# 仅推送 git，无需管理员权限；当前用户直接运行本脚本即可注册。
# 用 UNC 路径，确保任务在盘符未映射时也能找到脚本。
$repo = "\\192.168.77.105\数学组\_共享文件夹"
$script = "$repo\tools\scripts\git_backup.ps1"

$action  = New-ScheduledTaskAction -Execute "powershell.exe" `
           -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -Daily -At 18:30
Register-ScheduledTask -TaskName "数学组工作区备份" -Action $action -Trigger $trigger -Force | Out-Null

Write-Host ""
Write-Host "  [OK] 已注册定时任务「数学组工作区备份」" -ForegroundColor Green
Write-Host "       触发：每天 18:30 自动提交并推送到 GitHub 私有仓" -ForegroundColor Green
Write-Host "       改时间：任务计划程序 -> 数学组工作区备份 -> 触发器" -ForegroundColor DarkGray
Write-Host ""
