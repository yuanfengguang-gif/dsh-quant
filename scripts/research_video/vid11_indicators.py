# -*- coding: utf-8 -*-
"""verify_v11_indicators.py - 逐个验证视频的 3 个指标是否「因果可用」

【昨天的教训】任何信号必须能用「当天收盘可得的量」写出表达式。
所以本脚本对每个指标都问三个问题：
  Q1 描述性：危机时它确实变了吗？（是不是巧合）
  Q2 时序性：它是在黄金见底【之前】还是【之后】转向？（之后=没用）
  Q3 可交易性：用它做规则，能跑赢买入持有吗？

视频的三个指标：
  指标1  10年期美债收益率 + 美元指数   上升 = 华尔街还缺钱 = 别抄底
  指标2  金银比                       冲高后转头向下 = 恐慌抛售出清 = 黄金见底
  指标3  美联储降息                   降息 = 黄金重启上涨
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CACHE = Path(r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant\data\cache\crisis")


def usc(s):
    d = pd.read_csv(CACHE / f"us_{s}.csv")
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
SPY = usc("SPY")
DXY = emidx("em_global_udi.csv")

b = pd.read_csv(CACHE / "us_10y_东财.csv")
b.columns = [str(c) for c in b.columns]
b["日期"] = pd.to_datetime(b["日期"])
c10 = [c for c in b.columns if "美国国债收益率10年" in c][0]
B10 = b.set_index("日期")[c10].astype(float).dropna()

r = pd.read_csv(CACHE / "macro_bank_usa_interest_rate.csv")
r.columns = [str(c) for c in r.columns]
r["日期"] = pd.to_datetime(r["日期"])
r = r.sort_values("日期")
fed_v = pd.to_numeric(r["今值"], errors="coerce").fillna(pd.to_numeric(r["前值"], errors="coerce"))
FED = pd.Series(fed_v.values, index=pd.DatetimeIndex(r["日期"].values)).dropna()

# 金银比：GLD/SLV 校准
gsr_etf = (GLD / SLV).dropna()
try:
    gc = pd.read_csv(CACHE / "px_gold_gc.csv"); gc["date"] = pd.to_datetime(gc["date"])
    si = pd.read_csv(CACHE / "px_silver_si.csv"); si["date"] = pd.to_datetime(si["date"])
    true_gsr = (gc.set_index("date")["close"].astype(float) / si.set_index("date")["close"].astype(float)).dropna()
    ov = gsr_etf.index.intersection(true_gsr.index)
    k = float((true_gsr.reindex(ov) / gsr_etf.reindex(ov)).median())
    GSR = gsr_etf * k
except Exception:
    GSR = gsr_etf
    k = np.nan

# 统一日频面板
CAL = pd.DataFrame({"gld": GLD, "spy": SPY, "uup": UUP, "dxy": DXY, "b10": B10, "gsr": GSR})
CAL = CAL.dropna(subset=["gld", "spy"])
CAL["uup"] = CAL["uup"].ffill()
CAL["dxy"] = CAL["dxy"].ffill()
CAL["b10"] = CAL["b10"].ffill()
CAL["gsr"] = CAL["gsr"].ffill()
CAL["fed"] = FED.reindex(CAL.index).ffill()

print("=" * 104)
print("【准备就绪】")
print("=" * 104)
print(f"  面板 {CAL.index.min().date()} ~ {CAL.index.max().date()}，{len(CAL)} 交易日")
print(f"  金银比校准系数 {k:.2f}（GLD/SLV × 系数 ≈ 真实金银比）")
print(f"  当前读数：")
print(f"    黄金 GLD      {CAL['gld'].iloc[-1]:.1f}")
print(f"    金银比        {CAL['gsr'].iloc[-1]:.1f}（历史分位 {float((CAL['gsr']<CAL['gsr'].iloc[-1]).mean()):.0%}）")
print(f"    美元指数      {CAL['dxy'].iloc[-1]:.1f}")
print(f"    美债10Y       {CAL['b10'].iloc[-1]:.2f}%")
print(f"    美联储利率    {CAL['fed'].iloc[-1]:.2f}%")

# ── 定义黄金的「谷底事件」：下跌≥12% 后的最低点，且之后反弹≥15%
def gold_troughs(s, dd_min=-0.12, rebound=0.15, cooldown=180):
    out = []
    peak = -np.inf
    low = np.inf
    low_d = None
    last = None
    for dt, p in s.items():
        p = float(p)
        if p >= peak:
            peak = p; low = p; low_d = dt
        if p < low:
            low = p; low_d = dt
        if peak > 0 and low < peak and (low / peak - 1) <= dd_min:
            if p / low - 1 >= rebound:
                if last is None or (dt - last).days >= cooldown:
                    out.append({"low_date": low_d, "low": low, "confirm": dt,
                                "dd": low / peak - 1, "peak_date": None})
                    last = dt
                    peak = p; low = p; low_d = dt
    return pd.DataFrame(out)


tr = gold_troughs(CAL["gld"])
print(f"\n  识别到黄金「下跌≥12% 后反弹≥15%」的谷底事件：{len(tr)} 次")
print(f"  {'谷底日':>12s}{'低点':>8s}{'跌幅':>8s}{'确认日':>12s}{'确认滞后':>9s}")
for _, r_ in tr.iterrows():
    print(f"  {str(r_['low_date'].date()):>12s}{r_['low']:>8.1f}{r_['dd']:>7.1%}"
          f"{str(r_['confirm'].date()):>12s}{(r_['confirm']-r_['low_date']).days:>8d}天")

print()
print("=" * 104)
print("【指标1】10年期美债收益率 + 美元指数 —— 「缺钱晴雨表」")
print("=" * 104)
print("  视频说法：只要美元指数和美债收益率还在往上升，就说明华尔街还得变卖资产，别抄底")
print()
print(f"  {'谷底日':>12s}{'谷前60天 10Y变化':>18s}{'谷前60天 美元变化':>18s}{'两者同升?':>10s}")
hit = 0
for _, r_ in tr.iterrows():
    d = r_["low_date"]
    p60 = CAL.index[CAL.index <= d]
    if len(p60) < 70:
        continue
    d60 = p60[-61]
    db = CAL["b10"].loc[d] - CAL["b10"].loc[d60]
    du = CAL["uup"].loc[d] / CAL["uup"].loc[d60] - 1
    both = (db > 0) and (du > 0)
    hit += int(both)
    print(f"  {str(d.date()):>12s}{db:>+17.2f}pp{du:>+17.1%}{'✅是' if both else '否':>10s}")
print(f"\n  「谷底前 60 天，10Y 与美元同时上升」的比例：{hit}/{len(tr)}")

# 因果规则：两者同时处于上升趋势时，回避黄金
CAL["b10_up"] = CAL["b10"] > CAL["b10"].shift(60)
CAL["uup_up"] = CAL["uup"] > CAL["uup"].shift(60)
CAL["squeeze"] = CAL["b10_up"] & CAL["uup_up"]
print(f"\n  因果检验：在「10Y与美元同时上升」的日子里持有黄金 vs 其他日子")
a = CAL["gld"].pct_change()
in_sq = a[CAL["squeeze"] == True].dropna()
out_sq = a[CAL["squeeze"] == False].dropna()
print(f"    缺钱期（同升）：{len(in_sq)} 天，日均 {in_sq.mean()*100:+.4f}%，年化 {((1+in_sq.mean())**252-1):+.1%}")
print(f"    非缺钱期：      {len(out_sq)} 天，日均 {out_sq.mean()*100:+.4f}%，年化 {((1+out_sq.mean())**252-1):+.1%}")

print()
print("=" * 104)
print("【指标2】金银比 —— 「恐慌出清信号」")
print("=" * 104)
print("  视频说法：危机第一阶段金银比飙到极端高位；当它「冲不动、开始转头向下」，说明抛售盘出清、黄金见底")
print()
print("  ★ 关键时序问题：金银比的峰值是在黄金谷底【之前】还是【之后】？")
print(f"  {'黄金谷底':>12s}{'金银比峰值日':>14s}{'时间差':>10s}{'峰值时GSR':>11s}{'谷底时GSR':>11s}{'谷底后是否回落':>14s}")
lead = []
for _, r_ in tr.iterrows():
    d = r_["low_date"]
    win = CAL["gsr"][(CAL.index >= d - pd.Timedelta(days=250)) & (CAL.index <= d + pd.Timedelta(days=250))]
    if len(win) < 100:
        continue
    pk_d = win.idxmax()
    gap = (pk_d - d).days
    lead.append(gap)
    after = CAL["gsr"][(CAL.index > d) & (CAL.index <= d + pd.Timedelta(days=120))]
    fall = (after.iloc[-1] / CAL["gsr"].loc[d] - 1) if len(after) > 20 else np.nan
    print(f"  {str(d.date()):>12s}{str(pk_d.date()):>14s}{gap:>+9d}天"
          f"{float(win.max()):>11.1f}{CAL['gsr'].loc[d]:>11.1f}{fall:>+13.1%}")
if lead:
    print(f"\n  时间差中位：{np.median(lead):+.0f} 天（负=GSR峰值在谷底之前，正=之后）")
    print(f"  峰值在谷底【之前】的次数：{sum(1 for x in lead if x<0)}/{len(lead)}")

# 因果规则：GSR 从滚动高点回落 X% 买入
print()
print("  因果规则：金银比从「滚动 250 日最高」回落 X% 时买入黄金，看之后表现")
for X in (0.03, 0.05, 0.08, 0.12):
    CAL["gsr_max250"] = CAL["gsr"].rolling(250, min_periods=120).max()
    CAL["gsr_fall"] = CAL["gsr"] / CAL["gsr_max250"] - 1
    cal = (CAL["gsr_fall"] <= -X) & (CAL["gsr_fall"].shift(1) > -X)
    idx = CAL.index[cal.fillna(False)]
    if len(idx) == 0:
        continue
    keep = []
    for d in idx:
        if not keep or (d - keep[-1]).days > 120:
            keep.append(d)
    rets = []
    for d in keep:
        fut = CAL["gld"][(CAL.index > d) & (CAL.index <= d + pd.Timedelta(days=365))]
        if len(fut) > 100:
            rets.append(float(fut.iloc[-1] / CAL["gld"].loc[d] - 1))
    if rets:
        print(f"    回落≥{X:.0%} 触发 {len(keep):>3d} 次，买后 1 年收益：中位 {np.median(rets):+.1%}  "
              f"最差 {min(rets):+.1%}  胜率 {sum(1 for x in rets if x>0)/len(rets):.0%}")

print()
print("=" * 104)
print("【指标3】美联储降息 —— 「黄金重启上涨」")
print("=" * 104)
print("  视频说法：什么时候美联储开会讨论降息，什么时候黄金重启上涨通道")
print()
# 找「首次降息」事件：Fed 从持平/上行转为下降
fd = FED.sort_index()
chg = fd.diff()
cuts = []
prev_dir = 0
for i in range(1, len(fd)):
    dv = chg.iloc[i]
    if pd.isna(dv):
        continue
    if dv < 0 and prev_dir >= 0:
        cuts.append(fd.index[i])
        prev_dir = -1
    elif dv > 0:
        prev_dir = 1
print(f"  识别到美联储「转向降息」事件 {len(cuts)} 次（1982-2025）")
print(f"  {'首次降息日':>14s}{'利率':>8s}{'之后1年黄金':>14s}{'之后1年标普':>14s}{'与黄金谷底关系':>18s}")
for d in cuts:
    if d < CAL.index.min():
        continue
    g1 = CAL["gld"][(CAL.index > d) & (CAL.index <= d + pd.Timedelta(days=365))]
    s1 = CAL["spy"][(CAL.index > d) & (CAL.index <= d + pd.Timedelta(days=365))]
    rg = float(g1.iloc[-1] / CAL["gld"].loc[:d].iloc[-1] - 1) if len(g1) > 100 else np.nan
    rs = float(s1.iloc[-1] / CAL["spy"].loc[:d].iloc[-1] - 1) if len(s1) > 100 else np.nan
    # 最近一次黄金谷底
    near = [r_["low_date"] for _, r_ in tr.iterrows()] if len(tr) else []
    if near:
        best = min(near, key=lambda x: abs((x - d).days))
        rel = f"{(d - best).days:+d}天（谷底{'之后' if d>best else '之前'}）"
    else:
        rel = "-"
    print(f"  {str(d.date()):>14s}{float(fd.loc[d]):>7.2f}%{rg:>13.1%}{rs:>14.1%}{rel:>18s}")
