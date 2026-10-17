# =====================================================================
# data/switch_main_db.ps1 —— 主库切换（bars.db → tdx_qfq.db 等四个库）
#
# 背景：CORE_ISSUE_TRACKER 9.14 / output\MAIN_DB_SWITCH_PROPOSAL_20261017.md
#   旧 bars.db 有 103,134 行垃圾价格 + 672,956 行历史缺失 + 减法式复权（早期为负）。
#   新库由 tdx_base.db（通达信全A日K 26 列）+ 后复权因子 按乘法口径重建。
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File data\switch_main_db.ps1            # 执行切换
#   powershell -ExecutionPolicy Bypass -File data\switch_main_db.ps1 -Rollback  # 回滚
#   powershell -ExecutionPolicy Bypass -File data\switch_main_db.ps1 -WhatIfOnly# 只演练
#
# 设计：旧库一律**改名归档**（不删），任何一步失败立即停止并提示回滚命令。
# =====================================================================
param(
    [switch]$Rollback,
    [switch]$WhatIfOnly
)

$ErrorActionPreference = "Stop"
$Root  = Split-Path -Parent $PSScriptRoot
$Cache = Join-Path $Root "data\cache"
$Tag   = "20261017"
$Log   = Join-Path $Root "logs\switch_main_db_$Tag.log"

function Say($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $msg
    Write-Host $line
    Add-Content -Path $Log -Value $line -Encoding UTF8
}

# 切换映射：旧库名 → 新库名
$Map = @(
    @{ Name = "bars.db";        New = "tdx_qfq.db";         Bak = "bars_before_qfq_switch_$Tag.db" },
    @{ Name = "hist_mv.db";     New = "hist_mv_new.db";     Bak = "hist_mv_before_switch_$Tag.db" },
    @{ Name = "valuation.db";   New = "valuation_new.db";   Bak = "valuation_before_switch_$Tag.db" },
    @{ Name = "stock_basic.db"; New = "stock_basic_new.db"; Bak = "stock_basic_before_switch_$Tag.db" }
)

Say "==================== 模式: $(if($Rollback){'回滚'}elseif($WhatIfOnly){'演练'}else{'切换'}) ===================="

if ($Rollback) {
    foreach ($m in $Map) {
        $bak = Join-Path $Cache $m.Bak
        $cur = Join-Path $Cache $m.Name
        if (-not (Test-Path $bak)) { Say "⚠️ 找不到备份 $($m.Bak)，跳过"; continue }
        if (Test-Path $cur) {
            $aside = "$cur.replaced_$((Get-Date -Format 'HHmmss'))"
            Say "把当前 $($m.Name) 移到 $([IO.Path]::GetFileName($aside))"
            Move-Item $cur $aside
        }
        Say "恢复 $($m.Bak) → $($m.Name)"
        Move-Item $bak $cur
    }
    Say "回滚完成。"
    exit 0
}

foreach ($m in $Map) {
    $new = Join-Path $Cache $m.New
    $cur = Join-Path $Cache $m.Name
    $bak = Join-Path $Cache $m.Bak
    if (-not (Test-Path $new)) { Say "⚠️ 新库不存在: $($m.New)，跳过 $($m.Name)"; continue }
    if (-not (Test-Path $cur)) { Say "⚠️ 旧库不存在: $($m.Name)，跳过"; continue }
    if (Test-Path $bak)       { Say "⚠️ 备份已存在: $($m.Bak)，跳过（避免覆盖）"; continue }
    $szNew = [math]::Round((Get-Item $new).Length / 1MB, 1)
    $szCur = [math]::Round((Get-Item $cur).Length / 1MB, 1)
    Say "$($m.Name) ($szCur MB) ← $($m.New) ($szNew MB)"
    if ($WhatIfOnly) { continue }
    Move-Item $cur $bak          # 旧库归档
    Say "  已归档 → $($m.Bak)"
    Move-Item $new $cur          # 新库就位
    Say "  新库就位 ✅"
}

if ($WhatIfOnly) { Say "演练结束（未改动任何文件）。"; exit 0 }
Say "全部切换完成。回滚命令："
Say "  powershell -ExecutionPolicy Bypass -File data\switch_main_db.ps1 -Rollback"
