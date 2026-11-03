# -*- coding: utf-8 -*-
"""verify_causal_signal.py - 把 S5 信号改成「因果版」，不再偷看未来

【问题的严重性】
之前的回测：
    trough = seg.idxmin()          ← 用了整个窗口的最低点 = 未来信息
    bounce = price / trough - 1
真实交易时：站在某一天，你只知道「到目前为止的最低点」，不知道未来还会不会更低。

【因果版做法】
逐日推进，只用手上已知的信息：
    peak  = 到今天的最高价（创新高就更新，同时把 low 重置为新高）
    low   = 从上次 peak 以来的最低价（创新低就更新）
    dd    = price / peak - 1                       ← 距高点回撤，实时可知
    bounce= price / low - 1                        ← 距「至今最低点」的反弹，实时可知
触发条件：
    dd <= -10%（确认在下跌途中）  且  bounce >= 15%（从至今最低点反弹15%）
这两个量在任何行情软件里都能当下算出来。

【要回答的三个问题】
  1. 因果版与事后版差多少？
  2. 因果版在 2005-2026 全程会触发多少次？（会不会太频繁）
  3. 每次触发后买红利，效果如何？
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
PX50 = li("H30269")        # 红利低波价格（买入价）
TR50 = li("H20269")        # 红利低波全收益（持有收益）
GLD = pd.read_csv(CACHE / "us_GLD.csv", parse_dates=["date"]).set_index("date")["close"].astype(float)


def causal_signals(series, dd_gate=-0.10, bounce_need=0.15, cooldown=120):
    """完全因果的信号生成器：逐日推进，只用当时已知信息"""
    out = []
    peak = -np.inf
    low = np.inf
    last_trig = None
    for dt, p in series.items():
        p = float(p)
        if p >= peak:                 # 创新高 → 重置下跌段
            peak = p
            low = p
        if p < low:
            low = p
        dd = p / peak - 1
        bounce = p / low - 1
        if dd <= dd_gate and bounce >= bounce_need:
            if last_trig is None or (dt - last_trig).days >= cooldown:
                out.append({"date": dt, "price": p, "dd": dd,
                            "bounce": bounce, "low": low, "peak": peak})
                last_trig = dt
    return pd.DataFrame(out)


print("=" * 108)
print("【问题 1】因果版信号在 2005-2026 全程触发多少次")
print("=" * 108)
sigs = causal_signals(HS300)
print(f"  沪深300 数据 {HS300.index.min().date()} ~ {HS300.index.max().date()}")
print(f"  因果版触发次数：{len(sigs)} 次（冷却期 120 天）")
print(f"\n  {'#':<4s}{'触发日':>12s}{'当时点位':>11s}{'距高点':>9s}{'距至今低点':>11s}{'当时最低点':>11s}")
for i, r in sigs.iterrows():
    print(f"  {i+1:<4d}{str(r['date'].date()):>12s}{r['price']:>11.0f}"
          f"{r['dd']:>8.1%}{r['bounce']:>10.1%}{r['low']:>11.0f}")

print()
print("=" * 108)
print("【问题 2】每次触发后买红利，1/2/3 年表现（换仓 = 卖金买红利）")
print("=" * 108)
print(f"  {'触发日':>12s}{'沪深300距高点':>13s}{'红利距底':>10s}"
      f"{'买后1年':>9s}{'买后2年':>9s}{'买后3年':>9s}{'相对持金2年':>13s}")


def px(s, dt):
    if dt in s.index:
        return float(s.loc[dt])
    i = s.index.get_indexer([dt], method="nearest")[0]
    return float(s.iloc[i])


rows = []
for _, r in sigs.iterrows():
    d = r["date"]
    # 红利距自己「至今最低点」（也是因果口径）
    dseg = PX50[(PX50.index >= "2005-01-01") & (PX50.index <= d)]
    dlow = float(dseg.min())
    div_above = px(PX50, d) / dlow - 1

    res = {}
    for H, tag in ((365, "y1"), (730, "y2"), (1095, "y3")):
        fut = TR50[(TR50.index > d) & (TR50.index <= d + pd.Timedelta(days=H))]
        res[tag] = float(fut.iloc[-1] / px(TR50, d) - 1) if len(fut) > (60 if H > 400 else 30) else np.nan
    # 相对持金（2年）
    g0, g1 = px(GLD, d), px(GLD, d + pd.Timedelta(days=730))
    d1 = px(TR50, d + pd.Timedelta(days=730))
    rel = (d1 / px(TR50, d)) / (g1 / g0) if not np.isnan(g1) else np.nan
    ok = div_above <= 0.20
    rows.append({"date": d, "div_above": div_above, "ok": ok, "rel": rel, **res})
    print(f"  {str(d.date()):>12s}{r['dd']:>12.1%}{div_above:>9.1%}"
          f"{res['y1']:>8.1%}{res['y2']:>8.1%}{res['y3']:>8.1%}{rel:>12.2f}"
          + ("" if ok else "  ← 红利已涨超20%，按规则不买"))

print()
print("=" * 108)
print("【问题 3】因果版 vs 事后版：差距多大")
print("=" * 108)
CR = [("2008 次贷", "2007-06-01", "2010-06-30"), ("2011 欧债", "2011-04-01", "2013-06-30"),
      ("2015 A股股灾", "2015-04-01", "2017-06-30"), ("2018 Q4", "2018-09-01", "2019-12-31"),
      ("2020 COVID", "2020-01-01", "2021-06-30"), ("2022 加息", "2022-01-01", "2025-06-30")]
print(f"  {'危机':<16s}{'事后版触发日':>14s}{'因果版触发日':>14s}{'差几天':>9s}{'事后买价/底':>12s}{'因果买价/底':>12s}")
for nm, t0, t1 in CR:
    seg = HS300[(HS300.index >= t0) & (HS300.index <= t1)].dropna()
    trough = seg.idxmin()
    low = float(seg.min())
    after = seg[seg.index > trough]
    h = (after / low - 1)[(after / low - 1) >= 0.15]
    ex_post = h.index[0] if len(h) else None
    cs = causal_signals(seg, dd_gate=-0.10, bounce_need=0.15, cooldown=120)
    causal = cs["date"].iloc[0] if len(cs) else None
    if ex_post is None and causal is None:
        print(f"  {nm:<16s}{'都没有':>14s}")
        continue
    e = str(ex_post.date()) if ex_post is not None else "无"
    c = str(causal.date()) if causal is not None else "无"
    gap = (causal - ex_post).days if (ex_post is not None and causal is not None) else np.nan
    ep = px(HS300, ex_post) / low if ex_post is not None else np.nan
    cp = px(HS300, causal) / low if causal is not None else np.nan
    print(f"  {nm:<16s}{e:>14s}{c:>14s}{gap:>8.0f}d{ep:>12.2f}{cp:>12.2f}")
