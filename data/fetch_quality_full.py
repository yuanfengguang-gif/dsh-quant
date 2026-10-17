# -*- coding: utf-8 -*-
"""
data/fetch_quality_full.py — 全历史财务质量抓取（F-Score 数据基础，修正版）

相对原 data/fetch_quality.py 的修正（2026-10-13 对 baostock 实测核实）：
1. 缩放口径：baostock 实测返回小数（roeAvg=0.331177=33.12%，对应茅台 2019 加权 ROE 33.09%），
   原脚本统一 /100 是错的（会再小 100 倍）→ 本脚本原样存小数。
   同理 gpMargin/npMargin/liabilityToAsset 均原样存小数；currentRatio/cfo 系列本就是倍率，不缩放。
2. 现金流字段索引：原脚本 cfoToNP=d[7] / cfoToOR=d[6] 错位。实测 query_cash_flow_data 字段序：
   [code, pubDate, statDate, CAToAsset, NCAToAsset, tangibleAssetToAsset, ebitToInterest(6),
    CFOToOR(7), CFOToNP(8), CFOToGr(9)] → 本脚本 cfo_to_or=d[7]、cfo_to_np=d[8]。
3. 时间窗：原 6 季（2025Q1-2026Q2）扩为 2018Q1-2026Q2（34 季），覆盖 2019+ 回测同比判断。
4. 季度对齐：用 statDate 作键，避免原脚本 rows[-1] 在利润表缺某季时错位挂到上一季。

baostock 三接口（免费无限频，多进程拉取，每进程独立登录）：
  query_profit_data    → roeAvg / npMargin / gpMargin
  query_balance_data   → currentRatio / liabilityToAsset
  query_cash_flow_data → CFOToOR / CFOToNP

落表 data/cache/finance_quality.db / quality：
  code, period, roe_avg, gp_margin, np_margin, current_ratio,
  liability_to_asset, cfo_to_np, cfo_to_or, pub_date
断点续传：logs/quality_full_progress.txt；失败清单 logs/quality_full_failed.csv

用法：
  python data/fetch_quality_full.py [--dry-run] [--limit N]
"""
import argparse
import csv
import multiprocessing
import os
import sqlite3
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
for k in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]:
    os.environ.pop(k, None)

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

QD_DB = Path(r"data/cache/finance_quality.db")
PROGRESS = BASE / "logs" / "quality_full_progress.txt"
FAILED = BASE / "logs" / "quality_full_failed.csv"

# 2018Q1 - 2026Q2（34 季），保证 2019 年起有上年同期可比
START = (2018, 1)
END = (2026, 2)
QUARTERS = []
_y, _q = START
while (_y, _q) <= END:
    QUARTERS.append((str(_y), _q))
    _q += 1
    if _q > 4:
        _q = 1
        _y += 1

N_WORKERS = 4
RATE = 0.05


def _conn():
    con = sqlite3.connect(str(QD_DB))
    con.execute("""CREATE TABLE IF NOT EXISTS quality (
        code TEXT, period TEXT, roe_avg REAL, gp_margin REAL, np_margin REAL,
        current_ratio REAL, liability_to_asset REAL, cfo_to_np REAL, cfo_to_or REAL,
        pub_date TEXT, PRIMARY KEY(code, period))""")
    con.commit()
    return con


def load_codes():
    con = sqlite3.connect(r"data/cache/stock_basic.db")
    codes = [r[0] for r in con.execute(
        "SELECT code FROM stock_basic WHERE code LIKE '%.SH' OR code LIKE '%.SZ'").fetchall()]
    con.close()
    return codes


def _fetch_worker(job):
    """子进程：独立登录，按季度拉 3 接口；statDate 作键对齐。"""
    code = job
    try:
        import baostock as bs
        lg = bs.login()
        if lg.error_code != "0":
            return code, None, f"login fail"
        rec = {}  # statDate -> {field: value}
        for year, quarter in QUARTERS:
            rs = bs.query_profit_data(code=code, year=year, quarter=quarter)
            if rs.error_code == "0" and rs.next():
                d = rs.get_row_data()
                rec[d[2]] = {"pubDate": d[1], "statDate": d[2],
                             "roeAvg": d[3], "npMargin": d[4], "gpMargin": d[5]}
            rs = bs.query_balance_data(code=code, year=year, quarter=quarter)
            if rs.error_code == "0" and rs.next():
                d = rs.get_row_data()
                if d[2] in rec:
                    rec[d[2]]["currentRatio"] = d[3]
                    rec[d[2]]["liabilityToAsset"] = d[7]
            rs = bs.query_cash_flow_data(code=code, year=year, quarter=quarter)
            if rs.error_code == "0" and rs.next():
                d = rs.get_row_data()
                if d[2] in rec:
                    rec[d[2]]["cfoToOR"] = d[7]   # CFOToOR
                    rec[d[2]]["cfoToNP"] = d[8]   # CFOToNP
        bs.logout()
        time.sleep(RATE)
        return code, list(rec.values()), None
    except Exception as e:
        return code, None, str(e)[:80]


def run(dry_run=False, limit=None):
    codes = load_codes()
    if limit:
        codes = codes[:limit]
    print(f"质量数据待拉 {len(codes)} 只 × {len(QUARTERS)} 季 × 3 接口（dry_run={dry_run}）", flush=True)
    done = set()
    if PROGRESS.exists():
        done = {l.strip() for l in PROGRESS.read_text(encoding="utf-8").splitlines() if l.strip()}
    todo = [c for c in codes if c not in done]
    print(f"已完成 {len(done)}，待处理 {len(todo)}", flush=True)

    if dry_run:
        for c in todo[:3]:
            code, rows, err = _fetch_worker(c)
            if rows:
                print(f"  {code}: {len(rows)} 季，样本 {rows[0]}", flush=True)
            else:
                print(f"  {code}: 失败 {err}", flush=True)
        return

    con = _conn()
    n_ok = n_rows = consecutive_fail = 0
    failed = []
    start_ts = time.time()
    with multiprocessing.Pool(N_WORKERS) as pool:
        for code, rows, err in pool.imap_unordered(_fetch_worker, todo, chunksize=4):
            if err or not rows:
                consecutive_fail += 1
                failed.append((code, err or "empty"))
                if consecutive_fail % 20 == 0:
                    print(f"  连续失败 {consecutive_fail}（累计 {len(failed)}），继续…", flush=True)
                continue
            try:
                recs = []
                for r in rows:
                    # ★原样存小数（baostock 已返回小数，不再 /100）
                    recs.append((code, _s(r.get("statDate")),
                                 _f(r.get("roeAvg")),
                                 _f(r.get("gpMargin")),
                                 _f(r.get("npMargin")),
                                 _f(r.get("currentRatio")),
                                 _f(r.get("liabilityToAsset")),
                                 _f(r.get("cfoToNP")),
                                 _f(r.get("cfoToOR")),
                                 _s(r.get("pubDate"))))
                con.executemany("INSERT OR REPLACE INTO quality VALUES (?,?,?,?,?,?,?,?,?,?)", recs)
                con.commit()
                n_ok += 1
                n_rows += len(recs)
                consecutive_fail = 0
                with open(PROGRESS, "a", encoding="utf-8") as pf:
                    pf.write(code + "\n")
                if n_ok % 100 == 0:
                    el = (time.time() - start_ts) / 60
                    print(f"进度 {n_ok}/{len(todo)}，{n_rows} 行，{el:.1f} 分钟，"
                          f"速度 {n_ok/el:.1f} 只/分", flush=True)
            except Exception as e:
                failed.append((code, str(e)[:80]))
    if failed:
        with open(FAILED, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["code", "reason"])
            w.writerows(failed)
        print(f"失败清单: {FAILED}（{len(failed)} 只，重跑本脚本自动续传）", flush=True)
    total = con.execute("SELECT COUNT(*) FROM quality").fetchone()[0]
    nstk = con.execute("SELECT COUNT(DISTINCT code) FROM quality").fetchone()[0]
    con.close()
    print(f"完成: {n_ok} 只成功 / {n_rows} 行入库 | 累计 {nstk} 只 / {total} 行 | {QD_DB}", flush=True)


def _f(v):
    try:
        return float(v) if v not in ("", None) else None
    except Exception:
        return None


def _s(v):
    if v is None:
        return ""
    s = str(v)
    return "" if s in ("nan", "None", "NaT", "NaN") else s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    run(dry_run=args.dry_run, limit=args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
