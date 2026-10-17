import sqlite3
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
C = r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant\data\cache"
con = sqlite3.connect(C + r"\finance_csmar.db")
df = pd.read_sql("""SELECT code, period, np_parent, equity, roe_weighted, roe_a,
                           net_profit, np_growth, rev_growth
                    FROM fin_core WHERE code='600519.SH' ORDER BY period DESC LIMIT 6""", con)
print("=== 贵州茅台（看 ROE / 增长率的单位）===")
print(df.to_string(index=False))

print("\n=== 全库数值范围（判断单位）===")
d2 = pd.read_sql("""SELECT MIN(roe_weighted) mn_w, MAX(roe_weighted) mx_w,
                           MIN(roe_a) mn_a, MAX(roe_a) mx_a,
                           MIN(np_growth) mn_g, MAX(np_growth) mx_g,
                           MIN(rev_growth) mn_rg, MAX(rev_growth) mx_rg
                    FROM fin_core""", con)
print(d2.to_string(index=False))
con.close()
