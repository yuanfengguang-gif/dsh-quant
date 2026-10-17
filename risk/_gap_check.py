import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
C = r"D:\Programs\DSH Projects\DSH Quant\data\cache"

print("=" * 70)
print("【通达信 bars_tdx.db】")
print("=" * 70)
con = sqlite3.connect(C + r"\bars_tdx.db")
print("表:", [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")])
cols = [r[1] for r in con.execute("PRAGMA table_info(daily_bar)")]
print(f"\ndaily_bar 字段（{len(cols)}）：{cols}")
print("总行数:", con.execute("SELECT COUNT(*) FROM daily_bar").fetchone()[0])
print("股票数:", con.execute("SELECT COUNT(DISTINCT code) FROM daily_bar").fetchone()[0])
print("日期范围:", con.execute("SELECT MIN(date), MAX(date) FROM daily_bar").fetchone())

print("\n--- 是否含「股票名称」字段？（is_st 判断需要）---")
print(f"  {'name' in cols or 'secShortName' in cols}")

print("\n--- 是否含退市股？（抽 3 只已知退市股）---")
for tk in ["000003.SZ", "000013.SZ", "600001.SH"]:
    n = con.execute("SELECT COUNT(*) FROM daily_bar WHERE code=?", (tk,)).fetchone()[0]
    rng = con.execute("SELECT MIN(date),MAX(date) FROM daily_bar WHERE code=?", (tk,)).fetchone()
    print(f"  {tk}: {n:,} 行 {rng if n else ''}")

print("\n--- 股票数逐年（看扩增/退市）---")
for r in con.execute("""SELECT substr(date,1,4) y, COUNT(DISTINCT code) c FROM daily_bar
                        GROUP BY y ORDER BY y"""):
    print(f"  {r[0]}: {r[1]:>5} 只")

print("\n--- 字段非空率 ---")
tot = con.execute("SELECT COUNT(*) FROM daily_bar").fetchone()[0]
for c in ["open", "close", "preclose", "volume", "amount", "turn", "pct_chg",
          "pe", "pb", "circ_mv", "total_mv", "total_share", "is_st"]:
    if c in cols:
        n = con.execute(f"SELECT COUNT({c}) FROM daily_bar").fetchone()[0]
        print(f"  {c:12s}: {n/tot*100:6.2f}%")
con.close()

print("\n" + "=" * 70)
print("【项目现有其他库】")
print("=" * 70)
for db, tbl in [("finance.db", "finance_report"), ("hist_mv.db", "hist_mv"),
                ("stock_basic.db", "stock_basic"), ("industry.db", None),
                ("lhb.db", None), ("rzrq.db", None), ("consensus.db", None),
                ("valuation.db", None), ("limitup.db", None), ("finance_quality.db", None)]:
    try:
        c2 = sqlite3.connect(f"{C}\\{db}")
        ts = [r[0] for r in c2.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        print(f"\n  {db}: 表={ts}")
        for t in ts[:2]:
            n = c2.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            cc = [r[1] for r in c2.execute(f"PRAGMA table_info({t})")]
            print(f"    [{t}] {n:,} 行, 字段: {cc}")
        c2.close()
    except Exception as e:
        print(f"\n  {db}: 读取失败 {e}")
