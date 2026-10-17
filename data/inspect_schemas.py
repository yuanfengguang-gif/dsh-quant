# -*- coding: utf-8 -*-
import sqlite3, os
for db in ["data/cache/finance.db", "data/cache/hist_mv.db", "data/cache/finance_ts.db"]:
    if not os.path.exists(db):
        print(f"--- {db}: NOT FOUND ---")
        continue
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    print(f"=== {db} ===")
    tabs = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    for t in tabs:
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
        n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t} ({n} rows): {cols}")
        # sample 2 rows
        try:
            rows = con.execute(f"SELECT * FROM {t} LIMIT 2").fetchall()
            for r in rows:
                print(f"      sample: {r}")
        except Exception as e:
            print(f"      sample err: {e}")
    con.close()
    print()
