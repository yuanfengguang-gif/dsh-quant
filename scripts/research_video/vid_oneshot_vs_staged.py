# -*- coding: utf-8 -*-
"""verify_oneshot_vs_staged2.py - 修正版：持仓期从「买入日」起算

修的两个 bug：
  ① 上一版 end = 危机顶 + 24 月，导致 2008 那场实际只持有 7 个月
     正确：end = 买入日 + H 月
  ② 2018 Q4 窗口延伸到 2020-06，把 COVID 也吃进去了
     正确：2018 Q4 窗口 2018-09 ~ 2019-12

另修：P4「跌20%全买」原来用 trough（事后最低点）作买入日 —— 那是未来函数，
      正确应在「首次触及 -20%」那天买。
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
H30269 = li("H30269")
SPX = emidx("em_global_spx.csv")
HS300 = emidx("em_global_hs300.csv")
BENCH = {"SPX": SPX, "HS300": HS300}

# 修正窗口：每场独立，不重叠
CRISES = [
    ("2008 次贷", "2007-06-01", "2010-06-30", "SPX"),
    ("2011 欧债", "2011-04-01", "2013-06-30", "SPX"),
    ("2015 A股股灾", "2015-04-01", "2017-06-30", "HS300"),
    ("2018 Q4", "2018-09-01", "2019-12-31", "SPX"),
    ("2020 COVID", "2020-01-01", "2021-06-30", "SPX"),
    ("2022 加息", "2022-01-01", "2024-06-30", "SPX"),
]


def px(series, dt):
    if dt in series.index:
        return float(series.loc[dt])
    i = series.index.get_indexer([dt], method="nearest")[0]
    return float(series.iloc[i])


def structure(bench, t0, t1):
    seg = bench[(bench.index >= t0) & (bench.index <= t1)].dropna()
    if len(seg) < 60:
        return None
    trough = seg.idxmin()
    top = seg[seg.index <= trough].idxmax()
    after = seg[seg.index > trough]
    low = float(seg.min())
    bounce = after / low - 1
    hit = bounce[bounce >= 0.15]
    dd = seg / seg.cummax() - 1
    h20 = dd[dd <= -0.20]
    return {"top": top, "trough": trough, "low": low,
            "trig": hit.index[0] if len(hit) else None,
            "first20": h20.index[0] if len(h20) else None,
            "deepest": float(dd.min())}


def sim(trades, start, H_months):
    """trades: [(date, fraction)]；以 1 单位黄金为初始；返回 (相对持金倍数, 最大浮亏, 实际投入比例)"""
    if not trades:
        return 1.0, 0.0, 0.0
    last = max(d for d, _ in trades)
    end = last + pd.Timedelta(days=int(H_months * 30.44))
    gl, sk, inv = 1.0, 0.0, 0.0
    for d, f in sorted(trades, key=lambda x: x[0]):
        amt = min(gl, f)
        if amt <= 0:
            continue
        gl -= amt
        sk += amt * px(GLD, d) / px(DIV, d)
        inv += amt
    final = gl * px(GLD, end) + sk * px(DIV, end)
    base = px(GLD, end)
    # 买入后最大浮亏
    cur = GLD.index[(GLD.index >= start) & (GLD.index <= end)]
    peak, mdd = 1.0, 0.0
    for d in cur:
        g2, s2 = 1.0, 0.0
        for td, f in sorted(trades, key=lambda x: x[0]):
            if td > d:
                continue
            a = min(g2, f)
            g2 -= a
            s2 += a * px(GLD, td) / px(DIV, td)
        v = g2 * px(GLD, d) + s2 * px(DIV, d)
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    return final / base, mdd, inv


def four_entry(st):
    trades = []
    s2 = H30269[H30269.index >= st["top"]]
    if len(s2) > 10:
        dd2 = s2 / s2.cummax() - 1
        h = dd2[dd2 <= -0.25]
        if len(h):
            trades.append((h.index[0], 0.25))
    if st["first20"] is not None:
        trades.append((st["first20"], 0.25))
    if st["trig"] is not None:
        trades.append((st["trig"], 0.40))
        trades.append((st["trig"] + pd.Timedelta(days=180), 0.10))
    agg = {}
    for d, f in trades:
        agg[d] = agg.get(d, 0) + f
    tot = sum(agg.values())
    if tot > 1:
        agg = {d: f / tot for d, f in agg.items()}
    return sorted(agg.items())


for H in (24, 36):
    print("=" * 116)
    print(f"【一次性 vs 分档：买入后持有 {H} 个月】")
    print("=" * 116)
    print(f"  {'危机':<16s}{'S5触发':>11s}{'P1 纯S5一次':>13s}{'P2 四入口':>12s}"
          f"{'P3 S5买70%':>12s}{'P4 跌20%首触全买':>17s}")
    R = []
    for nm, t0, t1, tag in CRISES:
        st = structure(BENCH[tag], t0, t1)
        if st is None:
            print(f"  {nm:<16s} 结构失败")
            continue
        p1 = sim([(st["trig"], 1.0)] if st["trig"] is not None else [], st["top"], H)[0]
        p2 = sim(four_entry(st), st["top"], H)[0]
        p3 = sim([(st["trig"], 0.7)] if st["trig"] is not None else [], st["top"], H)[0]
        p4 = sim([(st["first20"], 1.0)] if st["first20"] is not None else [], st["top"], H)[0]
        tg = str(st["trig"].date()) if st["trig"] is not None else "未触发"
        print(f"  {nm:<16s}{tg:>11s}{p1:>13.2f}{p2:>12.2f}{p3:>12.2f}{p4:>17.2f}")
        R.append((nm, p1, p2, p3, p4, st))
    if R:
        print(f"\n  {'中位数':<16s}{'':>11s}{np.median([r[1] for r in R]):>13.2f}"
              f"{np.median([r[2] for r in R]):>12.2f}{np.median([r[3] for r in R]):>12.2f}"
              f"{np.median([r[4] for r in R]):>17.2f}")
        print(f"  {'最差':<16s}{'':>11s}{min(r[1] for r in R):>13.2f}"
              f"{min(r[2] for r in R):>12.2f}{min(r[3] for r in R):>12.2f}"
              f"{min(r[4] for r in R):>17.2f}")
        print(f"  {'跑赢持金的场次':<16s}{'':>11s}"
              f"{sum(1 for r in R if r[1]>1)}/6{'':>8s}{sum(1 for r in R if r[2]>1)}/6"
              f"{'':>8s}{sum(1 for r in R if r[3]>1)}/6{'':>12s}{sum(1 for r in R if r[4]>1)}/6")
    print()

print("=" * 116)
print("【关键：S5 触发率与「不触发」的后果】")
print("=" * 116)
for nm, t0, t1, tag in CRISES:
    st = structure(BENCH[tag], t0, t1)
    if st is None:
        continue
    trig = str(st["trig"].date()) if st["trig"] is not None else "❌ 未触发"
    f20 = str(st["first20"].date()) if st["first20"] is not None else "❌ 未跌到-20%"
    print(f"  {nm:<16s} 最深 {st['deepest']:>7.1%}   首次-20%: {f20:<14s}  S5: {trig}")
