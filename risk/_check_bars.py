import sqlite3
c = sqlite3.connect('data/cache/bars.db')
print("daily_bar 列:", [r[1] for r in c.execute("PRAGMA table_info(daily_bar)")])
for row in c.execute("SELECT * FROM daily_bar LIMIT 2"):
    print("行:", row)
print("交易日数:", c.execute("SELECT COUNT(DISTINCT trade_date) FROM daily_bar").fetchone()[0])
print("日期范围:", c.execute("SELECT MIN(trade_date), MAX(trade_date) FROM daily_bar").fetchone())
c.close()
