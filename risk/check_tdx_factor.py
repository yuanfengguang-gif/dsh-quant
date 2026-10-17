# -*- coding: utf-8 -*-
"""risk/check_tdx_factor.py —— 通达信复权因子正确性深查"""
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

A = Path(r"C:\Users\Administrator\.dsh\attachments\v1\files")
QFQ = A / "e0" / "e037e9440a15bc75ab808810025e860191a6ef9498d40a521f25739e35316807" / "前复权因子样本.csv"
HFQ = A / "61" / "6184d5507cd4dfd6b8dc56f99549b176975515e8d0fe0ccae93e86ef27a10112" / "后复权因子样本.csv"

frames = {}
for name, path in [("前复权", QFQ), ("后复权", HFQ)]:
    df = pd.read_csv(path, encoding="utf-8-sig")
    df.columns = ["code", "date", "factor"]
    df["date"] = pd.to_datetime(df["date"].astype(str), format="%Y%m%d")
    df = df.sort_values("date").reset_index(drop=True)
    frames[name] = df
    d = df["factor"].diff()
    inc = (d > 1e-10).mean() * 100
    flat = (d.abs() <= 1e-10).mean() * 100
    dec = (d < -1e-10).mean() * 100
    print(f"\n=== {name}因子（{df['code'].iloc[0]}）===")
    print(f"  行数 {len(df)}, 日期 {df['date'].min().date()} ~ {df['date'].max().date()}")
    print(f"  因子范围 {df['factor'].min():.8f} ~ {df['factor'].max():.8f}")
    print(f"  递增 {inc:.2f}% | 持平 {flat:.2f}% | 递减 {dec:.2f}%")
    print(f"  diff: min={d.min():.8f} max={d.max():.8f}")
    if dec > 1:
        neg_idx = df.index[d < -1e-10]
        print(f"  递减示例（前5处）：")
        for i in neg_idx[:5]:
            print(f"    {df.loc[i-1,'date'].date()} {df.loc[i-1,'factor']:.10f} → "
                  f"{df.loc[i,'date'].date()} {df.loc[i,'factor']:.10f}  (Δ={df.loc[i,'factor']-df.loc[i-1,'factor']:.10f})")

# 两者关系：后复权因子 / 前复权因子 应恒定（= 最新日后复权因子）
q = frames["前复权"].set_index("date")["factor"]
h = frames["后复权"].set_index("date")["factor"]
common = q.index.intersection(h.index)
if len(common):
    ratio = (h.reindex(common) / q.reindex(common))
    print(f"\n=== 前复权 vs 后复权 关系（共同日期 {len(common)} 天）===")
    print(f"  hfq/qfq 比值: mean={ratio.mean():.8f} std={ratio.std():.8f} "
          f"min={ratio.min():.8f} max={ratio.max():.8f}")
    print(f"  → 若 std≈0，说明两因子严格一致（仅基准不同），复权逻辑正确")
    print(f"  抽样：")
    for i in [0, len(common)//4, len(common)//2, -1]:
        dt = common[i]
        print(f"    {dt.date()}: qfq={q[dt]:.8f} hfq={h[dt]:.8f} ratio={ratio[dt]:.8f}")
