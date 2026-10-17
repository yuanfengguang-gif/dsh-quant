# -*- coding: utf-8 -*-
"""data/fix_bars_increment.py —— 把 bars_tdx.db 的 unadj 增量转 qfq 补进 bars.db

背景：switch_to_tdx_bars.py 只搬了 adjust='qfq' 行；tdx_daily_update.py 的增量写的是
      adjust='unadj'，导致 bars.db 缺最新几日。
做法：读 bars_tdx.db 的 unadj 行 → join adj_factor → 生成 qfq → 写入 bars.db
"""
import sqlite3
import sys
import time
from pathlib import Path

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

CACHE = Path(r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant\data\cache")
BARS = CACHE / "bars.db"
TDX = CACHE / "bars_tdx.db"
t0 = time.time()

# 1) bars.db 当前最新
con = sqlite3.connect(str(BARS))
con.execute("PRAGMA synchronous=OFF")
cur_max = con.execute("SELECT MAX(date) FROM daily_bar").fetchone()[0]
print(f"bars.db 当前最新: {cur_max}")

# 2) 取 bars_tdx.db 里更晚的 unadj 行
src = sqlite3.connect(f"file:{TDX}?mode=ro", uri=True)
un = pd.read_sql(
    "SELECT code,date,open,high,low,close,preclose,volume,amount,turn,pct_chg,is_st "
    "FROM daily_bar WHERE adjust='unadj' AND date>?", src, params=(cur_max,))
print(f"bars_tdx.db unadj 增量（>{cur_max}）: {len(un):,} 行")
if un.empty:
    print("无增量，退出")
    con.close(); src.close(); sys.exit(0)

# 3) 关联复权因子 → qfq
af = pd.read_sql("SELECT code,date,qfq_factor FROM adj_factor WHERE qfq_factor IS NOT NULL AND qfq_factor>0", src)
src.close()
print(f"复权因子: {len(af):,} 行")
m = un.merge(af, on=["code", "date"], how="left")
hit = m["qfq_factor"].notna().sum()
print(f"  匹配到复权因子: {hit:,} / {len(m):,}（{hit/max(len(m),1)*100:.1f}%）")
# 未匹配的：用「该股票最新一日的因子」兜底（前复权以最新日为 1.0，最新因子即最优近似）
last_af = af.sort_values("date").groupby("code")["qfq_factor"].last()
m["qfq_factor"] = m["qfq_factor"].fillna(m["code"].map(last_af))
n_fb = m["qfq_factor"].notna().sum()
print(f"  用最新因子兜底后可用: {n_fb:,} / {len(m):,}")
bad = m[m["qfq_factor"].isna()]["code"].nunique()
if bad:
    print(f"  ⚠️ 仍无因子的股票数: {bad}（这些行将跳过）")
m = m[m["qfq_factor"].notna()].copy()

for c in ("open", "high", "low", "close", "preclose"):
    m[c] = pd.to_numeric(m[c], errors="coerce") * m["qfq_factor"]
m["adjust"] = "qfq"
m["source"] = "tdx_api"
out = m[["code", "date", "open", "high", "low", "close", "preclose", "volume",
         "amount", "turn", "pct_chg", "is_st", "adjust", "source"]].copy()
out.dropna(subset=["code", "date"], inplace=True)

# 4) 写入
out.to_sql("_tmp_fix", con, if_exists="replace", index=False)
con.execute("INSERT OR REPLACE INTO daily_bar SELECT * FROM _tmp_fix")
con.execute("DROP TABLE IF EXISTS _tmp_fix")
con.commit()

# 5) 重建这两天的 meta
con.execute("""INSERT OR REPLACE INTO bar_meta
               SELECT code, adjust, MIN(date), MAX(date), COUNT(*), datetime('now')
               FROM daily_bar WHERE date>? GROUP BY code, adjust""", (cur_max,))
con.commit()

print("\n=== 校验 ===")
print("  daily_bar:", con.execute("SELECT COUNT(*) FROM daily_bar").fetchone()[0], "行")
print("  日期范围:", con.execute("SELECT MIN(date),MAX(date) FROM daily_bar").fetchone())
for code in ("600519.SH",):
    r = con.execute("SELECT date,close FROM daily_bar WHERE code=? AND adjust='qfq' ORDER BY date DESC LIMIT 3", (code,)).fetchall()
    print(f"  {code} 最新3日: {r}")
print(f"\n✅ 修复完成，耗时 {time.time()-t0:.0f}s")
con.close()
