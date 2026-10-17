# -*- coding: utf-8 -*-
"""risk/verify_datayes_v11.py —— 查 api_info 的计费字段完整值（导航API免费）"""
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
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"_error": f"{type(e).__name__}: {e}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default=os.environ.get("DATAYES_TOKEN"))
    args = ap.parse_args()
    HEADERS["Authorization"] = f"Bearer {args.token}"

    for ne in ["Astock_market_daily", "fdmt_is_new_lt", "getEquIndustry"]:
        r = call("https://gw.datayes.com/aladdin_llm_mgmt/web/whitelist/api"
                 "?nameEn=" + urllib.parse.quote(ne))
        d = r.get("data", r) if isinstance(r, dict) else r
        print(f"\n===== api_info[{ne}] =====")
        if not isinstance(d, dict):
            print("  原始:", json.dumps(r, ensure_ascii=False)[:400])
            continue
        for k in ["name", "nameEn", "chargeType", "limitType", "priceAmountCent",
                  "priceInternalOnly", "limitConfigs", "parametersInput", "parametersOutput"]:
            v = d.get(k)
            if v is not None:
                s = json.dumps(v, ensure_ascii=False)
                print(f"  {k}: {s[:800]}")


if __name__ == "__main__":
    main()
