<#
.SYNOPSIS
  讲题视频 · 友好重渲染入口

.USAGE
  powershell -ExecutionPolicy Bypass -File "Z:\_共享文件夹\tools\lecture_pipeline\rerender.ps1" -Latest
  powershell -ExecutionPolicy Bypass -File "Z:\_共享文件夹\tools\lecture_pipeline\rerender.ps1" -Changed
  powershell -ExecutionPolicy Bypass -File "Z:\_共享文件夹\tools\lecture_pipeline\rerender.ps1" "<yaml路径>"
  powershell -ExecutionPolicy Bypass -File "Z:\_共享文件夹\tools\lecture_pipeline\rerender.ps1" -Root "...\讲课\由切线条件反求参数" -Changed

  默认搜索范围：
    1. 传了 -Root：使用 -Root
    2. 传了目录：使用该目录
    3. 当前目录在项目内且目录下有 yaml：使用当前目录
    4. 能识别用户身份：使用 community/team/{姓名}/讲课
    5. 否则：使用 community/team
#>
param(
  [Parameter(Position=0)][string]$Target = "",
  [switch]$Latest,
  [switch]$Changed,
  [string]$Root = "",
  [ValidateSet("low","medium","high")][string]$Quality = "medium",
  [switch]$NoAudio,
  [switch]$NoStatement,
  [ValidateSet("auto","aliyun","doubao")][string]$TtsProvider = "auto",
  [string]$TtsVoice = "",
  [int]$TtsRetries = 2,
  [string]$Local = "$env:USERPROFILE\lecture_pipeline",
  [switch]$Yes,
  [switch]$List,
  [int]$Max = 20
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).ProviderPath
$RenderScript = Join-Path $PSScriptRoot "render.ps1"

function Get-IdentityName {
  $whoami = Join-Path $ProjectRoot "tools\scripts\whoami.py"
  if (-not (Test-Path $whoami)) { return "" }
  try {
    $name = (& python $whoami $ProjectRoot 2>$null | Select-Object -First 1).Trim()
    if ($LASTEXITCODE -eq 0 -and $name -and -not $name.StartsWith("UNKNOWN")) { return $name }
  } catch {
    return ""
  }
  return ""
}

function Resolve-DefaultRoot {
  if ($Root) { return (Resolve-Path $Root).ProviderPath }

  if ($Target -and (Test-Path $Target) -and (Get-Item $Target).PSIsContainer) {
    return (Resolve-Path $Target).ProviderPath
  }

  $cwd = (Resolve-Path ".").ProviderPath
  if ($cwd.StartsWith($ProjectRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    $hasYaml = Get-ChildItem -LiteralPath $cwd -File -Filter "*.yaml" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($hasYaml) { return $cwd }
  }

  $name = Get-IdentityName
  if ($name) {
    $lectureRoot = Join-Path $ProjectRoot "community\team\$name\讲课"
    if (Test-Path $lectureRoot) { return $lectureRoot }
  }

  return (Join-Path $ProjectRoot "community\team")
}

function Get-Mp4Path([string]$yamlPath) {
  $dir = [IO.Path]::GetDirectoryName($yamlPath)
  $stem = [IO.Path]::GetFileNameWithoutExtension($yamlPath)
  return (Join-Path $dir "$stem.mp4")
}

function Find-TargetYaml {
  if ($Target -and (Test-Path $Target) -and -not (Get-Item $Target).PSIsContainer) {
    $item = Get-Item $Target
    if ($item.Extension -ne ".yaml") { throw "目标不是 yaml 文件：$Target" }
    return @($item)
  }

  $searchRoot = Resolve-DefaultRoot
  Write-Host "[rerender] 搜索范围：$searchRoot" -ForegroundColor Cyan

  $yamls = Get-ChildItem -LiteralPath $searchRoot -Recurse -File -Filter "*.yaml" |
           Where-Object { $_.FullName -notmatch "\\media\\|\\__pycache__\\" }

  if ($Target -and -not (Test-Path $Target)) {
    $needle = $Target
    $yamls = $yamls | Where-Object { $_.BaseName -like "*$needle*" -or $_.Name -like "*$needle*" }
  }

  if ($Changed) {
    return @($yamls | Where-Object {
      $mp4 = Get-Mp4Path $_.FullName
      (-not (Test-Path $mp4)) -or ($_.LastWriteTime -gt (Get-Item $mp4).LastWriteTime)
    } | Sort-Object LastWriteTime -Descending | Select-Object -First $Max)
  }

  return @($yamls | Sort-Object LastWriteTime -Descending | Select-Object -First 1)
}

function Show-Plan($items) {
  Write-Host ""
  Write-Host "将要重渲染：" -ForegroundColor Yellow
  foreach ($item in $items) {
    $mp4 = Get-Mp4Path $item.FullName
    $status = if (Test-Path $mp4) {
      if ($item.LastWriteTime -gt (Get-Item $mp4).LastWriteTime) { "YAML 新于 MP4" } else { "覆盖现有 MP4" }
    } else {
      "尚无 MP4"
    }
    Write-Host ("  - {0}  ({1})" -f $item.FullName, $status)
  }
  Write-Host ""
}

function Confirm-Render($items) {
  Show-Plan $items
  if ($Yes) { return $true }
  $answer = Read-Host "输入 y 开始；其他输入或空回车取消"
  return ($answer -eq "y" -or $answer -eq "Y" -or $answer -eq "yes" -or $answer -eq "YES")
}

$items = Find-TargetYaml
if (-not $items -or $items.Count -eq 0) {
  Write-Host "没有找到需要重渲染的 yaml。" -ForegroundColor Yellow
  exit 0
}

if ($List) {
  Show-Plan $items
  exit 0
}

if (-not $Latest -and -not $Changed -and -not $Target) {
  Write-Host "[rerender] 未指定模式，默认使用最近修改的 yaml（等同 -Latest）。" -ForegroundColor DarkGray
}

if (-not (Confirm-Render $items)) {
  Write-Host "已取消。"
  exit 0
}

foreach ($item in $items) {
  Write-Host ""
  Write-Host "==== 渲染：$($item.FullName) ====" -ForegroundColor Cyan
  $args = @("-ExecutionPolicy","Bypass","-File",$RenderScript,$item.FullName,"-Quality",$Quality,"-TtsProvider",$TtsProvider,"-Local",$Local)
  if ($NoAudio) { $args += "-NoAudio" }
  if ($NoStatement) { $args += "-NoStatement" }
  if ($TtsVoice) { $args += @("-TtsVoice",$TtsVoice) }
  if ($TtsRetries -ne 2) { $args += @("-TtsRetries","$TtsRetries") }
  & powershell @args
  if ($LASTEXITCODE -ne 0) { throw "重渲染失败：$($item.FullName)" }
}

Write-Host ""
Write-Host "✓ 重渲染完成" -ForegroundColor Green
