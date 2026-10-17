# -*- coding: utf-8 -*-
"""data/switch_to_tdx_bars.py —— 把通达信数据原地升级进 bars.db（零代码改动切换）

策略：
  1) 现 bars.db 已备份 → bars_legacy_backup_20261016.db
  2) 从 bars_tdx.db 读 adjust='qfq' 行 → 映射成 bars.db 的 14 列 schema
  3) 写入 bars.db 的新表 daily_bar_new → 校验 → RENAME 成 daily_bar
  4) 重建 bar_meta（每 (code, adjust) 的 start/end/rows）
  5) 全程保留老库为 daily_bar_legacy 以便回滚对比

用法：python data/switch_to_tdx_bars.py [--dry-run]
"""
import argparse
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

SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_bar_new (
    code       TEXT NOT NULL,
    date       TEXT NOT NULL,
    open       REAL, high REAL, low REAL, close REAL,
    preclose   REAL, volume REAL, amount REAL,
    turn       REAL, pct_chg REAL, is_st INTEGER,
    adjust     TEXT NOT NULL,
    source     TEXT NOT NULL,
    PRIMARY KEY (code, date, adjust)
);
"""
META_SCHEMA = """
CREATE TABLE IF NOT EXISTS bar_meta_new (
    code       TEXT NOT NULL,
    adjust     TEXT NOT NULL,
    start_date TEXT, end_date TEXT, rows INTEGER, updated_at TEXT,
    PRIMARY KEY (code, adjust)
);
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--source-adjust", default="qfq")
    args = ap.parse_args()
    t0 = time.time()

    if not TDX.exists():
        print(f"❌ 找不到 {TDX}")
        return
    if not BARS.exists():
        print(f"❌ 找不到 {BARS}")
        return
    bkp = CACHE / "bars_legacy_backup_20261016.db"
    if not bkp.exists():
        print("⚠️ 未发现备份 bars_legacy_backup_20261016.db，请先备份！")
        return

    src = sqlite3.connect(f"file:{TDX}?mode=ro", uri=True)
    n_src = src.execute(
        "SELECT COUNT(*) FROM daily_bar WHERE adjust=?", (args.source_adjust,)).fetchone()[0]
    rng = src.execute(
        "SELECT MIN(date),MAX(date) FROM daily_bar WHERE adjust=?", (args.source_adjust,)).fetchone()
    print(f"源（bars_tdx.db, adjust={args.source_adjust}）: {n_src:,} 行, {rng[0]} ~ {rng[1]}")
    if args.dry_run:
        src.close()
        print("[dry-run] 不写入")
        return

    con = sqlite3.connect(str(BARS))
    con.execute("PRAGMA synchronous=OFF")
    con.execute("PRAGMA journal_mode=MEMORY")
    con.executescript(SCHEMA)
    con.executescript(META_SCHEMA)
    # 保留老表（改名），便于回滚/对比
    try:
        con.execute("DROP TABLE IF EXISTS daily_bar_legacy")
        con.execute("ALTER TABLE daily_bar RENAME TO daily_bar_legacy")
        print("  老表已改名 → daily_bar_legacy")
    except Exception as e:
        print(f"  （老表改名跳过：{e}）")
    con.commit()

    # 分批搬运
    total = 0
    reader = pd.read_sql(
        f"SELECT code,date,open,high,low,close,preclose,volume,amount,turn,pct_chg,is_st "
        f"FROM daily_bar WHERE adjust='{args.source_adjust}'", src, chunksize=500000)
    for ch in reader:
        ch["adjust"] = args.source_adjust
        ch["source"] = "tdx"
        ch["is_st"] = pd.to_numeric(ch["is_st"], errors="coerce").fillna(0).astype(int)
        ch.to_sql("_tmp_sw", con, if_exists="replace", index=False)
        con.execute("INSERT OR REPLACE INTO daily_bar_new SELECT * FROM _tmp_sw")
        con.commit()
        total += len(ch)
        print(f"  搬运 {total:,} / {n_src:,}  {time.time()-t0:.0f}s", flush=True)
    src.close()
    con.execute("DROP TABLE IF EXISTS _tmp_sw")
    con.commit()
    n_new = con.execute("SELECT COUNT(*) FROM daily_bar_new").fetchone()[0]
    print(f"  写入 daily_bar_new: {n_new:,} 行")

    # 重建 bar_meta
    print("  重建 bar_meta …")
    con.execute("""INSERT OR REPLACE INTO bar_meta_new
                   SELECT code, adjust, MIN(date), MAX(date), COUNT(*), datetime('now')
                   FROM daily_bar_new GROUP BY code, adjust""")
    con.commit()
    n_meta = con.execute("SELECT COUNT(*) FROM bar_meta_new").fetchone()[0]
    print(f"  bar_meta_new: {n_meta:,} 行")

    # 切换表名
    con.execute("DROP TABLE IF EXISTS daily_bar_prev")
    con.execute("ALTER TABLE daily_bar_new RENAME TO daily_bar")
    con.execute("DROP TABLE IF EXISTS bar_meta_prev")
    try:
        con.execute("ALTER TABLE bar_meta RENAME TO bar_meta_prev")
    except Exception:
        pass
    con.execute("ALTER TABLE bar_meta_new RENAME TO bar_meta")
    con.execute("CREATE INDEX IF NOT EXISTS idx_daily_bar ON daily_bar (code, adjust, date)")
    con.commit()

    # 校验
    print("\n=== 校验 ===")
    print("  daily_bar:", con.execute("SELECT COUNT(*) FROM daily_bar").fetchone()[0], "行")
    print("  日期范围:", con.execute("SELECT MIN(date),MAX(date) FROM daily_bar").fetchone())
    for r in con.execute("SELECT adjust,COUNT(*) FROM daily_bar GROUP BY adjust"):
        print(f"  adjust={r[0]}: {r[1]:,}")
    print("  bar_meta:", con.execute("SELECT COUNT(*) FROM bar_meta").fetchone()[0], "行")
    # 与老表对比同一股票
    try:
        for code in ("600519.SH",):
            old = con.execute("SELECT date,close FROM daily_bar_legacy WHERE code=? AND adjust='qfq' ORDER BY date DESC LIMIT 2", (code,)).fetchall()
            new = con.execute("SELECT date,close FROM daily_bar WHERE code=? AND adjust='qfq' ORDER BY date DESC LIMIT 2", (code,)).fetchall()
            print(f"\n  {code} 老库最新: {old}")
            print(f"  {code} 新库最新: {new}")
    except Exception as e:
        print(f"  对比跳过: {e}")
    con.close()
    print(f"\n✅ 切换完成，耗时 {time.time()-t0:.0f}s")
    print("   回滚：把 daily_bar 改回 daily_bar_tdx、daily_bar_legacy 改回 daily_bar 即可")


if __name__ == "__main__":
    main()
