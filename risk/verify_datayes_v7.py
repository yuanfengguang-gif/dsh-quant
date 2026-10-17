# -*- coding: utf-8 -*-
"""risk/verify_datayes_v7.py —— ST 标记验证 + 行情最早边界"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}


def call(url, timeout=60):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, {"_error": f"HTTP {e.code}: {e.read().decode('utf-8')[:300]}"}
    except Exception as e:
        return -1, {"_error": f"{type(e).__name__}: {e}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default=os.environ.get("DATAYES_TOKEN"))
    args = ap.parse_args()
    HEADERS["Authorization"] = f"Bearer {args.token}"

    # H1 上市股全量，统计 secShortName 含 ST 的数量
    url = ("https://gw.datayes.com/aladdin_proxy/data_api/api/master/getSecID.json"
           "?assetClass=E&listStatusCD=L")
    status, r = call(url)
    data = r.get("data", []) if isinstance(r, dict) else []
    if isinstance(data, list) and data:
        st = [d for d in data if "ST" in str(d.get("secShortName", "")).upper()]
        print(f"H1 上市股 listStatusCD=L: HTTP {status}, 共 {len(data)} 只")
        print(f"   其中 secShortName 含 ST 的有 {len(st)} 只")
        for d in st[:10]:
            print(f"     {d.get('ticker')} {d.get('secShortName')}")
    else:
        print(f"H1 上市股: HTTP {status}, 数据={json.dumps(r, ensure_ascii=False)[:300]}")

    # H2 行情最早边界：2010 / 2015
    for begin, end in [("20100104", "20100108"), ("20150105", "20150109")]:
        url = ("https://gw.datayes.com/aladdin_proxy/data_api/api/market/getMktEqud.json"
               f"?ticker=600519&beginDate={begin}&endDate={end}"
               "&field=ticker,tradeDate,closePrice")
        status, r = call(url)
        data = r.get("data", []) if isinstance(r, dict) else []
        n = len(data) if isinstance(data, list) else 0
        print(f"H2 行情 {begin}~{end}: HTTP {status}, {n} 条")


if __name__ == "__main__":
    main()
