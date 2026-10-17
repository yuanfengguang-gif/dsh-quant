# -*- coding: utf-8 -*-
"""risk/verify_suspension_gaps.py —— V3：停牌缺口检测

为什么重要：回测里「T 日买入、T+N 卖出」如果跨过一段停牌，收益率会把停牌期间的
"跳跃"算进单笔收益，产生假信号（尤其 A 股长期停牌重组）。

检测：
  ① 每只股票在其 [首个交易日, 最后交易日] 区间内的**日历覆盖率**
  ② 长停牌（连续缺失 ≥ 20 个交易日）的次数与分布
  ③ 受影响规模：5 日、20 日前瞻收益里有多少比例"跨停牌"
用法：python risk/verify_suspension_gaps.py
"""
from __future__ import annotations

import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

C = r"D:\Programs\DSH Projects\DSH Quant\data\cache"


def main() -> int:
    con = sqlite3.connect(f"file:{C}\\bars.db?mode=ro", uri=True, timeout=120)

    print("① 交易日历 …", flush=True)
    cal = [r[0] for r in con.execute(
        "SELECT DISTINCT date FROM daily_bar WHERE date>='2010-01-01' ORDER BY date")]
    idx = {d: i for i, d in enumerate(cal)}
    print(f"  2010+ 交易日 {len(cal):,} 天（{cal[0]} ~ {cal[-1]}）")

    print("② 逐股票覆盖率 …", flush=True)
    rows = con.execute("""SELECT code, MIN(date), MAX(date), COUNT(*) FROM daily_bar
                          WHERE date>='2010-01-01' GROUP BY code""").fetchall()
    low_cov, gaps = [], Counter()
    for code, d0, d1, n in rows:
        span = idx[d1] - idx[d0] + 1 if d0 in idx and d1 in idx else n
        cov = n / max(span, 1)
        if cov < 0.90:
            low_cov.append((code, round(cov * 100, 1), n, span))
    print(f"  股票数 {len(rows):,} | 覆盖率 <90% 的 {len(low_cov):,} 只 "
          f"({len(low_cov)/max(len(rows),1)*100:.1f}%)")
    low_cov.sort(key=lambda x: x[1])
    print("  覆盖率最低 8 只:", low_cov[:8])

    print("\n③ 长停牌（连续缺失 ≥20 交易日）", flush=True)
    n_long = 0
    affected = set()
    for code, d0, d1, n in rows:
        ds = [d for (d,) in con.execute(
            "SELECT date FROM daily_bar WHERE code=? AND date>=? AND date<=? ORDER BY date",
            (code, d0, d1))]
        prev = None
        for d in ds:
            i = idx.get(d)
            if i is None:
                continue
            if prev is not None and i - prev > 20:
                n_long += 1
                gaps[i - prev] += 1
                affected.add(code)
            prev = i
    print(f"  长停牌段数 {n_long:,} | 涉及股票 {len(affected):,} 只")
    print(f"  缺口长度分布（前 10）: {gaps.most_common(10)}")

    print("\n④ 前瞻收益的跨停牌比例（抽样 200 只 × 全部日期）", flush=True)
    sample = [r[0] for r in con.execute(
        "SELECT code FROM daily_bar WHERE date>='2018-01-01' GROUP BY code "
        "HAVING COUNT(*)>200 LIMIT 200")]
    tot5 = cross5 = tot20 = cross20 = 0
    for code in sample:
        ds = [d for (d,) in con.execute(
            "SELECT date FROM daily_bar WHERE code=? AND date>='2018-01-01' ORDER BY date", (code,))]
        ii = [idx[d] for d in ds if d in idx]
        for k in range(len(ii) - 20):
            if k + 5 < len(ii):
                tot5 += 1
                if ii[k + 5] - ii[k] > 5:
                    cross5 += 1
            tot20 += 1
            if ii[k + 20] - ii[k] > 20:
                cross20 += 1
    if tot5:
        print(f"  5 日窗: {tot5:,} 笔中跨停牌 {cross5:,} = {cross5/tot5*100:.2f}%")
    if tot20:
        print(f"  20 日窗: {tot20:,} 笔中跨停牌 {cross20:,} = {cross20/tot20*100:.2f}%")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
