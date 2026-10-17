# -*- coding: utf-8 -*-
"""临时：查看各数据库表结构 + 关键字段分布，供数据诊断脚本设计。"""
import sqlite3
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = Path(__file__).resolve().parent.parent
CACHE = BASE / "data" / "cache"

for db, tables in [
    ("bars.db", ["daily_bar", "bar_meta"]),
    ("finance.db", ["finance_report"]),
    ("hist_mv.db", ["hist_mv"]),
    ("stock_basic.db", ["stock_basic"]),
]:
    p = CACHE / db
    print(f"\n===== {db} =====")
    if not p.exists():
        print("  不存在")
        continue
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    for t in tables:
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})").fetchall()]
        print(f"  {t}: {cols}")
    con.close()

# bars.db 关键字段分布
con = sqlite3.connect(f"file:{CACHE / 'bars.db'}?mode=ro", uri=True)
print("\n===== daily_bar 关键分布 =====")
print("source:", con.execute("SELECT source, COUNT(*), MIN(date), MAX(date) FROM daily_bar GROUP BY source").fetchall())
print("adjust:", con.execute("SELECT adjust, COUNT(*) FROM daily_bar GROUP BY adjust").fetchall())
print("is_st:", con.execute("SELECT is_st, COUNT(*) FROM daily_bar GROUP BY is_st").fetchall())
print("amount 缺失(按source):", con.execute("SELECT source, SUM(CASE WHEN amount IS NULL OR amount=0 THEN 1 ELSE 0 END), COUNT(*) FROM daily_bar GROUP BY source").fetchall())
con.close()
