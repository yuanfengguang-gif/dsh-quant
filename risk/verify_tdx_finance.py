# -*- coding: utf-8 -*-
"""risk/verify_tdx_finance.py —— 通达信财务库 vs CSMAR 全量对照 + PIT 质量评估

验收项：
  ① 覆盖（行数/股票/期间/披露日覆盖率）
  ② 与 CSMAR 逐条对账（eps / np_parent / revenue / total_assets）
  ③ PIT：披露日相对报告期的滞后天数分布（是否落在 1-4 个月合理区间）
  ④ 2026 年数据是否补齐（CSMAR 缺的 2026-06-30）
用法：python risk/verify_tdx_finance.py
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CACHE = Path(__file__).resolve().parent.parent / "data" / "cache"


def main() -> int:
    t = sqlite3.connect(f"file:{(CACHE / 'tdx_finance.db').as_posix()}?mode=ro", uri=True, timeout=60)
    c = sqlite3.connect(f"file:{(CACHE / 'finance_csmar.db').as_posix()}?mode=ro", uri=True, timeout=60)
    t.execute(f"ATTACH DATABASE '{(CACHE / 'finance_csmar.db').as_posix()}' AS cs")

    print("=" * 92)
    print("① 覆盖")
    print("=" * 92)
    n, codes, mn, mx = t.execute("SELECT COUNT(*), COUNT(DISTINCT code), MIN(period), MAX(period) FROM fin_tdx").fetchone()
    ann = t.execute("SELECT SUM(announce_date IS NOT NULL AND announce_date<>''), COUNT(*) FROM fin_tdx").fetchone()
    print(f"  tdx_finance : {n:>9,} 行 / {codes:>5,} 只 / {mn} ~ {mx}")
    print(f"  披露日覆盖  : {ann[0]:,}/{ann[1]:,} = {ann[0]/max(ann[1],1)*100:.2f}%")
    cn, ccodes, cmn, cmx = c.execute("SELECT COUNT(*), COUNT(DISTINCT code), MIN(period), MAX(period) FROM fin_core_q").fetchone()
    print(f"  CSMAR 季度  : {cn:>9,} 行 / {ccodes:>5,} 只 / {cmn} ~ {cmx}")
    for per in ("2026-03-31", "2026-06-30", "2025-12-31"):
        a = t.execute("SELECT COUNT(*) FROM fin_tdx WHERE period=?", (per,)).fetchone()[0]
        b = c.execute("SELECT COUNT(*) FROM fin_core_q WHERE period=?", (per,)).fetchone()[0]
        print(f"  {per}: TDX {a:>5,} 行 | CSMAR {b:>5,} 行  {'← TDX 补齐' if a and not b else ''}")

    print("\n" + "=" * 92)
    print("② 与 CSMAR 逐条对账（同一 (code, period)）")
    print("=" * 92)
    for col_t, col_c, name in (("eps", "eps", "EPS"), ("np_parent", "np_parent", "归母净利"),
                               ("revenue", "revenue", "营业收入"), ("total_assets", "total_assets", "总资产")):
        rows = t.execute(f"""
            SELECT t.{col_t}, c.{col_c} FROM fin_tdx t
            JOIN cs.fin_core_q c ON c.code=t.code AND c.period=t.period
            WHERE t.{col_t} IS NOT NULL AND c.{col_c} IS NOT NULL AND c.{col_c}<>0""").fetchall()
        if not rows:
            print(f"  {name:8s}: 无可比行")
            continue
        devs = sorted(abs(a - b) / abs(b) for a, b in rows)
        good = sum(1 for d in devs if d < 0.005)
        print(f"  {name:8s}: n={len(rows):>7,} | 偏差<0.5%: {good/max(len(devs),1)*100:>5.1f}% | "
              f"中位 {devs[len(devs)//2]*100:>7.4f}% | P99 {devs[int(len(devs)*0.99)]*100:>7.2f}%")

    print("\n" + "=" * 92)
    print("③ PIT：披露日距报告期的滞后天数")
    print("=" * 92)
    lags = []
    for per, ann_d in t.execute(
            "SELECT period, announce_date FROM fin_tdx "
            "WHERE announce_date IS NOT NULL AND announce_date<>'' AND length(announce_date)=10"):
        try:
            d1 = date.fromisoformat(per)
            d2 = date.fromisoformat(ann_d)
            lag = (d2 - d1).days
            if -5 < lag < 400:
                lags.append(lag)
        except ValueError:
            continue
    if lags:
        lags.sort()
        neg = sum(1 for x in lags if x < 0)
        print(f"  样本 {len(lags):,} | 中位 {lags[len(lags)//2]} 天 | P10 {lags[int(len(lags)*0.1)]} | "
              f"P90 {lags[int(len(lags)*0.9)]} 天 | 负数(披露早于报告期) {neg} 条")
        buckets = {"<30天": 0, "30-60": 0, "60-120": 0, "120-180": 0, ">180": 0}
        for x in lags:
            if x < 30:
                buckets["<30天"] += 1
            elif x < 60:
                buckets["30-60"] += 1
            elif x < 120:
                buckets["60-120"] += 1
            elif x < 180:
                buckets["120-180"] += 1
            else:
                buckets[">180"] += 1
        print(f"  分布: {buckets}")

    print("\n" + "=" * 92)
    print("④ 抽样（茅台 2025-12-31 / 2026-06-30）")
    print("=" * 92)
    for per in ("2025-12-31", "2026-06-30"):
        r = t.execute("SELECT code,period,eps,bps,roe,revenue,np_parent,announce_date "
                      "FROM fin_tdx WHERE code='600519.SH' AND period=?", (per,)).fetchone()
        print(f"  {r}")
    t.close(); c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
