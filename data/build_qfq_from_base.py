# -*- coding: utf-8 -*-
"""data/build_qfq_from_base.py —— 从 tdx_base（原始价）+ 后复权因子 生成乘法口径前复权库

背景（CORE_ISSUE_TRACKER 9.15 定案）：
  通达信自带的前复权是「减法式」，累计分红超过原价即转负（茅台 2015 = -55），
  所以 bars.db 里有 673,001 行历史缺失。正确做法是乘法口径：
      qfq(t) = raw(t) × h(t) / h(最新)        （h = 复权因子_后复权.zip 的因子）
  实测：文件 h 与 API 后复权价只差常数 320.26（2010/2020/2026 三点比值 320.08/320.25/320.26）→ 口径自洽。
  无 h 因子的股票（如 430047.BJ）已用 get_divid_factors 验证「无除权事件」→ qfq = raw。

输入：data/cache/tdx_base.db（daily：raw OHLCV/amount/turnover/…）
      D:\\BaiduNetdiskDownload\\复权因子\\复权因子_后复权.zip（每股一个 CSV）
      data/cache/bars.db（用于沿用 is_st）
输出：data/cache/tdx_qfq.db → 表 daily_bar，schema 与 bars.db.daily_bar 完全一致
      （code,date,open,high,low,close,preclose,volume,amount,turn,pct_chg,is_st,adjust,source）

用法：python data/build_qfq_from_base.py [--limit N] [--stocks 600519.SH,000001.SZ]
"""
from __future__ import annotations

import argparse
import bisect
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

BASE = Path(__file__).resolve().parent.parent
CACHE = BASE / "data" / "cache"
SRC = CACHE / "tdx_base.db"
BARS = CACHE / "bars.db"
OUT = CACHE / "tdx_qfq.db"
HFQ = Path(r"D:\BaiduNetdiskDownload\复权因子\复权因子_后复权.zip")

DDL = """CREATE TABLE IF NOT EXISTS daily_bar (
    code TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, preclose REAL,
    volume REAL, amount REAL, turn REAL, pct_chg REAL, is_st INTEGER,
    adjust TEXT, source TEXT, PRIMARY KEY (code, date))"""
COLS = ["open", "high", "low", "close"]


def load_h(zf: zipfile.ZipFile, code: str) -> dict[str, float]:
    name = f"{code}.csv"
    try:
        raw = zf.read(name).decode("utf-8-sig", errors="replace")
    except KeyError:
        return {}
    out = {}
    for row in csv.DictReader(io.StringIO(raw)):
        try:
            out[row["交易日期"].strip()] = float(row["复权因子"])
        except (KeyError, TypeError, ValueError):
            pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--stocks", default="")
    args = ap.parse_args()
    t0 = time.time()

    src = sqlite3.connect(f"file:{SRC.as_posix()}?mode=ro", uri=True, timeout=30)
    bars = sqlite3.connect(f"file:{BARS.as_posix()}?mode=ro", uri=True, timeout=30)
    out = sqlite3.connect(str(OUT))
    out.execute("PRAGMA journal_mode=MEMORY")
    out.execute("PRAGMA synchronous=OFF")
    out.execute("PRAGMA cache_size=-800000")
    out.execute(DDL)
    out.commit()

    codes = [r[0] for r in src.execute("SELECT DISTINCT code FROM daily ORDER BY code")]
    if args.stocks:
        want = set(args.stocks.split(","))
        codes = [c for c in codes if c in want]
    if args.limit:
        codes = codes[: args.limit]
    print(f"待生成 {len(codes):,} 只 → {OUT}")

    n_rows = 0
    no_factor = []
    neg_factor = []
    with zipfile.ZipFile(HFQ) as zf:
        for i, code in enumerate(codes, 1):
            h = load_h(zf, code)
            rows = src.execute(
                "SELECT date, open, high, low, close, volume, amount, turnover "
                "FROM daily WHERE code=? ORDER BY date", (code,)).fetchall()
            if not rows:
                continue
            if h:
                h_last = h[max(h)]
                h_dates = sorted(h)
            else:
                h_last = None
                h_dates = []
                no_factor.append(code)
            # is_st 沿用 bars.db 现状
            st_map = dict(bars.execute(
                "SELECT date, is_st FROM daily_bar WHERE code=? AND adjust='qfq'", (code,)).fetchall())

            def factor_at(date: str) -> float:
                """按日期前向填充因子（因子文件可能缺某些交易日）→ h(date)/h(最新)
                ★负值保护：部分股票（65 只，如 000004.SZ 国华退）分红超过股价，
                  乘法口径的比值本身为负 → 这里取正下限 1e-6，避免出现负价格；
                  同时把这些股票记进 neg_factor 名单，供下游选择剔除。
                """
                if not h_dates:
                    return 1.0
                i = bisect.bisect_right(h_dates, date) - 1
                if i < 0:
                    i = 0
                f = h[h_dates[i]] / h_last
                if f <= 0:
                    if code not in neg_factor:
                        neg_factor.append(code)
                    return 1e-6
                return f

            buf, prev_close = [], None
            for date, o, hi, lo, c, vol, amt, tor in rows:
                f = factor_at(date)
                qc = (c * f) if c is not None else None
                qo = (o * f) if o is not None else None
                qh = (hi * f) if hi is not None else None
                ql = (lo * f) if lo is not None else None
                pc = (qc / prev_close - 1.0) if (qc and prev_close) else None
                buf.append((code, date, qo, qh, ql, qc, prev_close, vol, amt,
                            (tor / 100.0) if tor is not None else None, pc,
                            int(st_map.get(date) or 0), "qfq", "tdx_front_mul"))
                prev_close = qc
            out.executemany(
                "INSERT OR REPLACE INTO daily_bar VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", buf)
            out.commit()
            n_rows += len(buf)
            if i % 200 == 0 or i == len(codes):
                el = time.time() - t0
                print(f"  [{i}/{len(codes)}] {n_rows:,} 行  {el:.0f}s", flush=True)

    out.execute("CREATE INDEX IF NOT EXISTS idx_qfq_date ON daily_bar(date)")
    out.commit()
    n = out.execute("SELECT COUNT(*) FROM daily_bar").fetchone()[0]
    c = out.execute("SELECT COUNT(DISTINCT code) FROM daily_bar").fetchone()[0]
    rng = out.execute("SELECT MIN(date), MAX(date) FROM daily_bar").fetchone()
    print(f"\n完成: {n:,} 行 / {c:,} 只 / {rng[0]} ~ {rng[1]} | 耗时 {time.time()-t0:.0f}s")
    print(f"无因子（qfq=raw）的股票 {len(no_factor)} 只，样例: {no_factor[:10]}")
    print(f"因子含负值（已取 1e-6 下限）的股票 {len(neg_factor)} 只，清单: {neg_factor}")
    if neg_factor:
        out.execute("CREATE TABLE IF NOT EXISTS qfq_negative_factor (code TEXT PRIMARY KEY, note TEXT)")
        out.executemany("INSERT OR REPLACE INTO qfq_negative_factor VALUES (?,?)",
                        [(n, "后复权因子存在非正值，qfq 已按 1e-6 下限处理；建议因子研究剔除") for n in neg_factor])
        out.commit()
    print(f"库: {OUT}  ({OUT.stat().st_size/1024/1024/1024:.2f} GiB)")
    src.close(); bars.close(); out.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
