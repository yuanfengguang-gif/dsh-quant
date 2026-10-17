import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
C = r"D:\Programs\DSH Projects\DSH Quant\data\cache"
con = sqlite3.connect(C + r"\bars.db")

print("=== 本地 bars.db 年份覆盖 ===")
print("总体:", con.execute("SELECT MIN(date), MAX(date) FROM daily_bar").fetchone())
print("\n按年统计（本地）：")
for r in con.execute("""SELECT substr(date,1,4) y, COUNT(*) n, COUNT(DISTINCT code) c
                        FROM daily_bar GROUP BY y ORDER BY y"""):
    print(f"  {r[0]}: {r[1]:>10,} 行, {r[2]:>5} 只")

print("\n=== 按 source 统计 ===")
for r in con.execute("SELECT source, COUNT(*), MIN(date), MAX(date) FROM daily_bar GROUP BY source"):
    print(f"  {r[0]}: {r[1]:,} 行, {r[2]} ~ {r[3]}")

print("\n=== 关键：通达信 zip 年份 vs 本地可对比年份 ===")
years_local = set(r[0] for r in con.execute("SELECT DISTINCT substr(date,1,4) FROM daily_bar"))
print(f"  本地有数据年份: {sorted(years_local)}")
print(f"  → 只有这些年份能与通达信做「真实交叉验证」")
con.close()
