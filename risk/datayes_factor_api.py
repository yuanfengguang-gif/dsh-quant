# -*- coding: utf-8 -*-
"""risk/datayes_factor_api.py —— 查因子数据接口参数（导航API免费）+ 测下载量"""
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


def call(url, timeout=60):
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

    for ne in ["getEquFancyFactors", "getEquFancyFactorsLite", "getStockFactorsDateRange", "getEquH2LFactorT1"]:
        s, r, _ = call("https://gw.datayes.com/aladdin_llm_mgmt/web/whitelist/api?nameEn=" + urllib.parse.quote(ne))
        d = r.get("data", r) if isinstance(r, dict) else r
        print(f"\n===== {ne} =====")
        if not isinstance(d, dict):
            print("  原始:", json.dumps(r, ensure_ascii=False)[:300])
            continue
        print("  chargeType:", d.get("chargeType"), " priceAmountCent:", d.get("priceAmountCent"))
        params = d.get("parametersInput", [])
        print(f"  入参 {len(params)} 个:")
        for p in params if isinstance(params, list) else []:
            if isinstance(p, dict):
                print(f"    - {p.get('nameEn')} ({p.get('name')}) type={p.get('type')} 必填={p.get('mandatory')}")


if __name__ == "__main__":
    main()
