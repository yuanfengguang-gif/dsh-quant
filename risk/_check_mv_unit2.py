import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
C = r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant\data\cache"

c_mv = sqlite3.connect(C + r"\hist_mv.db")
c_tdx = sqlite3.connect(C + r"\bars_tdx_test.db")
c_bars = sqlite3.connect(C + r"\bars.db")

print("=== 用 300602.SZ 2026-01 三点核对（项目月频市值 / 通达信日频 / 本地价格）===")
print("\n[1] 通达信 2026-01-05:")
for r in c_tdx.execute("""SELECT code,date,close,float_share,total_share,circ_mv,total_mv
                          FROM daily_bar_tdx WHERE code='300602.SZ' LIMIT 2"""):
    print("   ", r)

print("\n[2] 项目 hist_mv（月频，2026-01）:")
row = c_mv.execute("SELECT * FROM hist_mv WHERE code='300602.SZ' AND month='2026-01'").fetchone()
print("   ", row)

print("\n[3] 本地 bars.db 2026-01-05 close:")
r = c_bars.execute("SELECT code,date,close FROM daily_bar WHERE code='300602.SZ' AND date='2026-01-05'").fetchone()
print("   ", r)

if row and r:
    tdx = c_tdx.execute("SELECT float_share,circ_mv FROM daily_bar_tdx WHERE code='300602.SZ' LIMIT 1").fetchone()
    close_local = r[2]
    close_tdx = c_tdx.execute("SELECT close FROM daily_bar_tdx WHERE code='300602.SZ' LIMIT 1").fetchone()[0]
    print("\n=== 判定 ===")
    print(f"  通达信 circ_mv = {tdx[1]:,.2f}（若万元 → {tdx[1]/10000:.2f} 亿元）")
    print(f"  项目 hist_mv circ_mv = {row[2]:,.2f}（若百万元 → {row[2]/100:.2f} 亿元）")
    print(f"  通达信 float_share × close(通达信) = {tdx[0]*close_tdx:,.2f}")
    print(f"  项目 local close = {close_local}, 通达信 close = {close_tdx}")
    print(f"\n  → 项目/通达信 市值比值 = {row[2]/tdx[1]:.6f}")

c_mv.close(); c_tdx.close(); c_bars.close()
