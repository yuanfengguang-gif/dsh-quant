# -*- coding: utf-8 -*-
"""risk/verify_datayes_v2.py —— 通联数据补充验证：财务/行业/上市股接口

在 verify_datayes.py（V1-V4）基础上，补充探测项目需要的其余数据结构：
  S1 上市股列表（getSecID listStatusCD=L）：数量 + 字段（是否有行业/状态）
  S2 财务摘要（getFdmtNew / getFdmt）：营收/净利/EPS/ROE 字段是否齐全
  S3 行业分类（industry_structure 等候选路径）
  S4 枚举字典（getSysCode）：确认 listStatusCD 等枚举值
  S5 行情字段完整性（getMktEqud 全字段，含 PE/PB/总市值）
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


def show(title, status, r, maxn=3):
    print("\n" + "=" * 64)
    print(title)
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


def s1_listed():
    show("S1 上市股列表 getSecID listStatusCD=L",
         *call(f"{GW}/aladdin_proxy/data_api/api/master/getSecID.json",
               {"assetClass": "E", "listStatusCD": "L"}))


def s2_finance():
    """财务摘要：探测候选路径 + 字段。"""
    for path, params in [
        ("equity/getFdmtNew.json", {"ticker": "600519"}),
        ("equity/getFdmt.json", {"ticker": "600519"}),
        ("fundamental/getFdmtNew.json", {"ticker": "600519"}),
    ]:
        status, r = call(f"{GW}/aladdin_proxy/data_api/api/{path}", params)
        show(f"S2 财务摘要 {path}", status, r)


def s3_industry():
    for path, params in [
        ("master/industry_structure.json", {}),
        ("master/getIndustryStructure.json", {}),
        ("master/getIndustrySW.json", {}),
        ("equity/industry_structure.json", {}),
    ]:
        status, r = call(f"{GW}/aladdin_proxy/data_api/api/{path}", params)
        show(f"S3 行业分类 {path}", status, r)


def s4_syscode():
    show("S4 枚举字典 getSysCode", *call(
        f"{GW}/aladdin_proxy/data_api/api/master/getSysCode.json", {}))


def s5_equd_fields():
    """行情全字段：抽 1 只 1 天，看全部字段（含 PE/PB/总市值）。"""
    status, r = call(f"{GW}/aladdin_proxy/data_api/api/market/getMktEqud.json",
                     {"ticker": "600519", "beginDate": "20261012", "endDate": "20261012",
                      "field": ""})
    print("\n" + "=" * 64)
    print("S5 行情字段完整性（getMktEqud 不指定 field，看返回全部列）")
    print("=" * 64)
    print(f"HTTP {status}")
    if isinstance(r, dict) and "_error" in r:
        print("  错误:", r["_error"])
        return
    data = r.get("data", [])
    if isinstance(data, list) and data:
        d = data[0]
        print("  字段名:", sorted(d.keys()))
        print("  样例:", json.dumps(d, ensure_ascii=False)[:800])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default=os.environ.get("DATAYES_TOKEN"))
    args = ap.parse_args()
    if not args.token:
        print("❌ 需要 --token 或环境变量 DATAYES_TOKEN")
        sys.exit(2)
    HEADERS["Authorization"] = f"Bearer {args.token}"

    s1_listed()
    s2_finance()
    s3_industry()
    s4_syscode()
    s5_equd_fields()
    print("\n补充验证完成")


if __name__ == "__main__":
    main()
