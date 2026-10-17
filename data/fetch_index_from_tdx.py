# -*- coding: utf-8 -*-
"""data/fetch_index_from_tdx.py —— 用通达信补回沪深300指数日线（修回归 + 去 baostock 依赖）

背景：切换到 tdx_qfq 重建主库时，旧库里的 `SH.000300`（baostock 源）没被带过来 →
      新 bars.db 无指数数据 → Regime 择时 / 基准对比 / check_consistency 会缺数据。
本脚本用通达信 `get_market_data('000300.SH', dividend_type='none')` 拉全历史，
按**旧代码 `SH.000300`**（保持兼容，不破坏下游引用）+ `adjust='none'` 写入 bars.db。

用法：python data/fetch_index_from_tdx.py [--dry-run]
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\Administrator\.dsh\skills\tdx-aidata")
sys.path.insert(0, r"C:\Users\Administrator\.dsh\skills\tdx-aidata\lib")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from tdxaidata import tqs

CACHE = Path(__file__).resolve().parent.parent / "data" / "cache"
BARS = CACHE / "bars.db"

# (通达信代码, 写入 bars.db 的代码) —— 索引类
INDEXES = [("000300.SH", "SH.000300")]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    con = sqlite3.connect(str(BARS), timeout=120)
    before = dict(con.execute(
        "SELECT code, COUNT(*) FROM daily_bar WHERE code NOT LIKE '%.SH' "
        "AND code NOT LIKE '%.SZ' AND code NOT LIKE '%.BJ' GROUP BY code").fetchall())
    print(f"补入前：非个股代码 {before or '（无）'}")

    total = 0
    for tdx_code, store_code in INDEXES:
        r = tqs.get_market_data(
            field_list=["Open", "High", "Low", "Close", "Volume", "Amount"],
            stock_list=[tdx_code], period="1d",
            start_time="2005-01-01", end_time="2026-10-16", dividend_type="none")
        df = r.get("Close")
        if df is None or len(df) == 0:
            print(f"  ✘ {tdx_code}: 无数据")
            continue
        cols = {k: r.get(k) for k in ("Open", "High", "Low", "Close", "Volume", "Amount")}
        rows = []
        prev = None
        for ts in df.index:
            d = str(ts)[:10]
            def g(k):
                v = cols[k]
                try:
                    return float(v.loc[ts].iloc[0]) if hasattr(v.loc[ts], "iloc") else float(v.loc[ts])
                except Exception:
                    return None
            c = g("Close")
            if c is None:
                continue
            pct = (c / prev - 1) if prev else None
            rows.append((store_code, d, g("Open"), g("High"), g("Low"), c, prev,
                         g("Volume"), g("Amount"), None, pct, 0, "none", "tdx"))
            prev = c
        print(f"  {tdx_code} → {store_code}: {len(rows):,} 行 "
              f"({rows[0][1]} ~ {rows[-1][1]})")
        if not args.dry_run and rows:
            with con:
                con.executemany(
                    "INSERT OR REPLACE INTO daily_bar VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        total += len(rows)

    after = dict(con.execute(
        "SELECT code, COUNT(*) FROM daily_bar WHERE code NOT LIKE '%.SH' "
        "AND code NOT LIKE '%.SZ' AND code NOT LIKE '%.BJ' GROUP BY code").fetchall())
    print(f"\n补入后：非个股代码 {after or '（无）'}")
    if not args.dry_run and total:
        print("\n抽验（前 3 行 + 末 3 行）:")
        for row in con.execute(
                "SELECT date, open, high, low, close, pct_chg, source FROM daily_bar "
                "WHERE code='SH.000300' ORDER BY date LIMIT 3"):
            print("  ", row)
        for row in con.execute(
                "SELECT date, close, pct_chg FROM daily_bar WHERE code='SH.000300' "
                "ORDER BY date DESC LIMIT 3"):
            print("  ", row)
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
