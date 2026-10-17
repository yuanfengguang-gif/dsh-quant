import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
C = r"D:\Programs\DSH Projects\DSH Quant\data\cache"

print("=== 项目 hist_mv（月频流通市值）===")
c1 = sqlite3.connect(C + r"\hist_mv.db")
for r in c1.execute("SELECT * FROM hist_mv WHERE code='000001.SZ' ORDER BY month DESC LIMIT 4"):
    print("  ", r)
print("  说明：需与通达信同月对比判断单位")

print("\n=== 通达信（日频）同股 circ_mv 关系 ===")
c2 = sqlite3.connect(C + r"\bars_tdx_test.db")
print("  通达信字段关系检验（circ_mv 应 = float_share × close）:")
for r in c2.execute("""SELECT code, date, float_share, close, circ_mv,
                       ROUND(circ_mv/(float_share*close), 6) AS ratio
                       FROM daily_bar_tdx
                       WHERE code='000001.SZ' AND float_share>0 ORDER BY date LIMIT 3"""):
    print("  ", r)
print("\n  → ratio≈1 说明 通达信 circ_mv 单位 = float_share单位（万股）× 元 = 万元")

# 用平安银行判定 hist_mv 单位
print("\n=== 单位判定 ===")
row = c1.execute("SELECT month, circ_mv FROM hist_mv WHERE code='000001.SZ' ORDER BY month DESC LIMIT 1").fetchone()
print(f"  hist_mv 最新: {row[0]} circ_mv={row[1]}")
print(f"  若单位=万元 → {row[1]/10000:.1f} 亿元")
print(f"  若单位=百万元 → {row[1]/100:.1f} 亿元")
print(f"  若单位=元 → {row[1]/1e8:.1f} 亿元")
print(f"  （平安银行 2020 年后流通市值应在 3000 亿元量级）")
c1.close()
c2.close()
