# -*- coding: utf-8 -*-
"""risk/verify_datayes_v5.py —— 实测财务 fdmtNew + 利润表 + 重搜 ST 标记"""
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


def call_raw(url, timeout=40):
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

    # F1 财务摘要 fdmtNew（TRIAL 可调，路径参数 ticker）
    for ticker in ["600519", "000001"]:
        url = f"https://gw.datayes.com/aladdin_proxy/aladdin_adventure/fdmtNew/{ticker}"
        status, r = call_raw(url + "?mergedFlag=1&reportType=SUMMARY")
        print(f"\n=== F1 fdmtNew[{ticker}] HTTP {status} ===")
        if isinstance(r, dict) and "_error" in r:
            print("  错误:", r["_error"])
            continue
        data = r.get("data", [])
        if isinstance(data, list):
            print(f"  返回 {len(data)} 期")
            if data:
                print("  字段:", sorted(data[0].keys()))
                print("  最新一期:", json.dumps(data[0], ensure_ascii=False)[:900])
        else:
            print("  原始:", json.dumps(r, ensure_ascii=False)[:800])

    # F2 利润表 getFdmtISLT2018
    for ticker in ["600519"]:
        url = ("https://gw.datayes.com/aladdin_proxy/data_api/api/fundamental/getFdmtISLT2018.json"
               "?ticker=" + ticker)
        status, r = call_raw(url)
        print(f"\n=== F2 getFdmtISLT2018[{ticker}] HTTP {status} ===")
        if isinstance(r, dict) and "_error" in r:
            print("  错误:", r["_error"])
            continue
        data = r.get("data", [])
        if isinstance(data, list):
            print(f"  返回 {len(data)} 条")
            if data:
                print("  字段:", sorted(data[0].keys()))
                print("  样例:", json.dumps(data[0], ensure_ascii=False)[:900])
        else:
            print("  原始:", json.dumps(r, ensure_ascii=False)[:800])

    # F3 重搜 ST 标记
    for q in ["ST", "风险警示", "证券状态", "上市状态"]:
        url = ("https://gw.datayes.com/aladdin_llm_mgmt/web/whitelist/api/search/mix"
               "?query=" + urllib.parse.quote(q))
        status, r = call_raw(url)
        print(f"\n=== F3 搜索「{q}」HTTP {status} ===")
        if isinstance(r, dict) and "_error" in r:
            print("  错误:", r["_error"])
            continue
        data = r.get("data", [])
        if isinstance(data, list):
            for d in data[:3]:
                print(f"  - [{d.get('nameEn')}] {d.get('name')}  locked={d.get('locked')} canInvoke={d.get('canInvoke')}")
                print(f"      {d.get('summary','')[:120]}")
        else:
            print("  原始:", json.dumps(r, ensure_ascii=False)[:600])


if __name__ == "__main__":
    main()
