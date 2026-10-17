# -*- coding: utf-8 -*-
"""validation/quality_brinson_industry.py —— 验收链第④步：Brinson 归因（行业配置 vs 选股）

对齐主系统 quality_brinson_industry.py 命名。实现复用 factors/validate_deep.py 的 brinson_daily。

用法：python validation/quality_brinson_industry.py
"""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from factors.import_qf_pool import load_panel
from factors.validate_deep import load_industry_map, brinson_daily
from factors.validate_all_factors import amihud, mom_120, near_high_250, ma200_trend
from factors.reproduce_factors import bp_value, sue, f_score, turn_mid_prox

FACTORS = [("amihud", amihud), ("ma200_trend", ma200_trend), ("f_score", f_score),
           ("mom_120", mom_120), ("bp_value", bp_value), ("near_high_250", near_high_250),
           ("sue", sue), ("turn_mid_prox", turn_mid_prox)]


def main():
    panel = load_panel("data/cache/bars.db", start="2019-01-01")
    close_wide = panel["close"].unstack()
    ind_map = load_industry_map()
    print(f"{'因子':<14} {'配置贡献':>10} {'选股贡献':>10} {'交互':>10}")
    for name, fn in FACTORS:
        try:
            sig = fn(panel).reindex(panel.index)
            a, s, i = brinson_daily(close_wide, sig, ind_map, topn=20)
            print(f"{name:<14} {a:+.2%} {s:+.2%} {i:+.2%}")
        except Exception as e:
            print(f"{name:<14} 失败: {str(e)[:80]}")


if __name__ == "__main__":
    main()
