# -*- coding: utf-8 -*-
"""data/fetch_rzrq_em.py —— 融资融券（两融）明细补拉（东财 datacenter，零 key）

reportName=RPTA_WEB_RZRQ_GGMX（融资融券个股明细），逐股拉历史（含融资余额/融资买入/融券余额/两融余额）。
东财防封：串行 + 每次 ≥1s 间隔 + 复用会话 + UA。
断点续传：logs/rzrq_progress.txt

用法：python data/fetch_rzrq_em.py [--limit N]
"""
import sqlite3
import sys
import time
from pathlib import Path

import pandas as pd
import requests

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
PROGRESS = BASE / "logs" / "rzrq_progress.txt"
MIN_INTERVAL = 1.0

_session = None


def _em_get(params):
    global _session
    if _session is None:
        _session = requests.Session()
    time.sleep(MIN_INTERVAL)
    r = _session.get(URL, params=params, headers={"User-Agent": UA, "Referer": "https://data.eastmoney.com/"}, timeout=20)
    r.raise_for_status()
    return r.json()


def fetch_one(code6, max_pages=10):
    """单股两融明细 → DataFrame。code6 纯 6 位。"""
    rows, page = [], 1
    while page <= max_pages:
        payload = _em_get({"reportName": "RPTA_WEB_RZRQ_GGMX", "columns": "ALL",
                           "source": "WEB", "client": "WEB", "sortColumns": "DATE",
                           "sortTypes": "-1", "pageNumber": str(page), "pageSize": "500",
                           "filter": f"(scode={code6})"})
        if payload.get("code") != 0 or not payload.get("result"):
            break
        result = payload["result"]
        data = result.get("data") or []
        rows.extend(data)
        pages = result.get("pages", 1)
        if page >= pages or not data:
            break
        page += 1
    return pd.DataFrame(rows)


def load_codes():
    con = sqlite3.connect(str(BASE / "data" / "cache" / "stock_basic.db"))
    codes = [r[0].split(".")[0].zfill(6) for r in con.execute(
        "SELECT code FROM stock_basic WHERE code LIKE '%.SH' OR code LIKE '%.SZ'").fetchall()]
    con.close()
    return codes


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    codes = load_codes()
    if args.limit:
        codes = codes[:args.limit]
    done = set()
    if PROGRESS.exists():
        done = {l.strip() for l in PROGRESS.read_text(encoding="utf-8").splitlines() if l.strip()}
    todo = [c for c in codes if c not in done]
    print(f"待拉 {len(todo)} 只（已完成 {len(done)}）", flush=True)

    con = sqlite3.connect(str(BASE / "data" / "cache" / "rzrq.db"))
    con.execute("""CREATE TABLE IF NOT EXISTS rzrq (
        code TEXT, date TEXT, rzye REAL, rzmre REAL, rqye REAL, rzrqye REAL,
        PRIMARY KEY(code, date))""")
    con.commit()
    n_ok = n_rows = 0
    t0 = time.time()
    for i, code in enumerate(todo):
        try:
            df = fetch_one(code)
            if not df.empty:
                # 东财字段名可能带中文/英文，取关键列
                def col(*names):
                    for n in names:
                        if n in df.columns:
                            return n
                    return None
                c_date = col("DATE", "date")
                c_rzye = col("RZYE", "rzye", "融资余额")
                c_rzmre = col("RZMRE", "rzmre", "融资买入额")
                c_rqye = col("RQYE", "rqye", "融券余额")
                c_rzrqye = col("RZRQYE", "rzrqye", "融资融券余额")
                out = df[[c_date, c_rzye, c_rzmre, c_rqye, c_rzrqye]].copy() if all(
                    x for x in [c_date, c_rzye]) else pd.DataFrame()
                if not out.empty:
                    out.columns = ["date", "rzye", "rzmre", "rqye", "rzrqye"]
                    out["code"] = code
                    out = out[["code", "date", "rzye", "rzmre", "rqye", "rzrqye"]]
                    out["date"] = out["date"].astype(str).str[:10]
                    out.to_sql("rzrq", con, if_exists="append", index=False)
                    con.commit()
                    n_rows += len(out)
            n_ok += 1
            with open(PROGRESS, "a", encoding="utf-8") as f:
                f.write(code + "\n")
        except Exception as e:
            print(f"  {code} 失败: {str(e)[:70]}", flush=True)
        if (i + 1) % 50 == 0:
            el = (time.time() - t0) / 60
            print(f"  进度 {i+1}/{len(todo)}，{n_rows} 行，{el:.1f} 分钟，{n_ok/el:.1f} 只/分", flush=True)
    con.close()
    print(f"完成: {n_ok}/{len(todo)}，{n_rows} 行", flush=True)


if __name__ == "__main__":
    main()
