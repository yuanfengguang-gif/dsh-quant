# -*- coding: utf-8 -*-
"""data/rebuild_finance_quality.py —— 用 CSMAR 重建 finance_quality.db（质量因子表）

背景（CORE_ISSUE_TRACKER DS-10 / T4 冒烟发现）：
  `finance_quality.db.quality` 每期只有 **~350 只**（远低于 `scan.py` 要求的 ≥1000）→
  `load_quality()` 恒返回空 → `scan.py` 缺 `gross_margin` 直接 KeyError。
  这是既有断点（与本次切换无关），本次一并修掉。

字段映射（old schema 10 列 → CSMAR 源）：
  roe_avg          ← fin_core_q.roe_a（小数）
  gp_margin        ← gross_margin（%）
  np_margin        ← np_parent / total_revenue * 100
  current_ratio    ← current_assets / current_liab
  liability_to_asset ← debt_ratio（%）
  cfo_to_np        ← ocf / np_parent
  cfo_to_or        ← ocf / total_revenue
  pub_date         ← fin_core.publish_date（年报期）/ 空（季度）
输出：data/cache/finance_quality_new.db → 表 quality（10 列，schema 与旧库一致）
用法：python data/rebuild_finance_quality.py
"""
from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CACHE = Path(__file__).resolve().parent.parent / "data" / "cache"
CSMAR = CACHE / "finance_csmar.db"
OLD = CACHE / "finance_quality.db"
OUT = CACHE / "finance_quality_new.db"


def r2(v, n=6):
    try:
        return round(float(v), n)
    except (TypeError, ValueError):
        return None


def div(a, b):
    try:
        a = float(a)
        b = float(b)
        return a / b if b else None
    except (TypeError, ValueError):
        return None


def main() -> int:
    t0 = time.time()
    if OUT.exists():
        OUT.unlink()
    out = sqlite3.connect(str(OUT))
    out.execute("PRAGMA synchronous=OFF")
    out.execute("""CREATE TABLE quality (
        code TEXT, period TEXT, roe_avg REAL, gp_margin REAL, np_margin REAL,
        current_ratio REAL, liability_to_asset REAL, cfo_to_np REAL, cfo_to_or REAL,
        pub_date TEXT, PRIMARY KEY (code, period))""")
    out.execute(f"ATTACH DATABASE '{CSMAR.as_posix()}' AS cs")

    # 年报期披露日（季度暂缺，用年报刊的披露日兜底）
    pub = {(r[0], r[1]): r[2] for r in out.execute(
        "SELECT code, period, publish_date FROM cs.fin_core WHERE publish_date IS NOT NULL")}

    print("生成质量表 …", flush=True)
    cur = out.execute("""
        SELECT code, period, roe_a, gross_margin, np_parent, total_revenue,
               current_assets, current_liab, debt_ratio, ocf
        FROM cs.fin_core_q ORDER BY code, period""")
    buf = []
    for (code, per, roe, gpm, npp, rev, ca, cl, dr, ocf) in cur:
        buf.append((
            code, per, r2(roe), r2(gpm), r2(div(npp, rev) * 100 if div(npp, rev) is not None else None),
            r2(div(ca, cl)), r2(dr), r2(div(ocf, npp)), r2(div(ocf, rev)),
            pub.get((code, per))))
        if len(buf) >= 50000:
            out.executemany("INSERT OR REPLACE INTO quality VALUES (?,?,?,?,?,?,?,?,?,?)", buf)
            buf.clear()
    if buf:
        out.executemany("INSERT OR REPLACE INTO quality VALUES (?,?,?,?,?,?,?,?,?,?)", buf)
    out.commit()
    out.execute("CREATE INDEX idx_q ON quality(code, period)")
    out.commit()

    n, c = out.execute("SELECT COUNT(*), COUNT(DISTINCT code) FROM quality").fetchone()
    print(f"完成: {n:,} 行 / {c:,} 只 / 耗时 {time.time()-t0:.0f}s")
    print(f"库: {OUT}  ({OUT.stat().st_size/1024/1024:.1f} MB)")

    print("\n各期覆盖（对比旧库 ~350 只）:")
    for per, k in out.execute(
            "SELECT period, COUNT(*) FROM quality GROUP BY period ORDER BY period DESC LIMIT 6"):
        print(f"  {per}: {k:,}")
    print("\n<2026-07-01 且 >=1000 只的最近期（scan.py 要的就是这个）:")
    print("  ", out.execute("SELECT period, COUNT(*) FROM quality WHERE period<'2026-07-01' "
                            "GROUP BY period HAVING COUNT(*)>=1000 ORDER BY period DESC LIMIT 1").fetchone())
    print("\n非空率:")
    for col in ("roe_avg", "gp_margin", "np_margin", "current_ratio", "liability_to_asset",
                "cfo_to_np", "cfo_to_or", "pub_date"):
        k = out.execute(f"SELECT COUNT(*) FROM quality WHERE {col} IS NOT NULL").fetchone()[0]
        print(f"  {col:18s} {k/max(n,1)*100:>5.1f}%")
    out.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
