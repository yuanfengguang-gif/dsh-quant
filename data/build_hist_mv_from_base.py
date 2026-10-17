# -*- coding: utf-8 -*-
"""data/build_hist_mv_from_base.py —— 从 tdx_base 重建流通市值月频库（替代旧 hist_mv.db）

背景（CORE_ISSUE_TRACKER DS-09）：
  旧 hist_mv.db 只有 2020-01 起的 82 个月、5,221 只，**且茅台 0 行**（覆盖残缺）。
  tdx_base 的 `circ_mv`（万元）是**逐日**流通市值，可回溯到 2000-04（319 个月）。
  单位换算（实测）：旧库单位 = 百万元 → 新值 = circ_mv(万元) / 100
  与旧库重叠点校验：0.08% ~ 1.1%（差异来自月末取价/数据源不同，可接受）

输出：data/cache/hist_mv_new.db → 表 hist_mv(month, code, circ_mv)  ← schema 与旧库一致
      + 表 meta(key, value) 记录单位与来源
用法：python data/build_hist_mv_from_base.py
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
OUT = CACHE / "hist_mv_new.db"


def main() -> int:
    t0 = time.time()
    if OUT.exists():
        OUT.unlink()
    con = sqlite3.connect(str(OUT))
    con.execute("PRAGMA journal_mode=MEMORY")
    con.execute("PRAGMA synchronous=OFF")
    con.execute("PRAGMA cache_size=-800000")
    con.execute("CREATE TABLE hist_mv (month TEXT, code TEXT, circ_mv REAL, last_date TEXT)")
    con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    con.commit()

    con.execute(f"ATTACH DATABASE '{SRC.as_posix()}' AS s")
    print("聚合中（每只股票每月取最后一个交易日）…", flush=True)
    con.execute("""
        INSERT INTO hist_mv (month, code, circ_mv, last_date)
        SELECT substr(date,1,7) AS m, code, circ_mv/100.0 AS mv, date
        FROM (
            SELECT code, date, circ_mv,
                   MAX(date) OVER (PARTITION BY code, substr(date,1,7)) AS mx
            FROM s.daily
            WHERE circ_mv IS NOT NULL AND circ_mv > 0
        )
        WHERE date = mx
    """)
    con.commit()
    con.execute("CREATE INDEX idx_hist_mv ON hist_mv(code, month)")
    con.execute("CREATE INDEX idx_hist_mv_m ON hist_mv(month)")
    con.executemany("INSERT OR REPLACE INTO meta VALUES (?,?)", [
        ("unit", "百万元（= tdx_base.circ_mv 万元 / 100）"),
        ("source", "tdx_base.daily.circ_mv（通达信全A日K 包）"),
        ("method", "每只股票每月取最后一个交易日的流通市值"),
        ("built_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    ])
    con.commit()

    n, c, mn, mx, nm = con.execute(
        "SELECT COUNT(*), COUNT(DISTINCT code), MIN(month), MAX(month), COUNT(DISTINCT month) "
        "FROM hist_mv").fetchone()
    print(f"完成: {n:,} 行 / {c:,} 只 / {nm} 个月 / {mn} ~ {mx} | 耗时 {time.time()-t0:.0f}s")
    print(f"库: {OUT}  ({OUT.stat().st_size/1024/1024:.1f} MB)")

    print("\n关键校验:")
    for code in ("600519.SH", "000651.SZ", "000001.SZ"):
        r = con.execute("SELECT COUNT(*), MIN(month), MAX(month) FROM hist_mv WHERE code=?", (code,)).fetchone()
        print(f"  {code}: {r[0]} 个月 ({r[1]} ~ {r[2]})")
    print("\n  抽样（600519.SH 2020-06 / 2026-09）:")
    for m in ("2020-06", "2026-09"):
        r = con.execute("SELECT month, code, circ_mv, last_date FROM hist_mv WHERE code='600519.SH' AND month=?", (m,)).fetchone()
        print(f"    {r}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
