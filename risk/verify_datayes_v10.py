# -*- coding: utf-8 -*-
"""risk/verify_datayes_v10.py —— 查导航 API 的计费字段（导航 API 永久免费，不消耗点数）"""
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


def call(url, timeout=40):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, {"_error": f"HTTP {e.code}: {e.read().decode('utf-8')[:200]}"}
    except Exception as e:
        return -1, {"_error": f"{type(e).__name__}: {e}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default=os.environ.get("DATAYES_TOKEN"))
    args = ap.parse_args()
    HEADERS["Authorization"] = f"Bearer {args.token}"

    # 搜"日线行情"找行情接口 nameEn
    status, r = call("https://gw.datayes.com/aladdin_llm_mgmt/web/whitelist/api/search/mix"
                     "?query=" + urllib.parse.quote("日线行情"))
    print(f"=== 搜索「日线行情」HTTP {status} ===")
    data = r.get("data", []) if isinstance(r, dict) else []
    names = []
    if isinstance(data, list):
        for d in data[:5]:
            print(f"  [{d.get('nameEn')}] {d.get('name')}  locked={d.get('locked')}")
            names.append(d.get("nameEn"))

    # 查 api_info 看计费字段
    for ne in (names[:2] + ["fdmt_is_new_lt", "getEquIndustry"]):
        if not ne:
            continue
        status, r = call("https://gw.datayes.com/aladdin_llm_mgmt/web/whitelist/api"
                         "?nameEn=" + urllib.parse.quote(ne))
        d = r.get("data", r) if isinstance(r, dict) else r
        print(f"\n=== api_info[{ne}] HTTP {status} ===")
        if isinstance(d, dict):
            for k in ["name", "nameEn", "httpMethod", "httpUrl", "cost", "price",
                      "points", "credit", "quota", "fee", "rateLimit", "limit"]:
                if k in d:
                    print(f"  {k}: {json.dumps(d[k], ensure_ascii=False)[:300]}")
            print("  全部字段:", sorted(d.keys()))
        else:
            print("  原始:", json.dumps(r, ensure_ascii=False)[:500])


if __name__ == "__main__":
    main()
