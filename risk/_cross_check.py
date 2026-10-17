# -*- coding: utf-8 -*-
"""risk/_cross_check.py —— 通达信(未复权) vs 本地(qfq) 交叉验证"""
import sqlite3
import sys

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
C = r"D:\Programs\DSH Projects\DSH Quant\data\cache"

codes = ["000001.SZ", "600519.SH", "000002.SZ", "600036.SH"]
start = "2010-01-01"

con_l = sqlite3.connect(C + r"\bars.db")
con_t = sqlite3.connect(C + r"\bars_tdx.db")

q = f"SELECT code,date,open,close,volume,amount,turn,pct_chg,preclose FROM daily_bar WHERE date>=? AND code IN ({','.join('?'*len(codes))})"
loc = pd.read_sql(q, con_l, params=[start] + codes)
tdx = pd.read_sql(q, con_t, params=[start] + codes)
con_l.close(); con_t.close()

print(f"本地 {len(loc):,} 行 | 通达信 {len(tdx):,} 行")
m = loc.merge(tdx, on=["code", "date"], suffixes=("_loc", "_tdx"))
print(f"交集 {len(m):,} 行\n")
if not len(m):
    print("无交集")
    sys.exit()

print(f"{'字段':<10}{'本地均值':>16}{'通达信均值':>16}{'相对偏差':>12}{'比值std':>12}")
print("-" * 68)
for c in ["open", "close", "volume", "amount", "turn", "pct_chg"]:
    a, b = m[f"{c}_loc"], m[f"{c}_tdx"]
    ok = a.notna() & b.notna() & (a != 0)
    if ok.sum() == 0:
        continue
    rel = ((b[ok] - a[ok]) / a[ok] * 100)
    ratio = b[ok] / a[ok]
    print(f"{c:<10}{a[ok].mean():>16.4f}{b[ok].mean():>16.4f}{rel.mean():>11.4f}%{ratio.std():>12.6f}")

print("\n=== 逐股比值（close_tdx / close_loc）===")
for code in codes:
    sub = m[m["code"] == code]
    if not len(sub):
        print(f"  {code}: 无交集")
        continue
    r = (sub["close_tdx"] / sub["close_loc"]).replace([np.inf, -np.inf], np.nan).dropna()
    print(f"  {code}: n={len(sub):>5}  比值 mean={r.mean():.6f} std={r.std():.6f} "
          f"min={r.min():.6f} max={r.max():.6f}")
print("\n判读：比值恒定→复权基准差异(正常)；随机波动→数据源差异；单位问题→比值=100/1000/0.01")
