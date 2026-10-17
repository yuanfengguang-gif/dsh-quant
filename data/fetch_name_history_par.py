# -*- coding: utf-8 -*-
"""data/fetch_name_history_par.py —— 多线程版简称变更抓取（东财限流下提速）

与 fetch_name_history.py 逻辑相同，改用线程池并发（默认 8 并发、无额外 sleep）。
实测单线程被限流到 ~7s/只（全量 10 小时），并发后可降到 ~1 小时内。

用法：python data/fetch_name_history_par.py [--workers 8] [--limit N]
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import akshare as ak

CACHE = Path(__file__).resolve().parent.parent / "data" / "cache"
META = CACHE / "tdx_meta.db"
OUT = CACHE / "name_history.db"

_lock = threading.Lock()
_cnt = {"ok": 0, "fail": 0, "names": 0}


def is_st_name(name: str) -> int:
    s = (name or "").upper().replace(" ", "")
    core = s[1:] if s.startswith("G") else s
    core = core[1:] if core.startswith("S") and "ST" in core else core
    return 1 if "ST" in core else 0


def one(code: str, con: sqlite3.Connection):
    six = code[:6]
    try:
        df = ak.stock_info_change_name(symbol=six)
        recs = []
        if df is not None and len(df) > 0:
            for seq, (_, row) in enumerate(df.iterrows(), start=1):
                nm = str(row.get("name") or "").strip()
                if nm:
                    recs.append((code, seq, nm, is_st_name(nm)))
        with _lock:
            if recs:
                con.executemany("INSERT OR REPLACE INTO name_change VALUES (?,?,?,?)", recs)
                con.execute("INSERT OR REPLACE INTO fetch_log VALUES (?,?,?,?)",
                            (code, len(recs), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "ok"))
                _cnt["names"] += len(recs)
            else:
                con.execute("INSERT OR REPLACE INTO fetch_log VALUES (?,?,?,?)",
                            (code, 0, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "empty"))
            con.commit()
            _cnt["ok"] += 1
    except Exception as exc:  # noqa: BLE001
        with _lock:
            con.execute("INSERT OR REPLACE INTO fetch_log VALUES (?,?,?,?)",
                        (code, 0, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                         f"err:{type(exc).__name__}:{str(exc)[:40]}"))
            con.commit()
            _cnt["fail"] += 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    t0 = time.time()

    con = sqlite3.connect(str(OUT), check_same_thread=False)
    con.execute("PRAGMA synchronous=OFF")
    con.execute("""CREATE TABLE IF NOT EXISTS name_change (
        code TEXT, seq INTEGER, name TEXT, is_st_flag INTEGER, PRIMARY KEY (code, seq))""")
    con.execute("""CREATE TABLE IF NOT EXISTS fetch_log (
        code TEXT PRIMARY KEY, n_names INTEGER, run_at TEXT, status TEXT)""")
    con.commit()

    meta = sqlite3.connect(f"file:{META.as_posix()}?mode=ro", uri=True, timeout=10)
    codes = [r[0] for r in meta.execute("SELECT code FROM universe ORDER BY code")]
    meta.close()
    done = {r[0] for r in con.execute("SELECT code FROM fetch_log WHERE status='ok'")}
    todo = [c for c in codes if c not in done]
    if args.limit:
        todo = todo[: args.limit]
    print(f"universe {len(codes):,} | 已完成 {len(done):,} | 待抓 {len(todo):,} | 并发 {args.workers}")

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(one, c, con): c for c in todo}
        for i, f in enumerate(as_completed(futs), 1):
            if i % 100 == 0 or i == len(todo):
                el = time.time() - t0
                print(f"  [{i}/{len(todo)}] ok={_cnt['ok']} fail={_cnt['fail']} "
                      f"names={_cnt['names']:,} {el:.0f}s ({el/i:.2f}s/只)", flush=True)

    n = con.execute("SELECT COUNT(*) FROM name_change").fetchone()[0]
    c = con.execute("SELECT COUNT(DISTINCT code) FROM name_change").fetchone()[0]
    st = con.execute("SELECT COUNT(DISTINCT code) FROM name_change WHERE is_st_flag=1").fetchone()[0]
    print(f"\n完成: {n:,} 条 / {c:,} 只 / 曾 ST {st:,} 只 | 耗时 {time.time()-t0:.0f}s")
    print(f"库: {OUT}  ({OUT.stat().st_size/1024/1024:.1f} MB)")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
