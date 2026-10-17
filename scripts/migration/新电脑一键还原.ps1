<#
.SYNOPSIS
  新电脑一键还原（DSH 量化交易系统迁移）

.DESCRIPTION
  按顺序自动完成：
    1) 环境检查（Python / 项目目录 / 权限）
    2) pip 安装 114 个依赖
    3) 拷贝通达信技能 tdx-aidata 到家目录
    4) 拷贝 API 配置 .env
    5) 拷贝 17 个核心数据库 + 3 个源数据库
    6) 批量修正硬编码路径（每日运行链 + 计划任务）
    7) 导入 7 个 Windows 计划任务
    8) 运行验收脚本

.USAGE
  以【管理员】身份打开 PowerShell，在本文件所在目录执行：
      powershell -ExecutionPolicy Bypass -File .\新电脑一键还原.ps1

  可选参数：
      -ProjectDir "D:\Programs\DSH Projects\DSH Quant"
      -PackageDir "E:\DSH量化项目数据"
      -NewHome    "C:\Users\Lenovo"

.NOTES
  每一步失败都会停下来并给出原因，不会静默跳过。
  本文件必须保存为 UTF-8 with BOM（否则 PowerShell 5.1 中文会解析失败）。
#>
param(
    [string]$ProjectDir = "D:\Programs\DSH Projects\DSH Quant",
    [string]$PackageDir = "E:\DSH量化项目数据",
    [string]$NewHome = "$env:USERPROFILE",
    [string]$OldProject = "C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant",
    [string]$OldHome = "C:\Users\Administrator",
    [switch]$SkipData,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$script:step = 0

function Step($title) {
    $script:step++
    Write-Host ""
    Write-Host ("=" * 72) -ForegroundColor DarkGray
    Write-Host ("[{0}] {1}" -f $script:step, $title) -ForegroundColor Cyan
    Write-Host ("=" * 72) -ForegroundColor DarkGray
}

function Fail($msg) {
    Write-Host ""
    Write-Host "  [失败] $msg" -ForegroundColor Red
    Write-Host "  已停止。修好后可从当前步骤重跑整个脚本（已完成的步骤会跳过或覆盖）。" -ForegroundColor Yellow
    exit 1
}

function Ok($msg) { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Info($msg) { Write-Host "  $msg" }

Write-Host ""
Write-Host "DSH 量化交易系统 · 新电脑一键还原" -ForegroundColor White
Write-Host ("  项目目录 : {0}" -f $ProjectDir)
Write-Host ("  数据包   : {0}" -f $PackageDir)
Write-Host ("  用户主目录: {0}" -f $NewHome)
if ($DryRun) { Write-Host "  (DryRun：只检查不执行)" -ForegroundColor Yellow }

# ---------------------------------------------------------------- 1
Step "环境检查"
if (-not (Test-Path -LiteralPath $ProjectDir)) { Fail "项目目录不存在：$ProjectDir（请先 git clone）" }
Ok "项目目录存在"
if (-not (Test-Path -LiteralPath (Join-Path $ProjectDir "data\cache.py"))) { Fail "项目目录不像 DSH 量化仓库（缺 data\cache.py）" }
Ok "项目结构正确"

if (-not (Test-Path -LiteralPath $PackageDir)) { Fail "数据包目录不存在：$PackageDir" }
Ok "数据包存在"

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { Fail "未找到 python（请装 Python 3.13 并勾选 Add to PATH）" }
$pyver = (& python -V 2>&1)
Ok "Python: $pyver"
if ($pyver -notmatch "3\.(1[1-9])") { Write-Host "  [提示] 建议 Python 3.13" -ForegroundColor Yellow }

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($isAdmin) { Ok "管理员权限" } else { Write-Host "  [提示] 非管理员，第 7 步导入计划任务可能失败" -ForegroundColor Yellow }

$dFree = (Get-PSDrive -Name ((Get-Item -LiteralPath $ProjectDir).PSDrive.Name)).Free
Info ("项目所在盘剩余空间: {0:N1} GB" -f ($dFree / 1GB))

# ---------------------------------------------------------------- 2
Step "安装 Python 依赖（114 个包）"
$req = Join-Path $ProjectDir "scripts\migration\requirements_frozen.txt"
if (-not (Test-Path -LiteralPath $req)) { Fail "找不到依赖清单：$req（请先 git pull 到最新）" }
if ($DryRun) { Info "将执行: pip install -r `"$req`"" } else {
    Push-Location $ProjectDir
    & python -m pip install --upgrade pip --quiet
    & python -m pip install -r $req
    if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "pip 安装失败（常见：网络问题，可换国内源 -i https://pypi.tuna.tsinghua.edu.cn/simple）" }
    Pop-Location
    Ok "依赖安装完成"
}

# ---------------------------------------------------------------- 3
Step "拷贝通达信技能 tdx-aidata"
$srcSkill = Join-Path $PackageDir "03_项目外依赖\.dsh_skills_tdx-aidata"
$dstSkill = Join-Path $NewHome ".dsh\skills\tdx-aidata"
if (-not (Test-Path -LiteralPath $srcSkill)) { Fail "数据包里没有技能目录：$srcSkill" }
if ($DryRun) { Info "将复制 $srcSkill -> $dstSkill" } else {
    if (Test-Path -LiteralPath $dstSkill) { Remove-Item -LiteralPath $dstSkill -Recurse -Force }
    New-Item -ItemType Directory -Force -Path (Split-Path $dstSkill) | Out-Null
    Copy-Item -LiteralPath $srcSkill -Destination $dstSkill -Recurse -Force
    $dlls = (Get-ChildItem -LiteralPath $dstSkill -Recurse -Filter *.dll -ErrorAction SilentlyContinue).Count
    Ok "已复制（$dlls 个 DLL）→ $dstSkill"
    if ($dlls -lt 8) { Write-Host "  [警告] DLL 数量少于 8，通达信 API 可能不可用" -ForegroundColor Yellow }
}

# ---------------------------------------------------------------- 4
Step "拷贝 API 配置 .env"
$srcEnv = Join-Path $PackageDir "03_项目外依赖\dsh-desktop.env"
$dstEnv = Join-Path $NewHome "dsh-desktop\.env"
if (-not (Test-Path -LiteralPath $srcEnv)) { Write-Host "  [警告] 数据包里没有 .env，跳过" -ForegroundColor Yellow } else {
    if ($DryRun) { Info "将复制 $srcEnv -> $dstEnv" } else {
        New-Item -ItemType Directory -Force -Path (Split-Path $dstEnv) | Out-Null
        Copy-Item -LiteralPath $srcEnv -Destination $dstEnv -Force
        Ok "已复制 → $dstEnv"
    }
}

# ---------------------------------------------------------------- 5
Step "拷贝数据库"
if ($SkipData) {
    Info "已指定 -SkipData，跳过"
} else {
    $cache = Join-Path $ProjectDir "data\cache"
    New-Item -ItemType Directory -Force -Path $cache | Out-Null
    $groups = @("01_核心数据库_必搬", "02_源数据库_建议搬")
    $needBytes = 0
    foreach ($g in $groups) {
        $gd = Join-Path $PackageDir $g
        if (Test-Path -LiteralPath $gd) {
            $needBytes += (Get-ChildItem -LiteralPath $gd -File | Measure-Object -Property Length -Sum).Sum
        }
    }
    Info ("需要 {0:N1} GB，目标盘剩余 {1:N1} GB" -f ($needBytes / 1GB), ($dFree / 1GB))
    if ($needBytes -gt $dFree * 0.95) { Fail "空间不足，请先清理项目所在盘" }

    foreach ($g in $groups) {
        $gd = Join-Path $PackageDir $g
        if (-not (Test-Path -LiteralPath $gd)) { Write-Host "  [跳过] $g 不存在" -ForegroundColor Yellow; continue }
        Info "复制 $g ..."
        if (-not $DryRun) {
            $files = Get-ChildItem -LiteralPath $gd -File
            foreach ($f in $files) {
                Copy-Item -LiteralPath $f.FullName -Destination (Join-Path $cache $f.Name) -Force
                Write-Host ("    {0,-34} {1,8:N0} MB" -f $f.Name, ($f.Length / 1MB))
            }
        }
    }
    Ok "数据库拷贝完成 → $cache"
}

# ---------------------------------------------------------------- 6
Step "修正硬编码路径"
$rt = Join-Path $ProjectDir "scripts\migration\retarget_paths.py"
if (-not (Test-Path -LiteralPath $rt)) { Fail "找不到 retarget_paths.py（请先 git pull）" }
$rtArgs = @($rt, "--old-project", $OldProject, "--new-project", $ProjectDir,
          "--old-home", $OldHome, "--new-home", $NewHome)
Push-Location $ProjectDir
if ($DryRun) {
    & python @rtArgs --dry-run
} else {
    Info "先 DryRun 看会改哪些文件 ..."
    & python @rtArgs --dry-run | Select-Object -Last 5
    Info "正式执行（只改每日运行链，最小改动）..."
    & python @rtArgs --apply --only-daily
    if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "路径修正失败" }
    Info "重写计划任务 XML ..."
    & python @rtArgs --apply --rewrite-tasks
}
Pop-Location
Ok "路径修正完成"

# ---------------------------------------------------------------- 7
Step "导入计划任务"
$tasksDir = Join-Path $ProjectDir "output\migration\tasks_fixed"
if (-not (Test-Path -LiteralPath $tasksDir)) { $tasksDir = Join-Path $PackageDir "04_计划任务XML" }
if (-not (Test-Path -LiteralPath $tasksDir)) { Write-Host "  [警告] 找不到任务 XML，跳过" -ForegroundColor Yellow } else {
    $xmls = Get-ChildItem -LiteralPath $tasksDir -Filter *.xml
    Info ("找到 {0} 个任务 XML" -f $xmls.Count)
    foreach ($x in $xmls) {
        if ($DryRun) { Info "将导入 $($x.BaseName)" } else {
            & schtasks /create /xml $x.FullName /tn $x.BaseName /f | Out-Null
            if ($LASTEXITCODE -eq 0) { Ok "导入 $($x.BaseName)" } else { Write-Host "  [失败] $($x.BaseName)（多半是权限，需管理员）" -ForegroundColor Yellow }
        }
    }
}

# ---------------------------------------------------------------- 8
Step "验收"
if ($DryRun) { Info "DryRun 结束，未执行验收" } else {
    Push-Location $ProjectDir
    & python "scripts\migration\verify_after_migration.py"
    $code = $LASTEXITCODE
    Pop-Location
    Write-Host ""
    if ($code -eq 0) {
        Write-Host "全部完成：迁移成功，可以开始跑因子。" -ForegroundColor Green
        Write-Host "  门户启动： python -u deck\deck_server.py   → http://127.0.0.1:8787/" -ForegroundColor Green
    } else {
        Write-Host "验收有失败项，请看上面的 [FAIL] 列表。" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "提醒：数据包里的 03_项目外依赖\dsh-desktop.env 含 API 密钥，用完后请从移动硬盘删除。" -ForegroundColor Yellow
