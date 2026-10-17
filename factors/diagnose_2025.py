# -*- coding: utf-8 -*-
"""factors/diagnose_2025.py —— 诊断组合 2025 年 -15.61% 是「真衰减」还是「行情风格切换」

对每个有效因子算分年度方向化 RankIC，若 3 个因子 2025 全弱=系统性（行情风格），
若仅个别弱=因子特定衰减。
"""
import sys
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import pandas as pd

from factors.import_qf_pool import load_panel, forward_returns, cross_sectional_ics
from factors.reproduce_factors import limup_ex_5, bp_value, sue

EFFECTIVE = [("limup_ex_5", limup_ex_5, -1), ("bp_value", bp_value, 1), ("sue", sue, 1)]


def main():
    print("加载面板...", flush=True)
    panel = load_panel("data/cache/bars.db", start="2019-01-01")
    fwd = forward_returns(panel)
    print(f"面板 {panel.shape}", flush=True)

    for name, fn, direction in EFFECTIVE:
        sig = fn(panel)
        ics = cross_sectional_ics(sig, fwd) * direction  # 方向化 IC
        yearly = {str(y): round(float(g.mean()), 4) for y, g in ics.groupby(ics.index.year)}
        full = round(float(ics.mean()), 4)
        y2025 = yearly.get("2025", None)
        print(f"\n{name}（方向 {direction:+d}）全期 IC 均值 {full}")
        for y in sorted(yearly):
            print(f"  {y}: {yearly[y]:+.4f}")
        print(f"  → 2025 IC {y2025:+}（{'弱' if y2025 is not None and abs(y2025) < 0.02 else '尚可'}）")


if __name__ == "__main__":
    main()
