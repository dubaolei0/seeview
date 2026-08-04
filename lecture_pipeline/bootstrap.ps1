<#
.SYNOPSIS
  讲题视频引擎 · 本地一键配置（每位老师在自己机器上跑一次）

  做四件事：
    1. 把引擎代码从共享盘复制到本地工作目录（默认 %USERPROFILE%\lecture_pipeline）
    2. 用 Python 3.12 建 .venv 并装依赖（manim 等）
    3. 检查 ffmpeg / xelatex 是否就位
    4. 准备 .env（提示填 DASHSCOPE key）

  幂等：可重复运行。已存在的 .venv / .env 不会被覆盖（除非 -Reinstall）。

.USAGE
  # 在本地机器、共享盘的引擎目录下运行：
  powershell -ExecutionPolicy Bypass -File "Z:\_共享文件夹\tools\lecture_pipeline\bootstrap.ps1"

  可选参数：
    -Local <路径>     自定义本地工作目录（默认 %USERPROFILE%\lecture_pipeline）
    -Reinstall        删除旧 .venv 重建并重装依赖
#>
param(
  [string]$Local = "$env:USERPROFILE\lecture_pipeline",
  [switch]$Reinstall
)

$ErrorActionPreference = "Stop"
$SharedEngine = $PSScriptRoot   # 本脚本所在目录 = 共享盘上的引擎源
Write-Host "==== 讲题视频引擎 · 本地配置 ====" -ForegroundColor Cyan
Write-Host "共享引擎源 : $SharedEngine"
Write-Host "本地工作目录: $Local`n"

# ---- 1. 复制引擎代码到本地（媒体/缓存/venv/env 不覆盖）----
Write-Host "[1/4] 同步引擎代码到本地 ..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force $Local | Out-Null
# /XD 排除目录，/XF 排除文件；不动本地 .venv/.env/media/output
robocopy $SharedEngine $Local /E /XD .venv media output __pycache__ /XF *.pyc .env /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy 失败（exit $LASTEXITCODE）" }
Write-Host "      代码已就位。"

# ---- 2. Python 3.12 venv + 依赖 ----
Write-Host "[2/4] 配置 Python 3.12 虚拟环境 ..." -ForegroundColor Yellow
$Py312 = "$env:USERPROFILE\.pyenv\pyenv-win\versions\3.12.10\python.exe"
if (-not (Test-Path $Py312)) {
  # 退而求其次：找任意 3.12.x
  $cand = Get-ChildItem "$env:USERPROFILE\.pyenv\pyenv-win\versions" -Directory -ErrorAction SilentlyContinue |
          Where-Object { $_.Name -like "3.12.*" } | Select-Object -First 1
  if ($cand) { $Py312 = Join-Path $cand.FullName "python.exe" }
}
if (-not (Test-Path $Py312)) {
  # 再查标准安装路径（非 pyenv）
  $stdPaths = @(
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:ProgramFiles\Python312\python.exe",
    "${env:ProgramFiles(x86)}\Python312\python.exe"
  )
  foreach ($p in $stdPaths) {
    if (Test-Path $p) { $Py312 = $p; break }
  }
  # 最后兜底：PATH 里的 python 如果是 3.12.x 也行
  if (-not (Test-Path $Py312)) {
    $sysPy = Get-Command python -ErrorAction SilentlyContinue
    if ($sysPy) {
      $ver = & $sysPy.Source --version 2>&1
      if ($ver -match '3\.12\.') { $Py312 = $sysPy.Source }
    }
  }
}
if (-not (Test-Path $Py312)) {
  Write-Host "      未找到 Python 3.12（manim 在 3.14 上常装不上）。" -ForegroundColor Red
  Write-Host "      建议先装：pyenv install 3.12.10   然后重跑本脚本。" -ForegroundColor Red
  throw "缺少 Python 3.12"
}
Write-Host "      用解释器: $Py312"

$Venv = Join-Path $Local ".venv"
if ($Reinstall -and (Test-Path $Venv)) { Remove-Item -Recurse -Force $Venv }
if (-not (Test-Path $Venv)) {
  & $Py312 -m venv $Venv
  Write-Host "      已建 .venv"
} else {
  Write-Host "      .venv 已存在（跳过；要重建用 -Reinstall）"
}
$VenvPy = Join-Path $Venv "Scripts\python.exe"
& $VenvPy -m pip install --upgrade pip --quiet
Write-Host "      装依赖（manim 等，首次较慢）..."
& $VenvPy -m pip install -r (Join-Path $Local "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "pip install 失败" }
Write-Host "      依赖装好。"

# ---- 3. 系统依赖检查 ----
Write-Host "[3/4] 检查系统依赖 ..." -ForegroundColor Yellow
foreach ($tool in @(@{n="ffmpeg";h="音视频合并，装 https://www.gyan.dev/ffmpeg/ 并加 PATH"},
                    @{n="xelatex";h="LaTeX 公式，装 MiKTeX https://miktex.org/ 并加 PATH"})) {
  if (Get-Command $tool.n -ErrorAction SilentlyContinue) { Write-Host ("      ✓ {0}" -f $tool.n) -ForegroundColor Green }
  else { Write-Host ("      ✗ 缺 {0} —— {1}" -f $tool.n, $tool.h) -ForegroundColor Red }
}

# ---- 4. .env ----
Write-Host "[4/4] 配置密钥 ..." -ForegroundColor Yellow
$EnvFile = Join-Path $Local ".env"
$SharedEnv = Join-Path $SharedEngine ".env"   # 共享盘上的团队 .env（gitignored，不入备份）
if (Test-Path $EnvFile) {
  Write-Host "      本地 .env 已存在（保留，不覆盖）"
} elseif (Test-Path $SharedEnv) {
  # 无感：直接继承共享盘上已填好的团队密钥
  Copy-Item $SharedEnv $EnvFile
  Write-Host "      已从共享盘 .env 继承密钥（含 DASHSCOPE_API_KEY），无需手填。" -ForegroundColor Green
} else {
  Copy-Item (Join-Path $Local ".env.example") $EnvFile
  Write-Host "      未发现共享 .env —— 已生成本地 .env，请填入 DASHSCOPE_API_KEY（CosyVoice TTS）" -ForegroundColor Magenta
}

Write-Host "`n==== 完成 ====" -ForegroundColor Cyan
Write-Host "渲染一道题（yaml 可直接指向共享盘）：" -ForegroundColor White
Write-Host "  powershell -ExecutionPolicy Bypass -File `"$SharedEngine\render.ps1`" `"<yaml路径>`"" -ForegroundColor White
Write-Host "本地工作目录：$Local（.venv / media 缓存都在这）"
