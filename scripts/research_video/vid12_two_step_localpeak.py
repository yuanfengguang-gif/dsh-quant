# -*- coding: utf-8 -*-
"""verify_two_step2.py - 修正版：用「红利低点之前的黄金局部高点」

上一版错误：
  我把「金价高点」定义成搜索窗口（危机后+24个月）内的最高价，结果取到的是
  几年后的历史大顶（如 2008 那场取到 2011-08），而红利低点在 2008-11。
  于是得出「金价高点在红利低点之后」—— 这会误导用户放弃一个可能正确的策略。

正确做法（用户真正问的）：
  在【红利低点之前】找金价的局部最高点。如果那时金价明显高于红利低点时的金价，
  就说明「先卖金、持币、后买红利」这条路在历史上是有空间的。

对比三种做法（都以「144 万黄金 → 最终换成红利 ETF」为场景）：
  A 两步法：金价局部高点卖金 → 持币 → 红利低点买入
  B 同步法：红利低点当天同时卖金买红利
  C 一直持金不动
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


DIV = li("H30269")
TR = li("H20269")
GLD = usc("us_GLD.csv")

CR = [("2008 次贷", "2007-06-01", "2010-06-30"), ("2011 欧债", "2011-04-01", "2013-06-30"),
      ("2015 A股股灾", "2015-04-01", "2017-06-30"), ("2018 Q4", "2018-09-01", "2019-12-31"),
      ("2020 COVID", "2020-01-01", "2021-06-30"), ("2022 加息", "2022-01-01", "2025-06-30")]

print("=" * 120)
print("【核心】红利低点【之前】的黄金局部高点 vs 红利低点时的金价")
print("=" * 120)
print("  金价局部高点 = 危机开始前 12 个月 ~ 红利低点 之间 GLD 的最高价")
print()
print(f"  {'危机':<14s}{'金价局部高点':>14s}{'高点金价':>10s}{'红利低点':>12s}{'低点金价':>10s}"
      f"{'金价落差':>10s}{'间隔天数':>9s}{'判定':>14s}")
rows = []
for nm, t0, t1 in CR:
    T0, T1 = pd.Timestamp(t0), pd.Timestamp(t1)
    seg_d = DIV[(DIV.index >= T0) & (DIV.index <= T1)].dropna()
    if len(seg_d) < 30:
        continue
    d_low = seg_d.idxmin()
    d_low_v = float(seg_d.min())
    # ★ 关键修正：只找【红利低点之前】的金价高点
    gwin = GLD[(GLD.index >= T0 - pd.Timedelta(days=365)) & (GLD.index <= d_low)].dropna()
    if len(gwin) < 50:
        continue
    g_pk = gwin.idxmax()
    g_pk_v = float(gwin.max())
    g_at_low = float(GLD.asof(d_low))
    drop = g_at_low / g_pk_v - 1          # 从局部高点到红利低点，金价跌了多少
    gap = (d_low - g_pk).days
    ok = drop < -0.03                      # 金价确实回落了 3% 以上
    verdict = "✅ 可两步" if ok else "⚠️ 金价没跌"
    rows.append({"crisis": nm, "g_pk": g_pk, "g_pk_v": g_pk_v, "d_low": d_low,
                 "d_low_v": d_low_v, "g_at_low": g_at_low, "drop": drop, "gap": gap})
    print(f"  {nm:<14s}{str(g_pk.date()):>14s}{g_pk_v:>10.1f}{str(d_low.date()):>12s}"
          f"{g_at_low:>10.1f}{drop:>9.1%}{gap:>9d}{verdict:>14s}")

if rows:
    a = np.array([[r["drop"], r["gap"]] for r in rows], dtype=float)
    print(f"\n  金价从局部高点到红利低点的回落：中位 {np.median(a[:,0]):.1%}，平均 {a[:,0].mean():.1%}")
    print(f"  间隔天数：中位 {np.median(a[:,1]):.0f} 天（约 {np.median(a[:,1])/30:.1f} 个月）")
    print(f"  → 金价明显回落（<-3%）的次数：{sum(1 for r in rows if r['drop']<-0.03)}/{len(rows)}")

print()
print("=" * 120)
print("【方案对比】144 万黄金，换成红利 ETF，持有 3 年后的相对价值（以黄金单位计，越大越好）")
print("=" * 120)
print("  A 两步法 = 金价局部高点卖金 → 持币 → 红利低点买入")
print("  B 同步法 = 红利低点那天同时卖金买红利")
print("  C 不动   = 一直持金")
print()
print(f"  {'危机':<14s}{'A 两步法':>11s}{'B 同步法':>11s}{'C 持金':>10s}"
      f"{'A/B 倍数':>10s}{'A优于C':>9s}{'B优于C':>9s}")
gains = []
for r in rows:
    A = r["g_pk_v"] / r["d_low_v"] * float(TR.asof(min(r["d_low"] + pd.Timedelta(days=1095), TR.index[-1])))
    B = r["g_at_low"] / r["d_low_v"] * float(TR.asof(min(r["d_low"] + pd.Timedelta(days=1095), TR.index[-1])))
    C = float(GLD.asof(min(r["d_low"] + pd.Timedelta(days=1095), GLD.index[-1])))
    gains.append({"crisis": r["crisis"], "A": A, "B": B, "C": C, "ratio": A / B})
    print(f"  {r['crisis']:<14s}{A:>11.1f}{B:>11.1f}{C:>10.1f}"
          f"{A/B:>10.2f}{('✅' if A>C else '❌'):>9s}{('✅' if B>C else '❌'):>9s}")
if gains:
    rat = np.array([g["ratio"] for g in gains])
    print(f"\n  A/B 中位：{np.median(rat):.2f} 倍   → 两步法比同步法多拿 {np.median(rat)-1:+.0%} 的份额")
    print(f"  A/B 最差：{rat.min():.2f} 倍")
    print(f"  A 优于 C（两步法跑赢持金）：{sum(1 for g in gains if g['A']>g['C'])}/{len(gains)}")
    print(f"  B 优于 C（同步法跑赢持金）：{sum(1 for g in gains if g['B']>g['C'])}/{len(gains)}")

print()
print("=" * 120)
print("【风险】如果卖金之后金价不跌反涨怎么办？（持币等待的机会成本）")
print("=" * 120)
print("  检查：卖出后到红利低点之间，金价最高涨到多少（相对卖出价）")
print(f"  {'危机':<14s}{'卖出日':>12s}{'卖出价':>9s}{'等待期间金价最高':>14s}{'卖出后最大踏空':>14s}{'等待天数':>9s}")
for r in rows:
    w = GLD[(GLD.index > r["g_pk"]) & (GLD.index <= r["d_low"])]
    if len(w) == 0:
        continue
    hi = float(w.max())
    print(f"  {r['crisis']:<14s}{str(r['g_pk'].date()):>12s}{r['g_pk_v']:>9.1f}"
          f"{hi:>14.1f}{hi/r['g_pk_v']-1:>13.1%}{r['gap']:>9d}")

print()
print("=" * 120)
print("【重要提醒】")
print("=" * 120)
print("""  上面用「事后的局部高点」和「事后的低点」配对，这本身就是未来函数。
  真实操作要回答两个更难的问题：
    1. 你能在事前判断出「这个金价高点就是高点」吗？—— 昨天已验证：不能（金银比峰值滞后、缺钱期不可交易）
    2. 你能在事前判断出「红利已经到底」吗？—— 也不能（回撤阈值会买在半山腰）
  所以「A 两步法」的数字，是【完美执行】的上限，不是可实现收益。
  真正的问题是：有没有一个【可实时计算】的规则，能近似这个上限？
""")
