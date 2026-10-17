# -*- coding: utf-8 -*-
"""risk/verify_datayes.py —— 通联数据(DataYes) 4 项验证（需 token）

验证我们项目的 4 项关键数据需求是否被通联满足：
  V1 退市股覆盖（F-2）：getSecID listStatusCD=DE 能否返回已退市股
  V2 复权因子精度（F-6）：getMktEqud 的 accumAdjFactor 是否与除权日对齐
  V3 披露日 actDate（F-5）：getEquReportPredisclo 实际披露日是否与报告期对齐
  V4 因子清单质量（因子库）：getEquFancyFactorsInfo 能否返回因子名/分类/起始日期（需个人版）

Token 来源优先级：--token 参数 > 环境变量 DATAYES_TOKEN > config/params.yaml 的 data.datayes_token
用法：python risk/verify_datayes.py [--token xxx] [--skip-factor]
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

GW = "https://gw.datayes.com"
HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}


def load_token(cli_token=None):
    if cli_token:
        return cli_token
    if os.environ.get("DATAYES_TOKEN"):
        return os.environ["DATAYES_TOKEN"]
    try:
        import yaml
        cfg = yaml.safe_load((BASE / "config" / "params.yaml").read_text(encoding="utf-8")) or {}
        return (cfg.get("data") or {}).get("datayes_token") or ""
    except Exception:
        return ""


def call(url, params=None, timeout=30):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, {"_error": f"HTTP {e.code}: {e.read().decode('utf-8')[:200]}"}
    except Exception as e:
        return -1, {"_error": f"{type(e).__name__}: {e}"}


def v1_delisted(token):
    """V1 退市股覆盖：listStatusCD=DE 能否返回退市股。"""
    print("\n" + "=" * 60)
    print("V1 退市股覆盖（getSecID listStatusCD=DE）")
    print("=" * 60)
    status, r = call(f"{GW}/aladdin_proxy/data_api/api/master/getSecID.json",
                     {"assetClass": "E", "listStatusCD": "DE"})
    print(f"HTTP {status}")
    if isinstance(r, dict) and "_error" in r:
        print("  错误:", r["_error"])
        return
    data = r.get("data", [])
    if isinstance(data, list):
        print(f"  返回退市股 {len(data)} 条")
        for d in data[:5]:
            print("   ", json.dumps(d, ensure_ascii=False)[:200])
        if not data:
            print("  ⚠️ 空列表：可能参数不对（listStatusCD 枚举需查 getSysCode）或无权限")
    else:
        print("  原始:", json.dumps(r, ensure_ascii=False)[:500])


def v2_adj_factor(token):
    """V2 复权因子精度：抽近期分红股看 accumAdjFactor。"""
    print("\n" + "=" * 60)
    print("V2 复权因子（getMktEqud accumAdjFactor）")
    print("=" * 60)
    # 抽几只近年有分红的代表股（茅台/平安/招商），近一月，看 accumAdjFactor 是否有非 1 值
    for ticker in ["600519", "000001", "600036"]:
        status, r = call(f"{GW}/aladdin_proxy/data_api/api/market/getMktEqud.json",
                         {"ticker": ticker, "beginDate": "20260901", "endDate": "20261012",
                          "field": "ticker,tradeDate,closePrice,actPreClosePrice,preClosePrice,accumAdjFactor,turnoverValue,turnoverVol,turnoverRate,negMarketValue"})
        if isinstance(r, dict) and "_error" in r:
            print(f"  {ticker} 错误: {r['_error']}")
            continue
        data = r.get("data", [])
        print(f"  {ticker}: {len(data)} 条")
        if isinstance(data, list):
            for d in data[:3]:
                print("   ", json.dumps(d, ensure_ascii=False))
            # 检查复权因子是否有非 1
            adj = [d.get("accumAdjFactor") for d in data if isinstance(d, dict)]
            non1 = [a for a in adj if a not in (None, 1, 1.0)]
            print(f"    accumAdjFactor 非1 的天数: {len(non1)}")


def v3_ann_date(token):
    """V3 披露日 actDate（getEquReportPredisclo）。"""
    print("\n" + "=" * 60)
    print("V3 财务披露日 actDate（getEquReportPredisclo）")
    print("=" * 60)
    for ticker in ["600519", "000001"]:
        status, r = call(f"{GW}/aladdin_proxy/data_api/api/equity/getEquReportPredisclo.json",
                         {"ticker": ticker})
        if isinstance(r, dict) and "_error" in r:
            print(f"  {ticker} 错误: {r['_error']}")
            continue
        data = r.get("data", [])
        print(f"  {ticker}: {len(data)} 条")
        if isinstance(data, list):
            for d in data[:3]:
                print("   ", json.dumps(d, ensure_ascii=False))


def v4_factor_info(token):
    """V4 因子清单（getEquFancyFactorsInfo，需个人版）。"""
    print("\n" + "=" * 60)
    print("V4 因子清单（getEquFancyFactorsInfo，需个人版）")
    print("=" * 60)
    status, r = call(f"{GW}/aladdin_proxy/data_api/api/market/getEquFancyFactorsInfo.json")
    print(f"HTTP {status}")
    if isinstance(r, dict) and "_error" in r:
        print("  错误:", r["_error"])
        return
    data = r.get("data", [])
    if isinstance(data, list):
        print(f"  精品因子共 {len(data)} 个")
        for d in data[:20]:
            print("   ", json.dumps(d, ensure_ascii=False)[:160])
    else:
        print("  原始:", json.dumps(r, ensure_ascii=False)[:500])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default=None)
    ap.add_argument("--skip-factor", action="store_true", help="跳过 V4（免费版因子库 locked）")
    args = ap.parse_args()

    token = load_token(args.token)
    if not token:
        print("❌ 未找到 token：用 --token xxx，或设 DATAYES_TOKEN 环境变量，"
              "或写入 config/params.yaml 的 data.datayes_token")
        sys.exit(2)
    HEADERS["Authorization"] = f"Bearer {token}"

    v1_delisted(token)
    v2_adj_factor(token)
    v3_ann_date(token)
    if not args.skip_factor:
        v4_factor_info(token)
    print("\n验证完成")


if __name__ == "__main__":
    main()
