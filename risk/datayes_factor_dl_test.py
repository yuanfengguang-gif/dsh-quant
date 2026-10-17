# -*- coding: utf-8 -*-
"""risk/datayes_factor_dl_test.py —— 实测因子数据下载粒度与数据量"""
import argparse
import json
import os
import sys
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}


def call(url, timeout=90):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            return r.status, json.loads(body.decode("utf-8")), len(body)
    except urllib.error.HTTPError as e:
        body = e.read()
        return e.code, {"_error": f"HTTP {e.code}: {body.decode('utf-8')[:300]}"}, len(body)
    except Exception as e:
        return -1, {"_error": f"{type(e).__name__}: {e}"}, 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default=os.environ.get("DATAYES_TOKEN"))
    args = ap.parse_args()
    HEADERS["Authorization"] = f"Bearer {args.token}"

    # 1. 精品因子 tradeDate 全市场一天
    url = ("https://gw.datayes.com/aladdin_proxy/data_api/api/market/getEquFancyFactors.json"
           "?tradeDate=20260105&pagesize=10")
    s, r, b = call(url)
    print(f"=== getEquFancyFactors tradeDate=20260105 pagesize=10 === HTTP {s}, {b/1024:.1f}KB")
    if isinstance(r, dict) and "_error" in r:
        print("  错误:", r["_error"])
    else:
        print("  原始:", json.dumps(r, ensure_ascii=False)[:1200])

    # 2. 精品因子 ticker 单股一天
    url = ("https://gw.datayes.com/aladdin_proxy/data_api/api/market/getEquFancyFactors.json"
           "?ticker=600519&tradeDate=20260105&pagesize=5")
    s, r, b = call(url)
    print(f"\n=== getEquFancyFactors ticker=600519 tradeDate=20260105 === HTTP {s}, {b/1024:.1f}KB")
    if isinstance(r, dict) and "_error" in r:
        print("  错误:", r["_error"])
    else:
        print("  原始:", json.dumps(r, ensure_ascii=False)[:1200])

    # 3. 精选精品因子 Lite
    url = ("https://gw.datayes.com/aladdin_proxy/data_api/api/market/getEquFancyFactorsLite.json"
           "?ticker=600519&tradeDate=20260105&pagesize=5")
    s, r, b = call(url)
    print(f"\n=== getEquFancyFactorsLite ticker=600519 === HTTP {s}, {b/1024:.1f}KB")
    if isinstance(r, dict) and "_error" in r:
        print("  错误:", r["_error"])
    else:
        print("  原始:", json.dumps(r, ensure_ascii=False)[:1200])


if __name__ == "__main__":
    main()
