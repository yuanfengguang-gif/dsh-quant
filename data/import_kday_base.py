# -*- coding: utf-8 -*-
"""data/import_kday_base.py —— 把「全A日K」27 个年度 zip 导入统一底座库 tdx_base.db

背景（CORE_ISSUE_TRACKER 9.7 / T1a 升级版）：
  本地 `D:\\BaiduNetdiskDownload\\全A日K\\{年}.zip` 内是**每股每年一个 CSV，26 列**，
  不只有未复权 OHLC，还自带：
    turnover(换手率%) / turnover_free / volume_ratio
    pe / pe_ttm / pb / ps / ps_ttm / dv_yield / dv_ttm        ← 估值（valuation.db 的替代）
    total_share / float_share / free_share（万股）            ← 逐日股本（T1b 不再需要 API）
    total_mv / circ_mv（万元）                                ← 市值（hist_mv.db 的替代，含茅台）
  实测单位（与 bars.db 交叉验证，倍数精确为 100/1000/1）：
    volume 文件=手 → ×100 = 股 ；amount 文件=千元 → ×1000 = 元 ；turnover 原样=%

输出：data/cache/tdx_base.db → 表 daily(code,date,...,26 列)，PK(code,date)
      + 表 import_log(year, files, rows, first_date, last_date, run_at)

用法：
  python data/import_kday_base.py --years 2000,2001   # 指定年份
  python data/import_kday_base.py                     # 全部年份（增量：已有年份可 --force 重导）
"""
from __future__ import annotations

import argparse
import csv
import io
import sqlite3
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SRC = Path(r"D:\BaiduNetdiskDownload\全A日K")
BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "data" / "cache" / "tdx_base.db"

COLS = ["open", "high", "low", "close", "pre_close", "change", "pct_chg",
        "volume", "amount", "turnover", "turnover_free", "volume_ratio",
        "pe", "pe_ttm", "pb", "ps", "ps_ttm", "dv_yield", "dv_ttm",
        "total_share", "float_share", "free_share", "total_mv", "circ_mv"]
SQL_COLS = "code, date, " + ", ".join(COLS)

DDL = f"""CREATE TABLE IF NOT EXISTS daily (
    code TEXT, date TEXT, {", ".join(c + " REAL" for c in COLS)},
    PRIMARY KEY (code, date))"""


def fnum(v):
    try:
        x = float(v)
        return x if x == x else None       # NaN → None
    except (TypeError, ValueError):
        return None


def import_year(zp: Path, con: sqlite3.Connection, force: bool) -> dict:
    year = zp.stem
    if not force and con.execute("SELECT 1 FROM import_log WHERE year=?", (year,)).fetchone():
        return {"year": year, "skipped": True}
    t0 = time.time()
    with zipfile.ZipFile(zp) as zf:
        names = [n for n in zf.namelist() if n.endswith(".csv") and not n.startswith("__MACOSX")]
        buf, files, rows, dmin, dmax = [], 0, 0, None, None
        for name in names:
            try:
                txt = zf.read(name).decode("utf-8-sig", errors="replace")
            except Exception:  # noqa: BLE001
                continue
            files += 1
            for row in csv.DictReader(io.StringIO(txt)):
                d = (row.get("datetime") or "").strip()
                code = (row.get("code") or "").strip()
                if not d or not code:
                    continue
                vals = [fnum(row.get(c)) for c in COLS]
                # 单位换算：volume 手→股(×100)；amount 千元→元(×1000)
                i_vol = COLS.index("volume")
                i_amt = COLS.index("amount")
                if vals[i_vol] is not None:
                    vals[i_vol] *= 100.0
                if vals[i_amt] is not None:
                    vals[i_amt] *= 1000.0
                buf.append((code, d, *vals))
                rows += 1
                dmin = d if dmin is None or d < dmin else dmin
                dmax = d if dmax is None or d > dmax else dmax
                if len(buf) >= 50000:
                    con.executemany(f"INSERT OR REPLACE INTO daily VALUES ({','.join('?'*26)})", buf)
                    buf.clear()
        if buf:
            con.executemany(f"INSERT OR REPLACE INTO daily VALUES ({','.join('?'*26)})", buf)
    con.execute("INSERT OR REPLACE INTO import_log VALUES (?,?,?,?,?,?)",
                (year, files, rows, dmin, dmax, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    con.commit()
    return {"year": year, "files": files, "rows": rows, "first": dmin, "last": dmax,
            "secs": round(time.time() - t0, 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default="", help="逗号分隔年份，默认全部")
    ap.add_argument("--force", action="store_true", help="已导入的年份也重导")
    args = ap.parse_args()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(OUT))
    con.execute("PRAGMA journal_mode=MEMORY")
    con.execute("PRAGMA synchronous=OFF")
    con.execute("PRAGMA cache_size=-800000")
    con.execute(DDL)
    con.execute("""CREATE TABLE IF NOT EXISTS import_log (
                     year TEXT PRIMARY KEY, files INTEGER, rows INTEGER,
                     first_date TEXT, last_date TEXT, run_at TEXT)""")
    con.commit()

    zips = sorted(SRC.glob("*.zip"))
    if args.years:
        keep = set(args.years.split(","))
        zips = [z for z in zips if z.stem in keep]
    print(f"待导入 {len(zips)} 个年度 zip → {OUT}")

    t0 = time.time()
    for zp in zips:
        r = import_year(zp, con, args.force)
        if r.get("skipped"):
            print(f"  {r['year']}: 已导入，跳过")
        else:
            print(f"  {r['year']}: {r['files']:,} 文件 / {r['rows']:,} 行  "
                  f"{r['first']}~{r['last']}  {r['secs']}s", flush=True)

    con.execute("CREATE INDEX IF NOT EXISTS idx_daily_date ON daily(date)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_daily_code ON daily(code)")
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM daily").fetchone()[0]
    codes = con.execute("SELECT COUNT(DISTINCT code) FROM daily").fetchone()[0]
    rng = con.execute("SELECT MIN(date), MAX(date) FROM daily").fetchone()
    print(f"\n完成: {n:,} 行 / {codes:,} 只 / {rng[0]} ~ {rng[1]} | 总耗时 {time.time()-t0:.0f}s")
    print(f"库: {OUT}  ({OUT.stat().st_size/1024/1024/1024:.2f} GiB)" if OUT.exists() else "")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
