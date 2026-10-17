# -*- coding: utf-8 -*-
"""risk/verify_datayes_v9.py —— 区分：额度用尽 vs 查询方式被限"""
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


def call(url, timeout=60):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            j = json.loads(body.decode("utf-8"))
            d = j.get("data", []) if isinstance(j, dict) else []
            n = len(d) if isinstance(d, list) else 0
            return r.status, n, len(body), j.get("message", "")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        return e.code, 0, len(body), body[:200]
    except Exception as e:
        return -1, 0, 0, f"{type(e).__name__}: {e}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default=os.environ.get("DATAYES_TOKEN"))
    args = ap.parse_args()
    HEADERS["Authorization"] = f"Bearer {args.token}"

    # T1 tradeDate 单日全市场（与 I2 相同，看是否还 200）
    for td in ["20200102", "20260901"]:
        url = ("https://gw.datayes.com/aladdin_proxy/data_api/api/market/getMktEqud.json"
               f"?tradeDate={td}&field=ticker,closePrice")
        s, n, b, m = call(url)
        print(f"T1 tradeDate={td} 全市场: HTTP {s}, {n} 行, {b/1024:.1f}KB, msg={m[:60]}")

    # T2 ticker 单日（tradeDate + ticker 组合，看能否查单只）
    url = ("https://gw.datayes.com/aladdin_proxy/data_api/api/market/getMktEqud.json"
           "?tradeDate=20200102&ticker=600519&field=ticker,closePrice")
    s, n, b, m = call(url)
    print(f"T2 tradeDate=20200102 + ticker=600519: HTTP {s}, {n} 行, msg={m[:60]}")

    # T3 ticker + 日期区间（复现 I3 的 402）
    url = ("https://gw.datayes.com/aladdin_proxy/data_api/api/market/getMktEqud.json"
           "?ticker=600519&beginDate=20200102&endDate=20200110&field=ticker,closePrice")
    s, n, b, m = call(url)
    print(f"T3 ticker=600519 + 20200102~20200110: HTTP {s}, {n} 行, msg={m[:60]}")

    # T4 财务（看财务接口是否还 200）
    url = ("https://gw.datayes.com/aladdin_proxy/data_api/api/fundamental/getFdmtISLT2018.json"
           "?ticker=600519")
    s, n, b, m = call(url)
    print(f"T4 getFdmtISLT2018 600519: HTTP {s}, {n} 行, {b/1024:.1f}KB, msg={m[:60]}")


if __name__ == "__main__":
    main()
