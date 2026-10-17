# -*- coding: utf-8 -*-
"""risk/analyze_delisted.py —— 退市股清单分析（幸存者偏差量化）"""
import sqlite3
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
C = r"D:\Programs\DSH Projects\DSH Quant\data\cache"

con = sqlite3.connect(C + r"\datayes_basic.db")
df = pd.read_sql("SELECT * FROM sec_delisted", con)
con.close()

print("=" * 66)
print("一、退市股清单概览")
print("=" * 66)
print(f"总条数: {len(df):,}")
print(f"字段: {list(df.columns)}")
print("\n按交易所:")
for k, v in df["exchangeCD"].value_counts().items():
    print(f"  {k}: {v:,}")
print("\n按资产类别 assetClass:")
for k, v in df["assetClass"].value_counts().items():
    print(f"  {k}: {v:,}")
print(f"\n有退市日期的: {df['delistDate'].notna().sum():,}")
print(f"有上市日期的: {df['listDate'].notna().sum():,}")

print("\n" + "=" * 66)
print("二、A股退市股按退市年份分布（assetClass=E 且 exchangeCD 为沪深）")
print("=" * 66)
a = df[(df["assetClass"] == "E") & (df["exchangeCD"].isin(["XSHE", "XSHG"]))].copy()
print(f"A 股退市记录: {len(a):,}")
a["delist_year"] = pd.to_datetime(a["delistDate"], errors="coerce").dt.year
vc = a["delist_year"].value_counts().sort_index()
print("\n逐年退市数量:")
for y, n in vc.items():
    bar = "█" * min(int(n), 60)
    print(f"  {int(y)}: {n:>3}  {bar}")

print("\n" + "=" * 66)
print("三、与通达信数据的对比（通达信是否有这些退市股）")
print("=" * 66)
con2 = sqlite3.connect(C + r"\bars_tdx.db")
tdx_codes = set(r[0] for r in con2.execute("SELECT DISTINCT code FROM daily_bar"))
con2.close()
print(f"通达信股票数: {len(tdx_codes):,}")
# 通联 ticker 是 6 位；转成 xxx.SZ/SH 格式
def to_code(r):
    ex = "SZ" if r["exchangeCD"] == "XSHE" else "SH"
    return f"{str(r['ticker']).zfill(6)}.{ex}"
a["code"] = a.apply(to_code, axis=1)
have = a[a["code"].isin(tdx_codes)]
missing = a[~a["code"].isin(tdx_codes)]
print(f"退市股中，通达信**有**行情的: {len(have):,} ({len(have)/len(a)*100:.1f}%)")
print(f"退市股中，通达信**没有**行情的: {len(missing):,} ({len(missing)/len(a)*100:.1f}%)")
print(f"\n→ 结论：通达信{'不含' if len(have) < len(a)*0.1 else '含'}退市股行情")

print("\n" + "=" * 66)
print("四、幸存者偏差的量化（关键）")
print("=" * 66)
con3 = sqlite3.connect(C + r"\bars_tdx.db")
for y in [2010, 2015, 2018, 2020, 2023, 2025]:
    # 该年通达信有行情的股票数
    n_tdx = con3.execute("SELECT COUNT(DISTINCT code) FROM daily_bar WHERE date LIKE ?", (f"{y}%",)).fetchone()[0]
    # 该年之后退市的股票数
    n_delist = a[pd.to_datetime(a["delistDate"], errors="coerce").dt.year >= y].shape[0]
    print(f"  {y}: 通达信 {n_tdx:,} 只 | 该年及之后退市 {n_delist:>3} 只 "
          f"| 若纳入则样本增加 ~{n_delist/max(n_tdx,1)*100:.1f}%")
con3.close()
