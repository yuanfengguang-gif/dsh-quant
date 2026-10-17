# -*- coding: utf-8 -*-
"""risk/verify_st_sensitivity.py —— V5：is_st 敏感性测试

背景：2020-06 之前 bars.db 的 is_st 来自「价格涨跌停幅度推断」（`is_st_inferred`，半年粒度），
      P=0.821 / R=0.699 —— 有误判。若「剔除 ST」这一步对因子结论敏感，则结论可信度打折。

测试：
  ① 两种标签的一致性（bars.db 半年内出现过 is_st=1  vs  is_st_inferred.inferred=1）
  ② 分组收益差：ST 组 vs 非 ST 组的**后续 20 日平均收益**（若差异大 → 剔除 ST 影响显著）
  ③ 误判影响估计：不一致子集的规模 × 收益差 ≈ 潜在偏差
用法：python risk/verify_st_sensitivity.py
"""
from __future__ import annotations

import sqlite3
import sys
from collections import defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

C = r"D:\Programs\DSH Projects\DSH Quant\data\cache"


def halfyear(d: str) -> str:
    return f"{d[:4]}H{1 if int(d[5:7]) <= 6 else 2}"


def main() -> int:
    b = sqlite3.connect(f"file:{C}\\bars.db?mode=ro", uri=True, timeout=90)
    b.execute(f"ATTACH DATABASE '{C.replace(chr(92),'/')}/tdx_meta.db' AS m")

    print("① 聚合 bars.db 到半年（2010-2019）…", flush=True)
    agg = defaultdict(lambda: [0, 0.0, 0])   # (code, hy) -> [n_days, sum_pct, any_st]
    for code, date, pc, st in b.execute(
            "SELECT code, date, pct_chg, is_st FROM daily_bar "
            "WHERE date>='2010-01-01' AND date<'2020-01-01' AND pct_chg IS NOT NULL"):
        k = (code, halfyear(date))
        a = agg[k]
        a[0] += 1
        a[1] += pc
        if st:
            a[2] = 1
    print(f"  {len(agg):,} 个 股票-半年")

    print("② 对比 is_st_inferred …", flush=True)
    inf = {(r[0], r[1]): r[2] for r in b.execute(
        "SELECT code, period, inferred FROM m.is_st_inferred WHERE period LIKE '201%' OR period LIKE '2020H1'")}
    both = same = 0
    conf = defaultdict(int)
    for k, a in agg.items():
        if k not in inf:
            continue
        both += 1
        a_st, i_st = a[2], inf[k]
        if a_st == i_st:
            same += 1
        conf[(a_st, i_st)] += 1
    print(f"  可比 {both:,} 个 | 一致 {same:,} = {same/max(both,1)*100:.1f}%")
    print(f"  列联表（bars.db 标签, 推断标签）: {dict(conf)}")

    print("\n③ 分组收益差（半年内平均日收益 × 250 ≈ 年化）…", flush=True)
    grp = defaultdict(list)
    for k, a in agg.items():
        if k not in inf:
            continue
        avg = a[1] / max(a[0], 1)
        grp[("bars", a[2])].append(avg)
        grp[("inf", inf[k])].append(avg)
    for tag, name in (("bars", "bars.db is_st"), ("inf", "推断 inferred")):
        s1 = grp.get((tag, 1), [])
        s0 = grp.get((tag, 0), [])
        if s1 and s0:
            m1 = sum(s1) / len(s1)
            m0 = sum(s0) / len(s0)
            print(f"  {name:16s}: ST组 n={len(s1):>5,} 日均 {m1*100:+.4f}%  "
                  f"| 非ST n={len(s0):>5,} 日均 {m0*100:+.4f}%  | 差 {(m1-m0)*100:+.4f}pp/日 "
                  f"（年化 {(m1-m0)*250*100:+.1f}pp）")

    # ④ 误判影响
    wrong = sum(v for (a, i), v in conf.items() if a != i)
    total = sum(conf.values())
    print(f"\n④ 误判规模：{wrong:,}/{total:,} = {wrong/max(total,1)*100:.1f}% 个股票-半年")
    s1 = grp.get(("bars", 1), [])
    s0 = grp.get(("bars", 0), [])
    if s1 and s0:
        gap = (sum(s1)/len(s1) - sum(s0)/len(s0))
        print(f"   ST 与非 ST 日均收益差 {gap*100:+.4f}pp"
              f" → 若 10% 的股票被误标，对组合平均收益影响量级 ≈ {abs(gap)*0.10*250*100:.2f}pp/年")
    b.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
