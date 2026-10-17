import sqlite3, os
sys_path = r"D:\Programs\DSH Projects\DSH Quant\data\cache"
dbs = ["bars.db", "finance.db", "hist_mv.db", "stock_basic.db"]
for db in dbs:
    p = os.path.join(sys_path, db)
    if not os.path.exists(p):
        print(f"\n### {db} 不存在")
        continue
    con = sqlite3.connect(p)
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    print(f"\n### {db}（表：{tables}）")
    for t in tables:
        cols = con.execute(f"PRAGMA table_info('{t}')").fetchall()
        print(f"  [{t}] {len(cols)} 列:")
        print("    " + ", ".join(c[1] for c in cols))
    con.close()
