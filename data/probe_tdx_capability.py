# -*- coding: utf-8 -*-
"""data/probe_tdx_capability.py —— 通达信 41 个接口能力盘点（C-1）

产出：
  logs/tdx_capability_<ts>.json  —— 每接口：签名 / 是否成功 / 返回结构 / 样例 / 行数
用途：为《通达信能力矩阵》提供原始事实，避免"只看文档不实测"的重复犯错。

用法：python data/probe_tdx_capability.py [--only 接口名1,接口名2]
"""
from __future__ import annotations

import argparse
import inspect
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, r"C:\Users\Lenovo\.dsh\skills\tdx-aidata")
sys.path.insert(0, r"C:\Users\Lenovo\.dsh\skills\tdx-aidata\lib")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from tdxaidata import tqs

BASE = Path(__file__).resolve().parent.parent
LOGS = BASE / "logs"

CODE = "600519.SH"
D0, D1 = "2026-10-01", "2026-10-09"

# 每个接口的探针参数（键=接口名）
PROBES = {
    "get_stock_list": {},
    "get_market_data": dict(field_list=["Open", "High", "Low", "Close", "Volume", "Amount"],
                            stock_list=[CODE], period="1d", start_time=D0, end_time=D1),
    "get_minute_data": dict(stock_list=[CODE], period="1m", start_time=D1, end_time=D1),
    "get_tick_data": dict(stock_list=[CODE], start_time=D1, end_time=D1),
    "get_market_snapshot": dict(stock_list=[CODE]),
    "get_market_snapshot_batch": dict(stock_list=[CODE]),
    "get_gb_info": dict(stock_code=CODE),
    "get_gb_info_by_date": dict(stock_code=CODE, start_date="2026-01-01", end_date=D1),
    "get_divid_factors": dict(stock_code=CODE),
    "get_financial_data": dict(stock_list=[CODE], field_list=["FN001", "FN074", "FN096", "FN040"],
                               start_time="2025-01-01", end_time="2026-12-31"),
    "get_financial_data_by_date": dict(stock_list=[CODE], field_list=["FN001", "FN096"], year=2025, mmdd=1231),
    "get_gpjy_value": dict(stock_list=[CODE], field_list=["GP2", "GP3"], start_time=D0, end_time=D1),
    "get_gpjy_value_by_date": dict(stock_list=[CODE], field_list=["GP2"], year=2026, mmdd=1009),
    "get_bkjy_value": dict(field_list=["BK1"], start_time=D0, end_time=D1),
    "get_bkjy_value_by_date": dict(field_list=["BK1"], year=2026, mmdd=1009),
    "get_scjy_value": dict(field_list=["SC1"], start_time=D0, end_time=D1),
    "get_scjy_value_by_date": dict(field_list=["SC1"], year=2026, mmdd=1009),
    "get_gp_one_data": dict(stock_list=[CODE], field_list=["GO3", "GO5"]),
    "get_stock_info": dict(stock_code=CODE),
    "get_stock_info_batch": dict(stock_list=[CODE]),
    "get_more_info": dict(stock_code=CODE),
    "get_more_info_batch": dict(stock_list=[CODE]),
    "get_index_member": dict(index_code="000300.SH"),
    "get_sector_list": {},
    "get_sector_list_ds": {},
    "get_stock_list_in_sector": dict(sector_code="880301"),
    "get_user_sector": {},
    "get_trading_dates": dict(start_time="2026-09-01", end_time=D1),
    "get_zdt_data": dict(stock_list=[CODE], start_time=D0, end_time=D1),
    "get_call_auction": dict(stock_list=[CODE], start_time=D1, end_time=D1),
    "get_call_auction_batch": dict(stock_list=[CODE]),
    "get_ipo_info": dict(stock_list=[CODE]),
    "get_kzz_info": dict(stock_code=CODE),
    "get_kzz_info_batch": dict(stock_list=[CODE]),
    "get_relation": dict(stock_code=CODE),
    "get_pricevol": dict(stock_list=[CODE], start_time=D0, end_time=D1),
    "get_exday_data": dict(stock_list=[CODE], start_time=D0, end_time=D1),
    "get_domain_sorthq": dict(stock_list=[CODE]),
    "get_match_stkinfo": dict(stock_list=[CODE]),
    "get_trackzs_etf_info": dict(stock_list=[CODE]),
    "get_zzgz_stocklist": {},
    "get_subscribe_hq_stock_list": {},
}


def summarize(v, depth=0):
    """把返回值压成可读的结构描述"""
    if isinstance(v, dict):
        keys = list(v.keys())
        head = keys[:6]
        return {"type": "dict", "n_keys": len(keys), "keys": head,
                "sample": {k: summarize(v[k], depth + 1) for k in head[:2]} if depth < 1 else None}
    if isinstance(v, list):
        return {"type": "list", "len": len(v),
                "first": summarize(v[0], depth + 1) if v and depth < 2 else None}
    if hasattr(v, "shape"):
        try:
            cols = list(v.columns)[:12]
            return {"type": "DataFrame", "shape": list(v.shape), "columns": cols}
        except Exception:
            return {"type": type(v).__name__}
    s = str(v)
    return {"type": type(v).__name__, "value": s[:160]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    only = {x.strip() for x in args.only.split(",") if x.strip()}

    fns = sorted(n for n in dir(tqs) if n.startswith("get_"))
    out = {"ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "n_interfaces": len(fns), "items": []}

    for name in fns:
        if only and name not in only:
            continue
        fn = getattr(tqs, name)
        try:
            sig = str(inspect.signature(fn))
        except Exception:
            sig = "(unknown)"
        rec = {"name": name, "signature": sig, "params": {}, "ok": None, "result": None, "error": None}
        probe = PROBES.get(name)
        if probe is None:
            rec["error"] = "（无探针参数，未调用）"
            out["items"].append(rec)
            print(f"  {name:32s} {sig[:70]}")
            continue
        try:
            for p in inspect.signature(fn).parameters.values():
                rec["params"][p.name] = str(p.default) if p.default is not inspect._empty else "REQUIRED"
        except Exception:
            pass
        try:
            r = fn(**probe)
            rec["ok"] = True
            rec["result"] = summarize(r)
            size = rec["result"].get("n_keys") or rec["result"].get("len") or rec["result"].get("shape")
            print(f"  {name:32s} ✅ {str(size)[:40]}")
        except Exception as exc:  # noqa: BLE001
            rec["ok"] = False
            rec["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
            print(f"  {name:32s} ✘ {rec['error'][:80]}")
            if "-v" in sys.argv:
                traceback.print_exc()
        out["items"].append(rec)

    dst = LOGS / f"tdx_capability_{datetime.now():%Y%m%d_%H%M%S}.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n已写入 {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
