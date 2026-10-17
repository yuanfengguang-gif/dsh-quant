# -*- coding: utf-8 -*-
"""risk/verify_datayes_factors2.py —— 查因子库基础信息表（因子清单）"""
import argparse
import json
import os
import sys
import urllib.parse
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
            return r.status, json.loads(r.read().decode("utf-8")), len(r.read() if False else b"")
    except urllib.error.HTTPError as e:
        body = e.read()
        return e.code, {"_error": f"HTTP {e.code}: {body.decode('utf-8')[:300]}"}, len(body)
    except Exception as e:
        return -1, {"_error": f"{type(e).__name__}: {e}"}, 0


def show(title, url):
    s, r, _ = call(url)
    print(f"\n===== {title} =====")
    print(f"HTTP {s}")
    if isinstance(r, dict) and "_error" in r:
        print("  错误:", r["_error"])
        return
    data = r.get("data", []) if isinstance(r, dict) else []
    if isinstance(data, list):
        print(f"  共 {len(data)} 个因子/条")
        for d in data[:40]:
            print("   ", json.dumps(d, ensure_ascii=False)[:300])
    else:
        print("  原始:", json.dumps(r, ensure_ascii=False)[:800])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default=os.environ.get("DATAYES_TOKEN"))
    args = ap.parse_args()
    HEADERS["Authorization"] = f"Bearer {args.token}"

    show("精品因子基础信息 getEquFancyFactorsInfo",
         "https://gw.datayes.com/aladdin_proxy/data_api/api/market/getEquFancyFactorsInfo.json")
    show("HF转低频因子基础信息 getEquH2LFactorInfo",
         "https://gw.datayes.com/aladdin_proxy/data_api/api/alternative/getEquH2LFactorInfo.json")
    show("普通因子(424) getStockFactorsDateRange",
         "https://gw.datayes.com/aladdin_proxy/data_api/api/market/getStockFactorsDateRange.json?ticker=600519&beginDate=20260101&endDate=20260110")


if __name__ == "__main__":
    main()
