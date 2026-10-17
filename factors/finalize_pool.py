# -*- coding: utf-8 -*-
"""factors/finalize_pool.py — 按第二层裁决结果诚实更新三件套 status

背景：bootstrap_pool 用「icir120≥0.3」标 status（全 5 因子都 <0.3 → 标「衰减」）。
但第二层组合裁决（唯一裁决）显示 turn_low/mom_120 是「有效」、near_high_250「无效」。
本脚本按第二层裁决重写三件套 status：有效/观察/失效，其余（rank/icir/direction）不变。

用法：python factors/finalize_pool.py
"""
import sys
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from factors.import_qf_pool import load_panel, cross_sectional_ics, forward_returns
from factors.bootstrap_pool import BUILTIN
from factors.factor_pool_writer import write_pool
from factors.combo_validate import _rolling_icir

# 第二层组合裁决结论（combo_validate_builtin.py 实测，唯一裁决）
STATUS_OVERRIDE = {
    "turnover": "有效",      # 年化+15.3% 净超额+3.03% 夏普1.15
    "lowvol_60": "观察",     # 净超额-4.01%
    "near_high_250": "失效",  # 净超额-30.30% 夏普-0.64
    "reversal20": "观察",    # 净超额-6.73%
    "mom_120": "有效",       # 年化+23.8% 净超额+11.52% 夏普0.85
}


def main():
    print("加载面板...", flush=True)
    panel = load_panel("data/cache/bars.db", start="2019-01-01")
    fwd = forward_returns(panel)

    factors = []
    for name, fn, sign, cn, cat, usage in BUILTIN:
        raw = fn(panel).astype(float)
        sig = (raw * sign).stack().reindex(panel.index)
        score = (raw * sign).rank(axis=1, pct=True)
        latest_rank = score.iloc[-1].dropna()
        ics = cross_sectional_ics(sig, fwd)
        status = STATUS_OVERRIDE.get(name, "观察")
        factors.append({
            "code": name, "name_cn": cn, "category": cat,
            "direction": sign, "status": status, "usage": usage,
            "icir_20": _rolling_icir(ics, 20), "icir_60": _rolling_icir(ics, 60),
            "icir_120": _rolling_icir(ics, 120), "rank": latest_rank,
        })
        print(f"  {name:<14s} → {status}", flush=True)

    data_date = str(panel.index.get_level_values(0).max())[:10]
    paths = write_pool(factors, data_date=data_date)
    print("\n=== 三件套已按第二层裁决更新 ===")
    for k, v in paths.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
