# -*- coding: utf-8 -*-
"""risk/fetch_datayes_sample.py —— 分年份抽样下载通联数据（精准控制行数）用于三方对比

设计：3 只股票 × 5 个年份 × 1 个月（约20交易日）= 约 300 行
额度保护：每批后打印累计行数；遇 402 立即停止。
"""
import argparse
import json
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = Path(__file__).resolve().parent.parent
cfg = yaml.safe_load((BASE / "config" / "params.yaml").read_text(encoding="utf-8"))
H = {"Authorization": f"Bearer {cfg['data']['datayes_token']}", "Accept": "application/json"}
EQUID = "https://gw.datayes.com/aladdin_proxy/data_api/api/market/getMktEqud.json"
DB = BASE / "data" / "cache" / "datayes_sample.db"

# 3 只股票 × 5 个年份的月份（分散在不同年代）
SAMPLES = [
    ("2008", "200806"),
    ("2013", "201306"),
    ("2018", "201806"),
    ("2023", "202306"),
    ("2026", "202601"),
]
CODES = ["000001", "600519", "000002"]
FIELDS = ("ticker,tradeDate,openPrice,highestPrice,lowestPrice,closePrice,"
          "actPreClosePrice,chgPct,turnoverVol,turnoverValue,turnoverRate,accumAdjFactor")


def call(url, timeout=90):
    req = urllib.request.Request(url, headers=H)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            b = r.read()
            return r.status, json.loads(b.decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, {"_error": e.read().decode("utf-8")[:200]}
    except Exception as e:
        return -1, {"_error": f"{type(e).__name__}: {e}"}


def month_range(ym):
    """YYYYMM -> (beginDate, endDate)"""
    y, m = int(ym[:4]), int(ym[4:])
    import calendar
    last = calendar.monthrange(y, m)[1]
    return f"{ym}01", f"{ym}{last:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-rows", type=int, default=520)
    args = ap.parse_args()

    con = sqlite3.connect(str(DB))
    con.execute("""CREATE TABLE IF NOT EXISTS datayes_bar (
        ticker TEXT, tradeDate TEXT, openPrice REAL, highestPrice REAL, lowestPrice REAL,
        closePrice REAL, actPreClosePrice REAL, chgPct REAL, turnoverVol REAL,
        turnoverValue REAL, turnoverRate REAL, accumAdjFactor REAL,
        PRIMARY KEY (ticker, tradeDate))""")
    con.commit()

    total = 0
    print(f"抽样：{len(CODES)} 只 × {len(SAMPLES)} 个年份")
    for year, ym in SAMPLES:
        b, e = month_range(ym)
        print(f"\n=== {year}（{b} ~ {e}）===")
        for tk in CODES:
            if total >= args.max_rows:
                print(f"  已达行数上限 {args.max_rows}，停止")
                return finish(con, total)
            url = EQUID + "?" + urllib.parse.urlencode(
                {"ticker": tk, "beginDate": b, "endDate": e, "field": FIELDS})
            s, r = call(url)
            if s != 200:
                msg = json.dumps(r, ensure_ascii=False)[:120]
                print(f"  {tk}: HTTP {s} {msg}")
                if "402" in msg or "额度" in msg:
                    print("  ⚠️ 额度耗尽，停止")
                    return finish(con, total)
                time.sleep(0.5)
                continue
            data = r.get("data", [])
            if not isinstance(data, list):
                data = []
            rows = []
            for d in data:
                rows.append((
                    d.get("ticker"), d.get("tradeDate"), d.get("openPrice"),
                    d.get("highestPrice"), d.get("lowestPrice"), d.get("closePrice"),
                    d.get("actPreClosePrice"), d.get("chgPct"), d.get("turnoverVol"),
                    d.get("turnoverValue"), d.get("turnoverRate"), d.get("accumAdjFactor"),
                ))
            if rows:
                con.executemany("INSERT OR REPLACE INTO datayes_bar VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
                con.commit()
            total += len(rows)
            print(f"  {tk}: {len(rows)} 行（累计 {total}）", flush=True)
            time.sleep(0.15)
    finish(con, total)


def finish(con, total):
    n = con.execute("SELECT COUNT(*) FROM datayes_bar").fetchone()[0]
    tk = con.execute("SELECT MIN(tradeDate), MAX(tradeDate) FROM datayes_bar").fetchone()
    con.close()
    print(f"\n{'='*56}")
    print(f"通联抽样完成：本次新增 {total} 行，库内累计 {n} 行")
    print(f"日期范围：{tk[0]} ~ {tk[1]}")
    print(f"库：{DB}")
    print(f"{'='*56}")


if __name__ == "__main__":
    main()
