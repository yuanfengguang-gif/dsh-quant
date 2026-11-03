# -*- coding: utf-8 -*-
"""verify_sell_high_buy_low2.py - 修正版：正确识别「顶-底」结构

上一版 bug：把窗口内的全局最大值当"顶部"。但如果窗口延伸到下一轮牛市，
最大值会出现在窗口末尾，导致 trough 计算错误、部分危机被跳过。
正确做法：
  底部 = 窗口内全局最小值
  顶部 = 底部【之前】的最高点
  反弹 = 底部【之后】相对底部的涨幅
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
SPX = emidx("em_global_spx.csv")
NDX = emidx("em_global_ndx.csv")
HS300 = emidx("em_global_hs300.csv")
BENCH = {"SPX": SPX, "HS300": HS300, "NDX": NDX}

CRISES = [
    ("2008 次贷", "2007-06-01", "2010-12-31", "SPX"),
    ("2011 欧债", "2011-04-01", "2013-06-30", "SPX"),
    ("2015 A股股灾", "2015-04-01", "2017-06-30", "HS300"),
    ("2018 Q4", "2018-09-01", "2020-03-31", "SPX"),
    ("2020 COVID", "2020-01-01", "2020-12-31", "SPX"),
    ("2022 加息", "2022-01-01", "2023-12-31", "SPX"),
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
    trig = hit.index[0] if len(hit) else None
    return {"top": top, "top_v": float(before.max()), "trough": trough, "low": low,
            "trig": trig, "trig_v": float(series.loc[trig]) if trig is not None else np.nan,
            "end": seg.index[-1]}


print("=" * 112)
print("【Q1 修正版】黄金峰值相对股市危机的位置（6 场全部纳入）")
print("=" * 112)
print(f"  {'危机':<16s}{'股市顶':>12s}{'股市底':>12s}{'股市跌幅':>9s}"
      f"{'黄金峰值':>12s}{'相对顶':>9s}{'相对底':>9s}{'金价峰值':>10s}")
rows = []
for nm, t0, t1, mkt in CRISES:
    st = structure(BENCH[mkt], t0, t1)
    if st is None:
        print(f"  {nm:<16s} 结构识别失败")
        continue
    # 黄金在更宽窗口里的峰值
    g0 = pd.Timestamp(st["top"]) - pd.Timedelta(days=365)
    g1 = pd.Timestamp(t1) + pd.Timedelta(days=900)
    gseg = GLD[(GLD.index >= g0) & (GLD.index <= g1)].dropna()
    if len(gseg) < 100:
        print(f"  {nm:<16s} 黄金数据不足")
        continue
    gpk = gseg.idxmax()
    m_top = (gpk - st["top"]).days / 30.44
    m_bot = (gpk - st["trough"]).days / 30.44
    dd = st["low"] / st["top_v"] - 1
    print(f"  {nm:<16s}{str(st['top'].date()):>12s}{str(st['trough'].date()):>12s}{dd:>8.1%}"
          f"{str(gpk.date()):>12s}{m_top:>+8.0f}月{m_bot:>+8.0f}月{float(gseg.max()):>10.1f}")
    rows.append((nm, st, gpk, m_top, m_bot, float(gseg.max())))

print()
print(f"  黄金峰值出现在股市顶【之前】的次数：{sum(1 for _,_,_,mt,_,_ in rows if mt<0)}/{len(rows)}")
print(f"  黄金峰值出现在股市顶【之后】的次数：{sum(1 for _,_,_,mt,_,_ in rows if mt>0)}/{len(rows)}")

print()
print("=" * 112)
print("【Q2 修正版】「危机前（股市顶）卖黄金」的机会成本")
print("=" * 112)
print(f"  {'危机':<16s}{'顶部卖金价':>12s}{'24月内最高':>12s}{'错过涨幅':>10s}{'黄金峰值距顶':>14s}")
miss_all = []
for nm, st, gpk, m_top, m_bot, gpk_v in rows:
    sell_d = st["top"]
    if sell_d not in GLD.index:
        sell_d = GLD.index[GLD.index.get_indexer([sell_d], method="nearest")[0]]
    sell_v = float(GLD.loc[sell_d])
    later = GLD[(GLD.index > sell_d) & (GLD.index <= sell_d + pd.Timedelta(days=730))].dropna()
    if len(later) < 20:
        continue
    hi = float(later.max())
    miss = hi / sell_v - 1
    miss_all.append(miss)
    print(f"  {nm:<16s}{sell_v:>12.1f}{hi:>12.1f}{miss:>9.1%}{m_top:>+13.0f}月")
print(f"\n  平均错过涨幅：{np.mean(miss_all):.1%}   最差：{max(miss_all):.1%}   "
      f"最好：{min(miss_all):.1%}")

print()
print("=" * 112)
print("【Q4 修正版】用 S5 信号（反弹15%）买股票，买点质量")
print("=" * 112)
print(f"  {'危机':<16s}{'底部日':>12s}{'S5触发日':>12s}{'距底部':>9s}"
      f"{'买价/底价':>10s}{'之后1年':>9s}{'之后3年':>9s}")
hit_n = 0
for nm, t0, t1, mkt in CRISES:
    st = structure(BENCH[mkt], t0, t1)
    if st is None or st["trig"] is None:
        print(f"  {nm:<16s}  无 15% 反弹触发")
        continue
    hit_n += 1
    months = (st["trig"] - st["trough"]).days / 30.44
    s = BENCH[mkt]
    f1 = s[(s.index > st["trig"]) & (s.index <= st["trig"] + pd.Timedelta(days=365))]
    f3 = s[(s.index > st["trig"]) & (s.index <= st["trig"] + pd.Timedelta(days=1095))]
    r1 = float(f1.iloc[-1] / st["trig_v"] - 1) if len(f1) > 60 else np.nan
    r3 = float(f3.iloc[-1] / st["trig_v"] - 1) if len(f3) > 200 else np.nan
    print(f"  {nm:<16s}{str(st['trough'].date()):>12s}{str(st['trig'].date()):>12s}"
          f"{months:>8.1f}月{st['trig_v']/st['low']:>10.2f}{r1:>8.1%}{r3:>8.1%}")
print(f"\n  S5 触发率：{hit_n}/{len(CRISES)} = {hit_n/len(CRISES):.0%}")
