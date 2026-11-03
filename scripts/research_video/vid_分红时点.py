# -*- coding: utf-8 -*-
"""verify_div_timing.py - 查两只 ETF 的分红事件时点（决定现金流是否平滑）

用户方案假设「每月 4,667 元」现金流。
若 ETF 是年度一次性大额分红，则月度现金流不成立，必须提前规划。
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CACHE = Path(r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant\data\cache\crisis")

for code, name in (("515100", "红利低波100ETF景顺"), ("515450", "红利低波50ETF南方")):
    d = pd.read_csv(CACHE / f"etf_{code}_nav.csv")
    d.columns = [str(c) for c in d.columns]
    d["净值日期"] = pd.to_datetime(d["净值日期"])
    d = d.sort_values("净值日期").reset_index(drop=True)
    nav = d["单位净值"].astype(float)
    cum = d["累计净值"].astype(float)
    dates = d["净值日期"]

    # 累计分红（累计净值 − 单位净值）的跳变 = 分红事件
    gap = cum - nav
    dgap = gap.diff()
    events = []
    for i in range(1, len(d)):
        if dgap.iloc[i] > 0.002:      # 单日累计分红增加 >0.002 元/份 视为一次分红
            events.append((dates.iloc[i], float(dgap.iloc[i]),
                           float(nav.iloc[i]), float(dgap.iloc[i] / nav.iloc[i])))

    print("=" * 100)
    print(f"【{code} {name}】分红事件（按累计分红跳变识别）")
    print("=" * 100)
    if not events:
        print("  未识别到分红事件")
        continue
    print(f"  {'除息日':<14s}{'每份分红':>10s}{'当日净值':>10s}{'占净值':>9s}")
    for dt, amt, nv, r in events:
        print(f"  {str(dt.date()):<14s}{amt:>10.4f}{nv:>10.4f}{r:>8.2%}")

    df = pd.DataFrame(events, columns=["date", "amt", "nav", "rate"])
    df["year"] = pd.to_datetime(df["date"]).dt.year
    print(f"\n  按年汇总：")
    for y, sub in df.groupby("year"):
        print(f"    {y}: {len(sub)} 次，合计 {sub['amt'].sum():.4f} 元/份"
              f"（占当年净值约 {sub['rate'].sum():.2%}）")
    print(f"\n  分红次数 {len(events)} 次 / 覆盖 {df['year'].nunique()} 个年份")
    months = sorted({pd.Timestamp(x).month for x in df["date"]})
    print(f"  分红发生的月份：{months}")
    print(f"  → {'⚠️ 集中在少数月份，现金流不平滑' if len(months) <= 3 else '分布在多个月份'}")
    print()
