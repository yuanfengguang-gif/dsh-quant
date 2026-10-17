# -*- coding: utf-8 -*-
"""data/rebuild_finance_tdx.py —— 用通达信财务源重建 finance_report（含 PIT 披露日）

背景（CORE_ISSUE_TRACKER 9.17 / 9.18）：
  通达信 `get_financial_data` 提供 1999 至今全历史报告期 + **披露日** + **2026 中报/三季报**
  （CSMAR 包只到 2026-03-31）。字段映射已用 CSMAR 交叉验证（归母净利 99.7%、总资产 99.8% 偏差<0.5%）。

口径（与旧库保持可比）：
  net_profit = 归母净利累计 / 1e8（亿元）
  revenue    = 营业收入累计 / 1e8（亿元）
  sq_net_profit / sq_revenue = 同财年内累计差分（单季）
  sq_net_yoy / sq_rev_yoy    = 与上年同季单季值比（fraction）
  eps        = FN001（通达信官方累计 EPS，元）
  roe        = FN006 / 100（累计 ROE，fra ction）
  **publish_date = announce_date（披露日，新增第 12 列 → 真 PIT）**

输出：data/cache/finance_tdx_new.db → 表 finance_report(12 列)
用法：python data/rebuild_finance_tdx.py
"""
from __future__ import annotations

import sqlite3
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CACHE = Path(__file__).resolve().parent.parent / "data" / "cache"
SRC = CACHE / "tdx_finance.db"
CSMAR = CACHE / "finance_csmar.db"
OLD = CACHE / "finance.db"
OUT = CACHE / "finance_tdx_new.db"


def main() -> int:
    t0 = time.time()
    if OUT.exists():
        OUT.unlink()
    out = sqlite3.connect(str(OUT))
    out.execute("PRAGMA synchronous=OFF")
    out.execute("""CREATE TABLE finance_report (
        code TEXT, period TEXT, net_profit REAL, revenue REAL,
        sq_net_profit REAL, sq_net_yoy REAL, sq_revenue REAL, sq_rev_yoy REAL,
        eps REAL, roe REAL, source TEXT, publish_date TEXT,
        PRIMARY KEY (code, period))""")
    out.execute("CREATE INDEX idx_fr_code ON finance_report(code)")
    out.execute("CREATE INDEX idx_fr_pub ON finance_report(publish_date)")
    out.commit()

    src = sqlite3.connect(f"file:{SRC.as_posix()}?mode=ro", uri=True, timeout=60)
    print("读取通达信财务 …", flush=True)
    by_code = defaultdict(dict)
    for code, per, eps, roe, rev, npp, ann in src.execute(
            "SELECT code, period, eps, roe, revenue, np_parent, announce_date FROM fin_tdx"):
        by_code[code][per] = (eps, roe, rev, npp, ann)
    print(f"  {len(by_code):,} 只")

    recs = []
    for code, per_map in by_code.items():
        c6 = code[:6]
        # 同财年差分（单季）
        years = defaultdict(list)
        for p in per_map:
            years[p[:4]].append(p)
        sq = {}
        for y, ps in years.items():
            ps.sort()
            prev_n = prev_r = 0.0
            for p in ps:
                _, _, rev, npp, _ = per_map[p]
                npp = npp or 0.0
                rev = rev or 0.0
                sq[p] = (npp - prev_n, rev - prev_r)
                prev_n, prev_r = npp, rev
        for p, (eps, roe, rev, npp, ann) in per_map.items():
            npp = npp or 0.0
            rev = rev or 0.0
            s_n, s_r = sq[p]
            prev_p = f"{int(p[:4])-1}{p[4:]}"
            yoy_n = yoy_r = None
            if prev_p in sq:
                pn, pr = sq[prev_p]
                if pn > 0:
                    yoy_n = s_n / pn - 1
                if pr > 0:
                    yoy_r = s_r / pr - 1
            recs.append((
                c6, p,
                round(npp / 1e8, 4) if npp else None,
                round(rev / 1e8, 4) if rev else None,
                round(s_n / 1e8, 4),
                round(yoy_n, 6) if yoy_n is not None else None,
                round(s_r / 1e8, 4),
                round(yoy_r, 6) if yoy_r is not None else None,
                eps, (roe / 100.0) if roe is not None else None,
                "tdx", ann))
    out.executemany("INSERT OR REPLACE INTO finance_report VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", recs)
    out.commit()

    n, c, mn, mx = out.execute(
        "SELECT COUNT(*), COUNT(DISTINCT code), MIN(period), MAX(period) FROM finance_report").fetchone()
    pit = out.execute("SELECT COUNT(*) FROM finance_report WHERE publish_date IS NULL OR publish_date=''").fetchone()[0]
    print(f"完成: {n:,} 行 / {c:,} 只 / {mn} ~ {mx} | 无披露日 {pit:,} | 耗时 {time.time()-t0:.0f}s")
    print(f"库: {OUT}  ({OUT.stat().st_size/1024/1024:.1f} MB)")

    # ---- 验收 ----
    print("\n① 覆盖 vs 旧库")
    old = sqlite3.connect(f"file:{OLD.as_posix()}?mode=ro", uri=True, timeout=30)
    o = old.execute("SELECT COUNT(*), COUNT(DISTINCT code), MAX(period) FROM finance_report").fetchone()
    print(f"   旧: {o[0]:,} 行 / {o[1]:,} 只 / 最新 {o[2]}  |  新: {n:,} 行 / {c:,} 只 / 最新 {mx}")

    print("\n② EPS 与 CSMAR 对比（相对 0.5% 或绝对 0.01 元 视为一致）")
    out.execute(f"ATTACH DATABASE '{CSMAR.as_posix()}' AS cs")
    r = out.execute("""
        SELECT COUNT(*),
               SUM(CASE WHEN ABS(f.eps-c.eps) <= 0.01
                          OR ABS(f.eps-c.eps)/MAX(ABS(c.eps),1e-9) <= 0.005 THEN 1 ELSE 0 END)
        FROM finance_report f JOIN cs.fin_core_q c ON c.code=f.code AND c.period=f.period
        WHERE f.eps IS NOT NULL AND c.eps IS NOT NULL""").fetchone()
    print(f"   n={r[0]:,} 一致 {r[1]:,} = {r[1]/max(r[0],1)*100:.1f}%")

    print("\n③ 归母净利 vs CSMAR")
    r2 = out.execute("""
        SELECT COUNT(*), SUM(CASE WHEN ABS(f.net_profit*1e8-c.np_parent)/MAX(ABS(c.np_parent),1e-9)<=0.005
                                  THEN 1 ELSE 0 END)
        FROM finance_report f JOIN cs.fin_core_q c ON c.code=f.code AND c.period=f.period
        WHERE f.net_profit IS NOT NULL AND c.np_parent IS NOT NULL AND c.np_parent<>0""").fetchone()
    print(f"   n={r2[0]:,} 偏差<0.5% {r2[1]:,} = {r2[1]/max(r2[0],1)*100:.2f}%")

    print("\n④ PIT 抽样（茅台）")
    for per in ("2026-06-30", "2026-09-30"):
        print("  ", out.execute("SELECT code,period,net_profit,revenue,eps,roe,publish_date "
                                "FROM finance_report WHERE code='600519' AND period=?", (per,)).fetchone())
    out.close(); src.close(); old.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
