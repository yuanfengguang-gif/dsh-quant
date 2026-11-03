# -*- coding: utf-8 -*-
"""verify_causal_rolling.py - 正确测法：从「市场在高位、我持金等待」开始

【上一版的错误】
从 2010-01-01 起算，但那天沪深300 已经距高点 -20%，所有回撤策略在第一天就全买了。
结果只测到一个日期，等于没测。

【正确测法】
用户的真实处境是：我现在持有全黄金，市场目前不便宜，我在等下一次机会。
所以回测的起点必须是「市场接近高位」的日子（dd >= -10%）。
对每一个这样的起点，向前推 5 年，看不同规则的结果。

【评价指标】
  · 终值倍数（相对一直持金）
  · 5 年内是否买进（不买 = 1.00，说明错过了）
  · 买入均价相对「这 5 年内红利最低点」的倍数 —— 越接近 1 越好
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

c = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
dy = pd.read_sql_query("SELECT date,dy_ttm FROM div_yield WHERE code='H30269' ORDER BY date", c)
b = pd.read_sql_query("SELECT date,value FROM macro WHERE key='cn10y' ORDER BY date", c)
c.close()
dy["date"] = pd.to_datetime(dy["date"]); b["date"] = pd.to_datetime(b["date"])
DY = dy.set_index("date")["dy_ttm"].astype(float)
B10 = b.set_index("date")["value"].astype(float)

CAL = pd.DataFrame({"hs": HS300, "div": PX50, "divtr": TR50, "gld": GLD})
CAL = CAL.dropna(subset=["hs", "gld", "div"])
CAL["dy"] = DY.reindex(CAL.index).ffill()
CAL["b10"] = B10.reindex(CAL.index).ffill()
CAL["dd"] = CAL["hs"] / CAL["hs"].rolling(756, min_periods=250).max() - 1
CAL["div_dd"] = CAL["div"] / CAL["div"].rolling(756, min_periods=250).max() - 1
CAL["spread"] = CAL["dy"] * 100 - CAL["b10"]
CAL = CAL.dropna(subset=["dd"])


def run(start_idx, H_years, rules):
    """从 start_idx 起，向前 H_years 年，执行规则。返回 (倍数相对持金, 投入比例, 买入价/期内最低)"""
    end_date = CAL.index[start_idx] + pd.Timedelta(days=int(H_years * 365.25))
    d = CAL[(CAL.index >= CAL.index[start_idx]) & (CAL.index <= end_date)]
    if len(d) < 250:
        return None
    gold, stock, inv = 1.0, 0.0, 0.0
    done = [False] * len(rules)
    buys = []
    for dt, row in d.iterrows():
        for k, (cond, frac) in enumerate(rules):
            if done[k]:
                continue
            if cond(row):
                amt = min(gold, frac)
                if amt > 1e-6:
                    gold -= amt
                    stock += amt * row["gld"] / row["div"]
                    inv += amt
                    buys.append((dt, row["div"]))
                done[k] = True
    final = gold * d["gld"].iloc[-1] + stock * d["divtr"].iloc[-1] / (d["divtr"].iloc[0] / d["div"].iloc[0])
    # 用全收益衡量股票端（分红的再投资），但买入价用价格指数
    final = gold * d["gld"].iloc[-1] + stock * (d["divtr"].iloc[-1] / d["divtr"].iloc[0] * d["div"].iloc[0])
    base = d["gld"].iloc[-1]
    pl = float(d["div"].min())
    ratios = [pxv / pl for _, pxv in buys]
    return final / base, inv, (np.mean(ratios) if ratios else np.nan), len(buys)


RULES = {
    "-20% 一次性": [((lambda r: r["dd"] <= -0.20), 1.0)],
    "-25% 一次性": [((lambda r: r["dd"] <= -0.25), 1.0)],
    "-30% 一次性": [((lambda r: r["dd"] <= -0.30), 1.0)],
    "三档 -15/-25/-35": [((lambda r: r["dd"] <= -0.15), 1/3),
                        ((lambda r: r["dd"] <= -0.25), 1/3),
                        ((lambda r: r["dd"] <= -0.35), 1/3)],
    "四档 -10/-20/-30/-40": [((lambda r: r["dd"] <= -0.10), 0.25),
                            ((lambda r: r["dd"] <= -0.20), 0.25),
                            ((lambda r: r["dd"] <= -0.30), 0.25),
                            ((lambda r: r["dd"] <= -0.40), 0.25)],
    "五档 -10/15/20/30/40": [((lambda r: r["dd"] <= -0.10), 0.20),
                            ((lambda r: r["dd"] <= -0.15), 0.20),
                            ((lambda r: r["dd"] <= -0.20), 0.20),
                            ((lambda r: r["dd"] <= -0.30), 0.20),
                            ((lambda r: r["dd"] <= -0.40), 0.20)],
    "利差>=2pp 一次性": [((lambda r: pd.notna(r["spread"]) and r["spread"] >= 2.0), 1.0)],
    "红利回撤-20% 一次性": [((lambda r: r["div_dd"] <= -0.20), 1.0)],
    "红利回撤三档 -10/-15/-25": [((lambda r: r["div_dd"] <= -0.10), 1/3),
                                ((lambda r: r["div_dd"] <= -0.15), 1/3),
                                ((lambda r: r["div_dd"] <= -0.25), 1/3)],
}

for H in (3, 5):
    print("=" * 106)
    print(f"【从「市场接近高位」出发，等 {H} 年：哪条规则最好】")
    print("=" * 106)
    starts = CAL.index[(CAL["dd"] >= -0.10)]
    starts = [i for i in range(len(CAL)) if CAL["dd"].iloc[i] >= -0.10
              and CAL.index[i] + pd.Timedelta(days=int(H * 365.25)) <= CAL.index[-1]]
    print(f"  可用起点：{len(starts)} 个「市场距高点 ≥ -10%」的日子（{CAL.index[starts[0]].date()} ~ {CAL.index[starts[-1]].date()}）")
    print(f"\n  {'规则':<26s}{'中位倍数':>10s}{'最差':>8s}{'最好':>8s}{'买进比例':>10s}{'买价/期内最低':>14s}")
    for nm, rules in RULES.items():
        out = []
        for i in starts:
            r = run(i, H, rules)
            if r:
                out.append(r)
        if not out:
            continue
        A = np.array([[o[0], o[1], o[2]] for o in out], dtype=float)
        print(f"  {nm:<26s}{np.nanmedian(A[:,0]):>10.2f}{np.nanmin(A[:,0]):>8.2f}"
              f"{np.nanmax(A[:,0]):>8.2f}{np.nanmean(A[:,1]):>9.0%}"
              f"{np.nanmedian(A[:,2]):>13.2f}")
    print()
