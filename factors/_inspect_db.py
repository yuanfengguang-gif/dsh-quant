# -*- coding: utf-8 -*-
"""临时：查看 stock_basic.db / hist_mv.db / finance.db 结构。"""
import sqlite3
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = Path(__file__).resolve().parent.parent
for db in ["stock_basic.db", "hist_mv.db", "finance.db"]:
    p = BASE / "data" / "cache" / db
    print(f"\n===== {db} ({p.exists()}) =====")
    if not p.exists():
        continue
    con = sqlite3.connect(str(p))
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print("tables:", tables)
    for t in tables:
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})").fetchall()]
        print(f"  {t} cols:", cols)
    con.close()
