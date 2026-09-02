# 数学组工作区 —— 自动备份到 git 远程
# 用法：Windows 任务计划器 定时调用（用桌面「注册数学组工作区备份.bat」一键注册）
# 用 UNC 路径而非 Z:，确保提权/计划任务（盘符可能未映射）下也能运行。
$ErrorActionPreference = "Continue"
$repo = "\\192.168.77.105\数学组\_共享文件夹"

$stamp = Get-Date -Format "yyyy-MM-dd HH:mm"
git -C $repo add -A

# 有改动才提交（避免空提交）
if (git -C $repo status --porcelain) {
    git -C $repo commit -q -m "auto backup $stamp"
    Write-Output "[$stamp] committed"
} else {
    Write-Output "[$stamp] 无改动，跳过提交"
}

# 先拉后推，减少多人/多机冲突；自动暂存本地未提交改动
git -C $repo pull --rebase --autostash
git -C $repo push

Write-Output "[$stamp] 备份完成"
