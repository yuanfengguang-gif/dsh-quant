# -*- coding: utf-8 -*-
"""verify_holdings_div2.py - 用「累计分红/份」重算真实分红率（避开日增长率的脏数据）

方法：
  累计分红/份 = 累计净值(末) − 单位净值(末)   （两者起点相同，故差值 = 累计每份分红）
  年均现金分红率 = 累计分红/份 ÷ 平均单位净值 ÷ 年数
另做三项交叉校验：
  ① 检查累计净值是否有可疑跳变
  ② 检查日增长率是否有异常值（|g|>8% 视为脏）
  ③ 用「累计净值涨幅 − 单位净值涨幅」直接算分红贡献
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CACHE = Path(r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant\data\cache\crisis")

for code, name, weight in (("515100", "红利低波100ETF景顺", 40),
                           ("515450", "红利低波50ETF南方", 35)):
    f = CACHE / f"etf_{code}_nav.csv"
    d = pd.read_csv(f)
    d.columns = [str(c) for c in d.columns]
    d["净值日期"] = pd.to_datetime(d["净值日期"])
    d = d.sort_values("净值日期").reset_index(drop=True)
    nav = d["单位净值"].astype(float)
    cum = d["累计净值"].astype(float)
    dates = d["净值日期"]
    g = pd.to_numeric(d["日增长率"], errors="coerce")

    print("=" * 100)
    print(f"【{code} {name}（配比 {weight}%）】")
    print("=" * 100)
    yrs = (dates.iloc[-1] - dates.iloc[0]).days / 365.25
    print(f"  区间 {dates.iloc[0].date()} ~ {dates.iloc[-1].date()}（{yrs:.2f} 年，{len(d)} 交易日）")
    print(f"  单位净值 {nav.iloc[0]:.4f} → {nav.iloc[-1]:.4f}")
    print(f"  累计净值 {cum.iloc[0]:.4f} → {cum.iloc[-1]:.4f}")

    # ① 累计分红/份
    total_div = float(cum.iloc[-1] - nav.iloc[-1])
    avg_nav = float(nav.mean())
    ann_yield = total_div / avg_nav / yrs
    print(f"\n  ── 口径 A：累计分红/份 ──")
    print(f"     累计每份分红 = {cum.iloc[-1]:.4f} − {nav.iloc[-1]:.4f} = **{total_div:.4f} 元/份**")
    print(f"     平均单位净值 = {avg_nav:.4f}")
    print(f"     年均现金分红率 = {total_div:.4f} ÷ {avg_nav:.4f} ÷ {yrs:.2f} = **{ann_yield:.2%}**")

    # ② 异常值检查
    bad = int((g.abs() > 8).sum())
    print(f"\n  ── 数据质量检查 ──")
    print(f"     日增长率 |g|>8% 的异常天数：{bad} / {len(g)}")
    if bad:
        print(f"       异常样例：{g[g.abs()>8].head(5).to_dict()}")
    dcum = cum.diff()
    neg = int((dcum < -1e-6).sum())
    print(f"     累计净值出现下降的天数：{neg}（应为 0）")

    # ③ 分红贡献交叉校验（用累计净值涨幅 vs 单位净值涨幅）
    nav_ret = float(nav.iloc[-1] / nav.iloc[0] - 1)
    cum_ret = float(cum.iloc[-1] / cum.iloc[0] - 1)
    print(f"\n  ── 口径 B：累计净值 vs 单位净值涨幅 ──")
    print(f"     单位净值涨幅 {nav_ret:+.2%}")
    print(f"     累计净值涨幅 {cum_ret:+.2%}")
    print(f"     差（分红贡献的累计涨幅） {cum_ret - nav_ret:+.2%}")
    print(f"     折年化 {((1+cum_ret)**(1/yrs) - (1+nav_ret)**(1/yrs)):.2%}")

    # ④ 按年：累计净值涨幅 − 单位净值涨幅
    print(f"\n  ── 逐年分红贡献（口径 B）──")
    df = pd.DataFrame({"date": dates, "nav": nav, "cum": cum})
    df["year"] = df["date"].dt.year
    print(f"     {'年份':<8s}{'单位净值涨幅':>13s}{'累计净值涨幅':>13s}{'分红贡献':>11s}")
    yearly = []
    for y, sub in df.groupby("year"):
        if len(sub) < 100:
            continue
        nr = float(sub["nav"].iloc[-1] / sub["nav"].iloc[0] - 1)
        cr = float(sub["cum"].iloc[-1] / sub["cum"].iloc[0] - 1)
        print(f"     {y:<8d}{nr:>12.2%}{cr:>13.2%}{cr-nr:>11.2%}")
        yearly.append(cr - nr)
    if yearly:
        print(f"     年均（简单平均）{np.mean(yearly):.2%}")

    print()

print("=" * 100)
print("【组合层面：按 40:35 加权的现金分红率】")
print("=" * 100)
res = {}
for code in ("515100", "515450"):
    d = pd.read_csv(CACHE / f"etf_{code}_nav.csv")
    d.columns = [str(c) for c in d.columns]
    d["净值日期"] = pd.to_datetime(d["净值日期"]); d = d.sort_values("净值日期")
    nav = d["单位净值"].astype(float); cum = d["累计净值"].astype(float)
    yrs = (d["净值日期"].iloc[-1] - d["净值日期"].iloc[0]).days / 365.25
    res[code] = float(cum.iloc[-1] - nav.iloc[-1]) / float(nav.mean()) / yrs
w = {"515100": 40, "515450": 35}
blend = sum(res[c] * w[c] for c in res) / sum(w.values())
print(f"  515100 年化现金分红率 {res['515100']:.2%}  ×  {w['515100']}%")
print(f"  515450 年化现金分红率 {res['515450']:.2%}  ×  {w['515450']}%")
print(f"  → 组合加权 **{blend:.2%}**")
print(f"\n  你的方案假设 5.6% → 实际 {'高于' if blend > 0.056 else '低于'}假设 {abs(blend-0.056)*100:.1f}pp")
print(f"  100 万按实际率算：年 {1_000_000*blend:,.0f} 元 / 月 {1_000_000*blend/12:,.0f} 元")
print(f"  覆盖 5,000 元开支：{1_000_000*blend/12/5000:.0%}")
