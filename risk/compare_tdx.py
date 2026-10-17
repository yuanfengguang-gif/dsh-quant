# -*- coding: utf-8 -*-
"""risk/compare_tdx.py —— 通达信 vs 本地 bars.db 数据一致性对比

用途：导入通达信数据后，验证其与本地数据的一致性，定位差异来源（复权基准/单位/口径）。
用法：python risk/compare_tdx.py [--codes 000001.SZ,600519.SH] [--start 2020-01-01]
"""
import argparse
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = Path(__file__).resolve().parent.parent
LOCAL = BASE / "data" / "cache" / "bars.db"
TDX = BASE / "data" / "cache" / "bars_tdx.db"


def load(db, table, codes, start, cols):
    con = sqlite3.connect(str(db))
    has = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
    use = [c for c in cols if c in has]
    q = (f"SELECT code, date, {', '.join(use)} FROM {table} "
         f"WHERE date >= ? AND code IN ({','.join('?' * len(codes))})")
    df = pd.read_sql(q, con, params=[start] + codes)
    con.close()
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", default="000001.SZ,600519.SH,300602.SZ")
    ap.add_argument("--start", default="2010-01-01")
    ap.add_argument("--local-table", default="daily_bar")
    ap.add_argument("--tdx-table", default="daily_bar")
    args = ap.parse_args()
    codes = [c.strip() for c in args.codes.split(",")]

    cols = ["open", "high", "low", "close", "preclose", "volume", "amount", "turn", "pct_chg"]
    try:
        loc = load(LOCAL, args.local_table, codes, args.start, cols)
    except Exception as e:
        print(f"❌ 读取本地库失败: {e}")
        return
    try:
        tdx = load(TDX, args.tdx_table, codes, args.start, cols)
    except Exception as e:
        print(f"❌ 读取通达信库失败（请先导入）: {e}")
        return

    print(f"本地 {len(loc):,} 行 | 通达信 {len(tdx):,} 行 | 股票 {codes}")
    m = loc.merge(tdx, on=["code", "date"], suffixes=("_loc", "_tdx"))
    print(f"日期交集：{len(m):,} 行\n")
    if not len(m):
        print("无交集（检查日期范围/股票代码格式）")
        return

    print(f"{'字段':<10}{'平均偏差':>14}{'相对偏差':>12}{'比值std':>12}{'结论':>16}")
    print("-" * 66)
    for c in ["open", "high", "low", "close", "volume", "amount", "turn", "pct_chg"]:
        a, b = m[f"{c}_loc"], m[f"{c}_tdx"]
        both = a.notna() & b.notna()
        if both.sum() == 0:
            continue
        diff = (b[both] - a[both])
        rel = (diff / a[both].replace(0, np.nan) * 100)
        ratio = (b[both] / a[both].replace(0, np.nan))
        rstd = ratio.std()
        if abs(rel.mean()) < 0.5 and rstd < 0.01:
            verdict = "✅ 一致(比例差)"
        elif abs(rel.mean()) < 5:
            verdict = "🟡 轻微差异"
        else:
            verdict = "❌ 差异大"
        print(f"{c:<10}{diff.mean():>14.4f}{rel.mean():>11.4f}%{rstd:>12.6f}{verdict:>18}")

    print("\n=== 逐股比值（close_tdx / close_loc）===")
    for code in codes:
        sub = m[m["code"] == code]
        if len(sub) == 0:
            print(f"  {code}: 无交集")
            continue
        ratio = (sub["close_tdx"] / sub["close_loc"].replace(0, np.nan)).dropna()
        print(f"  {code}: n={len(sub):>5}  比值 mean={ratio.mean():.6f} "
              f"min={ratio.min():.6f} max={ratio.max():.6f}")
    print("\n判读：比值恒定(≈1) → 数据一致；比值系统性偏离 → 复权基准差异；比值随机波动 → 数据源差异")


if __name__ == "__main__":
    main()
