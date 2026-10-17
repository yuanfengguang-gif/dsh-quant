# -*- coding: utf-8 -*-
"""临时验证：基本面特征（SUE/BP/EP/REV_YOY/ACCEL）在「年中起点」面板上的非 NaN 覆盖率。

年中起点（如 2023-06-01）会触发旧 PIT ffill 的「面板起点前 eff_date 被丢弃」bug，
用它能严格验证 union+ffill 修复是否生效。
"""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import pandas as pd

from factors.import_qf_pool import load_panel
from factors import formula_miner as fm

START = "2023-06-01"  # 年中起点，刻意触发旧 bug 场景

print(f"加载面板 start={START} ...", flush=True)
panel = load_panel("data/cache/bars.db", start=START)
print(f"面板 {panel.shape}, 日期 {panel.index.get_level_values(0).min()} ~ {panel.index.get_level_values(0).max()}", flush=True)

print("\n=== 基本面特征覆盖率（非 NaN 占比）===", flush=True)
for name in ["SUE", "BP", "EP", "REV_YOY", "ACCEL"]:
    fn = fm.FEATURE_BUILDERS[name]
    try:
        v = fn(panel).reindex(panel.index)
        cov = float(v.notna().mean())
        n = int(v.notna().sum())
        print(f"  {name:<9} 覆盖 {cov:6.1%}  (非NaN {n}/{len(v)})", flush=True)
    except Exception as e:
        print(f"  {name:<9} 异常: {str(e)[:120]}", flush=True)

print("\n=== 对照：修复后的 reproduce_factors（sue / bp_value / f_score）===", flush=True)
from factors.reproduce_factors import sue, bp_value, f_score
for name, fn in [("sue", sue), ("bp_value", bp_value), ("f_score", f_score)]:
    try:
        v = fn(panel).reindex(panel.index)
        cov = float(v.notna().mean())
        print(f"  {name:<9} 覆盖 {cov:6.1%}  (非NaN {int(v.notna().sum())}/{len(v)})", flush=True)
    except Exception as e:
        print(f"  {name:<9} 异常: {str(e)[:120]}", flush=True)

print("\nDONE", flush=True)
