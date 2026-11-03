# -*- coding: utf-8 -*-
"""verify_s5_asset_state.py - S5 触发那一刻，红利ETF 和黄金各自处于什么位置

问题：我们用「沪深300 自低点反弹 15%」作为买入信号。
      但买的是红利ETF（515100 / 515450）和纳指，不是沪深300。
      所以必须查：沪深300 反弹 15% 时，红利指数和黄金各自在什么状态？

代理说明（ETF 自身历史太短，用其跟踪指数代替）：
  515100 红利低波100ETF景顺 → 中证红利低波动100（930955 价格 / H20955 全收益）
  515450 红利低波50ETF南方  → 中证红利低波动（H30269 价格 / H20269 全收益）
  黄金 → GLD
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


def usc(s):
    return pd.read_csv(CACHE / f"us_{s}.csv", parse_dates=["date"]).set_index("date")["close"].astype(float)


def emidx(fn):
    d = pd.read_csv(CACHE / fn)
    dc = next(c for c in d.columns if "日期" in c)
    d[dc] = pd.to_datetime(d[dc])
    return d.sort_values(dc).set_index(dc)["最新价"].astype(float)


HS300 = emidx("em_global_hs300.csv")
PX100 = li("930955")      # 红利低波100 价格（515100 跟踪）
PX50 = li("H30269")       # 红利低波   价格（515450 跟踪）
TR100 = li("H20955")      # 红利低波100 全收益
TR50 = li("H20269")       # 红利低波   全收益
GLD = usc("GLD")

ASSETS = {
    "沪深300(信号源)": HS300,
    "515100代理·红利低波100价格": PX100,
    "515450代理·红利低波价格": PX50,
    "黄金 GLD": GLD,
}

CRISES = [
    ("2008 次贷", "2007-06-01", "2010-06-30"),
    ("2011 欧债", "2011-04-01", "2013-06-30"),
    ("2015 A股股灾", "2015-04-01", "2017-06-30"),
    ("2018 Q4", "2018-09-01", "2019-12-31"),
    ("2020 COVID", "2020-01-01", "2021-06-30"),
    ("2022 加息", "2022-01-01", "2024-06-30"),
]


def px(s, dt):
    if dt in s.index:
        return float(s.loc[dt])
    i = s.index.get_indexer([dt], method="nearest")[0]
    return float(s.iloc[i])


def s5_date(t0, t1):
    seg = HS300[(HS300.index >= t0) & (HS300.index <= t1)].dropna()
    if len(seg) < 60:
        return None, None, None
    trough = seg.idxmin()
    low = float(seg.min())
    after = seg[seg.index > trough]
    bounce = after / low - 1
    hit = bounce[bounce >= 0.15]
    return (trough, low, hit.index[0] if len(hit) else None)


print("=" * 120)
print("【核心问题】沪深300 反弹 15%（S5）那一刻，各资产在什么位置")
print("=" * 120)
print("  「距底」= 当时价格比该资产自己的最低点高多少；「距顶」= 比该资产自己的最高点低多少")
print()

for nm, t0, t1 in CRISES:
    trough, low, trig = s5_date(t0, t1)
    if trough is None:
        print(f"\n  ── {nm} ── 数据不足")
        continue
    print(f"\n  ── {nm} ──")
    if trig is None:
        print(f"     沪深300 未出现 15% 反弹（底部 {trough.date()}，最深 {low/px(HS300, t0):.1%}）")
        continue
    print(f"     沪深300 底部 {trough.date()} → S5 触发 {trig.date()}")
    print(f"     {'资产':<28s}{'距自己的底':>11s}{'距自己的顶':>11s}"
          f"{'之后12月':>10s}{'之后24月':>10s}{'之后36月':>10s}")
    for an, s in ASSETS.items():
        seg = s[(s.index >= t0) & (s.index <= trig)]
        if len(seg) < 20:
            continue
        own_low = float(seg.min())
        own_high = float(seg.max())
        p = px(s, trig)
        above_low = p / own_low - 1
        below_high = p / own_high - 1
        r12 = r24 = r36 = np.nan
        for H, bag in ((365, "r12"), (730, "r24"), (1095, "r36")):
            fut = s[(s.index > trig) & (s.index <= trig + pd.Timedelta(days=H))]
            if len(fut) > (20 if H == 365 else 60):
                v = float(fut.iloc[-1] / p - 1)
                if bag == "r12": r12 = v
                elif bag == "r24": r24 = v
                else: r36 = v
        print(f"     {an:<28s}{above_low:>10.1%}{below_high:>11.1%}"
              f"{r12:>10.1%}{r24:>10.1%}{r36:>10.1%}")

print()
print("=" * 120)
print("【汇总：每次 S5 触发时，红利ETF代理 距自己底部多远】")
print("=" * 120)
print(f"  {'危机':<16s}{'沪深300距底':>13s}{'515100代理距底':>17s}{'515450代理距底':>17s}{'黄金距底':>11s}")
rec = []
for nm, t0, t1 in CRISES:
    trough, low, trig = s5_date(t0, t1)
    if trig is None:
        continue
    row = [nm]
    for s in (HS300, PX100, PX50, GLD):
        seg = s[(s.index >= t0) & (s.index <= trig)]
        if len(seg) < 20:
            row.append(np.nan); continue
        row.append(px(s, trig) / float(seg.min()) - 1)
    rec.append(row)
    print(f"  {row[0]:<16s}{row[1]:>12.1%}{row[2]:>17.1%}{row[3]:>17.1%}{row[4]:>10.1%}")
if rec:
    a = np.array([r[1:] for r in rec], dtype=float)
    print(f"\n  {'中位数':<16s}{np.nanmedian(a[:,0]):>12.1%}{np.nanmedian(a[:,1]):>17.1%}"
          f"{np.nanmedian(a[:,2]):>17.1%}{np.nanmedian(a[:,3]):>10.1%}")
    print(f"  {'平均':<16s}{np.nanmean(a[:,0]):>12.1%}{np.nanmean(a[:,1]):>17.1%}"
          f"{np.nanmean(a[:,2]):>17.1%}{np.nanmean(a[:,3]):>10.1%}")
