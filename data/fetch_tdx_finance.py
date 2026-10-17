# -*- coding: utf-8 -*-
"""data/fetch_tdx_finance.py —— 通达信财务数据全量抓取（含披露日 → PIT）

背景（CORE_ISSUE_TRACKER 9.17）：
  `tqs.get_financial_data` 单次调用返回该股**全历史报告期**（实测 100-103 期，2000 至今），
  且自带 `announce_time`（披露日）→ 财务类因子可做真 PIT，不再依赖「报告期+60日延迟」近似。
  字段映射由 CSMAR 交叉验证反推（3 只股票误差 0.0000%）：
      FN001 基本每股收益 | FN004 每股净资产 | FN006 ROE(%) | FN040 总资产
      FN074 营业收入 | FN095 净利润(含少数) | FN096 归母净利润

输出：data/cache/tdx_finance.db
      表 fin_tdx(code, period, tag_date, announce_date, eps, bps, roe, total_assets, revenue, net_profit, np_parent)
      表 fetch_log(code, n_rows, first_period, last_period, run_at, status)
用法：
  python data/fetch_tdx_finance.py --limit 20   # 试点
  python data/fetch_tdx_finance.py              # 全市场（自动续跑）
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
OUT = CACHE / "tdx_finance.db"
F = {"FN001": "eps", "FN004": "bps", "FN006": "roe", "FN040": "total_assets",
     "FN074": "revenue", "FN095": "net_profit", "FN096": "np_parent"}


def fmt(d) -> str:
    s = str(d).split(".")[0].strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s


def fnum(v):
    try:
        x = float(v)
        return x if x == x else None
    except (TypeError, ValueError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sleep", type=float, default=0.03)
    args = ap.parse_args()
    t0 = time.time()

    con = sqlite3.connect(str(OUT))
    con.execute("PRAGMA synchronous=OFF")
    con.execute("""CREATE TABLE IF NOT EXISTS fin_tdx (
        code TEXT, period TEXT, tag_date TEXT, announce_date TEXT,
        eps REAL, bps REAL, roe REAL, total_assets REAL, revenue REAL,
        net_profit REAL, np_parent REAL, PRIMARY KEY (code, period))""")
    con.execute("""CREATE TABLE IF NOT EXISTS fetch_log (
        code TEXT PRIMARY KEY, n_rows INTEGER, first_period TEXT, last_period TEXT,
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

    ok = fail = rows_n = 0
    for i, code in enumerate(todo, 1):
        try:
            r = tqs.get_financial_data([code], list(F), "1999-01-01", "2026-12-31")
            df = r.get(code)
            if df is None or len(df) == 0:
                with con:
                    con.execute("INSERT OR REPLACE INTO fetch_log VALUES (?,?,?,?,?,?)",
                                (code, 0, None, None,
                                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "empty"))
                fail += 1
            else:
                recs = []
                for _, row in df.iterrows():
                    tag = str(row.get("tag_time") or "").split(".")[0]
                    if not tag:
                        continue
                    per = fmt(tag)
                    recs.append((code, per, per, fmt(row.get("announce_time")),
                                 *(fnum(row.get(fn)) for fn in F)))
                if recs:
                    with con:
                        con.executemany(
                            "INSERT OR REPLACE INTO fin_tdx VALUES (?,?,?,?,?,?,?,?,?,?,?)", recs)
                        con.execute("INSERT OR REPLACE INTO fetch_log VALUES (?,?,?,?,?,?)",
                                    (code, len(recs), recs[0][1], recs[-1][1],
                                     datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "ok"))
                    rows_n += len(recs)
                    ok += 1
                else:
                    fail += 1
        except Exception as exc:  # noqa: BLE001
            fail += 1
            with con:
                con.execute("INSERT OR REPLACE INTO fetch_log VALUES (?,?,?,?,?,?)",
                            (code, 0, None, None,
                             datetime.now().strftime("%Y-%m-%d %H:%M:%S"), f"err:{str(exc)[:60]}"))
        if i % 100 == 0 or i == len(todo):
            el = time.time() - t0
            print(f"  [{i}/{len(todo)}] ok={ok} fail={fail} rows={rows_n:,} "
                  f"{el:.0f}s ({el/i:.2f}s/只)", flush=True)
        time.sleep(args.sleep)

    n = con.execute("SELECT COUNT(*) FROM fin_tdx").fetchone()[0]
    c = con.execute("SELECT COUNT(DISTINCT code) FROM fin_tdx").fetchone()[0]
    rng = con.execute("SELECT MIN(period), MAX(period) FROM fin_tdx").fetchone()
    pit = con.execute("SELECT SUM(announce_date IS NOT NULL AND announce_date<>''), COUNT(*) "
                      "FROM fin_tdx").fetchone()
    print(f"\n完成: {n:,} 行 / {c:,} 只 / {rng[0]} ~ {rng[1]} | 披露日覆盖 "
          f"{pit[0]:,}/{pit[1]:,} = {pit[0]/max(pit[1],1)*100:.1f}%")
    print(f"库: {OUT}  ({OUT.stat().st_size/1024/1024:.1f} MB)")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
