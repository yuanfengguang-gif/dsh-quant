import sqlite3
import sys
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DB = r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant\data\cache\bars_tdx_test.db"
con = sqlite3.connect(DB)
print("表:", [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")])
print("列:", [r[1] for r in con.execute("PRAGMA table_info(daily_bar)")])
print("\n行数:", con.execute("SELECT COUNT(*) FROM daily_bar").fetchone()[0])

df = pd.read_sql("""SELECT code,date,open,close,volume,amount,turn,pct_chg,
                    total_share,float_share,circ_mv,total_mv,is_st,adjust,source
                    FROM daily_bar WHERE code='000001.SZ' ORDER BY date LIMIT 2""", con)
print("\n样例（单位换算后）:")
print(df.to_string(index=False))
r = df.iloc[0]
print(f"\n单位校验:")
print(f"  volume={r['volume']:,.0f} 股（原 61355 手 × 100）")
print(f"  amount={r['amount']:,.0f} 元（原 112469.5747 千元 × 1000）")
print(f"  turn={r['turn']:.6f}（原 0.5725% ÷100）")
print(f"  pct_chg={r['pct_chg']:.6f}（原 -0.49% ÷100）")
print(f"  float_share={r['float_share']:,.0f} 股（原 107163.4434 万股 × 10000）")
print(f"  circ_mv={r['circ_mv']:,.0f} 元（原 1958947.7454 万元 × 10000）")
print(f"  自洽: float_share × close = {r['float_share']*r['close']:,.0f} vs circ_mv = {r['circ_mv']:,.0f}")
con.close()
