# -*- coding: utf-8 -*-
"""risk/measure_cost_v2.py —— 精准成本测算（分类型下载 + 精确记录行数）

目的：精确测定「每行消耗多少点」，从而精确测算全量成本。
方法：下载前后由用户在控制台看余额，本脚本精确记录下载的行数。

用法：
  python risk/measure_cost_v2.py --kind market --days 10    # 测行情（全字段）
  python risk/measure_cost_v2.py --kind finance --stocks 20 # 测财务三表
  python risk/measure_cost_v2.py --kind basic               # 测基础信息
"""
import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = Path(__file__).resolve().parent.parent
cfg = yaml.safe_load((BASE / "config" / "params.yaml").read_text(encoding="utf-8"))
TOKEN = cfg["data"]["datayes_token"]
H = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

GW = "https://gw.datayes.com/aladdin_proxy/data_api/api"
MARKET = f"{GW}/market/getMktEqud.json"
FDMT_IS = f"{GW}/fundamental/getFdmtISLT2018.json"
FDMT_BS = f"{GW}/fundamental/getFdmtBSLT2018.json"
FDMT_CF = f"{GW}/fundamental/getFdmtCFLT2018.json"
SECID = f"{GW}/master/getSecID.json"
INDUSTRY = f"{GW}/equity/getEquIndustry.json"

OUT = BASE / "logs" / "cost_measure"
OUT.mkdir(parents=True, exist_ok=True)


def call(url, params=None, timeout=90):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=H)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            return r.status, json.loads(body.decode("utf-8")), len(body)
    except urllib.error.HTTPError as e:
        body = e.read()
        return e.code, {"_error": body.decode("utf-8")[:200]}, len(body)
    except Exception as e:
        return -1, {"_error": f"{type(e).__name__}: {e}"}, 0


def measure_market(days):
    """下载 N 天全市场行情（全字段）。"""
    con = sqlite3.connect(str(BASE / "data" / "cache" / "bars.db"))
    dates = [r[0] for r in con.execute(
        "SELECT DISTINCT date FROM daily_bar ORDER BY date DESC LIMIT ?", (days,))]
    con.close()
    dates = sorted(dates)
    print(f"行情测试：{len(dates)} 个交易日 {dates[0]} ~ {dates[-1]}")
    total = 0
    detail = []
    for d in dates:
        d8 = d.replace("-", "")
        rows, page, bytes_ = [], 1, 0
        while True:
            s, r, b = call(MARKET, {"tradeDate": d8, "pagenum": page, "pagesize": 1000})
            bytes_ += b
            if s != 200:
                print(f"  {d} HTTP {s} {json.dumps(r, ensure_ascii=False)[:100]}")
                break
            data = r.get("data", [])
            rows.extend(data)
            if len(data) < 1000:
                break
            page += 1
            time.sleep(0.15)
        total += len(rows)
        detail.append({"date": d, "rows": len(rows), "bytes": bytes_})
        print(f"  {d}: {len(rows)} 行, {bytes_/1024:.1f} KB", flush=True)
        time.sleep(0.15)
    return {"kind": "market", "days": len(dates), "total_rows": total,
            "bytes": sum(x["bytes"] for x in detail), "detail": detail}


def measure_finance(n_stocks):
    """下载 N 只股票完整财务三表。"""
    con = sqlite3.connect(str(BASE / "data" / "cache" / "bars.db"))
    codes = [r[0] for r in con.execute(
        "SELECT DISTINCT code FROM daily_bar ORDER BY code LIMIT ?", (n_stocks,))]
    con.close()
    codes = [c.split(".")[0].zfill(6) for c in codes]
    print(f"财务测试：{len(codes)} 只股票（利润表+资产负债表+现金流量表）")
    total = 0
    detail = []
    for c in codes:
        n = 0
        for name, url in [("IS", FDMT_IS), ("BS", FDMT_BS), ("CF", FDMT_CF)]:
            s, r, b = call(url, {"ticker": c})
            if s != 200:
                print(f"  {c} {name} HTTP {s}")
                continue
            data = r.get("data", [])
            n += len(data) if isinstance(data, list) else 0
            time.sleep(0.15)
        total += n
        detail.append({"ticker": c, "rows": n})
        print(f"  {c}: {n} 行", flush=True)
    return {"kind": "finance", "stocks": len(codes), "total_rows": total, "detail": detail}


def measure_basic():
    """下载基础信息（退市股 + 上市股 + 行业）。"""
    print("基础信息测试：")
    total = 0
    detail = []
    for name, url, params in [
        ("退市股", SECID, {"assetClass": "E", "listStatusCD": "DE"}),
        ("上市股", SECID, {"assetClass": "E", "listStatusCD": "L"}),
    ]:
        s, r, b = call(url, params)
        data = r.get("data", []) if isinstance(r, dict) else []
        n = len(data) if isinstance(data, list) else 0
        total += n
        detail.append({"name": name, "rows": n, "bytes": b})
        print(f"  {name}: {n} 行, {b/1024:.1f} KB")
        time.sleep(0.15)
    return {"kind": "basic", "total_rows": total, "detail": detail}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", required=True, choices=["market", "finance", "basic"])
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--stocks", type=int, default=20)
    args = ap.parse_args()

    if args.kind == "market":
        res = measure_market(args.days)
    elif args.kind == "finance":
        res = measure_finance(args.stocks)
    else:
        res = measure_basic()

    res["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    path = OUT / f"measure_{args.kind}_{res['total_rows']}rows.json"
    path.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'='*56}")
    print(f"【{args.kind}】下载完成")
    print(f"  总行数：{res['total_rows']:,} 行")
    print(f"  → 请现在截图 DataYes 控制台「点数余额」，我再算单价")
    print(f"  记录已存：{path}")
    print(f"{'='*56}")


if __name__ == "__main__":
    main()
