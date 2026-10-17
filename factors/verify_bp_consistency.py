# -*- coding: utf-8 -*-
"""时间对齐的一致性验证：最新交易日 2026-10-12 横截面上 finance版bp vs pbMRQ版bp"""
import sqlite3
import numpy as np
import pandas as pd

DATE = "2026-10-12"

# 1. pbMRQ 版 bp（valuation.db，当日）
con = sqlite3.connect("data/cache/valuation.db")
v = pd.read_sql("SELECT code, date, pbMRQ FROM valuation", con)
con.close()
v["pb"] = pd.to_numeric(v["pbMRQ"], errors="coerce")
v = v[(v["pb"] > 0) & (v["date"] == DATE)]
v["bp_pb"] = 1.0 / v["pb"]

# 2. finance 版 bp（每股净资产/当日收盘价）
con = sqlite3.connect("data/cache/finance.db")
f = pd.read_sql("SELECT code, period, eps, roe FROM finance_report", con)
con.close()
f["roe"] = pd.to_numeric(f["roe"], errors="coerce")
f["eps"] = pd.to_numeric(f["eps"], errors="coerce")
f["bps"] = np.where(f["roe"] > 0, f["eps"] / f["roe"], np.nan)
f = f.dropna(subset=["bps"])
f["eff"] = pd.to_datetime(f["period"]) + pd.Timedelta(days=60)
f = f[f["eff"] <= DATE].sort_values("eff").groupby("code").tail(1)  # 取当日已知的最新一期

con = sqlite3.connect("file:data/cache/bars.db?mode=ro", uri=True)
cl = pd.read_sql("SELECT code, close FROM daily_bar WHERE adjust='qfq' AND date=?", con, params=(DATE,))
con.close()
cl["code"] = cl["code"].astype(str).str.split(".").str[0].str.zfill(6)  # 对齐 6 位
f = f.merge(cl, on="code", how="inner")
f["bp_fin"] = f["bps"] / f["close"]

# 3. 对齐 + 相关
m = v[["code", "bp_pb"]].merge(f[["code", "bp_fin"]], on="code", how="inner")
print(f"共同股票（当日 {DATE}）: {len(m)}")
if len(m) > 100:
    a, b = m["bp_fin"].values, m["bp_pb"].values
    print(f"Pearson 相关: {np.corrcoef(a, b)[0, 1]:.4f}")
    print(f"Spearman 相关: {pd.Series(a).rank().corr(pd.Series(b).rank()):.4f}")
    print(f"finance版 bp 中位数 {np.median(a):.3f} vs pbMRQ版 bp 中位数 {np.median(b):.3f}")
