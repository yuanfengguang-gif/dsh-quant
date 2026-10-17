# -*- coding: utf-8 -*-
"""scripts/b0_etf_feasibility.py —— 轨道 B · 步骤 0 可行性验证（只取证，不做回测）

回答 4 个问题：
  1) 通达信能否取 ETF 日线（510300/510500/511990/518880）
  2) ETF 是否需前复权（有无分红记录）
  3) 各 ETF 历史起始日
  4) 指数代理是否齐全（399006.SZ / 000922.CSI 等）

产物：reports/B0_ETF可行性.json + reports/B0_ETF可行性.md
用法：python scripts/b0_etf_feasibility.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, r"C:\Users\Lenovo\.dsh\skills\tdx-aidata")
sys.path.insert(0, r"C:\Users\Lenovo\.dsh\skills\tdx-aidata\lib")

from tdxaidata import tqs  # noqa: E402

ETFS = [("510300.SH", "沪深300ETF"), ("510500.SH", "中证500ETF"),
        ("511990.SH", "货币ETF"), ("518880.SH", "黄金ETF")]
INDEXES = ["399006.SZ", "000922.CSI", "000922.SH", "000300.SH", "000905.SH", "000852.SH"]
FIELDS = ["Open", "High", "Low", "Close", "Volume", "Amount"]


def fetch(code: str, start="2000-01-01", end="2026-10-17"):
    r = tqs.get_market_data(field_list=FIELDS, stock_list=[code], period="1d",
                            start_time=start, end_time=end, dividend_type="none")
    close = r.get("Close")
    if close is None or len(close) == 0:
        return None, r
    df = close.copy()
    df.columns = ["close"]
    for k in ("Open", "High", "Low", "Volume", "Amount"):
        v = r.get(k)
        if v is not None:
            df[k.lower()] = v.iloc[:, 0]
    df = df.dropna(subset=["close"])
    return df, r


def main() -> int:
    out = {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "etf": {}, "dividends": {}, "index": {}}

    print("=== 1/3) ETF 日线 ===", flush=True)
    for code, name in ETFS:
        try:
            df, _ = fetch(code)
            if df is None or df.empty:
                print(f"  ✘ {code} {name}: 无数据")
                out["etf"][code] = {"name": name, "ok": False}
                continue
            d0, d1 = str(df.index[0])[:10], str(df.index[-1])[:10]
            sample = [{"date": str(i)[:10], "close": float(row["close"]),
                       "volume": (float(row["volume"]) if "volume" in row and row["volume"] == row["volume"] else None)}
                      for i, row in df.tail(2).iterrows()]
            out["etf"][code] = {"name": name, "ok": True, "rows": int(len(df)),
                                "start": d0, "end": d1, "sample": sample}
            print(f"  ✅ {code} {name}: {len(df):,} 行 {d0} ~ {d1}", flush=True)
        except Exception as e:
            out["etf"][code] = {"name": name, "ok": False, "error": str(e)[:200]}
            print(f"  ✘ {code} {name}: {type(e).__name__} {str(e)[:120]}", flush=True)

    print("\n=== 2) 分红记录（是否需前复权）===", flush=True)
    for code in ("510300.SH", "510500.SH"):
        try:
            df = tqs.get_divid_factors(stock_code=code)
            n = 0 if df is None else len(df)
            out["dividends"][code] = {"rows": int(n),
                                      "columns": list(df.columns) if df is not None and n else [],
                                      "sample": df.tail(2).reset_index().astype(str).to_dict("records") if n else []}
            print(f"  {code}: {n} 条分红记录", flush=True)
        except Exception as e:
            out["dividends"][code] = {"error": str(e)[:200]}
            print(f"  {code}: ERR {str(e)[:100]}", flush=True)

    print("\n=== 3) 指数代理 ===", flush=True)
    for code in INDEXES:
        try:
            df, _ = fetch(code)
            if df is None or df.empty:
                out["index"][code] = {"ok": False}
                print(f"  ✘ {code}: 无数据")
                continue
            out["index"][code] = {"ok": True, "rows": int(len(df)),
                                  "start": str(df.index[0])[:10], "end": str(df.index[-1])[:10]}
            print(f"  ✅ {code}: {len(df):,} 行 {str(df.index[0])[:10]} ~ {str(df.index[-1])[:10]}", flush=True)
        except Exception as e:
            out["index"][code] = {"ok": False, "error": str(e)[:200]}
            print(f"  ✘ {code}: {str(e)[:100]}", flush=True)

    # 已有的 index.parquet
    pq = BASE / "mining" / "AI-Quant-Factor-Miner" / "data" / "index.parquet"
    if pq.exists():
        try:
            import pandas as pd
            d = pd.read_parquet(pq)
            out["parquet_index"] = {"path": str(pq), "rows": int(len(d)), "columns": list(d.columns)[:8],
                                    "start": str(d.iloc[0, 0])[:10], "end": str(d.iloc[-1, 0])[:10]}
            print(f"\n  index.parquet: {len(d):,} 行, 列 {list(d.columns)[:6]}")
        except Exception as e:
            out["parquet_index"] = {"error": str(e)[:200]}
    else:
        out["parquet_index"] = {"missing": True}
        print("\n  index.parquet 缺失")

    rp = BASE / "reports" / "B0_ETF可行性.json"
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n结果已存：{rp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
