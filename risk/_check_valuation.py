import sqlite3
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
C = r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant\data\cache"
con = sqlite3.connect(C + r"\valuation.db")
print("valuation 表结构:", [r[1] for r in con.execute("PRAGMA table_info(valuation)")])
print("行数:", con.execute("SELECT COUNT(*) FROM valuation").fetchone()[0])
print("日期范围:", con.execute("SELECT MIN(date), MAX(date) FROM valuation").fetchone())
print("code 样例:", [r[0] for r in con.execute("SELECT DISTINCT code FROM valuation LIMIT 5")])

print("\n--- isST 取值分布 ---")
for r in con.execute("SELECT isST, COUNT(*) FROM valuation GROUP BY isST"):
    print(f"  isST={r[0]}: {r[1]:,}")

print("\n--- tradestatus 分布 ---")
for r in con.execute("SELECT tradestatus, COUNT(*) FROM valuation GROUP BY tradestatus"):
    print(f"  tradestatus={r[0]}: {r[1]:,}")

print("\n--- 按年（看覆盖）---")
for r in con.execute("""SELECT substr(date,1,4) y, COUNT(*) n, COUNT(DISTINCT code) c,
                        SUM(CASE WHEN isST=1 THEN 1 ELSE 0 END) st_n
                        FROM valuation GROUP BY y ORDER BY y"""):
    print(f"  {r[0]}: {r[1]:>9,} 行, {r[2]:>5} 只, ST {r[3]:>6,}")

print("\n--- 与通达信股票代码格式对比 ---")
con2 = sqlite3.connect(C + r"\bars_tdx.db")
print("通达信 code 样例:", [r[0] for r in con2.execute("SELECT DISTINCT code FROM daily_bar LIMIT 5")])
con2.close()
con.close()
