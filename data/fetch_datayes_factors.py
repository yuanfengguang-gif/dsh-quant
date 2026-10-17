# -*- coding: utf-8 -*-
"""data/fetch_datayes_factors.py —— 下载通联精品因子（Lite 30 精选）到本地

按 tradeDate 逐日拉全市场，保存到 SQLite（data/cache/datayes_factors.db，表 datayes_fancy_lite）。
支持断点续传 + 限流（10次/秒）+ 每日 2000 次调用保护。

用法：
  python data/fetch_datayes_factors.py --start 2019-01-01 --end 2019-01-31   # 下载指定区间
  python data/fetch_datayes_factors.py --days 5                               # 只下载最近 5 个交易日（测试）
"""
import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}
LITE_URL = "https://gw.datayes.com/aladdin_proxy/data_api/api/market/getEquFancyFactors.json"
DB = BASE / "data" / "cache" / "datayes_factors.db"
BAR_DB = BASE / "data" / "cache" / "bars.db"
PAGESIZE = 1000


def load_token():
    import yaml
    cfg = yaml.safe_load((BASE / "config" / "params.yaml").read_text(encoding="utf-8")) or {}
    return (cfg.get("data") or {}).get("datayes_token") or os.environ.get("DATAYES_TOKEN") or ""


def call(url, timeout=90):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        return {"_error": f"HTTP {e.code}: {body[:200]}"}
    except Exception as e:
        return {"_error": f"{type(e).__name__}: {e}"}


def fetch_day(trade_date):
    trade_date = trade_date.replace("-", "")  # DataYes 要求 YYYYMMDD
    rows = []
    pagenum = 1
    while True:
        url = LITE_URL + "?" + urllib.parse.urlencode(
            {"tradeDate": trade_date, "pagenum": pagenum, "pagesize": PAGESIZE})
        r = call(url)
        if "_error" in r:
            return None, r["_error"]
        if r.get("retCode") not in (1, None) and "data" not in r:
            return None, json.dumps(r, ensure_ascii=False)[:200]
        data = r.get("data", [])
        if not data:
            break
        rows.extend(data)
        if len(data) < PAGESIZE:
            break
        pagenum += 1
        time.sleep(0.15)
    return rows, None


def trade_dates(start, end):
    con = sqlite3.connect(str(BAR_DB))
    if end:
        dates = [r[0] for r in con.execute(
            "SELECT DISTINCT date FROM daily_bar WHERE date>=? AND date<=? ORDER BY date", (start, end))]
    else:
        dates = [r[0] for r in con.execute(
            "SELECT DISTINCT date FROM daily_bar WHERE date>=? ORDER BY date", (start,))]
    con.close()
    return dates


def get_table_cols(con):
    try:
        cols = [r[1] for r in con.execute("PRAGMA table_info(datayes_fancy_lite)")]
        return cols
    except Exception:
        return []


def ensure_table(con, factor_cols):
    cols = ["tradeDate TEXT", "ticker TEXT"] + [f'"{c}" REAL' for c in factor_cols]
    con.execute(f"CREATE TABLE IF NOT EXISTS datayes_fancy_lite ({', '.join(cols)})")
    con.execute("CREATE INDEX IF NOT EXISTS idx_fancy_date ON datayes_fancy_lite(tradeDate)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_fancy_ticker ON datayes_fancy_lite(ticker)")
    con.commit()


def insert_day(con, trade_date, rows):
    if not rows:
        return 0
    # 动态确定因子列（排除 ticker/tradeDate/secID 等标识列）
    id_cols = {"ticker", "tradeDate", "secID", "exchangeCD", "secShortName", "partyID"}
    factor_cols = [k for k in rows[0].keys() if k not in id_cols]
    existing = get_table_cols(con)
    if not existing or set(existing) != set(["tradeDate", "ticker"] + factor_cols):
        ensure_table(con, factor_cols)
    cols = ["tradeDate", "ticker"] + factor_cols
    vals = []
    for r in rows:
        row = [trade_date, r.get("ticker")]
        for c in factor_cols:
            v = r.get(c)
            row.append(None if v is None else float(v))
        vals.append(row)
    con.executemany(
        f"INSERT OR REPLACE INTO datayes_fancy_lite ({', '.join('\"'+c+'\"' for c in cols)}) "
        f"VALUES ({', '.join('?' * len(cols))})", vals)
    con.commit()
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2019-01-01")
    ap.add_argument("--end", default=None, help="结束日期（含），默认到今天")
    ap.add_argument("--days", type=int, default=0, help="只下载最近 N 个交易日（测试用，覆盖 start/end）")
    args = ap.parse_args()

    token = load_token()
    if not token:
        print("❌ 未找到 token（config/params.yaml 的 data.datayes_token）")
        sys.exit(2)
    HEADERS["Authorization"] = f"Bearer {token}"

    dates = trade_dates(args.start, args.end)
    if args.days > 0:
        dates = dates[-args.days:]
    print(f"交易日 {len(dates)} 个：{dates[0] if dates else '无'} ~ {dates[-1] if dates else '无'}", flush=True)

    con = sqlite3.connect(str(DB))
    try:
        done = {r[0] for r in con.execute("SELECT DISTINCT tradeDate FROM datayes_fancy_lite")}
    except sqlite3.OperationalError:
        done = set()
    todo = [d for d in dates if d not in done]
    print(f"已下载 {len(done)} 天，待下载 {len(todo)} 天", flush=True)

    total_rows = 0
    calls = 0
    for i, d in enumerate(todo):
        rows, err = fetch_day(d)
        calls += 1
        if err:
            if "402" in err or "额度" in err or "订单额度" in err:
                print(f"  ⚠️ {d} 额度用尽（{err[:80]}），停止", flush=True)
                break
            print(f"  ⚠️ {d} 错误: {err[:100]}，跳过", flush=True)
            time.sleep(0.5)
            continue
        n = insert_day(con, d, rows)
        total_rows += n
        print(f"  [{i+1}/{len(todo)}] {d}: {n} 行（累计 {total_rows} 行，调用 {calls} 次）", flush=True)
        time.sleep(0.15)
        if calls % 1800 == 0:
            print("  接近每日 2000 次调用上限，休息 60s…", flush=True)
            time.sleep(60)

    con.close()
    print(f"\n完成：共下载 {total_rows} 行，调用 {calls} 次", flush=True)


if __name__ == "__main__":
    main()
