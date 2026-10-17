# -*- coding: utf-8 -*-
"""data/fetch_tdx_capital.py —— 通达信逐日股本（流通股本 Ltgb / 总股本 Zgb）落库

背景（CORE_ISSUE_TRACKER 9.7 T1b）：
  hist_mv 重建（DS-09）、估值自算（DS-16）、turn 复算校验（DS-14）都需要「逐日股本」。
  实测 `tqs.get_gb_info_by_date(stock_code, start_date, end_date)` 一次调用即可返回该股全历史：
    [{'Date': 20010827, 'Ltgb': 71500000.0, 'Zgb': 250000000.0}, ...]   ← 单位=股

输出：data/cache/tdx_capital.db → 表 capital_daily(code, date, ltgb, zgb)  PK(code,date)
      + 表 fetch_log(code, n_rows, first_date, last_date, run_at, status) 便于断点续跑

用法：
  python data/fetch_tdx_capital.py --limit 20     # 试点（只跑 20 只）
  python data/fetch_tdx_capital.py                # 全市场（自动跳过已抓取的）
  python data/fetch_tdx_capital.py --reset        # 重抓
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, r"C:\Users\Administrator\.dsh\skills\tdx-aidata")
sys.path.insert(0, r"C:\Users\Administrator\.dsh\skills\tdx-aidata\lib")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from tdxaidata import tqs

BASE = Path(__file__).resolve().parent.parent
CACHE = BASE / "data" / "cache"
META = CACHE / "tdx_meta.db"
OUT = CACHE / "tdx_capital.db"
START = "1990-01-01"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 只（试点）")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.03)
    args = ap.parse_args()
    t0 = time.time()

    meta = sqlite3.connect(f"file:{META.as_posix()}?mode=ro", uri=True, timeout=10)
    codes = [r[0] for r in meta.execute("SELECT code FROM universe ORDER BY code")]
    meta.close()
    print(f"universe: {len(codes):,} 只")

    con = sqlite3.connect(str(OUT))
    con.execute("PRAGMA synchronous=OFF")
    con.execute("""CREATE TABLE IF NOT EXISTS capital_daily (
                     code TEXT, date TEXT, ltgb REAL, zgb REAL, PRIMARY KEY (code, date))""")
    con.execute("""CREATE TABLE IF NOT EXISTS fetch_log (
                     code TEXT PRIMARY KEY, n_rows INTEGER, first_date TEXT, last_date TEXT,
                     run_at TEXT, status TEXT)""")
    con.commit()
    if args.reset:
        con.execute("DELETE FROM capital_daily")
        con.execute("DELETE FROM fetch_log")
        con.commit()

    done = {r[0] for r in con.execute("SELECT code FROM fetch_log WHERE status='ok'")}
    todo = [c for c in codes if c not in done]
    if args.limit:
        todo = todo[: args.limit]
    print(f"待抓取: {len(todo):,} 只（已完成 {len(done):,}）")

    end = datetime.now().strftime("%Y-%m-%d")
    ok = fail = rows_total = 0
    for i, code in enumerate(todo, 1):
        try:
            r = tqs.get_gb_info_by_date(stock_code=code, start_date=START, end_date=end)
            if isinstance(r, list) and r:
                recs = []
                for it in r:
                    d = str(it.get("Date") or "")
                    if len(d) == 8:
                        d = f"{d[:4]}-{d[4:6]}-{d[6:]}"
                    if not d:
                        continue
                    recs.append((code, d, it.get("Ltgb"), it.get("Zgb")))
                if recs:
                    with con:
                        con.executemany(
                            "INSERT OR REPLACE INTO capital_daily VALUES (?,?,?,?)", recs)
                        con.execute(
                            "INSERT OR REPLACE INTO fetch_log VALUES (?,?,?,?,?,?)",
                            (code, len(recs), recs[0][1], recs[-1][1],
                             datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "ok"))
                    rows_total += len(recs)
                    ok += 1
                else:
                    fail += 1
            else:
                with con:
                    con.execute("INSERT OR REPLACE INTO fetch_log VALUES (?,?,?,?,?,?)",
                                (code, 0, None, None,
                                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "empty"))
                fail += 1
        except Exception as exc:  # noqa: BLE001
            fail += 1
            with con:
                con.execute("INSERT OR REPLACE INTO fetch_log VALUES (?,?,?,?,?,?)",
                            (code, 0, None, None,
                             datetime.now().strftime("%Y-%m-%d %H:%M:%S"), f"err:{str(exc)[:60]}"))
        if i % 50 == 0 or i == len(todo):
            el = time.time() - t0
            print(f"  [{i}/{len(todo)}] ok={ok} fail={fail} rows={rows_total:,} "
                  f"耗时 {el:.0f}s（{el/i:.2f}s/只）", flush=True)
        time.sleep(args.sleep)

    n = con.execute("SELECT COUNT(*) FROM capital_daily").fetchone()[0]
    codes_n = con.execute("SELECT COUNT(DISTINCT code) FROM capital_daily").fetchone()[0]
    print(f"\n完成: {n:,} 行 / {codes_n:,} 只 | 本次 ok={ok} fail={fail} | 总耗时 {time.time()-t0:.0f}s")
    print(f"库: {OUT}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
