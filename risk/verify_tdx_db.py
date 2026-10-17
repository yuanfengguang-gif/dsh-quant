# -*- coding: utf-8 -*-
"""risk/verify_tdx_db.py —— 导入后的通达信库整体验证（概览 + 内部一致性）"""
import sqlite3
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DB = r"D:\Programs\DSH Projects\DSH Quant\data\cache\bars_tdx.db"
con = sqlite3.connect(DB)

print("=" * 64)
print("一、概览")
print("=" * 64)
for t in [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]:
    n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"  {t}: {n:,} 行")

print("\n  daily_bar 日期范围:", con.execute("SELECT MIN(date),MAX(date) FROM daily_bar").fetchone())
print("  daily_bar 股票数:", con.execute("SELECT COUNT(DISTINCT code) FROM daily_bar").fetchone()[0])
print("\n  按 adjust 分组:")
for r in con.execute("SELECT adjust, COUNT(*) FROM daily_bar GROUP BY adjust"):
    print(f"    {r[0]}: {r[1]:,}")

print("\n  按年（unadj 部分）:")
for r in con.execute("""SELECT substr(date,1,4) y, COUNT(*) n, COUNT(DISTINCT code) c
                        FROM daily_bar WHERE adjust='unadj' GROUP BY y ORDER BY y"""):
    print(f"    {r[0]}: {r[1]:>9,} 行, {r[2]:>5} 只")

print("\n" + "=" * 64)
print("二、内部一致性（能抓出单位错/价格异常/缺口）")
print("=" * 64)
tot = con.execute("SELECT COUNT(*) FROM daily_bar").fetchone()[0]
print(f"  样本总量: {tot:,}")

checks = [
    ("high < max(open,close)", "SELECT COUNT(*) FROM daily_bar WHERE high < MAX(open,close)"),
    ("low > min(open,close)", "SELECT COUNT(*) FROM daily_bar WHERE low > MIN(open,close)"),
    ("pct_chg 与 close/preclose 不自洽(>0.5pp)",
     "SELECT COUNT(*) FROM daily_bar WHERE preclose>0 AND ABS(pct_chg-(close/preclose-1))>0.005"),
    ("价格<=0", "SELECT COUNT(*) FROM daily_bar WHERE close<=0 OR open<=0"),
    ("volume<0", "SELECT COUNT(*) FROM daily_bar WHERE volume<0"),
]
for name, q in checks:
    n = con.execute(q).fetchone()[0]
    mark = "✅" if n == 0 else ("🟡" if n / tot < 0.001 else "❌")
    print(f"  {mark} {name}: {n:,} ({n/tot*100:.3f}%)")

print("\n  关键字段非空率:")
for c in ["open", "high", "low", "close", "preclose", "pct_chg", "volume", "amount", "turn", "circ_mv"]:
    n = con.execute(f"SELECT COUNT({c}) FROM daily_bar").fetchone()[0]
    print(f"    {c:10s}: {n/tot*100:6.2f}%")

print("\n" + "=" * 64)
print("三、与复权因子的覆盖匹配度")
print("=" * 64)
has_af = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='adj_factor'").fetchone()
if has_af:
    af = con.execute("SELECT COUNT(*) FROM adj_factor").fetchone()[0]
    print(f"  adj_factor: {af:,} 行, {con.execute('SELECT COUNT(DISTINCT code) FROM adj_factor').fetchone()[0]:,} 只")
    m = con.execute("""SELECT COUNT(*) FROM daily_bar b
                       JOIN adj_factor a ON a.code=b.code AND a.date=b.date""").fetchone()[0]
    print(f"  daily_bar × adj_factor 匹配行: {m:,} / {tot:,} ({m/tot*100:.1f}%)")
con.close()
