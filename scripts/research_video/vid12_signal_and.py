# -*- coding: utf-8 -*-
"""verify_signal_and.py - 方案 B 验证：沪深300 与 红利 双条件同时满足

对照三套口径：
  C 现行：沪深300 距36月高点 ≤ -25%（单一条件）
  A 替代：红利自身距36月高点 ≤ -20% / -30%（单一条件）
  B 双条件：沪深300 ≤ X% 且 红利 ≤ Y%（同时满足）

评价指标（全部以【红利低波全收益 H20269】为实际持有标的）：
  · 触发次数
  · 信号发出后红利还要跌多少（越接近 0 越好）
  · 持 1/2/3 年收益
  · 持有期内最深浮亏
  · 买入价 / 区间最低点（越接近 1 越好）

⚠️ 样本只有 6 场危机，任何"最优"都可能是过拟合，结论必须标注。
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


def em(fn):
    d = pd.read_csv(CACHE / fn)
    dc = next(c for c in d.columns if "日期" in str(c))
    d[dc] = pd.to_datetime(d[dc])
    return d.sort_values(dc).set_index(dc)["最新价"].astype(float)


HS = em("em_global_hs300.csv")
DIV = li("H30269")
TR = li("H20269")

hs_rm = HS.rolling(756, min_periods=250).max()
div_rm = DIV.rolling(756, min_periods=250).max()
hs_dd = HS / hs_rm - 1
div_dd = DIV / div_rm - 1

CR = [("2008 次贷", "2007-06-01", "2010-06-30"), ("2011 欧债", "2011-04-01", "2013-06-30"),
      ("2015 A股股灾", "2015-04-01", "2017-06-30"), ("2018 Q4", "2018-09-01", "2019-12-31"),
      ("2020 COVID", "2020-01-01", "2021-06-30"), ("2022 加息", "2022-01-01", "2025-06-30")]


def find_trigger(hs_lv, div_lv, t0, t1):
    """返回首次满足条件的日期。hs_lv / div_lv 为 None 表示该条件不参与"""
    idx = hs_dd.index.intersection(div_dd.index)
    idx = idx[(idx >= t0) & (idx <= t1)]
    ok = pd.Series(True, index=idx)
    if hs_lv is not None:
        ok &= (hs_dd.reindex(idx) <= -hs_lv)
    if div_lv is not None:
        ok &= (div_dd.reindex(idx) <= -div_lv)
    hit = ok[ok]
    return hit.index[0] if len(hit) else None


def evaluate(hs_lv, div_lv, horizon_days=1095):
    """返回该口径在各危机下的明细"""
    rows = []
    for nm, t0, t1 in CR:
        T0, T1 = pd.Timestamp(t0), pd.Timestamp(t1)
        d = find_trigger(hs_lv, div_lv, T0, T1)
        if d is None:
            rows.append({"crisis": nm, "date": None})
            continue
        v_at = float(DIV.asof(d))
        seg = DIV[(DIV.index >= T0) & (DIV.index <= T1)]
        v_low = float(seg[seg.index >= d].min())
        base = float(TR.asof(d))
        rets = {}
        for H, k in ((365, "r1"), (730, "r2"), (1095, "r3")):
            e = d + pd.Timedelta(days=H)
            rets[k] = (float(TR.asof(e)) / base - 1) if e <= TR.index[-1] else np.nan
        win = TR[(TR.index >= d) & (TR.index <= d + pd.Timedelta(days=horizon_days))]
        mdd = float((win / win.cummax() - 1).min()) if len(win) > 30 else np.nan
        rows.append({"crisis": nm, "date": d, "more_fall": v_low / v_at - 1,
                     "price_vs_low": v_at / float(seg.min()), "mdd": mdd, **rets})
    return rows


def summarize(label, rows):
    ok = [r for r in rows if r.get("date") is not None]
    if not ok:
        print(f"  {label:<30s}  从未触发")
        return None
    r3 = [r["r3"] for r in ok if not np.isnan(r["r3"])]
    r1 = [r["r1"] for r in ok if not np.isnan(r["r1"])]
    more = [r["more_fall"] for r in ok]
    mdd = [r["mdd"] for r in ok if not np.isnan(r["mdd"])]
    pvl = [r["price_vs_low"] for r in ok]
    return {
        "label": label, "n": len(ok),
        "r1_med": np.median(r1) if r1 else np.nan,
        "r3_med": np.median(r3) if r3 else np.nan,
        "r3_min": min(r3) if r3 else np.nan,
        "more_med": np.median(more), "more_worst": min(more),
        "mdd_med": np.median(mdd) if mdd else np.nan,
        "mdd_worst": min(mdd) if mdd else np.nan,
        "pvl": np.mean(pvl),
    }


print("=" * 116)
print("【一】方案 B 各种组合 vs 现行 C vs 替代 A —— 汇总对比")
print("=" * 116)
print(f"  {'口径':<30s}{'触发':>5s}{'持1年中位':>10s}{'持3年中位':>10s}{'持3年最差':>10s}"
      f"{'再跌中位':>9s}{'再跌最差':>9s}{'浮亏中位':>9s}{'浮亏最差':>9s}{'买价/低点':>9s}")

CASES = [
    ("C 现行：HS300≤-25%", 0.25, None),
    ("C'：HS300≤-35%", 0.35, None),
    ("A1：红利≤-20%", None, 0.20),
    ("A2：红利≤-25%", None, 0.25),
    ("B1：HS300≤-20% 且 红利≤-15%", 0.20, 0.15),
    ("B2：HS300≤-20% 且 红利≤-20%", 0.20, 0.20),
    ("B3：HS300≤-25% 且 红利≤-15%", 0.25, 0.15),
    ("B4：HS300≤-25% 且 红利≤-20%", 0.25, 0.20),
    ("B5：HS300≤-30% 且 红利≤-20%", 0.30, 0.20),
    ("B6：HS300≤-30% 且 红利≤-25%", 0.30, 0.25),
]
sums = []
for lab, h, dv in CASES:
    s = summarize(lab, evaluate(h, dv))
    if s:
        sums.append(s)
        print(f"  {lab:<30s}{s['n']:>5d}{s['r1_med']:>+9.1%}{s['r3_med']:>+10.1%}{s['r3_min']:>+10.1%}"
              f"{s['more_med']:>8.1%}{s['more_worst']:>9.1%}{s['mdd_med']:>8.1%}{s['mdd_worst']:>9.1%}"
              f"{s['pvl']:>9.2f}")

print()
print("=" * 116)
print("【二】重点三个口径的逐场明细")
print("=" * 116)
for lab, h, dv in (("C 现行 HS300≤-25%", 0.25, None),
                   ("A1 红利≤-20%", None, 0.20),
                   ("B4 HS300≤-25% 且 红利≤-20%", 0.25, 0.20)):
    print(f"\n  ── {lab} ──")
    rows = evaluate(h, dv)
    print(f"     {'危机':<14s}{'信号日':>12s}{'红利再跌':>9s}{'持1年':>9s}{'持2年':>9s}{'持3年':>9s}{'最深浮亏':>10s}{'买价/低点':>10s}")
    for r in rows:
        if r.get("date") is None:
            print(f"     {r['crisis']:<14s}{'未触发':>12s}")
            continue
        f = lambda x: f"{x:>+8.1%}" if not np.isnan(x) else "       —"
        print(f"     {r['crisis']:<14s}{str(r['date'].date()):>12s}"
              f"{r['more_fall']:>8.1%}{f(r['r1'])}{f(r['r2'])}{f(r['r3'])}"
              f"{r['mdd']:>9.1%}{r['price_vs_low']:>10.2f}")

print()
print("=" * 116)
print("【三】两档组合方案：B4 第1档 + 更深的第2档（分两次买）")
print("=" * 116)
print("  第1档 = HS300≤-25% 且 红利≤-20%；第2档 = HS300≤-35% 且 红利≤-30%")
print(f"  {'危机':<14s}{'第1档日期':>13s}{'第2档日期':>13s}")
for nm, t0, t1 in CR:
    T0, T1 = pd.Timestamp(t0), pd.Timestamp(t1)
    d1 = find_trigger(0.25, 0.20, T0, T1)
    d2 = find_trigger(0.35, 0.30, T0, T1)
    print(f"  {nm:<14s}{(str(d1.date()) if d1 is not None else '未触发'):>13s}"
          f"{(str(d2.date()) if d2 is not None else '未触发'):>13s}")

print()
print("=" * 116)
print("【四】当前状态（2026-11-03）")
print("=" * 116)
print(f"  沪深300 回撤 {float(hs_dd.iloc[-1]):.2%}   红利低波回撤 {float(div_dd.iloc[-1]):.2%}")
for lab, h, dv in (("C 现行 HS300≤-25%", 0.25, None),
                   ("A1 红利≤-20%", None, 0.20),
                   ("B4 HS300≤-25% 且 红利≤-20%", 0.25, 0.20)):
    c1 = (float(hs_dd.iloc[-1]) <= -h) if h else True
    c2 = (float(div_dd.iloc[-1]) <= -dv) if dv else True
    print(f"  {lab:<30s} HS300条件={'✅' if (h is None or c1) else '❌'}"
          f"  红利条件={'✅' if (dv is None or c2) else '❌'}"
          f"  综合={'✅满足' if (c1 and c2) else '❌未满足'}")

print()
print("=" * 116)
print("【五】过拟合警示")
print("=" * 116)
print("""  上面比较了 10 种口径，但样本只有 6 场危机（其中有效触发 4–6 次）。
  在这么小的样本上挑"最优"，本质上是在拟合噪声。
  因此结论应看「哪个方向的逻辑更对」，而不是「哪个数字最高」：
    · 用 HS300 判、买红利 → 口径错配（逻辑缺陷）
    · 用红利自己判 → 逻辑正确（买什么就量什么）
    · 双条件 → 逻辑最保守（大盘崩 + 标的也跌了才动手），但触发更少
""")
