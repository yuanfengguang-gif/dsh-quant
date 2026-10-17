import sqlite3
import sys
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DB = r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant\data\cache\bars_tdx_test.db"
con = sqlite3.connect(DB)

print("=== daily_bar_tdx 概况 ===")
print("总行数:", con.execute("SELECT COUNT(*) FROM daily_bar_tdx").fetchone()[0])
print("股票数:", con.execute("SELECT COUNT(DISTINCT code) FROM daily_bar_tdx").fetchone()[0])
print("日期范围:", con.execute("SELECT MIN(date), MAX(date) FROM daily_bar_tdx").fetchone())

print("\n=== 按年统计 ===")
for r in con.execute("""SELECT substr(date,1,4) y, COUNT(*) n, COUNT(DISTINCT code) c
                        FROM daily_bar_tdx GROUP BY y ORDER BY y"""):
    print(f"  {r[0]}: {r[1]:>8,} 行, {r[2]:>5} 只")

print("\n=== 关键字段非空率 ===")
tot = con.execute("SELECT COUNT(*) FROM daily_bar_tdx").fetchone()[0]
for c in ["open", "close", "preclose", "pct_chg", "volume", "amount", "turn", "pe", "pb", "circ_mv", "total_mv"]:
    n = con.execute(f"SELECT COUNT({c}) FROM daily_bar_tdx").fetchone()[0]
    print(f"  {c:12s}: {n/tot*100:6.2f}%")

print("\n=== 内部一致性 ===")
bad = con.execute("""SELECT COUNT(*) FROM daily_bar_tdx
    WHERE high < MAX(open, close) OR low > MIN(open, close)""").fetchone()[0]
print(f"  high/low 越界: {bad}")
bad2 = con.execute("""SELECT COUNT(*) FROM daily_bar_tdx
    WHERE ABS(pct_chg - (close/preclose - 1)) > 0.001 AND preclose > 0""").fetchone()[0]
print(f"  pct_chg 不自洽: {bad2}")

print("\n=== 样例 ===")
print(pd.read_sql("SELECT code,date,open,close,preclose,pct_chg,volume,amount,turn,pe,pb,circ_mv FROM daily_bar_tdx WHERE code='000001.SZ' ORDER BY date LIMIT 3", con).to_string(index=False))
con.close()
