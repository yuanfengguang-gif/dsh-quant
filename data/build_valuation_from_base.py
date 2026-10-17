# -*- coding: utf-8 -*-
"""data/build_valuation_from_base.py —— 从 tdx_base 重建日频估值库（替代旧 valuation.db）

背景（CORE_ISSUE_TRACKER DS-16 / DS-10）：
  旧 valuation.db 只有 2020-06 起的 5,196,708 行（baostock：PE/PB/PS/PCF/换手/isST）。
  tdx_base 自带 `pe / pe_ttm / pb / ps / ps_ttm / dv_yield / dv_ttm / turnover`，
  可回溯 2000-04（3.9 倍覆盖）。

字段映射（保持旧库 schema 与单位，便于适配器直接替换）：
  close    ← daily.close（**未复权原始价**，与旧库 baostock close 口径一致）
  peTTM    ← pe_ttm      pbMRQ ← pb      psTTM ← ps_ttm
  pcfNcfTTM← 无对应源 → NULL（旧库该列本就可选）
  turn     ← turnover（**百分数**，与旧库口径一致；注意 bars.db.turn 是小数）
  tradestatus ← volume>0 ? 1 : 0（停牌推断）
  isST     ← 沿用 bars.db.daily_bar.is_st（2020-06+ 精确 / 之前近似），缺失记 0

输出：data/cache/valuation_new.db → 表 valuation(date,code,close,peTTM,pbMRQ,psTTM,pcfNcfTTM,turn,tradestatus,isST)
      + 表 meta
用法：python data/build_valuation_from_base.py
"""
from __future__ import annotations

import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CACHE = Path(__file__).resolve().parent.parent / "data" / "cache"
SRC = CACHE / "tdx_base.db"
BARS = CACHE / "bars.db"
OUT = CACHE / "valuation_new.db"


def main() -> int:
    t0 = time.time()
    if OUT.exists():
        OUT.unlink()
    con = sqlite3.connect(str(OUT))
    con.execute("PRAGMA journal_mode=MEMORY")
    con.execute("PRAGMA synchronous=OFF")
    con.execute("PRAGMA cache_size=-800000")
    con.execute("""CREATE TABLE valuation (
        date TEXT, code TEXT, close REAL, peTTM REAL, pbMRQ REAL, psTTM REAL,
        pcfNcfTTM REAL, turn REAL, tradestatus INTEGER, isST INTEGER)""")
    con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    con.commit()

    # is_st 映射（来自 bars.db，稳定口径）
    print("读取 is_st 映射 …", flush=True)
    b = sqlite3.connect(f"file:{BARS.as_posix()}?mode=ro", uri=True, timeout=60)
    st = {(c, d): v for c, d, v in b.execute(
        "SELECT code, date, is_st FROM daily_bar WHERE adjust='qfq' AND is_st=1")}
    b.close()
    print(f"  is_st=1 的记录 {len(st):,} 条")

    con.execute(f"ATTACH DATABASE '{SRC.as_posix()}' AS s")
    print("生成估值表 …", flush=True)
    cur = con.execute("""
        SELECT date, code, close, pe_ttm, pb, ps_ttm, turnover, volume
        FROM s.daily ORDER BY code, date""")
    buf = []
    n = 0
    for date, code, close, pe, pb, ps, tor, vol in cur:
        buf.append((date, code, close, pe, pb, ps, None, tor,
                    1 if (vol and vol > 0) else 0, st.get((code, date), 0)))
        if len(buf) >= 100000:
            con.executemany("INSERT INTO valuation VALUES (?,?,?,?,?,?,?,?,?,?)", buf)
            n += len(buf); buf.clear()
            if n % 2000000 < 100000:
                print(f"  {n:,} 行  {time.time()-t0:.0f}s", flush=True)
    if buf:
        con.executemany("INSERT INTO valuation VALUES (?,?,?,?,?,?,?,?,?,?)", buf)
        n += len(buf)
    con.commit()
    con.execute("CREATE INDEX idx_val ON valuation(code, date)")
    con.execute("CREATE INDEX idx_val_d ON valuation(date)")
    con.executemany("INSERT OR REPLACE INTO meta VALUES (?,?)", [
        ("unit_turn", "百分数（与旧 valuation.db 一致；bars.db.turn 是小数）"),
        ("unit_close", "未复权原始价"),
        ("source", "tdx_base.daily（通达信全A日K）"),
        ("pcfNcfTTM", "无源，恒 NULL"),
        ("isST", "沿用 bars.db.daily_bar.is_st"),
        ("built_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    ])
    con.commit()

    c, codes, mn, mx = con.execute(
        "SELECT COUNT(*), COUNT(DISTINCT code), MIN(date), MAX(date) FROM valuation").fetchone()
    print(f"\n完成: {c:,} 行 / {codes:,} 只 / {mn} ~ {mx} | 耗时 {time.time()-t0:.0f}s")
    print(f"库: {OUT}  ({OUT.stat().st_size/1024/1024/1024:.2f} GiB)")
    print("\n关键校验（600519.SH 2026-10-09）:")
    print(" ", con.execute("SELECT * FROM valuation WHERE code='600519.SH' AND date='2026-10-09'").fetchone())
    print("  空值率: peTTM %.1f%% | pb %.1f%% | psTTM %.1f%% | turn %.1f%%" % tuple(
        100 * con.execute(f"SELECT AVG(CASE WHEN {c} IS NULL THEN 1.0 ELSE 0 END) FROM valuation").fetchone()[0]
        for c in ("peTTM", "pbMRQ", "psTTM", "turn")))
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
