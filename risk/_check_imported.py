import sqlite3
import sys
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DB = r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant\data\cache\bars_tdx_test.db"
con = sqlite3.connect(DB)

print("=== 表清单 ===")
print([r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")])

print("\n=== daily_bar_tdx（日频行情）===")
n = con.execute("SELECT COUNT(*) FROM daily_bar_tdx").fetchone()[0]
print(f"行数 {n}")
df = pd.read_sql("SELECT code,date,open,high,low,close,preclose,pct_chg,volume,amount,turn,pe,pb,circ_mv FROM daily_bar_tdx LIMIT 3", con)
print(df.to_string(index=False))
print("\n单位换算后校验（换手率应<100，成交量应为股数级）:")
v = pd.read_sql("SELECT date,turn,volume,amount,close,pct_chg FROM daily_bar_tdx", con)
print(f"  turn 范围: {v['turn'].min():.4f} ~ {v['turn'].max():.4f}（小数，应<1）")
print(f"  volume 均值: {v['volume'].mean():,.0f}（股）")
print(f"  amount 均值: {v['amount'].mean():,.0f}（元）")
print(f"  pct_chg 范围: {v['pct_chg'].min():.4f} ~ {v['pct_chg'].max():.4f}（小数）")

print("\n=== adj_factor（复权因子）===")
n2 = con.execute("SELECT COUNT(*) FROM adj_factor").fetchone()[0]
print(f"行数 {n2}")
af = pd.read_sql("SELECT * FROM adj_factor ORDER BY date LIMIT 3", con)
print(af.to_string(index=False))
af2 = pd.read_sql("SELECT * FROM adj_factor WHERE qfq_factor IS NOT NULL AND hfq_factor IS NOT NULL", con)
print(f"\n两列同时有值的行数: {len(af2)}")
if len(af2):
    ratio = af2["hfq_factor"] / af2["qfq_factor"]
    print(f"  hfq/qfq 比值: mean={ratio.mean():.6f} std={ratio.std():.6f} "
          f"min={ratio.min():.6f} max={ratio.max():.6f}")
    print(f"  最新日 qfq={af2['qfq_factor'].iloc[-1]:.6f} hfq={af2['hfq_factor'].iloc[-1]:.6f}")
con.close()
