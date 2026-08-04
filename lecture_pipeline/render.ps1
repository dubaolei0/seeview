<#
.SYNOPSIS
  讲题视频引擎 · 本地渲染包装（先 bootstrap.ps1 配好环境再用）

  在本地工作目录用 .venv 渲染一道题的 yaml，并把成片 mp4 拷回 yaml 同目录
  （yaml 在共享盘则 mp4 也回到共享盘，全组可见；mp4 已被 gitignore 不进备份）。

.USAGE
  powershell -ExecutionPolicy Bypass -File "...\render.ps1" "<yaml路径>" [-Quality medium] [-NoAudio] [-NoSync] [-TtsVoice longwan|liufei] [-TtsProvider aliyun|doubao]

  参数：
    -Quality low|medium|high   画质（默认 medium）
    -NoAudio                   跳过 TTS，仅冒烟（调试用）
    -NoStatement               讲解阶段不显示题干横幅（默认 C/D 布局顶部常驻题干卡片）
    -NoSync                    跳过引擎同步，直接用本地引擎（默认会先从共享盘同步）
    -Sync                      （已弃用，保留兼容）默认即同步，无需再传
    -TtsVoice <短名或音色ID>   本次渲染使用的音色；默认阿里云 longcheng_v3，可传 liufei
    -TtsProvider auto|aliyun|doubao
                              TTS 平台；默认 auto，zh_ 开头音色自动走豆包
    -TtsRetries <次数>         当前音色失败后的重试次数；默认 2
    -Local <路径>              本地工作目录（默认 %USERPROFILE%\lecture_pipeline）
#>
param(
  [Parameter(Mandatory=$true, Position=0)][string]$Yaml,
  [ValidateSet("low","medium","high")][string]$Quality = "medium",
  [switch]$NoAudio,
  [switch]$NoStatement,
  [switch]$NoSync,
  [switch]$Sync,
  [ValidateSet("auto","aliyun","doubao")][string]$TtsProvider = "auto",
  [string]$TtsVoice = "",
  [int]$TtsRetries = 2,
  [string]$Local = "$env:USERPROFILE\lecture_pipeline"
)

$ErrorActionPreference = "Stop"
$SharedEngine = $PSScriptRoot
$env:PYTHONIOENCODING = "utf-8"

if (-not (Test-Path $Yaml)) { throw "找不到 yaml: $Yaml" }
$VenvPy = Join-Path $Local ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPy)) { throw "本地环境未配置，请先跑 bootstrap.ps1" }

# 默认渲染前先从共享盘同步引擎代码：共享盘是单一事实源，robocopy 增量很快，
# 避免成员本地旧引擎与共享盘脱节（旧字号/旧逻辑导致渲染异常）。
# 只有显式传 -NoSync 才跳过，直接信任本地引擎（离线或临时调试用）。
if ($NoSync) {
  Write-Host "[sync] 已跳过引擎同步（-NoSync），使用本地引擎。" -ForegroundColor DarkGray
} else {
  Write-Host "[sync] 从共享盘更新引擎代码 ..." -ForegroundColor Yellow
  robocopy $SharedEngine $Local /E /XD .venv media output __pycache__ /XF *.pyc .env /NFL /NDL /NJH /NJS /NP | Out-Null
}

$YamlFull = (Resolve-Path $Yaml).ProviderPath
Push-Location $Local
try {
  Write-Host "[1/3] schema 校验 ..." -ForegroundColor Yellow
  & $VenvPy -m renderer.render "$YamlFull" --validate-only
  if ($LASTEXITCODE -ne 0) { throw "schema 校验失败，先修 yaml" }

  Write-Host "[2/3] say 数字规范化 ..." -ForegroundColor Yellow
  & $VenvPy -m normalize_say "$YamlFull"
  if ($LASTEXITCODE -eq 1) {
    Write-Host "      ⚠ 检测到多位数，需人工确认读法（基数 vs 逐位），见上方输出。" -ForegroundColor Magenta
  }

  Write-Host "[3/3] 渲染 ..." -ForegroundColor Yellow
  $renderArgs = @("-m","renderer.render","$YamlFull","--quality",$Quality)
  if ($NoAudio) { $renderArgs += "--no-audio" }
  if ($NoStatement) { $renderArgs += "--no-statement" }
  if (-not $NoAudio) {
    if ($TtsProvider -ne "auto") { $renderArgs += @("--tts-provider", $TtsProvider) }
    if ($TtsVoice) { $renderArgs += @("--tts-voice", $TtsVoice) }
    if ($TtsRetries -ne 2) { $renderArgs += @("--tts-retries", "$TtsRetries") }
  }
  & $VenvPy @renderArgs
  if ($LASTEXITCODE -ne 0) { throw "渲染失败" }
}
finally { Pop-Location }

# 把成片拷回 yaml 同目录
$stem = [IO.Path]::GetFileNameWithoutExtension($YamlFull)
$mp4 = Get-ChildItem (Join-Path $Local "media\videos") -Recurse -Filter "$stem.mp4" -ErrorAction SilentlyContinue |
       Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($mp4) {
  $yamlDir = [IO.Path]::GetDirectoryName($YamlFull)
  $dest = Join-Path $yamlDir "$stem.mp4"
  Copy-Item $mp4.FullName $dest -Force
  Write-Host "`n✓ 成片已拷回: $dest" -ForegroundColor Green
} else {
  Write-Host "`n⚠ 未在 media\videos 找到成片，请看上方渲染日志。" -ForegroundColor Red
}
