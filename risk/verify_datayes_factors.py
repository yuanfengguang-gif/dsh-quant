# -*- coding: utf-8 -*-
"""risk/verify_datayes_factors.py —— 查因子库接口定义（付费版）"""
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
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"_error": f"HTTP {e.code}: {e.read().decode('utf-8')[:300]}"}
    except Exception as e:
        return {"_error": f"{type(e).__name__}: {e}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default=os.environ.get("DATAYES_TOKEN"))
    args = ap.parse_args()
    HEADERS["Authorization"] = f"Bearer {args.token}"

    # 1. 搜"因子"
    r = call("https://gw.datayes.com/aladdin_llm_mgmt/web/whitelist/api/search/mix"
             "?query=" + urllib.parse.quote("因子"))
    print("===== 搜索「因子」=====")
    data = r.get("data", []) if isinstance(r, dict) else []
    if isinstance(data, list):
        for d in data[:20]:
            print(f"[{d.get('nameEn')}] {d.get('name')}  locked={d.get('locked')} canInvoke={d.get('canInvoke')}")
            print(f"    url={d.get('httpUrl')}")
            print(f"    {d.get('summary','')[:100]}")
    else:
        print("原始:", json.dumps(r, ensure_ascii=False)[:600])


if __name__ == "__main__":
    main()
