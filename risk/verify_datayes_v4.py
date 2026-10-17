# -*- coding: utf-8 -*-
"""risk/verify_datayes_v4.py —— 用新版导航 API 定位财务/ST/披露接口的正确路径

调用：
  api_mix_search 按自然语言搜 API → 拿到 nameEn
  api_info       查接口完整定义（httpUrl + 参数）
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
SEARCH_URL = "https://gw.datayes.com/aladdin_llm_mgmt/web/whitelist/api/search/mix"
INFO_URL = "https://gw.datayes.com/aladdin_llm_mgmt/web/whitelist/api"
CATALOG_URL = "https://gw.datayes.com/aladdin_llm_mgmt/web/whitelist/api/catalog/all"


def call(url, params=None, timeout=30):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, {"_error": f"HTTP {e.code}: {e.read().decode('utf-8')[:300]}"}
    except Exception as e:
        return -1, {"_error": f"{type(e).__name__}: {e}"}


def search(q):
    status, r = call(SEARCH_URL, {"query": q})
    print(f"\n=== 搜索「{q}」HTTP {status} ===")
    if isinstance(r, dict) and "_error" in r:
        print("  错误:", r["_error"])
        return []
    # 打印原始结构，识别字段名
    print("  原始:", json.dumps(r, ensure_ascii=False)[:1200])
    return r


def info(nameEn):
    status, r = call(INFO_URL, {"nameEn": nameEn})
    print(f"\n=== api_info[{nameEn}] HTTP {status} ===")
    if isinstance(r, dict) and "_error" in r:
        print("  错误:", r["_error"])
        return
    print("  原始:", json.dumps(r, ensure_ascii=False)[:1500])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default=os.environ.get("DATAYES_TOKEN"))
    args = ap.parse_args()
    HEADERS["Authorization"] = f"Bearer {args.token}"

    for q in ["财务数据", "财务报表", "ST标记", "退市", "披露日", "行业分类"]:
        search(q)

    print("\n\n===== 目录树（前 3000 字符）=====")
    status, r = call(CATALOG_URL)
    print(f"HTTP {status}")
    print(json.dumps(r, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main()
