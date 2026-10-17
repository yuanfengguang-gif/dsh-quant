# -*- coding: utf-8 -*-
"""单跑 lhb_jg_cnt_20（机构净买次数版）三层验证"""
import sys
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import pandas as pd

from factors.import_qf_pool import load_panel
from factors.reproduce_factors import lhb_jg_cnt_20
from factors.combo_validate import combo_validate_sig, DEFAULT_TOPN, DEFAULT_REBALANCE, DEFAULT_START, DEFAULT_END

panel = load_panel("data/cache/bars.db", start="2019-01-01")
sig = lhb_jg_cnt_20(panel)
r = combo_validate_sig("lhb_jg_cnt_20", sig, panel, topn=DEFAULT_TOPN, rebalance=DEFAULT_REBALANCE,
                       start=DEFAULT_START, end=DEFAULT_END)
m = r["metrics"]
print(f"结论={r['verdict']} 方向={r['direction']:+d} icir20={r['health']['icir_20']} "
      f"icir120={r['health']['icir_120']} 净超额={r['excess_annual']:+.2%} 夏普={m['sharpe']:.2f}")
