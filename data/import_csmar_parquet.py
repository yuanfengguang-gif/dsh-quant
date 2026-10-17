# -*- coding: utf-8 -*-
"""data/import_csmar_parquet.py —— CSMAR 财务全字段 → parquet（供因子挖掘）

背景（HANDOFF.md 第五节 P1）：
  「导入 CSMAR 949 列全字段，用 parquet 存储（比 SQLite 高效），供未来因子挖掘」
  现状：data/import_csmar.py 只把 41 个核心字段导入了 SQLite（finance_csmar.db），
        卡点 5「CSMAR 949 列全字段未导入」即指此。本脚本补齐。

源：D:\\BaiduNetdiskDownload\\A股上市公司财务数据（1990-2026.3.31）\\
      年度最终合并.csv（949 列，638 MB）
      季度合并.csv  （835 列，2046 MB）
输出：data/parquet/csmar_annual/part-*.parquet
      data/parquet/csmar_quarter/part-*.parquet
      data/parquet/_manifest.json
  派生列：code（600519.SH / 000001.SZ 口径）、period（年度 → YYYY-12-31；季度 → 季度日期）
  压缩：zstd

已知边界（务必在质量报告中披露）：
  · 源文件「报表类型编码」全部为 A（合并报表）→ 无需再过滤，但也没有母公司报表口径
  · 年度表有「年报公布日期」（PIT 可用）；**季度表没有公告日** → 季度数据的 PIT 需另找源
  · 「股东户数」「审计意见」不在本文件内（HANDOFF 卡点 5 的另一半），需另有数据源

用法：python data/import_csmar_parquet.py [--which year|quarter|both] [--chunksize 20000]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SRC = Path(r"D:\BaiduNetdiskDownload\A股上市公司财务数据（1990-2026.3.31）")
BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "data" / "parquet"


def norm_code(s: pd.Series) -> pd.Series:
    c = s.astype(str).str.strip().str.zfill(6)
    suffix = pd.Series("SZ", index=c.index)
    suffix[c.str.startswith(("6", "9"))] = "SH"
    suffix[c.str.startswith(("4", "8"))] = "BJ"
    return c + "." + suffix


def convert(csv_path: Path, sub: str, chunksize: int, period_col: str) -> dict:
    outdir = OUT / sub
    if outdir.exists():
        shutil.rmtree(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    total_in = 0
    total_out = 0
    parts = []
    cols_seen: list[str] = []
    reader = pd.read_csv(csv_path, encoding="utf-8-sig", chunksize=chunksize,
                         low_memory=False, dtype={"证券代码": str})
    for i, chunk in enumerate(reader, start=1):
        total_in += len(chunk)
        if not cols_seen:
            cols_seen = list(chunk.columns)
        # 派生列
        chunk["code"] = norm_code(chunk["证券代码"])
        if period_col in chunk.columns:
            if period_col == "年份":
                chunk["period"] = chunk["年份"].astype(str).str[:4] + "-12-31"
            else:
                chunk["period"] = pd.to_datetime(chunk[period_col], errors="coerce").dt.strftime("%Y-%m-%d")
        else:
            chunk["period"] = None
        chunk = chunk.dropna(subset=["period"])
        if chunk.empty:
            continue
        part = outdir / f"part-{i:04d}.parquet"
        chunk.to_parquet(part, engine="pyarrow", compression="zstd", index=False)
        parts.append(part.name)
        total_out += len(chunk)
        print(f"  批{i}: 读 {len(chunk):,} 写出累计 {total_out:,}  "
              f"({time.time()-t0:.0f}s)", flush=True)

    elapsed = time.time() - t0
    return {
        "source": str(csv_path),
        "source_mb": round(csv_path.stat().st_size / 1e6, 1),
        "rows_read": total_in,
        "rows_written": total_out,
        "n_columns_source": len(cols_seen),
        "n_columns_output": len(cols_seen) + 2,
        "parts": len(parts),
        "outdir": str(outdir),
        "elapsed_s": round(elapsed, 1),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--which", default="both", choices=["year", "quarter", "both"])
    ap.add_argument("--chunksize", type=int, default=20000)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    man: dict = {"ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 "note": "CSMAR 财务全字段 parquet；派生列 code/period；zstd 压缩",
                 "jobs": {}}

    if args.which in ("year", "both"):
        print("=== 年度最终合并.csv → csmar_annual ===")
        man["jobs"]["annual"] = convert(SRC / "年度最终合并.csv", "csmar_annual",
                                        args.chunksize, "年份")
    if args.which in ("quarter", "both"):
        print("=== 季度合并.csv → csmar_quarter ===")
        man["jobs"]["quarter"] = convert(SRC / "季度合并.csv", "csmar_quarter",
                                         args.chunksize, "季度日期")

    (OUT / "_manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
    print("\n" + "=" * 64)
    for k, v in man["jobs"].items():
        print(f"{k}: {v['rows_written']:,} 行 × {v['n_columns_output']} 列 "
              f"→ {v['parts']} 个 part ({v['elapsed_s']}s)")
        print(f"   {v['outdir']}")
    print(f"\n清单: {OUT / '_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
