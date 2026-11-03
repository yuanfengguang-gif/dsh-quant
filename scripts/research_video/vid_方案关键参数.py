# -*- coding: utf-8 -*-
"""verify_plan_params.py - 验证方案的两个关键参数

A. 分档买入档位：在什么回撤深度买多少，比"一次性在S5买"或"立即定投"更好？
B. 卫星仓阈值重锚：现行 2.5%/4.0% 已失效 8.75 年，新阈值该定在哪？
"""
import sys, sqlite3
from pathlib import Path
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant")
DB = BASE / "data" / "cache" / "dividend_research.db"
CACHE = BASE / "data" / "cache" / "crisis"


def q(sql):
    c = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    d = pd.read_sql_query(sql, c); c.close(); return d


def me(s):
    x = s.resample("ME").last().dropna()
    x.index = x.index.to_period("M").to_timestamp("M"); return x


def li(code, col="close"):
    d = q(f"SELECT date,{col} FROM idx_daily WHERE code='{code}' ORDER BY date")
    d["date"] = pd.to_datetime(d["date"])
    return d.set_index("date")[col].astype(float)


TR = me(li("H20269"))                      # 红利低波全收益
HS = me(li("000300"))                      # 沪深300
DY = me(li("H30269", "close"))             # 占位，下面用 div_yield
dy = q("SELECT date,dy_ttm FROM div_yield WHERE code='H30269' ORDER BY date")
dy["date"] = pd.to_datetime(dy["date"]); DY = me(dy.set_index("date")["dy_ttm"].astype(float))
b = q("SELECT date,value FROM macro WHERE key='cn10y' ORDER BY date")
b["date"] = pd.to_datetime(b["date"]); B10 = me(b.set_index("date")["value"].astype(float))

df = pd.DataFrame({"tr": TR, "hs": HS, "dy": DY, "b10": B10}).dropna(subset=["tr", "hs"])
df["spread"] = (df["dy"] * 100 - df["b10"].reindex(df.index).ffill())
df["dd_hs"] = df["hs"] / df["hs"].cummax() - 1

print("=" * 104)
print("【A. 分档买入：不同回撤档位买多少，哪个方案最好】")
print("=" * 104)
print("  设定：起点持有现金，按沪深300 从历史高点的回撤深度分档买入红利低波全收益，")
print("        持有 36 个月后评估。比较四种方案的终值/浮亏。")


def run_plan(start_i, H, plan):
    """plan: [(回撤阈值, 累计应投入比例)]，按回撤深度触发，每档只买一次"""
    if start_i + H >= len(df):
        return None
    tr = df["tr"].values
    dd = df["dd_hs"].values
    cash = 1.0          # 期初 100% 现金
    shares = 0.0
    bought = 0.0        # 已投入比例（相对总资金）
    trig = [False] * len(plan)
    peak = 1.0
    mdd = 0.0
    for step in range(1, H + 1):
        t = start_i + step
        for k, (thresh, cum_frac) in enumerate(plan):
            if (not trig[k]) and dd[t] <= thresh:
                need = cum_frac - bought
                if need > 0:
                    mv = min(cash, need)
                    shares += mv / tr[t]
                    cash -= mv
                    bought += mv
                trig[k] = True
        val = cash + shares * tr[t]
        peak = max(peak, val)
        mdd = min(mdd, val / peak - 1)
    final = cash + shares * tr[start_i + H]
    return final, mdd, bought


PLANS = {
    "立即全额买（基准）": [(0.0, 1.0)],
    "S3起一次买": [(-0.10, 1.0)],
    "S4起一次买（≤-20%）": [(-0.20, 1.0)],
    "三档：-10%买30%、-20%再40%、-30%再30%": [(-0.10, 0.30), (-0.20, 0.70), (-0.30, 1.00)],
    "两档：-15%买50%、-25%再50%": [(-0.15, 0.50), (-0.25, 1.00)],
    "四档：-5/10/20/30 各25%": [(-0.05, 0.25), (-0.10, 0.50), (-0.20, 0.75), (-0.30, 1.00)],
}

for H in (36, 60):
    print(f"\n  ── 持有 {H} 个月 ──")
    print(f"  {'方案':<42s}{'中位终值':>10s}{'均值':>8s}{'最差浮亏5%':>12s}{'平均投入':>10s}")
    for name, plan in PLANS.items():
        vals, mdds, fills = [], [], []
        for i in range(len(df)):
            if df.index[i] < pd.Timestamp("2006-01-01") or i + H >= len(df):
                continue
            r = run_plan(i, H, plan)
            if r is None:
                continue
            vals.append(r[0]); mdds.append(r[1]); fills.append(r[2])
        if not vals:
            continue
        a = np.array(vals)
        print(f"  {name:<42s}{np.median(a):>10.2f}{np.mean(a):>8.2f}"
              f"{np.percentile(np.array(mdds), 5):>12.1%}{np.mean(fills):>10.0%}")

print()
print("=" * 104)
print("【B. 卫星仓阈值重锚：30% 仓位按估值调仓，阈值定在哪】")
print("=" * 104)
print("  规则：股债利差 ≥ X 买回满仓 / < Y 卖出卫星仓；其余时间不动。")
print("  评估：2018 起（国债数据起点）红利低波全收益的 Calmar。")


def sat_backtest(d, buy_pp, sell_pp):
    ret = d["tr"].pct_change().fillna(0.0)
    sp = d["spread"]
    # 卫星仓 30%：持有=1.0，卖出=0.7（只剩底仓70%）
    pos = pd.Series(1.0, index=d.index)
    cur = 1.0
    for dt in d.index:
        v = sp.get(dt, np.nan)
        if pd.notna(v):
            if v >= buy_pp:
                cur = 1.0
            elif v < sell_pp:
                cur = 0.7
        pos[dt] = cur
    nav = (1 + pos.shift(1).fillna(1.0) * ret).cumprod()
    yrs = (d.index[-1] - d.index[0]).days / 365.25
    ann = nav.iloc[-1] ** (1 / yrs) - 1
    mdd = float((nav / nav.cummax() - 1).min())
    return ann, mdd, ann / abs(mdd), float(pos.mean())


d = df[df.index >= "2018-01-01"].copy()
bh = (1 + d["tr"].pct_change().fillna(0)).cumprod()
yrs = (d.index[-1] - d.index[0]).days / 365.25
bann = bh.iloc[-1] ** (1 / yrs) - 1
bmdd = float((bh / bh.cummax() - 1).min())
print(f"  基准（一直满仓）：年化 {bann:.2%}  回撤 {bmdd:.1%}  Calmar {bann/abs(bmdd):.3f}")
print(f"\n  {'买回阈值':<10s}" + "".join(f"{s:>12.1f}" for s in (0.5, 1.0, 1.5, 2.0)) + "   （卖出阈值，pp）")
for buy in (2.0, 2.5, 3.0, 3.5):
    line = f"  {buy:<10.1f}"
    for sell in (0.5, 1.0, 1.5, 2.0):
        if sell >= buy:
            line += f"{'—':>12s}"
            continue
        a, m, c, expo = sat_backtest(d, buy, sell)
        line += f"{c:>12.3f}"
    print(line)

print(f"\n  当前股债利差 = {df['spread'].dropna().iloc[-1]:.2f}pp，"
      f"历史分位 {float((df['spread'].dropna() < df['spread'].dropna().iloc[-1]).mean()):.0%}")
print(f"  单看阈值是否会被触发（2018 起）：")
sp = df["spread"].dropna()
for th in (1.0, 1.5, 2.0, 2.5, 3.0):
    print(f"    利差 < {th}pp 的月份：{int((sp < th).sum())}/{len(sp)} = {float((sp<th).mean()):.0%}")
