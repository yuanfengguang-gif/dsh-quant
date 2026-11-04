# -*- coding: utf-8 -*-
"""verify_two_step.py - 两步法可行性：先卖黄金（金价高点）→ 持币 → 后买红利（红利低点）

用户的设想：
  第一步：黄金到高点时卖掉黄金
  第二步：持币等待，等红利 ETF 到低点再买

能否成立，取决于一个**时序事实**：
  黄金的高点，是否出现在【红利低点之前】？

  · 如果金价高点 < 红利低点日期  → 两步法可行（先卖后买，中间持币）
  · 如果金价高点 > 红利低点日期  → 两步法不可行（红利已经涨了你还没卖金，没钱买）

同时对比：
  方案A 两步法：金价高点卖金 → 红利低点买红利
  方案B 同步法：在红利低点那天同时卖金买红利
  方案C 一直持金：不动
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import sqlite3

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant")
CACHE = BASE / "data" / "cache" / "crisis"
DB = BASE / "data" / "cache" / "dividend_research.db"


def li(code):
    c = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    d = pd.read_sql_query("SELECT date,close FROM idx_daily WHERE code=? ORDER BY date", c, params=(code,))
    c.close()
    d["date"] = pd.to_datetime(d["date"])
    return d.set_index("date")["close"].astype(float)


def usc(fn):
    d = pd.read_csv(CACHE / fn)
    dc = [c for c in d.columns if str(c).lower() in ("date", "日期")][0]
    d[dc] = pd.to_datetime(d[dc])
    cc = [c for c in d.columns if str(c).lower() in ("close", "收盘")]
    return d.sort_values(dc).set_index(dc)[cc[0]].astype(float)


DIV = li("H30269")       # 红利低波价格（买入标的）
TR = li("H20269")        # 红利低波全收益（持有收益）
GLD = usc("us_GLD.csv")  # 黄金

CR = [("2008 次贷", "2007-06-01", "2010-06-30"), ("2011 欧债", "2011-04-01", "2013-06-30"),
      ("2015 A股股灾", "2015-04-01", "2017-06-30"), ("2018 Q4", "2018-09-01", "2019-12-31"),
      ("2020 COVID", "2020-01-01", "2021-06-30"), ("2022 加息", "2022-01-01", "2025-06-30")]

print("=" * 118)
print("【核心问题】黄金的高点 在 红利低点 之前还是之后？")
print("=" * 118)
print("  搜索窗口：危机开始前 6 个月 → 危机结束后 24 个月（给黄金足够时间见顶）")
print()
print(f"  {'危机':<14s}{'红利低点':>12s}{'红利低点价':>10s}{'金价高点':>12s}"
      f"{'时间差':>10s}{'红利低点时金价':>14s}{'已从高点回落':>13s}{'判定':>10s}")
rows = []
for nm, t0, t1 in CR:
    T0, T1 = pd.Timestamp(t0), pd.Timestamp(t1)
    seg_d = DIV[(DIV.index >= T0) & (DIV.index <= T1)].dropna()
    if len(seg_d) < 30:
        continue
    d_low = seg_d.idxmin()
    d_low_v = float(seg_d.min())
    # 黄金高点搜索窗口
    g0, g1 = T0 - pd.Timedelta(days=180), T1 + pd.Timedelta(days=730)
    gseg = GLD[(GLD.index >= g0) & (GLD.index <= g1)].dropna()
    if len(gseg) < 50:
        continue
    g_pk = gseg.idxmax()
    g_pk_v = float(gseg.max())
    g_at_div_low = float(GLD.asof(d_low))
    fall = g_at_div_low / g_pk_v - 1
    gap_days = (g_pk - d_low).days
    verdict = "✅ 金先顶" if gap_days < 0 else "❌ 红利先底"
    rows.append({"crisis": nm, "div_low": d_low, "div_low_v": d_low_v,
                 "gld_peak": g_pk, "gld_peak_v": g_pk_v,
                 "gld_at_low": g_at_div_low, "gap_days": gap_days, "fall": fall})
    print(f"  {nm:<14s}{str(d_low.date()):>12s}{d_low_v:>10.0f}{str(g_pk.date()):>12s}"
          f"{gap_days:>+9d}天{g_at_div_low:>14.1f}{fall:>12.1%}{verdict:>10s}")

if rows:
    a = np.array([[r["gap_days"], r["fall"]] for r in rows], dtype=float)
    print(f"\n  时间差中位：{np.median(a[:,0]):+.0f} 天（负=金价高点在红利低点之前）")
    print(f"  → 金价高点在红利低点【之前】的次数：{sum(1 for r in rows if r['gap_days']<0)}/{len(rows)}")
    print(f"  → 金价高点在红利低点【之后】的次数：{sum(1 for r in rows if r['gap_days']>0)}/{len(rows)}")
    print(f"\n  在红利低点时，金价相对自己高点的平均位置：{a[:,1].mean():.1%}")
    print(f"  （如果这一步是 −20%，说明等你等到红利低点，金价已经从高点掉了 20% —— 卖晚了）")

print()
print("=" * 118)
print("【方案对比】假设 144 万黄金，最终换成红利 ETF，持有到危机结束后 3 年")
print("=" * 118)
print("  A 两步法：金价高点卖金（拿现金）→ 红利低点买红利")
print("  B 同步法：红利低点那天，同时卖金买红利")
print("  C 不动：一直持金")
print()
print(f"  {'危机':<14s}{'A 两步法':>12s}{'B 同步法':>12s}{'C 持金':>10s}{'A-B':>9s}{'B-A的现金损失':>14s}")
for r in rows:
    nm = r["crisis"]
    # A：在黄金高点卖金换现金，在红利低点用现金买红利
    cash = r["gld_peak_v"]                      # 以黄金单位计，卖在高点得到
    a_shares = cash / r["div_low_v"]
    # B：在红利低点同时卖金买红利
    b_shares = r["gld_at_low"] / r["div_low_v"]
    # 同一时点估值：危机结束后 3 年
    end = r["div_low"] + pd.Timedelta(days=1095)
    if end > TR.index[-1]:
        end = TR.index[-1]
    tr_end = float(TR.asof(end))
    gld_end = float(GLD.asof(end))
    A = a_shares * tr_end
    B = b_shares * tr_end
    C = gld_end
    print(f"  {nm:<14s}{A:>12.1f}{B:>12.1f}{C:>10.1f}{A-B:>+9.1f}"
          f"{(r['gld_at_low']-r['gld_peak_v']):>14.1f}")
print("\n  说明：A 比 B 多出的部分 = 在黄金高点卖出、在红利低点买入的价差（以黄金单位计）")
print("        若 A > B，两步法确实优于同步法；若接近，说明多此一举")

print()
print("=" * 118)
print("【关键风险】如果金价高点迟迟不来（或金价一直涨），两步法会怎样？")
print("=" * 118)
print("  检查：红利低点之后，金价还涨了多少？（即'等金价见顶'要等多久、代价多大）")
print(f"  {'危机':<14s}{'红利低点':>12s}{'之后1年金价':>13s}{'之后2年':>10s}{'之后3年':>10s}{'金价高点距红利低点':>20s}")
for r in rows:
    d = r["div_low"]
    cells = []
    for H in (365, 730, 1095):
        e = d + pd.Timedelta(days=H)
        cells.append(f"{float(GLD.asof(e))/r['gld_at_low']-1:>+9.1%}" if e <= GLD.index[-1] else "        —")
    print(f"  {r['crisis']:<14s}{str(d.date()):>12s}{cells[0]}{cells[1]}{cells[2]}"
          f"{r['gap_days']:>+17d}天")
