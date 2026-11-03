# -*- coding: utf-8 -*-
"""verify_sequence.py - 测「先按黄金信号卖金 → 等股市 S5 买股」这条路径

核心矛盾（上一轮发现）：
  · 黄金从不在股市见顶前见顶（5/5 都在之后，最晚 +51 月）
  · 所以要"买股票在底部"，就必须在黄金还没见顶时就卖金

本脚本量化这个矛盾，并比较三条路径：
  A 在股市顶部卖金 → 等 S5 买股（用户原本的想法）
  B 在股市底部同步卖金买股（牺牲黄金后续涨幅，换取买股及时）
  C 黄金走强信号卖一半（RSI>=75）+ 股市 S5 买股（分两批）
  D 什么都不做：一直持金
评价：以 24 个月为窗口，看最终「现金+股票」价值相对「一直持金」的倍数
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


def usc(s):
    return pd.read_csv(CACHE / f"us_{s}.csv", parse_dates=["date"]).set_index("date")["close"].astype(float)


def emidx(fn):
    d = pd.read_csv(CACHE / fn)
    dc = next(c for c in d.columns if "日期" in c)
    d[dc] = pd.to_datetime(d[dc])
    return d.sort_values(dc).set_index(dc)["最新价"].astype(float)


def li(code):
    c = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    d = pd.read_sql_query("SELECT date,close FROM idx_daily WHERE code=? ORDER BY date", c, params=(code,))
    c.close()
    d["date"] = pd.to_datetime(d["date"])
    return d.set_index("date")["close"].astype(float)


GLD = usc("GLD")
DIV = li("H20269")
SPX = emidx("em_global_spx.csv")
HS300 = emidx("em_global_hs300.csv")


def rsi_w(close, n=14):
    d = close.diff()
    au = d.clip(lower=0).ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    ad = (-d).clip(lower=0).ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    return 100 - 100 / (1 + au / ad.replace(0, np.nan))


RSI_G = rsi_w(GLD, 14)

CRISES = [
    ("2008 次贷", "2007-06-01", "2012-12-31", SPX, "SPX"),
    ("2011 欧债", "2011-04-01", "2013-12-31", SPX, "SPX"),
    ("2015 A股股灾", "2015-04-01", "2018-12-31", HS300, "HS300"),
    ("2020 COVID", "2020-01-01", "2022-06-30", SPX, "SPX"),
    ("2022 加息", "2022-01-01", "2026-06-30", SPX, "SPX"),
]


def structure(series, t0, t1):
    seg = series[(series.index >= t0) & (series.index <= t1)].dropna()
    if len(seg) < 60:
        return None
    trough = seg.idxmin()
    before = seg[seg.index <= trough]
    top = before.idxmax()
    after = seg[seg.index > trough]
    if len(after) < 20:
        return None
    low = float(seg.min())
    bounce = after / low - 1
    hit = bounce[bounce >= 0.15]
    return {"top": top, "trough": trough, "low": low,
            "trig": hit.index[0] if len(hit) else None}


print("=" * 116)
print("【核心矛盾量化：如果在「股市底部」卖金买股，黄金是在它最终峰值的百分之几卖出？】")
print("=" * 116)
print(f"  {'危机':<16s}{'股市底':>12s}{'卖金价':>9s}{'黄金最终峰':>10s}{'峰值日':>12s}"
      f"{'卖在峰值%':>10s}{'若等到峰值':>11s}")
for nm, t0, t1, bench, tag in CRISES:
    st = structure(bench, t0, t1)
    if st is None or st["trig"] is None:
        continue
    d = st["trough"]
    if d not in GLD.index:
        d = GLD.index[GLD.index.get_indexer([d], method="nearest")[0]]
    sell_v = float(GLD.loc[d])
    later = GLD[GLD.index >= d].dropna()
    pk_v = float(later.max()); pk_d = later.idxmax()
    print(f"  {nm:<16s}{str(st['trough'].date()):>12s}{sell_v:>9.1f}{pk_v:>10.1f}"
          f"{str(pk_d.date()):>12s}{sell_v/pk_v:>9.0%}{f'{pk_v/sell_v-1:+.0%}':>11s}")

print()
print("=" * 116)
print("【四条路径对比】以危机顶部为起点、持有 24 个月，看总资产相对「一直持金」的倍数")
print("=" * 116)


def evaluate(nm, t0, t1, bench):
    st = structure(bench, t0, t1)
    if st is None or st["trig"] is None:
        return None
    top, trough, trig = st["top"], st["trough"], st["trig"]

    def px(series, dt):
        if dt in series.index:
            return float(series.loc[dt])
        i = series.index.get_indexer([dt], method="nearest")[0]
        return float(series.iloc[i])

    # 路径 A：在股市顶卖金，持现金到 S5，全买股票
    g_at_top = px(GLD, top); g_at_trig_A = px(GLD, trig)
    # 现金按 2% 年化
    yrs = (trig - top).days / 365.25
    cashA = g_at_top * (1.02 ** yrs)
    shA = cashA / px(DIV, trig)
    endA = shA * px(DIV, trig + pd.Timedelta(days=730))

    # 路径 B：一直持有黄金到期（基准）
    endB = g_at_top * 0 + px(GLD, top + pd.Timedelta(days=730))  # 以 1 单位黄金计

    # 路径 C：在 S5 卖金买股
    g_at_trig = px(GLD, trig)
    shC = px(DIV, trig) / px(DIV, trig)   # 1 单位黄金 -> 换红利
    endC = (g_at_trig / px(DIV, trig)) * px(DIV, trig + pd.Timedelta(days=730))

    # 路径 D：黄金 RSI>=75 卖一半，其余在 S5 卖
    win = GLD[(GLD.index >= top) & (GLD.index <= trig)]
    r = RSI_G.reindex(win.index)
    rsi_hit = r[r >= 75]
    if len(rsi_hit):
        d_rsi = rsi_hit.index[0]
        half_cash = 0.5 * px(GLD, d_rsi)
        half_stock_at_s5 = (half_cash / px(GLD, trig)) * (g_at_trig / px(DIV, trig))
        other_half = (0.5 * g_at_trig / px(DIV, trig))
        endD = (half_stock_at_s5 + other_half) * px(DIV, trig + pd.Timedelta(days=730))
    else:
        endD = endC

    return {"nm": nm, "A": endA / endB, "B": 1.0, "C": endC / endB, "D": endD / endB,
            "top": top, "trig": trig}


print(f"  {'危机':<16s}{'A 顶卖金再买股':>16s}{'B 一直持金':>12s}"
      f"{'C S5时卖金买股':>16s}{'D 分批(RSI+S5)':>16s}")
res = []
for nm, t0, t1, bench, tag in CRISES:
    r = evaluate(nm, t0, t1, bench)
    if r is None:
        print(f"  {nm:<16s}  无法评估")
        continue
    res.append(r)
    print(f"  {nm:<16s}{r['A']:>16.2f}{r['B']:>12.2f}{r['C']:>16.2f}{r['D']:>16.2f}")

if res:
    print(f"\n  {'中位数':<16s}{np.median([x['A'] for x in res]):>16.2f}"
          f"{1.0:>12.2f}{np.median([x['C'] for x in res]):>16.2f}"
          f"{np.median([x['D'] for x in res]):>16.2f}")
    print(f"  {'最好':<16s}{max(x['A'] for x in res):>16.2f}{1.0:>12.2f}"
          f"{max(x['C'] for x in res):>16.2f}{max(x['D'] for x in res):>16.2f}")
    print(f"  {'最差':<16s}{min(x['A'] for x in res):>16.2f}{1.0:>12.2f}"
          f"{min(x['C'] for x in res):>16.2f}{min(x['D'] for x in res):>16.2f}")
print("\n  说明：>1 表示在这 24 个月窗口里跑赢「一直持金」；<1 表示跑输")
print("  标的：黄金 GLD、股票用红利低波全收益 H20269（因 A股/美股统一口径）")
