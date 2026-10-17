"""bars.db 数据源切换（通达信）下游回归自检

用途：HANDOFF.md 第五节 P0-2「特别检查」清单的可重复验证脚本。
检查项：
  1. 库结构/行数/日期覆盖/复权取值/来源分布
  2. is_st 过滤可用性（按年分布）
  3. turn 可用性（铁律③：2019 前换手类结论作废 —— 验证 2019 前确实缺失）
  4. 单位一致性（amount / (volume * close) 比值 → 判定 volume 是股还是手）
  5. qfq 过滤可用性（adjust='qfq' 覆盖到最新交易日）
  6. 与原通达信 unadj 库交叉验证（qfq 基准日 close 应等于 unadj close）
  7. 重点个股现价合理性抽查

用法：python risk/verify_bars_switch.py
输出：logs/verify_bars_switch_<时间戳>.json + 控制台摘要
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "data" / "cache" / "bars.db"
TDX = BASE / "data" / "cache" / "bars_tdx.db"
LOGS = BASE / "logs"
LOGS.mkdir(exist_ok=True)

SPOT = ["600519.SH", "000001.SZ", "300750.SZ", "601318.SH"]


def ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


def table_cols(con: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in con.execute(f"PRAGMA table_info({table})")]


def scalar(con: sqlite3.Connection, sql: str, params=()):
    try:
        row = con.execute(sql, params).fetchone()
        return row[0] if row else None
    except Exception as exc:  # noqa: BLE001
        return f"ERR: {exc}"


def rows(con: sqlite3.Connection, sql: str, params=()):
    try:
        return con.execute(sql, params).fetchall()
    except Exception as exc:  # noqa: BLE001
        return [("ERR", str(exc))]


def main() -> int:
    rep: dict = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "db": str(DB),
        "db_size_mb": round(DB.stat().st_size / 1024 / 1024, 1),
        "db_mtime": datetime.fromtimestamp(DB.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
    }
    con = ro(DB)
    t = "daily_bar"
    cols = table_cols(con, t)
    rep["columns"] = cols

    rep["tables"] = [r[0] for r in rows(con, "SELECT name FROM sqlite_master WHERE type='table'")]
    rep["rows_total"] = scalar(con, f"SELECT COUNT(*) FROM {t}")
    rep["date_min"] = scalar(con, f"SELECT MIN(date) FROM {t}")
    rep["date_max"] = scalar(con, f"SELECT MAX(date) FROM {t}")
    rep["stock_count"] = scalar(con, f"SELECT COUNT(DISTINCT code) FROM {t}")

    # 1. 复权取值分布
    if "adjust" in cols:
        rep["adjust_dist"] = rows(con, f"SELECT adjust, COUNT(*) FROM {t} GROUP BY adjust ORDER BY 2 DESC")
        rep["qfq_date_max"] = scalar(con, f"SELECT MAX(date) FROM {t} WHERE adjust='qfq'")
    if "source" in cols:
        rep["source_dist"] = rows(con, f"SELECT source, COUNT(*) FROM {t} GROUP BY source ORDER BY 2 DESC")

    # 2. is_st 按年
    if "is_st" in cols:
        rep["is_st_by_year"] = rows(
            con,
            f"SELECT substr(date,1,4) yr, SUM(CASE WHEN is_st=1 THEN 1 ELSE 0 END), COUNT(*) "
            f"FROM {t} GROUP BY yr ORDER BY yr",
        )

    # 3. turn 可用性按年（铁律③实证）
    if "turn" in cols:
        rep["turn_by_year"] = rows(
            con,
            f"SELECT substr(date,1,4) yr, "
            f"SUM(CASE WHEN turn IS NOT NULL AND turn>0 THEN 1 ELSE 0 END), COUNT(*) "
            f"FROM {t} GROUP BY yr ORDER BY yr",
        )

    # 4a. qfq 口径下 amount/(volume*close) —— 注意：amount/volume 是未复权原值、close 是前复权，
    #     所以该比值不是单位校验，而是「复权倍数指示」（≈1 表示接近基准日）
    if all(c in cols for c in ("amount", "volume", "close")):
        rep["qfq_ratio_by_year"] = rows(
            con,
            f"SELECT substr(date,1,4) yr, "
            f"ROUND(AVG(CASE WHEN volume>0 AND close>0 AND amount>0 "
            f"THEN amount/(volume*close) END), 4), COUNT(*) "
            f"FROM {t} GROUP BY yr ORDER BY yr",
        )

    # 4b. 真实单位校验：用未复权库（amount/(volume*close) ≈1 → 元/股；≈100 → 元/手）
    unit_unadj = None
    if TDX.exists():
        ucon = ro(TDX)
        ucols = table_cols(ucon, t)
        if all(c in ucols for c in ("amount", "volume", "close", "date")):
            unit_unadj = rows(
                ucon,
                f"SELECT substr(date,1,4) yr, "
                f"ROUND(AVG(CASE WHEN volume>0 AND close>0 AND amount>0 "
                f"THEN amount/(volume*close) END), 4), COUNT(*) "
                f"FROM {t} WHERE date >= '2015-01-01' GROUP BY yr ORDER BY yr",
            )
        ucon.close()
    rep["unit_check_unadj"] = unit_unadj

    # 4c. 增量源字段完整性（tdx_api 写入的行是否缺 turn/amount/volume）
    if "source" in cols:
        rep["null_by_source"] = rows(
            con,
            f"SELECT source, COUNT(*), "
            f"SUM(CASE WHEN turn IS NULL OR turn<=0 THEN 1 ELSE 0 END), "
            f"SUM(CASE WHEN amount IS NULL OR amount<=0 THEN 1 ELSE 0 END), "
            f"SUM(CASE WHEN volume IS NULL OR volume<=0 THEN 1 ELSE 0 END) "
            f"FROM {t} GROUP BY source",
        )
        rep["recent_days_null_turn"] = rows(
            con,
            f"SELECT date, COUNT(*), SUM(CASE WHEN turn IS NULL OR turn<=0 THEN 1 ELSE 0 END), "
            f"MAX(source) FROM {t} WHERE date >= '2026-10-01' GROUP BY date ORDER BY date",
        )

    # 5. 重点个股最新价抽查
    dmax = rep["date_max"]
    spot = {}
    for code in SPOT:
        r = rows(
            con,
            f"SELECT date, close, volume, amount, turn, is_st FROM {t} "
            f"WHERE code=? AND adjust='qfq' ORDER BY date DESC LIMIT 1",
            (code,),
        )
        spot[code] = r[0] if r and r[0] and r[0][0] != "ERR" else r
    rep["spot_latest_qfq"] = spot

    # 6. 与通达信 unadj 交叉验证（qfq 最新日 close 应 == unadj 最新日 close）
    xcheck = {}
    if TDX.exists():
        tcon = ro(TDX)
        tcols = table_cols(tcon, t)
        for code in SPOT:
            a = rows(con, f"SELECT date, close FROM {t} WHERE code=? AND adjust='qfq' "
                          f"ORDER BY date DESC LIMIT 1", (code,))
            b = rows(tcon, f"SELECT date, close FROM {t} WHERE code=? ORDER BY date DESC LIMIT 1", (code,))
            av = a[0] if a else None
            bv = b[0] if b else None
            same_date = bool(av and bv and av[0] == bv[0])
            diff = None
            if av and bv and av[1] and bv[1]:
                diff = round(abs(av[1] - bv[1]) / bv[1] * 100, 4)
            xcheck[code] = {"bars_qfq": av, "tdx_unadj": bv,
                            "same_date": same_date, "pct_diff": diff}
        rep["xcheck_tdx"] = xcheck
        rep["tdx_table_cols"] = tcols[:20]

    con.close()

    out = LOGS / f"verify_bars_switch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    # ---------- 控制台摘要 ----------
    print("=" * 68)
    print(f"bars.db 切换自检  {rep['ts']}  ({rep['db_size_mb']} MB, mtime {rep['db_mtime']})")
    print("=" * 68)
    print(f"表: {rep['tables']}")
    print(f"daily_bar 行数: {rep['rows_total']:,}  股票: {rep['stock_count']}  "
          f"日期: {rep['date_min']} ~ {rep['date_max']}")
    if "adjust_dist" in rep:
        print(f"复权分布: {rep['adjust_dist']}   qfq 最新日期: {rep.get('qfq_date_max')}")
    if "source_dist" in rep:
        print(f"来源分布: {rep['source_dist']}")

    if "is_st_by_year" in rep:
        print("\n[2] is_st 覆盖（年: ST行/总行）")
        for yr, n_st, n in rep["is_st_by_year"]:
            print(f"    {yr}: {n_st}/{n}  ({0 if not n else round(100*n_st/n,2)}%)")

    if "turn_by_year" in rep:
        print("\n[3] turn 可用性（年: 有效行/总行）—— 铁律③")
        for yr, n_ok, n in rep["turn_by_year"]:
            flag = "" if (yr >= "2019" or n_ok) else "  ← 2019 前缺失(符合铁律③)"
            print(f"    {yr}: {n_ok}/{n}{flag}")

    if "qfq_ratio_by_year" in rep:
        print("\n[4a] qfq 口径 amount/(volume*close)（≈1 近基准日；数值越大=该年复权倍数越大；"
              "**非单位校验**，因 amount/volume 未复权）")
        for yr, ratio, n in rep["qfq_ratio_by_year"]:
            print(f"    {yr}: {ratio}   n={n}")

    if rep.get("unit_check_unadj"):
        print("\n[4b] 真实单位校验（未复权库 bars_tdx.db：≈1 → 元/股；≈100 → 元/手）")
        for yr, ratio, n in rep["unit_check_unadj"]:
            print(f"    {yr}: {ratio}   n={n}")

    if rep.get("null_by_source"):
        print("\n[4c] 分来源字段完整性（source, 行数, turn缺, amount缺, volume缺）")
        for src, n, nt, na, nv in rep["null_by_source"]:
            print(f"    {src}: {n:,} 行 | turn 缺 {nt:,} | amount 缺 {na:,} | volume 缺 {nv:,}")

    if rep.get("recent_days_null_turn"):
        print("\n[4d] 近月每日 turn 缺失（date, 行数, turn缺, source）")
        for d, n, nt, src in rep["recent_days_null_turn"]:
            print(f"    {d}: {n:,} 行, turn 缺 {nt:,}  ({src})")

    print("\n[5] 重点个股最新 qfq 行情（date, close, volume, amount, turn, is_st）")
    for code, v in rep["spot_latest_qfq"].items():
        print(f"    {code}: {v}")

    if "xcheck_tdx" in rep:
        print("\n[6] 与通达信 unadj 交叉验证（qfq 基准日应等于 unadj）")
        for code, v in rep["xcheck_tdx"].items():
            ok = "✅" if v.get("same_date") and (v.get("pct_diff") or 0) < 0.01 else "⚠️"
            print(f"    {ok} {code}: qfq={v['bars_qfq']} unadj={v['tdx_unadj']} 差异={v.get('pct_diff')}%")

    print(f"\n报告: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
