# -*- coding: utf-8 -*-
"""data/fetch_name_history.py —— 抓「股票简称变更历史」（东财，akshare）

目的（方案 A 的一半）：ST 状态与简称强绑定（`ST`/`*ST` 前缀）。
通达信只有"今天的简称"，akshare 的 `stock_info_change_name` 给**名称序列**（有序、无日期）。
配合价格 5% 涨跌停签名，可把 ST 区间反推出来。

输出：data/cache/name_history.db
      name_change(code, seq, name, is_st_flag)      ← 名称序列（seq 从 1 开始）
      fetch_log(code, n_names, run_at, status)
用法：python data/fetch_name_history.py [--limit N] [--sleep 0.15]
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import akshare as ak

CACHE = Path(__file__).resolve().parent.parent / "data" / "cache"
META = CACHE / "tdx_meta.db"
OUT = CACHE / "name_history.db"


def is_st_name(name: str) -> int:
    """简称里是否带 ST / *ST 前缀（含 S*ST / SST / G*ST 变体）"""
    s = (name or "").upper().replace(" ", "")
    core = s[1:] if s.startswith("G") else s    # 去掉股改 G 前缀
    core = core[1:] if core.startswith("S") and "ST" in core else core
    return 1 if "ST" in core else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sleep", type=float, default=0.15)
    args = ap.parse_args()
    t0 = time.time()

    con = sqlite3.connect(str(OUT))
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
    print(f"universe {len(codes):,} | 已完成 {len(done):,} | 待抓 {len(todo):,}")

    ok = fail = n_names = 0
    for i, code in enumerate(todo, 1):
        six = code[:6]
        try:
            df = ak.stock_info_change_name(symbol=six)
            recs = []
            if df is not None and len(df) > 0:
                for seq, (_, row) in enumerate(df.iterrows(), start=1):
                    nm = str(row.get("name") or "").strip()
                    if nm:
                        recs.append((code, seq, nm, is_st_name(nm)))
            with con:
                if recs:
                    con.executemany("INSERT OR REPLACE INTO name_change VALUES (?,?,?,?)", recs)
                    con.execute("INSERT OR REPLACE INTO fetch_log VALUES (?,?,?,?)",
                                (code, len(recs), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "ok"))
                    n_names += len(recs)
                else:
                    con.execute("INSERT OR REPLACE INTO fetch_log VALUES (?,?,?,?)",
                                (code, 0, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "empty"))
            ok += 1
        except Exception as exc:  # noqa: BLE001
            fail += 1
            with con:
                con.execute("INSERT OR REPLACE INTO fetch_log VALUES (?,?,?,?)",
                            (code, 0, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                             f"err:{type(exc).__name__}:{str(exc)[:50]}"))
        if i % 50 == 0 or i == len(todo):
            el = time.time() - t0
            rate = ok / i * 100
            print(f"  [{i}/{len(todo)}] ok={ok}({rate:.0f}%) fail={fail} names={n_names:,} "
                  f"{el:.0f}s ({el/i:.2f}s/只)", flush=True)
        time.sleep(args.sleep)

    n = con.execute("SELECT COUNT(*) FROM name_change").fetchone()[0]
    c = con.execute("SELECT COUNT(DISTINCT code) FROM name_change").fetchone()[0]
    st_codes = con.execute("SELECT COUNT(DISTINCT code) FROM name_change WHERE is_st_flag=1").fetchone()[0]
    print(f"\n完成: {n:,} 条名称记录 / {c:,} 只 / 其中曾出现 ST 简称的 {st_codes:,} 只")
    print(f"库: {OUT}  ({OUT.stat().st_size/1024/1024:.1f} MB)")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
