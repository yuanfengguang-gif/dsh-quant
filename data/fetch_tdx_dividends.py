# -*- coding: utf-8 -*-
"""data/fetch_tdx_dividends.py —— 全市场除权除息明细抓取（供自算复权因子）

背景（CORE_ISSUE_TRACKER DS-20）：通达信「后复权因子」文件不是纯事件乘数（末次除权后仍漂移 1.63%），
导致用它构造的 qfq 有系统性偏差（最高 ~30%）。改为用**除权明细 + 原始前收盘**自算。

`get_divid_factors(stock_code)` 返回 DataFrame（索引=除权日）：
    Type | Bonus(元/10股) | AllotPrice(配股价) | ShareBonus(股/10股) | Allotment(股/10股)

输出：data/cache/tdx_dividends.db
      dividend(code, ex_date, type, bonus, allot_price, share_bonus, allotment)
      fetch_log(code, n_events, first_date, last_date, run_at, status)
用法：python data/fetch_tdx_dividends.py [--limit N]
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, r"C:\Users\Lenovo\.dsh\skills\tdx-aidata")
sys.path.insert(0, r"C:\Users\Lenovo\.dsh\skills\tdx-aidata\lib")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from tdxaidata import tqs

CACHE = Path(__file__).resolve().parent.parent / "data" / "cache"
META = CACHE / "tdx_meta.db"
OUT = CACHE / "tdx_dividends.db"


def fnum(v):
    try:
        x = float(v)
        return x if x == x else 0.0
    except (TypeError, ValueError):
        return 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sleep", type=float, default=0.02)
    args = ap.parse_args()
    t0 = time.time()

    con = sqlite3.connect(str(OUT))
    con.execute("PRAGMA synchronous=OFF")
    con.execute("""CREATE TABLE IF NOT EXISTS dividend (
        code TEXT, ex_date TEXT, type TEXT, bonus REAL, allot_price REAL,
        share_bonus REAL, allotment REAL, PRIMARY KEY (code, ex_date))""")
    con.execute("""CREATE TABLE IF NOT EXISTS fetch_log (
        code TEXT PRIMARY KEY, n_events INTEGER, first_date TEXT, last_date TEXT,
        run_at TEXT, status TEXT)""")
    con.commit()

    meta = sqlite3.connect(f"file:{META.as_posix()}?mode=ro", uri=True, timeout=10)
    codes = [r[0] for r in meta.execute("SELECT code FROM universe ORDER BY code")]
    meta.close()
    done = {r[0] for r in con.execute("SELECT code FROM fetch_log WHERE status='ok'")}
    todo = [c for c in codes if c not in done]
    if args.limit:
        todo = todo[: args.limit]
    print(f"universe {len(codes):,} | 已完成 {len(done):,} | 待抓 {len(todo):,}")

    ok = fail = n_ev = 0
    for i, code in enumerate(todo, 1):
        try:
            df = tqs.get_divid_factors(stock_code=code)
            recs = []
            if df is not None and len(df) > 0:
                for dt, row in df.iterrows():
                    d = str(dt)[:10]
                    B = fnum(row.get("Bonus"))
                    S = fnum(row.get("ShareBonus"))
                    A = fnum(row.get("Allotment"))
                    if B == 0 and S == 0 and A == 0:
                        continue
                    recs.append((code, d, str(row.get("Type") or ""), B,
                                 fnum(row.get("AllotPrice")), S, A))
            if recs:
                with con:
                    con.executemany("INSERT OR REPLACE INTO dividend VALUES (?,?,?,?,?,?,?)", recs)
                    con.execute("INSERT OR REPLACE INTO fetch_log VALUES (?,?,?,?,?,?)",
                                (code, len(recs), recs[0][1], recs[-1][1],
                                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "ok"))
                n_ev += len(recs)
                ok += 1
            else:
                with con:
                    con.execute("INSERT OR REPLACE INTO fetch_log VALUES (?,?,?,?,?,?)",
                                (code, 0, None, None,
                                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "empty"))
                ok += 1   # 无除权事件也算成功
        except Exception as exc:  # noqa: BLE001
            fail += 1
            with con:
                con.execute("INSERT OR REPLACE INTO fetch_log VALUES (?,?,?,?,?,?)",
                            (code, 0, None, None,
                             datetime.now().strftime("%Y-%m-%d %H:%M:%S"), f"err:{str(exc)[:60]}"))
        if i % 200 == 0 or i == len(todo):
            el = time.time() - t0
            print(f"  [{i}/{len(todo)}] ok={ok} fail={fail} events={n_ev:,} "
                  f"{el:.0f}s ({el/i:.2f}s/只)", flush=True)
        time.sleep(args.sleep)

    n = con.execute("SELECT COUNT(*) FROM dividend").fetchone()[0]
    c = con.execute("SELECT COUNT(DISTINCT code) FROM dividend").fetchone()[0]
    rng = con.execute("SELECT MIN(ex_date), MAX(ex_date) FROM dividend").fetchone()
    print(f"\n完成: {n:,} 条除权记录 / {c:,} 只 / {rng[0]} ~ {rng[1]}")
    print(f"库: {OUT}  ({OUT.stat().st_size/1024/1024:.1f} MB)")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
