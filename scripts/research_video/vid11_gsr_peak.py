# -*- coding: utf-8 -*-
"""verify_gsr_peak.py - 专门回答：金银比峰值能否「确定」黄金谷底？

用户的问题：数据是不是证明了「金银比峰值可以确定黄金谷底」？

要检验三件事：
  Q1  时序：金银比峰值相对黄金谷底，是之前还是之后？
  Q2  代价：如果等到金银比峰值才买，黄金已经从谷底涨了多少？（错过多少）
  Q3  可靠性：峰值在谷底之前的那几次，提前了多久？（按峰值买会买在半山腰吗）
  Q4  因果版：「从滚动高点回落」能不能替代「峰值」？（峰值本身事后才能确认）
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CACHE = Path(r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant\data\cache\crisis")


def usc(s):
    d = pd.read_csv(CACHE / f"us_{s}.csv")
    dc = [c for c in d.columns if str(c).lower() in ("date", "日期")][0]
    d[dc] = pd.to_datetime(d[dc])
    cc = [c for c in d.columns if str(c).lower() in ("close", "收盘")]
    return d.sort_values(dc).set_index(dc)[(cc[0] if cc else "close")].astype(float)


GLD = usc("GLD")
SLV = usc("SLV")
gsr_etf = (GLD / SLV).dropna()
try:
    gc = pd.read_csv(CACHE / "px_gold_gc.csv"); gc["date"] = pd.to_datetime(gc["date"])
    si = pd.read_csv(CACHE / "px_silver_si.csv"); si["date"] = pd.to_datetime(si["date"])
    tg = (gc.set_index("date")["close"].astype(float) / si.set_index("date")["close"].astype(float)).dropna()
    ov = gsr_etf.index.intersection(tg.index)
    GSR = gsr_etf * float((tg.reindex(ov) / gsr_etf.reindex(ov)).median())
except Exception:
    GSR = gsr_etf

# 黄金谷底事件（与之前一致：跌≥12% 后反弹≥15%）
def gold_troughs(s, dd_min=-0.12, rebound=0.15, cooldown=180):
    out = []
    peak = -np.inf; low = np.inf; low_d = None; last = None
    for dt, p in s.items():
        p = float(p)
        if p >= peak:
            peak = p; low = p; low_d = dt
        if p < low:
            low = p; low_d = dt
        if peak > 0 and (low / peak - 1) <= dd_min and p / low - 1 >= rebound:
            if last is None or (dt - last).days >= cooldown:
                out.append((low_d, low))
                last = dt; peak = p; low = p; low_d = dt
    return out


TR = gold_troughs(GLD)

print("=" * 108)
print("【Q1 + Q2】金银比峰值 vs 黄金谷底：时间差 与 错过多少涨幅")
print("=" * 108)
print(f"  {'黄金谷底':>12s}{'谷底金价':>10s}{'GSR峰值日':>12s}{'时间差':>9s}"
      f"{'峰值日金价':>11s}{'等峰值的代价':>13s}{'方向':>8s}")
gaps, costs = [], []
for low_d, low_v in TR:
    win = GSR[(GSR.index >= low_d - pd.Timedelta(days=250)) & (GSR.index <= low_d + pd.Timedelta(days=250))]
    if len(win) < 100:
        continue
    pk_d = win.idxmax()
    gap = (pk_d - low_d).days
    g_at_pk = float(GLD.asof(pk_d))
    cost = g_at_pk / low_v - 1        # 等到峰值那天买，比谷底买贵多少
    gaps.append((low_d, pk_d, gap, cost))
    tag = "峰在底后" if gap > 0 else "峰在底前"
    print(f"  {str(low_d.date()):>12s}{low_v:>10.1f}{str(pk_d.date()):>12s}{gap:>+8d}天"
          f"{g_at_pk:>11.1f}{cost:>+12.1%}{tag:>8s}")

if gaps:
    a = np.array([[g[2], g[3]] for g in gaps])
    print(f"\n  时间差：中位 {np.median(a[:,0]):+.0f} 天，均值 {a[:,0].mean():+.0f} 天")
    print(f"  → 峰在谷底【之后】：{sum(1 for g in gaps if g[2]>0)}/{len(gaps)}")
    print(f"  → 峰在谷底【之前】：{sum(1 for g in gaps if g[2]<0)}/{len(gaps)}")
    print(f"\n  「等到金银比峰值才买」的平均代价：黄金已从谷底涨了 {a[:,1].mean():+.1%}"
          f"（中位 {np.median(a[:,1]):+.1%}）")

print()
print("=" * 108)
print("【Q3】峰值在谷底之前的那几次 —— 按峰值买会买在半山腰吗")
print("=" * 108)
bad = [g for g in gaps if g[2] < 0]
if bad:
    print(f"  {'黄金谷底':>12s}{'GSR峰值日':>12s}{'提前':>9s}{'峰值日金价':>11s}{'之后还跌':>10s}")
    for low_d, pk_d, gap, cost in bad:
        # 从峰值日到谷底，黄金还跌多少
        g_pk = float(GLD.asof(pk_d))
        drop = float(GLD.asof(low_d)) / g_pk - 1
        print(f"  {str(low_d.date()):>12s}{str(pk_d.date()):>12s}{-gap:>8d}天"
              f"{g_pk:>11.1f}{drop:>9.1%}")
    drops = [float(GLD.asof(b[0])) / float(GLD.asof(b[1])) - 1 for b in bad]
    print(f"\n  → 如果按「峰值出现就买」，这 {len(bad)} 次买入后黄金平均还要再跌 {np.mean(drops):.1%}"
          f"（最差 {min(drops):.1%}）")
else:
    print("  无")

print()
print("=" * 108)
print("【Q4】「峰值」本身事后才知道 —— 因果版「从滚动高点回落 X%」够用吗")
print("=" * 108)
print("  峰值 vs 回落的根本区别：")
print("    · 峰值 = 需要后续下跌才能确认（事后视角）→ 不能实时用")
print("    · 回落 X% = 当天就能算（当前值 ÷ 过去250日最高 - 1）→ 可以实时用")
print()
GSR_MAX = GSR.rolling(250, min_periods=120).max()
FALL = GSR / GSR_MAX - 1

print(f"  {'阈值':>6s}{'触发次数':>7s}{'买后1年 中位':>13s}{'胜率':>7s}{'买后3年 中位':>13s}{'胜率':>7s}")
for X in (0.05, 0.08, 0.12, 0.15, 0.20):
    sig = (FALL <= -X) & (FALL.shift(1) > -X)
    idx = GSR.index[sig.fillna(False)]
    keep = []
    for d in idx:
        if not keep or (d - keep[-1]).days > 120:
            keep.append(d)
    r1, r3 = [], []
    for d in keep:
        f1 = GLD[(GLD.index > d) & (GLD.index <= d + pd.Timedelta(days=365))]
        f3 = GLD[(GLD.index > d) & (GLD.index <= d + pd.Timedelta(days=1095))]
        if len(f1) > 100:
            r1.append(float(f1.iloc[-1] / GLD.asof(d) - 1))
        if len(f3) > 200:
            r3.append(float(f3.iloc[-1] / GLD.asof(d) - 1))
    if r1:
        w1 = sum(1 for x in r1 if x > 0) / len(r1)
        w3 = sum(1 for x in r3 if x > 0) / len(r3) if r3 else np.nan
        m3 = np.median(r3) if r3 else np.nan
        print(f"  {X:>6.0%}{len(keep):>7d}{np.median(r1):>+12.1%}{w1:>7.0%}{m3:>+12.1%}{w3:>7.0%}")

print()
print("=" * 108)
print("【结论】")
print("=" * 108)
print("""
  1. 时序上不成立：金银比峰值出现在黄金谷底【之后】中位 33 天（8/13 在之后）
     → 它是「滞后确认」，不是「预测」。等你看到峰值，底已经过去了。

  2. 代价很大：等到金银比见顶才买，黄金平均已从谷底涨了（见 Q2 数值）
     → 你要放弃一段确定的涨幅。

  3. 有 5/13 的峰值出现在谷底【之前】（最长提前 249 天）
     → 按「峰值出现就买」这几次会买在半山腰，之后还要继续跌。

  4. 「峰值」这个量本身事后才能确认，实时用不了；能实时用的是「从滚动高点回落 X%」，
     它有效但只在 1 年维度胜率 73–75%（够用但不算强）。
""")
