# -*- coding: utf-8 -*-
"""risk/verify_datayes_v8.py —— 核实点数计量 + 按天全市场拉取的数据量

1. api_info 查 getMktEqud 完整定义（看参数 + 是否有计费字段）
2. getMktEqud tradeDate 拉全市场一天，测行数与响应字节（估算点数消耗）
3. getMktEqud ticker+日期 拉一只股票一段日期，对比
"""
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

    # I1 api_info getMktEqud
    status, r, _ = call("https://gw.datayes.com/aladdin_llm_mgmt/web/whitelist/api?nameEn=getMktEqud")
    print(f"\n=== I1 api_info[getMktEqud] HTTP {status} ===")
    d = r.get("data", r) if isinstance(r, dict) else r
    if isinstance(d, dict):
        print("  字段:", sorted(d.keys()))
        print("  httpUrl:", d.get("httpUrl"))
        print("  httpMethod:", d.get("httpMethod"))
        params = d.get("parametersInput", [])
        if isinstance(params, list):
            print(f"  入参 {len(params)} 个:")
            for p in params:
                if isinstance(p, dict):
                    print(f"    - {p.get('name')}({p.get('nameEn')}) type={p.get('type')} 必填={p.get('mandatory')}")
    else:
        print("  原始:", json.dumps(r, ensure_ascii=False)[:800])

    # I2 getMktEqud tradeDate 全市场一天
    url = ("https://gw.datayes.com/aladdin_proxy/data_api/api/market/getMktEqud.json"
           "?tradeDate=20200102&field=ticker,secShortName,closePrice,accumAdjFactor,negMarketValue,turnoverValue,turnoverRate")
    status, r, nbytes = call(url)
    data = r.get("data", []) if isinstance(r, dict) else []
    n = len(data) if isinstance(data, list) else 0
    print(f"\n=== I2 getMktEqud tradeDate=20200102 全市场 ===\n  HTTP {status}, {n} 行, 响应 {nbytes/1024:.1f} KB")
    if n:
        print("  首行:", json.dumps(data[0], ensure_ascii=False)[:200])

    # I3 getMktEqud 一只股票一段日期（对比）
    url = ("https://gw.datayes.com/aladdin_proxy/data_api/api/market/getMktEqud.json"
           "?ticker=600519&beginDate=20200102&endDate=20200110&field=ticker,closePrice")
    status, r, nbytes = call(url)
    data = r.get("data", []) if isinstance(r, dict) else []
    print(f"\n=== I3 getMktEqud 600519 2020-01 一段 ===\n  HTTP {status}, {len(data) if isinstance(data,list) else 0} 行, {nbytes} 字节")


if __name__ == "__main__":
    main()
