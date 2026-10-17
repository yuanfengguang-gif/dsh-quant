# -*- coding: utf-8 -*-
"""risk/check_tdx_factor2.py —— 复权因子日间波动性质（近期数据）"""
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

A = Path(r"C:\Users\Administrator\.dsh\attachments\v1\files")
QFQ = A / "e0" / "e037e9440a15bc75ab808810025e860191a6ef9498d40a521f25739e35316807" / "前复权因子样本.csv"
HFQ = A / "61" / "6184d5507cd4dfd6b8dc56f99549b176975515e8d0fe0ccae93e86ef27a10112" / "后复权因子样本.csv"

for name, path in [("前复权", QFQ), ("后复权", HFQ)]:
    df = pd.read_csv(path, encoding="utf-8-sig")
    df.columns = ["code", "date", "factor"]
    df["date"] = pd.to_datetime(df["date"].astype(str), format="%Y%m%d")
    df = df.sort_values("date").reset_index(drop=True)
    df["chg_pct"] = df["factor"].pct_change() * 100

    print(f"\n{'='*66}\n{name}因子（{df['code'].iloc[0]}）近期序列抽样\n{'='*66}")
    recent = df[df["date"] >= "2024-01-01"]
    print(f"2024 起 {len(recent)} 行，日间变动幅度: "
          f"median={recent['chg_pct'].abs().median():.6f}%  "
          f"p90={recent['chg_pct'].abs().quantile(0.9):.6f}%  "
          f"max={recent['chg_pct'].abs().max():.6f}%")
    # 逐月抽样（每月第一个交易日）
    samp = recent.groupby(recent["date"].dt.to_period("M")).first().head(14)
    print("  月度抽样:")
    for _, r in samp.iterrows():
        print(f"    {r['date'].date()}  factor={r['factor']:.10f}  Δ={r['chg_pct']:+.6f}%")

    # 是否存在「长时间恒定段」（标准复权因子的特征）
    runs, cur, prev = [], 1, None
    for v in df["factor"]:
        if prev is not None and abs(v - prev) < 1e-12:
            cur += 1
        else:
            if cur > 1:
                runs.append(cur)
            cur = 1
        prev = v
    if runs:
        print(f"  恒定段: 共 {len(runs)} 段, 最长 {max(runs)} 天, 平均 {sum(runs)/len(runs):.1f} 天")
    else:
        print("  恒定段: 无（每个交易日因子都在变 → 非标准分红送股因子）")
