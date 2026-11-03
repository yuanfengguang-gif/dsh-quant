# -*- coding: utf-8 -*-
"""verify_qqq.py - 正确计算纳指 QDII ETF 的真实表现（处理份额拆分）

陷阱：QDII ETF 做过份额拆分，导致
  · 单位净值 大幅下降
  · 累计净值 − 单位净值 出现巨额假"分红"
所以不能用累计净值算分红，也不能用单位净值算收益。
正确做法：用「日增长率复利」= 基金公司公布的总收益（已做拆分/分红调整），
并用纳斯达克指数交叉验证。
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CACHE = Path(r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant\data\cache\crisis")


def load_index_ndx():
    d = pd.read_csv(CACHE / "em_global_ndx.csv")
    dc = next(c for c in d.columns if "日期" in c)
    d[dc] = pd.to_datetime(d[dc])
    return d.sort_values(dc).set_index(dc)["最新价"].astype(float)


NDX = load_index_ndx()

print("=" * 104)
print("【拆份额检测：单位净值是否出现异常单日跳变】")
print("=" * 104)
for code, nm in (("513100", "纳指ETF国泰"), ("159941", "纳指100ETF广发"),
                 ("513300", "纳斯达克100ETF华夏")):
    f = CACHE / f"etf_{code}_nav.csv"
    if not f.exists():
        continue
    d = pd.read_csv(f); d.columns = [str(c) for c in d.columns]
    d["净值日期"] = pd.to_datetime(d["净值日期"])
    d = d.sort_values("净值日期").reset_index(drop=True)
    nav = d["单位净值"].astype(float)
    chg = nav.pct_change()
    big = chg[chg.abs() > 0.15]
    print(f"\n  {code} {nm}")
    print(f"     单位净值单日变动 |Δ|>15% 的天数：{len(big)}")
    for dt, v in big.items():
        print(f"       {d['净值日期'].iloc[dt].date()}  {v:+.2%}")
    # 累计净值是否连续
    cum = d["累计净值"].astype(float)
    dc = cum.pct_change()
    jb = dc[dc.abs() > 0.30]
    print(f"     累计净值单日变动 |Δ|>30% 的天数：{len(jb)}")

print()
print("=" * 104)
print("【正确口径：日增长率复利 vs 纳指指数（交叉验证）】")
print("=" * 104)
for code, nm in (("513100", "纳指ETF国泰"), ("159941", "纳指100ETF广发")):
    f = CACHE / f"etf_{code}_nav.csv"
    if not f.exists():
        continue
    d = pd.read_csv(f); d.columns = [str(c) for c in d.columns]
    d["净值日期"] = pd.to_datetime(d["净值日期"])
    d = d.sort_values("净值日期").reset_index(drop=True)
    g = pd.to_numeric(d["日增长率"], errors="coerce").fillna(0) / 100.0
    tr = (1 + g).cumprod()
    nav = d["单位净值"].astype(float)
    yrs = (d["净值日期"].iloc[-1] - d["净值日期"].iloc[0]).days / 365.25

    # 同期纳指
    seg = NDX[(NDX.index >= d["净值日期"].iloc[0]) & (NDX.index <= d["净值日期"].iloc[-1])]
    ndx_ret = float(seg.iloc[-1] / seg.iloc[0] - 1) if len(seg) > 10 else np.nan

    tr_ret = float(tr.iloc[-1] - 1)
    nav_ret = float(nav.iloc[-1] / nav.iloc[0] - 1)

    print(f"\n  {code} {nm}  （{yrs:.1f} 年）")
    print(f"     日增长率复利总收益：{tr_ret:+.1%}   → 年化 {(1+tr_ret)**(1/yrs)-1:+.2%}")
    print(f"     单位净值涨幅：      {nav_ret:+.1%}   ← 被拆份额污染，不可用")
    print(f"     同期纳指涨幅：      {ndx_ret:+.1%}   → 年化 {(1+ndx_ret)**(1/yrs)-1:+.2%}")
    print(f"     → 日增长率与纳指偏差 {abs(tr_ret-ndx_ret)*100:.1f}pp，"
          f"{'✅ 可信' if abs(tr_ret-ndx_ret)<0.35 else '⚠️ 偏差大'}")

    # 用日增长率算年化波动与最大回撤
    nav_tr = tr / tr.iloc[0]
    vol = float(g.std() * np.sqrt(252))
    mdd = float((nav_tr / nav_tr.cummax() - 1).min())
    print(f"     年化波动 {vol:.1%}   最大回撤 {mdd:.1%}")

print()
print("=" * 104)
print("【结论：纳指 vs 红利 的风险收益对比（同区间 2018 起）】")
print("=" * 104)
print(f"  {'标的':<22s}{'年化':>9s}{'年化波动':>10s}{'最大回撤':>10s}{'收益/波动':>11s}")
for code, nm in (("513100", "纳指ETF国泰(513100)"),
                 ("515100", "红利低波100(515100)"),
                 ("515450", "红利低波50(515450)")):
    f = CACHE / f"etf_{code}_nav.csv"
    if not f.exists():
        continue
    d = pd.read_csv(f); d.columns = [str(c) for c in d.columns]
    d["净值日期"] = pd.to_datetime(d["净值日期"])
    d = d.sort_values("净值日期").reset_index(drop=True)
    d = d[d["净值日期"] >= "2020-10-22"].reset_index(drop=True)
    if len(d) < 250:
        continue
    g = pd.to_numeric(d["日增长率"], errors="coerce").fillna(0) / 100.0
    tr = (1 + g).cumprod()
    yrs = (d["净值日期"].iloc[-1] - d["净值日期"].iloc[0]).days / 365.25
    ann = tr.iloc[-1] ** (1 / yrs) - 1
    vol = float(g.std() * np.sqrt(252))
    mdd = float((tr / tr.cummax() - 1).min())
    print(f"  {nm:<22s}{ann:>9.2%}{vol:>10.1%}{mdd:>10.1%}{ann/vol:>11.2f}")
