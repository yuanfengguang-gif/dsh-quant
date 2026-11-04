# -*- coding: utf-8 -*-
"""verify_v11_combined.py - 把视频的 3 个指标组合成可执行规则，测「卖金买红利」

用户的真实场景：手里全是黄金，要换成红利 ETF 获取现金流。
所以要问：这三个指标能不能告诉我「什么时候换」？

视频的三阶段对应关系：
  阶段1 杀流动性：10Y↑ + 美元↑ → 黄金和股票都在跌 → 【警告：别换】
  阶段2 杀基本面：还在跌 → 【等待】
  阶段3 主权信用重估：金银比转头向下 + 美联储降息 → 抛售出清 → 【行动：换】

全部规则只用当天可得的量。
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant")
CACHE = BASE / "data" / "cache" / "crisis"
import sqlite3
DB = BASE / "data" / "cache" / "dividend_research.db"


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


def li(code):
    c = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    d = pd.read_sql_query("SELECT date,close FROM idx_daily WHERE code=? ORDER BY date", c, params=(code,))
    c.close()
    d["date"] = pd.to_datetime(d["date"])
    return d.set_index("date")["close"].astype(float)


GLD = usc("GLD"); SLV = usc("SLV"); UUP = usc("UUP")
SPY = usc("SPY"); DXY = emidx("em_global_udi.csv")
DIVTR = li("H20269")     # 红利低波全收益
HS300 = emidx("em_global_hs300.csv")

b = pd.read_csv(CACHE / "us_10y_东财.csv")
b.columns = [str(c) for c in b.columns]
b["日期"] = pd.to_datetime(b["日期"])
c10 = [c for c in b.columns if "美国国债收益率10年" in c][0]
B10 = b.set_index("日期")[c10].astype(float).dropna()

r = pd.read_csv(CACHE / "macro_bank_usa_interest_rate.csv")
r.columns = [str(c) for c in r.columns]
r["日期"] = pd.to_datetime(r["日期"]); r = r.sort_values("日期")
fv = pd.to_numeric(r["今值"], errors="coerce").fillna(pd.to_numeric(r["前值"], errors="coerce"))
FED = pd.Series(fv.values, index=pd.DatetimeIndex(r["日期"].values)).dropna()

gsr_etf = (GLD / SLV).dropna()
try:
    gc = pd.read_csv(CACHE / "px_gold_gc.csv"); gc["date"] = pd.to_datetime(gc["date"])
    si = pd.read_csv(CACHE / "px_silver_si.csv"); si["date"] = pd.to_datetime(si["date"])
    tg = (gc.set_index("date")["close"].astype(float) / si.set_index("date")["close"].astype(float)).dropna()
    ov = gsr_etf.index.intersection(tg.index)
    GSR = gsr_etf * float((tg.reindex(ov) / gsr_etf.reindex(ov)).median())
except Exception:
    GSR = gsr_etf

CAL = pd.DataFrame({"gld": GLD, "divtr": DIVTR, "spy": SPY, "uup": UUP,
                    "dxy": DXY, "b10": B10, "gsr": GSR})
CAL = CAL.dropna(subset=["gld", "divtr"])
for c in ("uup", "dxy", "b10", "gsr"):
    CAL[c] = CAL[c].ffill()
CAL["fed"] = FED.reindex(CAL.index).ffill()

# ── 三个因果指标
CAL["b10_up"] = CAL["b10"] > CAL["b10"].shift(60)          # 10Y 高于 60 天前
CAL["uup_up"] = CAL["uup"] > CAL["uup"].shift(60)          # 美元高于 60 天前
CAL["squeeze"] = CAL["b10_up"] & CAL["uup_up"]             # 缺钱期
CAL["gsr_max250"] = CAL["gsr"].rolling(250, min_periods=120).max()
CAL["gsr_fall"] = CAL["gsr"] / CAL["gsr_max250"] - 1       # 金银比距滚动高点
CAL["fed_chg"] = CAL["fed"].diff(20)                       # 20 个观测点（约一年）的利率变化

print("=" * 100)
print("【当前三个指标读数】")
print("=" * 100)
last = CAL.iloc[-1]
print(f"  10Y 美债       {last['b10']:.2f}%   {'↑在升' if last['b10_up'] else '↓在降'}")
print(f"  美元指数       {last['dxy']:.1f}    {'↑在升' if last['uup_up'] else '↓在降'}")
print(f"  → 缺钱期(阶段1) {'是 ⚠️' if last['squeeze'] else '否'}")
print(f"  金银比         {last['gsr']:.1f}   距250日高点 {last['gsr_fall']:+.1%}")
print(f"  美联储利率     {last['fed']:.2f}%  20期变化 {last['fed_chg']:+.2f}pp")
print(f"  数据截止       {CAL.index[-1].date()}")

print()
print("=" * 100)
print("【测试 1】视频指标1：「缺钱期」回避，之后持有 —— 纯黄金择时")
print("=" * 100)
for cost in (0.0, 0.001):
    pos = (~CAL["squeeze"]).astype(float)
    ret = CAL["gld"].pct_change().fillna(0)
    strat = (1 + pos.shift(1).fillna(1) * ret).cumprod()
    bh = (1 + ret).cumprod()
    yrs = (CAL.index[-1] - CAL.index[0]).days / 365.25
    a_s = strat.iloc[-1] ** (1 / yrs) - 1
    a_b = bh.iloc[-1] ** (1 / yrs) - 1
    m_s = float((strat / strat.cummax() - 1).min())
    m_b = float((bh / bh.cummax() - 1).min())
    print(f"  {'（含成本时略）' if cost else '不计成本'}")
    print(f"    买入持有黄金  年化 {a_b:>7.2%}  最大回撤 {m_b:>7.1%}  Calmar {a_b/abs(m_b):.3f}")
    print(f"    缺钱期空仓    年化 {a_s:>7.2%}  最大回撤 {m_s:>7.1%}  Calmar {a_s/abs(m_s):.3f}")
    print(f"    平均持仓 {float(pos.mean()):.0%}")

print()
print("=" * 100)
print("【测试 2】视频指标2：金银比从高点回落 X% 时「卖金买红利」")
print("=" * 100)
print("  这是你的真实场景：手里全是黄金，要换成红利 ETF")
print(f"  {'触发阈值':<12s}{'次数':>6s}{'1年:换仓/持金':>20s}{'2年:换仓/持金':>20s}{'3年:换仓/持金':>20s}")

for X in (0.05, 0.08, 0.12):
    cal = (CAL["gsr_fall"] <= -X) & (CAL["gsr_fall"].shift(1) > -X)
    idx = CAL.index[cal.fillna(False)]
    keep = []
    for d in idx:
        if not keep or (d - keep[-1]).days > 180:
            keep.append(d)
    res = {1: [], 2: [], 3: []}
    for d in keep:
        for H in (1, 2, 3):
            end = d + pd.Timedelta(days=365 * H)
            if end > CAL.index[-1]:
                continue
            g_ret = float(CAL["gld"].asof(end) / CAL["gld"].asof(d) - 1)
            v_ret = float(CAL["divtr"].asof(end) / CAL["divtr"].asof(d) - 1)
            res[H].append((v_ret, g_ret, v_ret - g_ret))
    if not res[1]:
        continue
    line = f"  {X:<12.0%}{len(keep):>6d}"
    for H in (1, 2, 3):
        if res[H]:
            ex = np.median([x[2] for x in res[H]])
            win = sum(1 for x in res[H] if x[2] > 0) / len(res[H])
            line += f"{ex:>+10.1%}({win:.0%})".rjust(20)
        else:
            line += "—".rjust(20)
    print(line)
print("  括号内为胜率；数值 = 换仓收益 − 持金收益 的中位差")

print()
print("=" * 100)
print("【测试 3】三指标合成：同时满足才换仓（最严格）")
print("=" * 100)
print("  条件：① 金银比从高点回落≥8%  ② 不在缺钱期  ③ 美联储利率已转向下行或持平")
CAL["fed_down"] = CAL["fed_chg"] <= 0
cond = (CAL["gsr_fall"] <= -0.08) & (~CAL["squeeze"]) & CAL["fed_down"]
trig = cond & (~cond.shift(1).fillna(False))
idx = CAL.index[trig.fillna(False)]
keep = []
for d in idx:
    if not keep or (d - keep[-1]).days > 180:
        keep.append(d)
print(f"  触发 {len(keep)} 次：")
for d in keep:
    print(f"    {d.date()}  金银比距高点 {CAL['gsr_fall'].loc[d]:+.1%}  "
          f"10Y {CAL['b10'].loc[d]:.2f}%  美元 {CAL['dxy'].loc[d]:.1f}  美联储 {CAL['fed'].loc[d]:.2f}%")
if keep:
    for H in (1, 2, 3):
        ex, win, n = [], [], 0
        for d in keep:
            end = d + pd.Timedelta(days=365 * H)
            if end > CAL.index[-1]:
                continue
            g_ret = float(CAL["gld"].asof(end) / CAL["gld"].asof(d) - 1)
            v_ret = float(CAL["divtr"].asof(end) / CAL["divtr"].asof(d) - 1)
            ex.append(v_ret - g_ret); win.append(v_ret > g_ret); n += 1
        if ex:
            print(f"    {H} 年：换仓−持金 中位 {np.median(ex):+.1%}  胜率 {sum(win)/n:.0%}  （{n} 个样本）")

print()
print("=" * 100)
print("【测试 4】换仓后绝对收益（不比较，只看赚不赚）")
print("=" * 100)
for X in (0.08, 0.12):
    cal = (CAL["gsr_fall"] <= -X) & (CAL["gsr_fall"].shift(1) > -X)
    idx = CAL.index[cal.fillna(False)]
    keep = []
    for d in idx:
        if not keep or (d - keep[-1]).days > 180:
            keep.append(d)
    print(f"\n  金银比回落≥{X:.0%}：")
    for H in (1, 2, 3):
        vs, gs = [], []
        for d in keep:
            end = d + pd.Timedelta(days=365 * H)
            if end > CAL.index[-1]:
                continue
            vs.append(float(CAL["divtr"].asof(end) / CAL["divtr"].asof(d) - 1))
            gs.append(float(CAL["gld"].asof(end) / CAL["gld"].asof(d) - 1))
        if vs:
            print(f"    持 {H} 年：红利ETF中位 {np.median(vs):+.1%}（最差 {min(vs):+.1%}）  "
                  f"黄金中位 {np.median(gs):+.1%}（最差 {min(gs):+.1%}）  正收益占比 {sum(1 for x in vs if x>0)/len(vs):.0%}")
