# -*- coding: utf-8 -*-
"""verify_two_step_causal.py - 两步法的【可实时执行版】

上一版证明：用「事后局部高点 + 事后低点」配对，两步法比同步法多拿 16% 份额。
但那有未来函数。本脚本只测【当天收盘能算出来】的规则：

卖出黄金的信号（候选，全部因果可算）：
  S1  GLD 从过去 250 日最高点回落 ≥ 8%（确认见顶后卖）
  S2  GLD RSI(14) ≥ 75（超买）
  S3  GLD 距 200 日均线 ≥ +20%（偏离过大）

买入红利的信号（候选，已在前几轮验证）：
  D1  红利低波距 36 月高点 ≤ −20%
  D2  沪深300 ≤ −25% 且 红利 ≤ −20%

执行逻辑：
  · 先等卖出信号 → 卖金持币
  · 再等买入信号 → 用现金买红利
  · 若卖出信号没来、买入信号先来 → 退回"同步法"（在买入信号当天同时卖金买红利）
  · 若卖出信号来了但买入信号一直不来 → 一直持币（计算这个机会成本）

对照：同步法（买卖同一个信号）
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import sqlite3

if hasattr(sys.stdout, "reresetreconfigure" if False else "reconfigure"):
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


def em(fn):
    d = pd.read_csv(CACHE / fn)
    dc = next(c for c in d.columns if "日期" in str(c))
    d[dc] = pd.to_datetime(d[dc])
    return d.sort_values(dc).set_index(dc)["最新价"].astype(float)


DIV = li("H30269")
TR = li("H20269")
GLD = usc("us_GLD.csv")
HS = em("em_global_hs300.csv")

div_rm = DIV.rolling(756, min_periods=250).max()
div_dd = DIV / div_rm - 1
hs_rm = HS.rolling(756, min_periods=250).max()
hs_dd = HS / hs_rm - 1


def rsi_w(s, n=14):
    d = s.diff()
    au = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    ad = (-d).clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return 100 - 100 / (1 + au / ad.replace(0, np.nan))


g_rsi = rsi_w(GLD, 14)
g_max250 = GLD.rolling(250, min_periods=120).max()
g_fall = GLD / g_max250 - 1
g_ma200 = GLD.rolling(200, min_periods=100).mean()
g_dev = GLD / g_ma200 - 1

CR = [("2008 次贷", "2007-06-01", "2010-06-30"), ("2011 欧债", "2011-04-01", "2013-06-30"),
      ("2015 A股股灾", "2015-04-01", "2017-06-30"), ("2018 Q4", "2018-09-01", "2019-12-31"),
      ("2020 COVID", "2020-01-01", "2021-06-30"), ("2022 加息", "2022-01-01", "2025-06-30")]


def first(cond_series, t0, t1):
    w = cond_series[(cond_series.index >= t0) & (cond_series.index <= t1)]
    h = w[w.fillna(False)]
    return h.index[0] if len(h) else None


SELL = {
    "S1 金价回落≥8%": (g_fall <= -0.08) & (g_fall.shift(1) > -0.08),
    "S2 金价RSI≥75": (g_rsi >= 75) & (g_rsi.shift(1) < 75),
    "S3 金价距200日线≥+20%": (g_dev >= 0.20) & (g_dev.shift(1) < 0.20),
}
BUY = {
    "D1 红利≤-20%": (div_dd <= -0.20) & (div_dd.shift(1) > -0.20),
    "D2 HS300≤-25%且红利≤-20%": ((hs_dd <= -0.25) & (div_dd <= -0.20)) &
                                  (~(((hs_dd.shift(1) <= -0.25) & (div_dd.shift(1) <= -0.20))).fillna(False)),
}

print("=" * 122)
print("【可实时执行版】卖金信号 vs 买红利信号 —— 谁先谁后？")
print("=" * 122)
for sname, scond in SELL.items():
    for bname, bcond in BUY.items():
        print(f"\n  ── {sname}  ×  {bname} ──")
        print(f"     {'危机':<14s}{'卖金日':>12s}{'卖价':>8s}{'买红利日':>12s}{'买价':>9s}"
              f"{'先卖后买?':>10s}{'两步法份额':>11s}{'同步法份额':>11s}{'倍数':>7s}")
        ratios = []
        for nm, t0, t1 in CR:
            T0, T1 = pd.Timestamp(t0), pd.Timestamp(t1)
            sd = first(scond, T0 - pd.Timedelta(days=365), T1)
            bd = first(bcond, T0, T1)
            if bd is None:
                print(f"     {nm:<14s}{'—':>12s}{'':>8s}{'无买入信号':>12s}")
                continue
            if sd is not None and sd < bd:
                sell_v = float(GLD.asof(sd))
                buy_v = float(DIV.asof(bd))
                a = sell_v / buy_v                      # 两步法份额
                b = float(GLD.asof(bd)) / buy_v          # 同步法份额
                tag = "✅ 是"
                ratios.append(a / b)
            else:
                sd_disp = sd if sd is not None else None
                sell_v = float(GLD.asof(bd))             # 退回同步法
                buy_v = float(DIV.asof(bd))
                a = sell_v / buy_v
                b = a
                tag = "→同步"
                sd = None
            print(f"     {nm:<14s}{(str(sd.date()) if sd is not None else '晚于买入'):>12s}"
                  f"{(f'{sell_v:.1f}' if sd is not None else '—'):>8s}{str(bd.date()):>12s}"
                  f"{buy_v:>9.0f}{tag:>10s}{a:>11.1f}{b:>11.1f}{(a/b if b else 1):>7.2f}")
        if ratios:
            print(f"     → 两步法生效 {len(ratios)} 次，A/B 中位 {np.median(ratios):.3f} 倍，最差 {min(ratios):.3f}")

print()
print("=" * 122)
print("【机会成本】卖了金但买入信号一直不来 —— 会踏空多少？")
print("=" * 122)
print("  做法：卖金后持币，若 24 个月内买入信号不来，计算这期间金价涨了多少（踏空）")
for sname, scond in SELL.items():
    print(f"\n  ── {sname} ──")
    print(f"     {'危机':<14s}{'卖金日':>12s}{'卖价':>8s}{'24月内买入?':>12s}"
          f"{'24月后金价':>11s}{'踏空/成本':>10s}")
    for nm, t0, t1 in CR:
        T0, T1 = pd.Timestamp(t0), pd.Timestamp(t1)
        sd = first(scond, T0 - pd.Timedelta(days=365), T1)
        if sd is None:
            print(f"     {nm:<14s}{'无卖金信号':>12s}")
            continue
        bd = first(BUY["D1 红利≤-20%"], sd, sd + pd.Timedelta(days=730))
        sell_v = float(GLD.asof(sd))
        e = sd + pd.Timedelta(days=730)
        g_e = float(GLD.asof(e)) if e <= GLD.index[-1] else float(GLD.iloc[-1])
        cost = g_e / sell_v - 1
        print(f"     {nm:<14s}{str(sd.date()):>12s}{sell_v:>8.1f}"
              f"{(('是 ' + str(bd.date())) if bd is not None else '否'):>12s}"
              f"{g_e:>11.1f}{cost:>9.1%}")

print()
print("=" * 122)
print("【结论要点】")
print("=" * 122)
print("""  · 理想的「事后配对」两步法：比同步法多拿 16% 份额（1.16 倍），6/6 场都跑赢持金
  · 但可实时执行的版本取决于「卖金信号」准不准 —— 见上面的 A/B 倍数
  · 关键风险不是"卖早了金价还涨"（历史上等红利见底期间金价从未超过卖出价），
    而是"卖出信号太频繁"或"买入信号不来，长期持币"
""")
