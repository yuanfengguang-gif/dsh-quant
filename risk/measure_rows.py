# -*- coding: utf-8 -*-
"""risk/measure_rows.py —— 下载指定行数的行情，精确测算单价"""
import argparse
import json
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = Path(r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant")
cfg = yaml.safe_load((BASE / "config" / "params.yaml").read_text(encoding="utf-8"))
H = {"Authorization": f"Bearer {cfg['data']['datayes_token']}", "Accept": "application/json"}
MARKET = "https://gw.datayes.com/aladdin_proxy/data_api/api/market/getMktEqud.json"


def call(url):
    req = urllib.request.Request(url, headers=H)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            b = r.read()
            return r.status, json.loads(b.decode("utf-8")), len(b)
    except urllib.error.HTTPError as e:
        b = e.read()
        return e.code, {"_error": b.decode("utf-8")[:150]}, len(b)


ap = argparse.ArgumentParser()
ap.add_argument("--rows", type=int, default=3000)
ap.add_argument("--date", default=None)
args = ap.parse_args()

con = sqlite3.connect(str(BASE / "data" / "cache" / "bars.db"))
if args.date:
    d = args.date
else:
    d = con.execute("SELECT DISTINCT date FROM daily_bar ORDER BY date DESC LIMIT 1").fetchone()[0]
con.close()
d8 = d.replace("-", "")
print(f"下载 {d} 行情（全字段），目标 {args.rows} 行", flush=True)

total, page, nbytes = 0, 1, 0
while total < args.rows:
    url = MARKET + "?" + urllib.parse.urlencode({"tradeDate": d8, "pagenum": page, "pagesize": 1000})
    s, r, b = call(url)
    nbytes += b
    if s != 200:
        print(f"  第 {page} 页 HTTP {s}: {json.dumps(r, ensure_ascii=False)[:120]}")
        break
    data = r.get("data", [])
    if not data:
        break
    take = min(len(data), args.rows - total)
    total += take
    print(f"  第 {page} 页: +{take} 行（累计 {total}）", flush=True)
    if take < len(data) or total >= args.rows:
        break
    page += 1
    time.sleep(0.15)

out = BASE / "logs" / "cost_measure" / f"rows_{total}.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({"date": d, "rows": total, "bytes": nbytes}, ensure_ascii=False), encoding="utf-8")
print(f"\n{'='*56}")
print(f"总行数：{total:,} 行（响应 {nbytes/1024:.1f} KB）")
print(f"→ 请截图控制台余额，我用「419.40M − 现在余额」算单价")
print(f"{'='*56}")
