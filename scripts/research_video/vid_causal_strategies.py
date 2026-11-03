# -*- coding: utf-8 -*-
"""verify_causal_strategies.py - 只测「实时可算」的策略，彻底去掉未来函数

【为什么重做】
前几轮的 S5 信号用 seg.idxmin() 找底，那是事后视角。
因果版（滚动最低点）实测：21 年触发 57 次、2008 早 203 天买在底部 2.32 倍。

【本轮原则】
任何策略里出现的量，必须是在当天收盘后就能算出来的：
  · 距「滚动 36 个月最高点」的回撤  dd      ← 可算
  · 距「滚动 36 个月最低点」的涨幅  bounce  ← 可算
  · 红利低波自己的回撤                div_dd  ← 可算
  · 股债利差（股息率 − 10Y国债）      spread  ← 可算
  · 距上次创新低过了多少天            days_since_low ← 可算

【要回答的问题】
  在不依赖"知道底"的前提下，哪条规则能把钱从黄金搬到红利，且不亏？
"""
import sys, sqlite3
from pathlib import Path
import numpy as np
import pandas as pd

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


def emidx(fn):
    d = pd.read_csv(CACHE / fn)
    dc = next(c for c in d.columns if "日期" in c)
    d[dc] = pd.to_datetime(d[dc])
    return d.sort_values(dc).set_index(dc)["最新价"].astype(float)


HS300 = emidx("em_global_hs300.csv")
PX50 = li("H30269")
TR50 = li("H20269")
GLD = pd.read_csv(CACHE / "us_GLD.csv", parse_dates=["date"]).set_index("date")["close"].astype(float)

# 股债利差（因果可算）
c = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
dy = pd.read_sql_query("SELECT date,dy_ttm FROM div_yield WHERE code='H30269' ORDER BY date", c)
b = pd.read_sql_query("SELECT date,value FROM macro WHERE key='cn10y' ORDER BY date", c)
c.close()
dy["date"] = pd.to_datetime(dy["date"]); b["date"] = pd.to_datetime(b["date"])
DY = dy.set_index("date")["dy_ttm"].astype(float)
B10 = b.set_index("date")["value"].astype(float)

CAL = pd.DataFrame({"hs": HS300, "div": PX50, "gld": GLD}).dropna(subset=["hs", "gld"])
CAL["div"] = CAL["div"].ffill()
CAL["dy"] = DY.reindex(CAL.index).ffill()
CAL["b10"] = B10.reindex(CAL.index).ffill()
CAL["dd"] = CAL["hs"] / CAL["hs"].rolling(756, min_periods=250).max() - 1
CAL["div_dd"] = CAL["div"] / CAL["div"].rolling(756, min_periods=250).max() - 1
CAL["spread"] = CAL["dy"] * 100 - CAL["b10"]
# 距上次创新低的天数
low = CAL["hs"].rolling(756, min_periods=250).min()
newlow = CAL["hs"] <= low * 1.0001
grp = newlow.cumsum()
CAL["days_since_low"] = CAL.groupby(grp).cumcount()
CAL = CAL.dropna(subset=["dd"])

print("=" * 104)
print("【可用的因果指标】")
print("=" * 104)
print(f"  日历范围 {CAL.index.min().date()} ~ {CAL.index.max().date()}，{len(CAL)} 个交易日")
print(f"  {'指标':<22s}{'最新值':>10s}{'说明':<40s}")
print(f"  {'沪深300 距36月高点':<22s}{CAL['dd'].iloc[-1]:>9.1%}   实时可算")
print(f"  {'红利低波 距36月高点':<22s}{CAL['div_dd'].iloc[-1]:>9.1%}   实时可算")
print(f"  {'股债利差':<22s}{CAL['spread'].iloc[-1]:>9.2f}pp  实时可算")
print(f"  {'距上次创新低天数':<22s}{CAL['days_since_low'].iloc[-1]:>9d}   实时可算")


def run_strategy(name, rules, start="2010-01-01"):
    """rules: [(armed_condition_series, action), ...]
    action: ('buy', fraction) —— 在满足条件的第一天买入 fraction（相对总资金）
    只买一次（每档独立），最多累计 1.0
    返回：最终倍数（相对全持金）、买入均价相对期间最低点的倍数、实际投入比例、买入次数
    """
    d = CAL[CAL.index >= start]
    gold, stock, invested = 1.0, 0.0, 0.0
    done = [False] * len(rules)
    buys = []
    for dt, row in d.iterrows():
        for k, (cond, frac) in enumerate(rules):
            if done[k]:
                continue
            if cond(row):
                amt = min(gold, frac)
                if amt > 0.0001:
                    gold -= amt
                    stock += amt * row["gld"] / row["div"]
                    invested += amt
                    buys.append((dt, amt, row["div"]))
                done[k] = True
    end = d.index[-1]
    final = gold * d["gld"].iloc[-1] + stock * d["div"].iloc[-1]
    base = 1.0 * d["gld"].iloc[-1]
    # 买入价相对「全期最低」的倍数
    period_low = float(d["div"].min())
    ratios = [px / period_low for _, _, px in buys] if buys else []
    return {
        "name": name, "mult": final / base, "invested": invested,
        "n": len(buys), "avg_ratio": np.mean(ratios) if ratios else np.nan,
        "buys": buys,
    }


RULES = {
    "A 回撤-20% 一次性": [((lambda r: r["dd"] <= -0.20), 1.0)],
    "B 回撤-30% 一次性": [((lambda r: r["dd"] <= -0.30), 1.0)],
    "C 三档回撤 -20/-30/-40": [((lambda r: r["dd"] <= -0.20), 1/3),
                              ((lambda r: r["dd"] <= -0.30), 1/3),
                              ((lambda r: r["dd"] <= -0.40), 1/3)],
    "D 四档回撤 -15/-25/-35/-45": [((lambda r: r["dd"] <= -0.15), 0.25),
                                  ((lambda r: r["dd"] <= -0.25), 0.25),
                                  ((lambda r: r["dd"] <= -0.35), 0.25),
                                  ((lambda r: r["dd"] <= -0.45), 0.25)],
    "E 回撤-20% 且 停跌60天": [((lambda r: r["dd"] <= -0.20 and r["days_since_low"] >= 60), 1.0)],
    "F 股债利差>=2pp": [((lambda r: r["spread"] >= 2.0), 1.0)],
    "G 股债利差三档 2/2.5/3pp": [((lambda r: pd.notna(r["spread"]) and r["spread"] >= 2.0), 1/3),
                                ((lambda r: pd.notna(r["spread"]) and r["spread"] >= 2.5), 1/3),
                                ((lambda r: pd.notna(r["spread"]) and r["spread"] >= 3.0), 1/3)],
    "H 回撤-25% 且 利差>=2pp": [((lambda r: r["dd"] <= -0.25 and pd.notna(r["spread"]) and r["spread"] >= 2.0), 1.0)],
    "I 组合：-20%买1/3 + 利差>=2.5pp买1/3 + -35%买1/3": [
        ((lambda r: r["dd"] <= -0.20), 1/3),
        ((lambda r: pd.notna(r["spread"]) and r["spread"] >= 2.5), 1/3),
        ((lambda r: r["dd"] <= -0.35), 1/3)],
}

print()
print("=" * 104)
print("【2010 起连续回测：从现在起 16 年，哪条规则最好】（基准 = 一直持金 = 1.00）")
print("=" * 104)
print(f"  {'策略':<38s}{'终值倍数':>10s}{'投入比例':>10s}{'买入次数':>9s}{'买价/期间最低':>13s}")
res = []
for nm, rules in RULES.items():
    r = run_strategy(nm, rules)
    res.append(r)
    print(f"  {r['name']:<38s}{r['mult']:>10.2f}{r['invested']:>9.0%}"
          f"{r['n']:>9d}{r['avg_ratio']:>12.2f}")

print()
print("=" * 104)
print("【买入明细：各策略实际在哪天买、买在什么价位】")
print("=" * 104)
for r in res:
    if not r["buys"]:
        print(f"\n  {r['name']}：从未触发")
        continue
    print(f"\n  {r['name']}（终值 {r['mult']:.2f} 倍）")
    print(f"     {'买入日':>12s}{'投入比例':>9s}{'红利点位':>11s}{'距期间最低':>11s}")
    pl = float(CAL[CAL.index >= "2010-01-01"]["div"].min())
    for dt, amt, pxv in r["buys"]:
        print(f"     {str(dt.date()):>12s}{amt:>8.0%}{pxv:>11.0f}{pxv/pl:>11.2f}")
