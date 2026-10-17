# run_daily_update.ps1 -- 通达信每日增量更新包装脚本（供计划任务调用）
#
# 功能：
#   步骤1  tdx_daily_update.py   拉取增量（自动补齐所有缺口）
#   步骤2  fix_bars_increment.py unadj 转 qfq 并合并进 bars.db
#   日志写入 logs/tdx_daily_update_YYYYMMDD.log（保留 60 天）
#
# 用法（计划任务）：
#   powershell -NoProfile -ExecutionPolicy Bypass -File <本脚本绝对路径>

$ErrorActionPreference = "Continue"
$BASE = "D:\Programs\DSH Projects\DSH Quant"
$LOG_DIR = Join-Path $BASE "logs"
$PY = "python"

New-Item -ItemType Directory -Force -Path $LOG_DIR | Out-Null
$stamp = Get-Date -Format "yyyyMMdd"
$LOG = Join-Path $LOG_DIR "tdx_daily_update_$stamp.log"

function Write-Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -Path $LOG -Value $line -Encoding UTF8
    Write-Output $line
}

Write-Log "=== 通达信每日增量更新 开始 ==="
Set-Location $BASE
Write-Log "工作目录: $BASE"

try {
    # 步骤 1：拉取增量 → 写入 bars_tdx.db（unadj）
    Write-Log "--- 步骤1/2：拉取通达信增量 ---"
    $out = & $PY "data\tdx_daily_update.py" 2>&1
    $code = $LASTEXITCODE
    foreach ($l in $out) { Write-Log $l }
    Write-Log "步骤1 退出码: $code"

    # 步骤 2：unadj → qfq → 合并进 bars.db（下游只读 qfq）
    Write-Log "--- 步骤2/3：转前复权并合并入 bars.db ---"
    $out2 = & $PY "data\fix_bars_increment.py" 2>&1
    $code2 = $LASTEXITCODE
    foreach ($l in $out2) { Write-Log $l }
    Write-Log "步骤2 退出码: $code2"

    # 步骤 3：通达信快照（more_info 92 字段 + relation 板块归属）→ tdx_snapshot.db
    #   这些是「当日快照、无历史序列」，必须每天落一份；时间越早开始积累越好
    Write-Log "--- 步骤3/3：落通达信快照（more_info + relation）---"
    $out3 = & $PY "data\fetch_tdx_more_info.py" 2>&1
    $code3 = $LASTEXITCODE
    foreach ($l in $out3) { Write-Log $l }
    Write-Log "步骤3 退出码: $code3"

    if ($code -eq 0 -and $code2 -eq 0 -and $code3 -eq 0) {
        Write-Log "=== 全部成功 ==="
    } else {
        Write-Log "=== 部分失败（step1=$code, step2=$code2, step3=$code3）==="
    }
} catch {
    Write-Log ("异常: " + $_.Exception.Message)
}

# 日志清理：保留最近 60 天
Get-ChildItem $LOG_DIR -Filter "tdx_daily_update_*.log" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-60) } |
    Remove-Item -Force -ErrorAction SilentlyContinue
