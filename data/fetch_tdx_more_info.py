# -*- coding: utf-8 -*-
"""data/fetch_tdx_more_info.py —— 通达信 more_info(92 字段) + relation(板块归属) 每日快照

背景（CORE_ISSUE_TRACKER 9.18 C-2）：
  `get_more_info` 返回 92 个字段的**当日快照**（多周期动量 ZAFPre5/10/20/60、市值 Ltsz/Zsz(亿元)、
  估值 DynaPE/PB_MRQ/DYRatio、资金流 Zjl/Wtb、涨跌停价、自由流通股本、事件日期…），
  但**没有历史序列** → 必须每日落一份，时间越早开始越好。
  `get_relation` 返回该股所属 19 个板块（地区/概念/风格/行业，含「高分红股」「基金重仓」「北向重仓」「MSCI成份」等现成风格标签）。

输出：data/cache/tdx_snapshot.db
      more_info(snapshot_date, code, <92 列自动建表>)   ← 宽表，便于直接查
      relation(snapshot_date, code, block_code, block_name, block_type)
      fetch_log(snapshot_date, code, n_fields, n_blocks, run_at, status)

用法：
  python data/fetch_tdx_more_info.py --limit 20   # 试点
  python data/fetch_tdx_more_info.py              # 全市场（同日重复跑会覆盖）
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

CACHE = Path(__file__).resolve().parent.parent / "data" / "cache"
META = CACHE / "tdx_meta.db"
OUT = CACHE / "tdx_snapshot.db"


def ensure_wide(con, keys):
    """按首条返回的字段集建宽表（缺列自动 ALTER）"""
    con.execute("""CREATE TABLE IF NOT EXISTS more_info (
        snapshot_date TEXT, code TEXT, PRIMARY KEY (snapshot_date, code))""")
    have = {r[1] for r in con.execute("PRAGMA table_info(more_info)")}
    for k in keys:
        if k not in have:
            con.execute(f'ALTER TABLE more_info ADD COLUMN "{k}" REAL')
    con.commit()
    return [k for k in keys if k in {r[1] for r in con.execute("PRAGMA table_info(more_info)")}]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sleep", type=float, default=0.02)
    args = ap.parse_args()
    t0 = time.time()
    today = datetime.now().strftime("%Y-%m-%d")

    con = sqlite3.connect(str(OUT))
    con.execute("PRAGMA synchronous=OFF")
    con.execute("""CREATE TABLE IF NOT EXISTS relation (
        snapshot_date TEXT, code TEXT, block_code TEXT, block_name TEXT,
        block_type TEXT, PRIMARY KEY (snapshot_date, code, block_code))""")
    con.execute("""CREATE TABLE IF NOT EXISTS fetch_log (
        snapshot_date TEXT, code TEXT, n_fields INTEGER, n_blocks INTEGER,
        run_at TEXT, status TEXT, PRIMARY KEY (snapshot_date, code))""")
    con.commit()

    meta = sqlite3.connect(f"file:{META.as_posix()}?mode=ro", uri=True, timeout=10)
    codes = [r[0] for r in meta.execute("SELECT code FROM universe ORDER BY code")]
    meta.close()
    if args.limit:
        codes = codes[: args.limit]
    print(f"待抓 {len(codes):,} 只 → {OUT}（snapshot_date={today}）")

    cols = None
    ok = fail = 0
    n_blocks = 0
    for i, code in enumerate(codes, 1):
        try:
            mi = tqs.get_more_info(stock_code=code)
            if not isinstance(mi, dict) or not mi:
                raise ValueError("empty more_info")
            keys = [k for k, v in mi.items() if v is not None and not isinstance(v, (list, dict))]
            if cols is None:
                cols = ensure_wide(con, keys)
                print(f"  建表：{len(cols)} 个数值字段")
            row = {"snapshot_date": today, "code": code}
            for k in cols:
                v = mi.get(k)
                try:
                    row[k] = float(v) if v not in (None, "", "--", "-") else None
                except (TypeError, ValueError):
                    row[k] = None
            use = [c for c in cols]
            con.execute(
                f'INSERT OR REPLACE INTO more_info (snapshot_date, code, {", ".join(chr(34)+c+chr(34) for c in use)}) '
                f'VALUES (?, ?, {", ".join("?"*len(use))})',
                [today, code] + [row[c] for c in use])

            rel = tqs.get_relation(stock_code=code) or []
            recs = [(today, code, x.get("BlockCode"), x.get("BlockName"), x.get("BlockType"))
                    for x in rel if isinstance(x, dict)]
            if recs:
                con.executemany("INSERT OR REPLACE INTO relation VALUES (?,?,?,?,?)", recs)
                n_blocks += len(recs)
            con.execute("INSERT OR REPLACE INTO fetch_log VALUES (?,?,?,?,?,?)",
                        (today, code, len(use), len(recs),
                         datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "ok"))
            con.commit()
            ok += 1
        except Exception as exc:  # noqa: BLE001
            fail += 1
            con.execute("INSERT OR REPLACE INTO fetch_log VALUES (?,?,?,?,?,?)",
                        (today, code, 0, 0, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                         f"err:{str(exc)[:60]}"))
            con.commit()
        if i % 200 == 0 or i == len(codes):
            el = time.time() - t0
            print(f"  [{i}/{len(codes)}] ok={ok} fail={fail} blocks={n_blocks:,} "
                  f"{el:.0f}s ({el/i:.2f}s/只)", flush=True)
        time.sleep(args.sleep)

    n = con.execute("SELECT COUNT(*) FROM more_info WHERE snapshot_date=?", (today,)).fetchone()[0]
    b = con.execute("SELECT COUNT(*) FROM relation WHERE snapshot_date=?", (today,)).fetchone()[0]
    print(f"\n完成：more_info {n:,} 行 / relation {b:,} 行 / 字段 {len(cols or []):,} 个")
    print(f"库: {OUT}  ({OUT.stat().st_size/1024/1024:.1f} MB)")

    print("\n关键字段抽样（600519.SH）:")
    for f in ("Ltsz", "Zsz", "DynaPE", "PB_MRQ", "DYRatio", "fHSL",
              "ZAFPre5", "ZAFPre20", "ZAFPre60", "Zjl", "FreeLtgb", "ZTPrice"):
        r = con.execute(f'SELECT "{f}" FROM more_info WHERE snapshot_date=? AND code=?',
                        (today, "600519.SH")).fetchone()
        print(f"   {f:12s} = {r[0] if r else None}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
