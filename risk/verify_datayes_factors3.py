# -*- coding: utf-8 -*-
"""risk/verify_datayes_factors3.py —— 完整拉取因子清单并保存 + 分类统计"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from collections import Counter, defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "output")
os.makedirs(OUT, exist_ok=True)

HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}


def call(url, timeout=90):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read()
        return e.code, {"_error": f"HTTP {e.code}: {body.decode('utf-8')[:300]}"}
    except Exception as e:
        return -1, {"_error": f"{type(e).__name__}: {e}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default=os.environ.get("DATAYES_TOKEN"))
    args = ap.parse_args()
    HEADERS["Authorization"] = f"Bearer {args.token}"

    # 1. 精品因子完整清单
    s, r = call("https://gw.datayes.com/aladdin_proxy/data_api/api/market/getEquFancyFactorsInfo.json")
    fancy = r.get("data", []) if isinstance(r, dict) else []
    print(f"精品因子清单: HTTP {s}, {len(fancy)} 个")

    # 分类统计
    c1 = Counter(f.get("category1", "?") for f in fancy)
    c2 = Counter(f.get("category2", "?") for f in fancy)
    c3 = Counter(f.get("category3", "?") for f in fancy if f.get("category3"))
    tbl = Counter(f.get("tableName", "?") for f in fancy)
    print("\n  category1 大类:", dict(c1))
    print("  category2 子类:", dict(c2))
    print("  category3 三类:", dict(c3))
    print("  分表:", dict(tbl))

    # 2. 普通因子字段名（拉一天 600519，提取字段）
    s2, r2 = call("https://gw.datayes.com/aladdin_proxy/data_api/api/market/getStockFactorsDateRange.json"
                  "?ticker=600519&beginDate=20260105&endDate=20260105")
    normal_fields = []
    if isinstance(r2, dict):
        data2 = r2.get("data", [])
        if isinstance(data2, list) and data2:
            row = data2[0]
            id_fields = {"secID", "ticker", "tradeDate", "exchangeCD", "secShortName", "partyID"}
            normal_fields = [k for k in row.keys() if k not in id_fields]
    print(f"\n普通因子库: HTTP {s2}, 字段数 {len(normal_fields)} 个")
    print("  前 40 个:", normal_fields[:40])

    # 3. 保存
    out = {
        "source": "DataYes",
        "fetched_at": "2026-10-15",
        "fancy_factors": fancy,
        "fancy_count": len(fancy),
        "normal_factor_fields": normal_fields,
        "normal_count": len(normal_fields),
    }
    path = os.path.join(OUT, "datayes_factor_catalog.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\n已保存: {path}")


if __name__ == "__main__":
    main()
