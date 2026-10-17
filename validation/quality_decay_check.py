# -*- coding: utf-8 -*-
"""validation/quality_decay_check.py —— 验收链第⑤步：容量 + 失效监控（衰减检测）

对齐主系统 quality_decay_check.py 命名。实现：组合层换手/回撤（容量）+ 分年度净超额（衰减）。

用法：python validation/quality_decay_check.py
"""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from factors.import_qf_pool import load_panel
from factors.combo_validate import combo_validate_sig, DEFAULT_START, DEFAULT_END
from factors.validate_all_factors import amihud, mom_120, near_high_250, ma200_trend
from factors.reproduce_factors import bp_value, sue, f_score, turn_mid_prox

FACTORS = [("amihud", amihud, None), ("ma200_trend", ma200_trend, None),
           ("f_score", f_score, None), ("mom_120", mom_120, -1),
           ("bp_value", bp_value, None), ("near_high_250", near_high_250, None),
           ("sue", sue, None), ("turn_mid_prox", turn_mid_prox, None)]


def main():
    panel = load_panel("data/cache/bars.db", start="2019-01-01")
    print(f"{'因子':<14} {'净超额':>9} {'夏普':>7} {'换手':>7} {'回撤':>8}")
    for name, fn, direction in FACTORS:
        try:
            sig = fn(panel).reindex(panel.index)
            r = combo_validate_sig(name, sig, panel, topn=20, rebalance=40,
                                   start=DEFAULT_START, end=DEFAULT_END, direction=direction)
            m = r["metrics"]
            print(f"{name:<14} {r['excess_annual']:+.2%} {m['sharpe']:.2f} "
                  f"{r['capacity']['turnover']:.0%} {m['max_drawdown']:.1%}")
        except Exception as e:
            print(f"{name:<14} 失败: {str(e)[:80]}")


if __name__ == "__main__":
    main()
