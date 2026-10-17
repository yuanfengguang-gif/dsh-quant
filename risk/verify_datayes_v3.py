# -*- coding: utf-8 -*-
"""risk/verify_datayes_v3.py —— 通联数据补充验证 v3：ST标记/行业/财务（正确 API 名）

依据 tushare 集成的 DataYes 接口名，探测 REST 路径：
  T1 ST 标记（getSecST）—— 对应 F-1 缺陷（is_st 全 0），关键
  T2 行业分类（getEquIndustry）
  T3 财务利润表（getFdmtIS）—— 营收/净利/EPS
  T4 财务资产负债表（getFdmtBS）—— 净资产/ROE 分母
  T5 股票基本信息（getEqu）—— 股本
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

GW = "https://gw.datayes.com"
HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}


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


def probe(title, path, params, maxn=3):
    status, r = call(f"{GW}/aladdin_proxy/data_api/api/{path}", params)
    print("\n" + "=" * 64)
    print(f"{title}  [{path}]")
    print("=" * 64)
    print(f"HTTP {status}")
    if isinstance(r, dict) and "_error" in r:
        print("  错误:", r["_error"])
        return None
    data = r.get("data", [])
    if isinstance(data, list):
        print(f"  返回 {len(data)} 条")
        for d in data[:maxn]:
            print("   ", json.dumps(d, ensure_ascii=False)[:500])
        return data
    print("  原始:", json.dumps(r, ensure_ascii=False)[:600])
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default=os.environ.get("DATAYES_TOKEN"))
    args = ap.parse_args()
    if not args.token:
        print("❌ 需要 --token 或环境变量 DATAYES_TOKEN")
        sys.exit(2)
    HEADERS["Authorization"] = f"Bearer {args.token}"

    # T1 ST 标记（多个候选路径 + 参数）
    for path, params in [
        ("equity/getSecST.json", {}),
        ("equity/getSecST.json", {"ticker": "600519"}),
        ("master/getSecST.json", {}),
    ]:
        probe("T1 ST标记", path, params)

    # T2 行业分类
    for path, params in [
        ("equity/getEquIndustry.json", {}),
        ("equity/getEquIndustry.json", {"ticker": "600519"}),
    ]:
        probe("T2 行业分类", path, params)

    # T3 利润表
    for path, params in [
        ("fundamental/getFdmtIS.json", {"ticker": "600519"}),
        ("equity/getFdmtIS.json", {"ticker": "600519"}),
    ]:
        probe("T3 利润表", path, params)

    # T4 资产负债表
    for path, params in [
        ("fundamental/getFdmtBS.json", {"ticker": "600519"}),
    ]:
        probe("T4 资产负债表", path, params)

    # T5 股票基本信息
    for path, params in [
        ("equity/getEqu.json", {"ticker": "600519"}),
    ]:
        probe("T5 股票基本信息", path, params)

    print("\n补充验证 v3 完成")


if __name__ == "__main__":
    main()
