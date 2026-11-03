# -*- coding: utf-8 -*-
"""verify_keep_gold_sizing.py - 保留多少黄金？用 ETF 现金流能覆盖多少？

用户的决定：保留一定数量实物黄金 + 用 ETF 获取现金流。
总资产 160 万 = 144 万黄金 + 16 万现金；月支出 5,000 元（年 6 万）。

必须回答：
  1. 在不同「保留黄金」比例下，年分红多少、缺口多少、黄金能撑多少年？
  2. 实测分红波动极大（2026 全年只 0.70%），最差 3 年会缺多少？
  3. 如果此时遇上 2008 级危机（ETF −40%），方案还成立吗？
  4. 「卖黄金过日子」本身可持续吗？（黄金长期回报 vs 提款率）
"""
import sys, sqlite3
from pathlib import Path
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant")
CACHE = BASE / "data" / "cache" / "crisis"

TOTAL = 160.0          # 万
GOLD_NOW = 144.0       # 万
CASH = 16.0            # 万
SPEND = 6.0            # 万/年
CASH_POOL = 12.0       # 万（24 个月缓冲）

# ── 1) 实测分红率（逐年，来自 verify_div_timing / verify_holdings_div2）
DIV_515100 = {2021: 0.0020, 2022: 0.0121, 2023: 0.1901, 2024: 0.0069, 2025: 0.0339, 2026: 0.0017}
DIV_515450 = {2021: 0.0520, 2022: 0.0311, 2023: 0.1142, 2024: 0.0843, 2025: 0.0222, 2026: 0.0131}
W100, W450 = 40 / 75, 35 / 75      # 红利内部的配比

print("=" * 104)
print("【第一步】实测逐年分红率（75 万红利 ETF 的组合口径，40:35）")
print("=" * 104)
print(f"  {'年份':<8s}{'515100':>9s}{'515450':>9s}{'组合加权':>10s}")
blend = {}
for y in sorted(DIV_515100):
    v = DIV_515100[y] * W100 + DIV_515450[y] * W450
    blend[y] = v
    print(f"  {y:<8d}{DIV_515100[y]:>8.2%}{DIV_515450[y]:>9.2%}{v:>10.2%}")
vals = np.array(list(blend.values()))
print(f"\n  6 年平均：{vals.mean():.2%}   中位：{np.median(vals):.2%}")
print(f"  最差年：{vals.min():.2%}（{list(blend)[int(vals.argmin())]}）   最好年：{vals.max():.2%}")

# 滚动 3 年
yrs = sorted(blend)
roll3 = []
for i in range(len(yrs) - 2):
    s = sum(blend[yrs[i + k]] for k in range(3))
    roll3.append((f"{yrs[i]}-{yrs[i+2]}", s, s / 3))
print(f"\n  滚动 3 年：")
for lab, s, a in roll3:
    print(f"    {lab}: 累计 {s:>7.2%}  年均 {a:>6.2%}")
worst3 = min(r[2] for r in roll3)
print(f"  最差 3 年年均：{worst3:.2%}")

# ── 2) 不同「保留黄金」比例下的推演
print()
print("=" * 104)
print("【第二步】保留多少黄金？（假设红利:纳指 = 75:25 在转换部分内部）")
print("=" * 104)
print(f"  参数：年支出 {SPEND} 万；分红按 6 年均值 {vals.mean():.2%}；现金池 {CASH_POOL} 万单独存放")
print()
print(f"  {'保留黄金':>8s}{'转换金额':>9s}{'红利ETF':>9s}{'纳指QDII':>9s}"
      f"{'年分红':>9s}{'覆盖支出':>9s}{'年缺口':>9s}{'黄金可撑':>9s}")
rows = []
for keep_pct in (0.50, 0.45, 0.40, 0.35, 0.30, 0.275, 0.25, 0.20):
    keep = GOLD_NOW * keep_pct
    conv = GOLD_NOW - keep
    div = conv * 0.75
    qqq = conv * 0.25
    inc = div * vals.mean() + qqq * 0.005   # QQQ 股息约 0.5%
    gap = SPEND - inc
    runway = keep / gap if gap > 0 else float("inf")
    rows.append((keep_pct, keep, conv, div, qqq, inc, inc / SPEND, gap, runway))
    print(f"  {keep_pct:>7.0%}{keep:>9.0f}{conv:>9.0f}{div:>9.0f}{qqq:>9.0f}"
          f"{inc:>9.2f}{inc/SPEND:>8.0%}{gap:>9.2f}"
          f"{(f'{runway:.0f}年' if runway != float('inf') else '无限'):>9s}")

# ── 3) 压力测试：最差 3 年分红
print()
print("=" * 104)
print("【第三步】压力测试：连续 3 年分红只有 {:.2%}（2024-2026 实测），现金池够不够".format(worst3))
print("=" * 104)
print(f"  {'保留黄金':>8s}{'转换金额':>9s}{'红利ETF':>9s}{'年分红(差)':>11s}"
      f"{'3年缺口合计':>12s}{'现金池12万能否覆盖':>20s}")
for keep_pct, keep, conv, div, qqq, inc, cov, gap, runway in rows:
    inc_bad = div * worst3 + qqq * 0.005
    gap3 = (SPEND - inc_bad) * 3
    ok = "✅ 够" if gap3 <= CASH_POOL else f"❌ 缺 {gap3-CASH_POOL:.1f} 万"
    print(f"  {keep_pct:>7.0%}{conv:>9.0f}{div:>9.0f}{inc_bad:>10.2f}"
          f"{gap3:>12.2f}{ok:>20s}")

# ── 4) 「只卖黄金不换仓」可持续吗
print()
print("=" * 104)
print("【第四步】关键对照：如果什么都不换，只卖金条过日子，能撑多久？")
print("=" * 104)
GLD = pd.read_csv(CACHE / "us_GLD.csv", parse_dates=["date"]).set_index("date")["close"].astype(float)
yrs_span = (GLD.index[-1] - GLD.index[0]).days / 365.25
cagr = (GLD.iloc[-1] / GLD.iloc[0]) ** (1 / yrs_span) - 1
wr = SPEND / TOTAL
print(f"  黄金 GLD {GLD.index[0].date()} ~ {GLD.index[-1].date()}（{yrs_span:.1f} 年）")
print(f"  年化回报：{cagr:.2%}")
print(f"  你的提款率：{SPEND} 万 ÷ {TOTAL} 万 = {wr:.2%}")
print(f"  → {'✅ 提款率 < 回报率，理论上可永久持续' if wr < cagr else '❌ 提款率 > 回报率，会耗尽'}")
print(f"  若不考虑任何回报，纯现金消耗：{TOTAL} ÷ {SPEND} = {TOTAL/SPEND:.0f} 年")

# 模拟：从 2004 起每年提 3.75%
v = 1.0
n = 0
for y in range(int(yrs_span)):
    s = y / yrs_span
    v *= (1 + cagr)
    v -= wr
    n += 1
    if v <= 0:
        break
print(f"  模拟（年化 {cagr:.2%}，每年提 {wr:.2%}）：{n} 年后 {'耗尽' if v<=0 else f'剩 {v:.2f} 倍'}")

# ── 5) 危机压力：换仓后遇 ETF -40%
print()
print("=" * 104)
print("【第五步】危机压力：换仓后立刻遇到 2008 级下跌（红利 −40%），账面如何")
print("=" * 104)
print(f"  {'保留黄金':>8s}{'黄金价值(危机中+15%)':>20s}{'ETF价值(-40%)':>15s}{'合计':>8s}{'相对160万':>10s}")
for keep_pct, keep, conv, div, qqq, inc, cov, gap, runway in rows:
    g2 = keep * 1.15          # 危机中黄金通常上涨
    e2 = conv * 0.60
    tot = g2 + e2 + CASH
    print(f"  {keep_pct:>7.0%}{g2:>20.0f}{e2:>15.0f}{tot:>8.0f}{tot/TOTAL:>9.0%}")
print("\n  注：黄金「危机中 +15%」是保守假设（2008 雷曼后 GLD 曾 −29%，但 2009 全年 +24%）")
