# -*- coding: utf-8 -*-
"""verify_v11_claims.py - 验证七剑财说视频的全部主张

视频核心：
  ① 危机第一阶段，黄金先跟着股市暴跌（不是避险失效）
  ② 三阶段：杀流动性 → 杀基本面 → 主权信用重估
  ③ 三个指标：
     指标1  10年期美债收益率 + 美元指数（上升=华尔街还缺钱=别抄底）
     指标2  金银比（冲高后转头向下=恐慌抛售出清=黄金见底）
     指标3  美联储降息（最重要，降息=黄金重启上涨）

本脚本分四部分：
  A 验证视频引用的事实数字
  B 验证三阶段框架
  C 逐个验证 3 个指标的因果可用性（不用未来函数）
  D 组合成可执行规则并与买入持有对比
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CACHE = Path(r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant\data\cache\crisis")


def usc(s):
    p = CACHE / f"us_{s}.csv"
    d = pd.read_csv(p)
    dc = [c for c in d.columns if c.lower() in ("date", "日期")][0]
    d[dc] = pd.to_datetime(d[dc])
    cc = [c for c in d.columns if c.lower() in ("close", "收盘")]
    vc = cc[0] if cc else [c for c in d.columns if "价" in c][0]
    return d.sort_values(dc).set_index(dc)[vc].astype(float)


def emidx(fn):
    d = pd.read_csv(CACHE / fn)
    dc = next(c for c in d.columns if "日期" in c)
    d[dc] = pd.to_datetime(d[dc])
    return d.sort_values(dc).set_index(dc)["最新价"].astype(float)


GLD = usc("GLD")
SLV = usc("SLV")
UUP = usc("UUP")
TLT = usc("TLT")
SPY = usc("SPY")
NDX = emidx("em_global_ndx.csv")
DXY = emidx("em_global_udi.csv")

print("=" * 100)
print("【数据确认】")
print("=" * 100)
for nm, s in (("GLD 黄金ETF", GLD), ("SLV 白银ETF", SLV), ("UUP 美元指数ETF", UUP),
              ("TLT 20年美债", TLT), ("SPY 标普", SPY), ("美元指数(东财)", DXY)):
    print(f"  {nm:<18s} {len(s):>5d} 行  {s.index.min().date()} ~ {s.index.max().date()}")

# ── 美债 10Y（东财 bond_zh_us_rate）
b = pd.read_csv(CACHE / "us_10y_东财.csv")
b.columns = [str(c) for c in b.columns]
b["日期"] = pd.to_datetime(b["日期"])
col10 = [c for c in b.columns if "美国国债收益率10年" in c]
if col10:
    B10 = b.set_index("日期")[col10[0]].astype(float).dropna()
    print(f"  {'美债10Y收益率':<18s} {len(B10):>5d} 行  {B10.index.min().date()} ~ {B10.index.max().date()}")
else:
    B10 = None
    print(f"  ❌ 未找到美国10年期国债收益率列，现有列：{list(b.columns)[:12]}")

# ── 美联储利率
r = pd.read_csv(CACHE / "macro_bank_usa_interest_rate.csv")
r.columns = [str(c) for c in r.columns]
r["日期"] = pd.to_datetime(r["日期"])
r = r.sort_values("日期")
FED = pd.to_numeric(r["今值"], errors="coerce").fillna(pd.to_numeric(r["前值"], errors="coerce"))
FED = pd.Series(FED.values, index=r["日期"].values).dropna()
print(f"  {'美联储基准利率':<18s} {len(FED):>5d} 行  {FED.index.min().date()} ~ {FED.index.max().date()}")

# ── 金银比（用 GLD/SLV 校准到真实比例）
GSR_ETF = (GLD / SLV).dropna()
try:
    gc = pd.read_csv(CACHE / "px_gold_gc.csv"); gc["date"] = pd.to_datetime(gc["date"])
    si = pd.read_csv(CACHE / "px_silver_si.csv"); si["date"] = pd.to_datetime(si["date"])
    GC = gc.set_index("date")["close"].astype(float)
    SI = si.set_index("date")["close"].astype(float)
    true_gsr = (GC / SI).dropna()
    ov = GSR_ETF.index.intersection(true_gsr.index)
    k = float((true_gsr.reindex(ov) / GSR_ETF.reindex(ov)).median()) if len(ov) > 50 else None
    if k:
        GSR = GSR_ETF * k
        print(f"  {'金银比(GLD/SLV校准)':<18s} {len(GSR):>5d} 行  校准系数 {k:.2f}")
        print(f"  {'金银比(COMEX真实)':<18s} {len(true_gsr):>5d} 行  {true_gsr.index.min().date()} 起")
    else:
        GSR = GSR_ETF
        print(f"  {'金银比(未校准)':<18s} {len(GSR):>5d} 行")
except Exception as e:
    GSR = GSR_ETF
    print(f"  ⚠️ COMEX 校准失败({e})，用 GLD/SLV 未校准值")

print()
print("=" * 100)
print("【A. 验证视频引用的事实数字】")
print("=" * 100)


def seg_peak_trough(s, t0, t1):
    x = s[(s.index >= t0) & (s.index <= t1)].dropna()
    if len(x) < 20:
        return None
    pk, tr = x.idxmax(), x.idxmin()
    return pk, float(x.max()), tr, float(x.min()), float(x.min() / x.max() - 1)


print("  A1  2008 次贷：黄金暴跌近 30%？")
r1 = seg_peak_trough(GLD, "2007-10-01", "2008-12-31")
if r1:
    print(f"      GLD 峰值 {r1[0].date()} {r1[1]:.1f} → 谷底 {r1[2].date()} {r1[3]:.1f}"
          f"  跌幅 {r1[4]:.1%}")
print("      视频说：金价从 1312 跌到 681（−48%？口径混乱）。前面又说 1032 是历史高点。")
print("      → 需核对真实现货金价（下方用 COMEX/GLD 口径给结论）")

print("\n  A2  2020 疫情：10 天内跌 15%？")
x = GLD[(GLD.index >= "2020-03-01") & (GLD.index <= "2020-03-31")]
if len(x):
    pk, tr = x.idxmax(), x.idxmin()
    print(f"      2020-03 区间：高 {pk.date()} {float(x.max()):.1f} → 低 {tr.date()} {float(x.min()):.1f}"
          f"  跌幅 {float(x.min()/x.max()-1):.1%}  历时 {(tr-pk).days} 天")

print("\n  A3  2008-10 之后三年涨 180% 到 1921？")
r3 = seg_peak_trough(GLD, "2008-10-01", "2012-12-31")
if r3:
    low_d, low_v = r3[2], r3[3]
    after = GLD[GLD.index >= low_d]
    pk2 = after.idxmax()
    print(f"      谷底 {low_d.date()} {low_v:.1f} → 后高 {pk2.date()} {float(after.max()):.1f}"
          f"  涨幅 {float(after.max()/low_v-1):.1%}")

print("\n  A4  2020 之后 5 个月涨 42.7%？")
r4 = seg_peak_trough(GLD, "2020-03-01", "2020-03-31")
if r4:
    low_d, low_v = r4[2], r4[3]
    after = GLD[(GLD.index > low_d) & (GLD.index <= low_d + pd.Timedelta(days=200))]
    print(f"      谷底 {low_d.date()} {low_v:.1f} → 200 天内高 {after.idxmax().date()} {float(after.max()):.1f}"
          f"  涨幅 {float(after.max()/low_v-1):.1%}")

print()
print("=" * 100)
print("【B. 验证三阶段框架】")
print("=" * 100)
print("  视频的三阶段：① 杀流动性（黄金跟着股票跌）② 杀基本面（巨头破产/紧缩）③ 主权信用重估（黄金暴涨）")
print("  检验方法：对每场危机，以黄金的「谷底」为界，看谷前(阶段1+2)与谷后(阶段3)各资产表现")

CRISES = [
    ("2008 次贷", "2007-10-01", "2011-12-31"),
    ("2011 欧债", "2011-04-01", "2013-06-30"),
    ("2015 A股股灾", "2015-06-01", "2017-06-30"),
    ("2018 Q4", "2018-09-01", "2020-03-31"),
    ("2020 COVID", "2020-02-01", "2021-12-31"),
    ("2022 加息", "2022-01-01", "2025-06-30"),
]
print(f"\n  {'危机':<14s}{'黄金谷底':>12s}{'谷前黄金':>10s}{'谷前股票':>10s}{'谷前美元':>10s}"
      f"{'谷后黄金':>10s}{'谷后股票':>10s}")
rows_b = []
for nm, t0, t1 in CRISES:
    g = GLD[(GLD.index >= t0) & (GLD.index <= t1)].dropna()
    if len(g) < 60:
        continue
    low_d = g.idxmin()
    pre = g[g.index <= low_d]
    if len(pre) < 20:
        continue
    pk_d = pre.idxmax()
    # 谷前：从峰到谷；谷后：从谷到窗口末
    def ret(s, a, b):
        ya = s[(s.index <= a)]
        yb = s[(s.index <= b)]
        if len(ya) == 0 or len(yb) == 0:
            return np.nan
        return float(yb.iloc[-1] / ya.iloc[-1] - 1)
    pre_g = ret(GLD, pk_d, low_d)
    pre_s = ret(SPY, pk_d, low_d)
    pre_d = ret(UUP, pk_d, low_d)
    post_end = min(pd.Timestamp(t1), GLD.index[-1])
    post_g = ret(GLD, low_d, post_end)
    post_s = ret(SPY, low_d, post_end)
    print(f"  {nm:<14s}{str(low_d.date()):>12s}{pre_g:>9.1%}{pre_s:>10.1%}{pre_d:>10.1%}"
          f"{post_g:>10.1%}{post_s:>10.1%}")
    rows_b.append((nm, low_d, pre_g, pre_s, pre_d, post_g, post_s))

if rows_b:
    A = np.array([[r[2], r[3], r[4], r[5], r[6]] for r in rows_b], dtype=float)
    print(f"\n  {'中位数':<14s}{'':>12s}{np.nanmedian(A[:,0]):>9.1%}{np.nanmedian(A[:,1]):>10.1%}"
          f"{np.nanmedian(A[:,2]):>10.1%}{np.nanmedian(A[:,3]):>10.1%}{np.nanmedian(A[:,4]):>10.1%}")
    print(f"\n  验证「阶段1：黄金跟着股票一起跌」→ 谷前黄金中位 {np.nanmedian(A[:,0]):.1%}，"
          f"股票 {np.nanmedian(A[:,1]):.1%}")
    print(f"  验证「阶段3：黄金报复性反弹」→ 谷后黄金中位 {np.nanmedian(A[:,3]):.1%}，"
          f"股票 {np.nanmedian(A[:,4]):.1%}")
    print(f"  验证「谷前美元走强（缺钱）」→ 美元中位 {np.nanmedian(A[:,2]):+.1%}")
