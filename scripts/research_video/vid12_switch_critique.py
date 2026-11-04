# -*- coding: utf-8 -*-
"""verify_switch_timing_critique.py - 严查换仓信号：发出后还要跌多少？

用户看图后质疑「换仓信号对吗」。图上的直观问题是：
  竖线（换仓）都在半山腰，之后曲线还继续暴跌。

必须回答三件事：
  Q1 按 HS300 回撤 -25% 发出信号后，【我们要买的红利低波】还要跌多少？
      （注意：模型用 HS300 判信号，但买的是红利 ETF —— 两者跌幅差别很大）
  Q2 如果改用【红利自己的回撤】发信号，会不会更好？
  Q3 现有信号 vs 替代信号：谁买入后继续跌得更少？
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant")
CACHE = BASE / "data" / "cache" / "crisis"
import sqlite3
DB = BASE / "data" / "cache" / "dividend_research.db"


def li(code):
    c = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    d = pd.read_sql_query("SELECT date,close FROM idx_daily WHERE code=? ORDER BY date", c, params=(code,))
    c.close()
    d["date"] = pd.to_datetime(d["date"])
    return d.set_index("date")["close"].astype(float)


def em(fn):
    d = pd.read_csv(CACHE / fn)
    dc = next(c for c in d.columns if "日期" in str(c))
    d[dc] = pd.to_datetime(d[dc])
    return d.sort_values(dc).set_index(dc)["最新价"].astype(float)


HS = em("em_global_hs300.csv")
DIV = li("H30269")      # 红利低波价格（买入标的）
TR = li("H20269")       # 红利低波全收益

CR = [("2008 次贷", "2007-06-01", "2010-06-30"), ("2011 欧债", "2011-04-01", "2013-06-30"),
      ("2015 A股股灾", "2015-04-01", "2017-06-30"), ("2018 Q4", "2018-09-01", "2019-12-31"),
      ("2020 COVID", "2020-01-01", "2021-06-30"), ("2022 加息", "2022-01-01", "2025-06-30")]


def first_cross(series, ref, level, t0, t1):
    """series 相对 ref（同为价格序列，按日期对齐）首次跌破 -(level) 的日期"""
    j = pd.DataFrame({"s": series, "r": ref}).dropna()
    dd = j["s"] / j["r"] - 1
    w = dd[(dd.index >= t0) & (dd.index <= t1)]
    hit = w[w <= -level]
    return hit.index[0] if len(hit) else None


print("=" * 110)
print("【Q1】按 HS300 回撤 -25% 发信号后，【红利低波】自己还要跌多少？")
print("=" * 110)
print(f"  {'危机':<14s}{'信号日':>12s}{'HS300点位':>10s}{'红利点位':>10s}"
      f"{'红利之后最低':>12s}{'红利还要跌':>11s}{'HS300还要跌':>12s}")
rows = []
hs_rm = HS.rolling(756, min_periods=250).max()
for nm, t0, t1 in CR:
    d = first_cross(HS, hs_rm, 0.25, pd.Timestamp(t0), pd.Timestamp(t1))
    if d is None:
        print(f"  {nm:<14s}{'未触发':>12s}")
        continue
    h_at = float(HS.asof(d))
    v_at = float(DIV.asof(d))
    seg = DIV[(DIV.index >= pd.Timestamp(t0)) & (DIV.index <= pd.Timestamp(t1))]
    after = seg[seg.index >= d]
    v_low = float(after.min())
    div_more = v_low / v_at - 1
    hs_seg = HS[(HS.index >= pd.Timestamp(t0)) & (HS.index <= pd.Timestamp(t1))]
    hs_low = float(hs_seg[hs_seg.index >= d].min())
    hs_more = hs_low / h_at - 1
    rows.append((nm, d, div_more, hs_more))
    print(f"  {nm:<14s}{str(d.date()):>12s}{h_at:>10.0f}{v_at:>10.0f}"
          f"{v_low:>12.0f}{div_more:>10.1%}{hs_more:>11.1%}")

if rows:
    a = np.array([[r[2], r[3]] for r in rows])
    print(f"\n  中位数：红利之后再跌 {np.median(a[:,0]):.1%}，HS300 再跌 {np.median(a[:,1]):.1%}")
    print(f"  最差：  红利 {a[:,0].min():.1%}，HS300 {a[:,1].min():.1%}")
    print(f"\n  → 用 HS300 判信号但买红利，红利实际只再跌 {np.median(a[:,0]):.0%}（HS300 是 {np.median(a[:,1]):.0%}）")
    print(f"    说明「红利抗跌」确实缓冲了一部分，但仍有 {abs(np.median(a[:,0])):.0%} 的浮亏")

print()
print("=" * 110)
print("【Q2】改用「红利自己的回撤」发信号，会不会更好？")
print("=" * 110)
print(f"  {'危机':<14s}{'HS300-25%':>12s}{'红利-15%':>12s}{'红利-20%':>12s}{'红利-25%':>12s}")
div_rm = DIV.rolling(756, min_periods=250).max()
table = []
for nm, t0, t1 in CR:
    T0, T1 = pd.Timestamp(t0), pd.Timestamp(t1)
    dA = first_cross(HS, hs_rm, 0.25, T0, T1)
    dB = first_cross(DIV, div_rm, 0.15, T0, T1)
    dC = first_cross(DIV, div_rm, 0.20, T0, T1)
    dD = first_cross(DIV, div_rm, 0.25, T0, T1)
    f = lambda x: str(x.date()) if x is not None else "未触发"
    table.append((nm, dA, dB, dC, dD))
    print(f"  {nm:<14s}{f(dA):>12s}{f(dB):>12s}{f(dC):>12s}{f(dD):>12s}")

print()
print("=" * 110)
print("【Q3】各信号发出后，红利还要跌多少（越接近0越好）")
print("=" * 110)
print(f"  {'信号':<26s}{'触发次数':>9s}{'之后再跌 中位':>14s}{'最差':>9s}{'平均买入价/区间低点':>20s}")


def eval_signal(kind, level):
    res = []
    for nm, t0, t1 in CR:
        T0, T1 = pd.Timestamp(t0), pd.Timestamp(t1)
        if kind == "hs":
            d = first_cross(HS, hs_rm, level, T0, T1)
        else:
            d = first_cross(DIV, div_rm, level, T0, T1)
        if d is None:
            continue
        v_at = float(DIV.asof(d))
        seg = DIV[(DIV.index >= T0) & (DIV.index <= T1)]
        v_low = float(seg[seg.index >= d].min())
        res.append((v_low / v_at - 1, v_at / float(seg.min())))
    if not res:
        return None
    a = np.array(res)
    return len(res), np.median(a[:, 0]), a[:, 0].min(), np.mean(a[:, 1])


for lab, kind, lv in (("HS300 回撤-25%（现行）", "hs", 0.25),
                      ("HS300 回撤-35%", "hs", 0.35),
                      ("红利自身回撤-10%", "div", 0.10),
                      ("红利自身回撤-15%", "div", 0.15),
                      ("红利自身回撤-20%", "div", 0.20),
                      ("红利自身回撤-25%", "div", 0.25)):
    r = eval_signal(kind, lv)
    if r:
        print(f"  {lab:<26s}{r[0]:>9d}{r[1]:>13.1%}{r[2]:>9.1%}{r[3]:>19.2f}")
    else:
        print(f"  {lab:<26s}{'从未触发':>9s}")

print()
print("=" * 110)
print("【Q4】关键：现行信号发出后 3 年，红利全收益表现如何（真实持有结果）")
print("=" * 110)
print(f"  {'危机':<14s}{'信号日':>12s}{'持1年':>9s}{'持2年':>9s}{'持3年':>9s}{'期间最深浮亏':>13s}")
for nm, t0, t1 in CR:
    T0, T1 = pd.Timestamp(t0), pd.Timestamp(t1)
    d = first_cross(HS, hs_rm, 0.25, T0, T1)
    if d is None:
        continue
    base = float(TR.asof(d))
    cells = []
    for H in (365, 730, 1095):
        e = d + pd.Timedelta(days=H)
        cells.append(f"{float(TR.asof(e))/base-1:>+8.1%}" if e <= TR.index[-1] else "     —")
    # 期间浮亏
    win = TR[(TR.index >= d) & (TR.index <= d + pd.Timedelta(days=1095))]
    mdd = float((win / win.cummax() - 1).min()) if len(win) > 30 else np.nan
    print(f"  {nm:<14s}{str(d.date()):>12s}{cells[0]}{cells[1]}{cells[2]}{mdd:>12.1%}")
