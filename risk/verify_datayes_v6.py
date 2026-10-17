# -*- coding: utf-8 -*-
"""risk/verify_datayes_v6.py —— 决定性验证：免费版历史数据范围

关键问题：免费版「近一月」限制到底限哪些接口？
  - 财务 getFdmtISLT2018 已返回 195 条（疑似完整历史）
  - 行情 getMktEqud 是否也能取 2019+ 历史？（决定能否根治 F-6）
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


def call(url, timeout=40):
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

    # G1 行情历史：测 2020 / 2023 / 2026 三个时间点
    for begin, end in [("20200102", "20200110"), ("20230103", "20230110"),
                       ("20260901", "20261012")]:
        url = ("https://gw.datayes.com/aladdin_proxy/data_api/api/market/getMktEqud.json"
               f"?ticker=600519&beginDate={begin}&endDate={end}"
               "&field=ticker,tradeDate,closePrice,accumAdjFactor")
        status, r = call(url)
        data = r.get("data", []) if isinstance(r, dict) else []
        n = len(data) if isinstance(data, list) else 0
        print(f"G1 行情 getMktEqud {begin}~{end}: HTTP {status}, {n} 条"
              + (f", 首日={data[0].get('tradeDate')}, 末日={data[-1].get('tradeDate')}" if n else ""))

    # G2 财务利润表数据范围
    url = ("https://gw.datayes.com/aladdin_proxy/data_api/api/fundamental/getFdmtISLT2018.json"
           "?ticker=600519")
    status, r = call(url)
    data = r.get("data", []) if isinstance(r, dict) else []
    if isinstance(data, list) and data:
        dates = [d.get("endDateRep") for d in data if d.get("endDateRep")]
        print(f"\nG2 利润表 600519: HTTP {status}, {len(data)} 条")
        print(f"   最早报告期: {min(dates)}  最新报告期: {max(dates)}")

    # G3 资产负债表历史
    url = ("https://gw.datayes.com/aladdin_proxy/data_api/api/fundamental/getFdmtBSLT2018.json"
           "?ticker=600519")
    status, r = call(url)
    data = r.get("data", []) if isinstance(r, dict) else []
    if isinstance(data, list) and data:
        dates = [d.get("endDateRep") for d in data if d.get("endDateRep")]
        print(f"G3 资产负债表 600519: HTTP {status}, {len(data)} 条")
        print(f"   最早报告期: {min(dates)}  最新报告期: {max(dates)}")
        if data:
            print("   字段:", sorted(data[0].keys())[:40])
    else:
        print(f"G3 资产负债表 600519: HTTP {status}, 数据={json.dumps(r, ensure_ascii=False)[:200]}")

    # G4 现金流量表历史
    url = ("https://gw.datayes.com/aladdin_proxy/data_api/api/fundamental/getFdmtCFLT2018.json"
           "?ticker=600519")
    status, r = call(url)
    data = r.get("data", []) if isinstance(r, dict) else []
    if isinstance(data, list) and data:
        dates = [d.get("endDateRep") for d in data if d.get("endDateRep")]
        print(f"G4 现金流量表 600519: HTTP {status}, {len(data)} 条, 范围 {min(dates)}~{max(dates)}")
    else:
        print(f"G4 现金流量表 600519: HTTP {status}, 数据={json.dumps(r, ensure_ascii=False)[:200]}")


if __name__ == "__main__":
    main()
