# -*- coding: utf-8 -*-
"""validation/quality_exposure_check.py —— 验收链第③步：暴露审计（行业×市值双中性）

对齐主系统 quality_exposure_check.py 命名。实现复用 factors/validate_deep.py 的
行业 demean + 市值正交化 + ICIR 幸存测试。

用法：python validation/quality_exposure_check.py
"""
import sys
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from factors.import_qf_pool import load_panel, forward_returns, cross_corr
from factors.validate_deep import (load_industry_map, load_mv_wide,
                                   industry_demean, size_orthogonalize, icir_of_long)
from factors.validate_all_factors import amihud, mom_120, near_high_250, ma200_trend
from factors.reproduce_factors import bp_value, sue, f_score, turn_mid_prox

FACTORS = [("amihud", amihud), ("ma200_trend", ma200_trend), ("f_score", f_score),
           ("mom_120", mom_120), ("bp_value", bp_value), ("near_high_250", near_high_250),
           ("sue", sue), ("turn_mid_prox", turn_mid_prox)]


def main():
    panel = load_panel("data/cache/bars.db", start="2019-01-01")
    fwd = forward_returns(panel)
    dates = panel.index.get_level_values(0).unique().sort_values()
    codes = panel.index.get_level_values("code").unique()
    ind_map = load_industry_map()
    mv_wide = load_mv_wide(dates, codes)
    lm = np.log(mv_wide)

    print(f"{'因子':<14} {'原始ICIR':>9} {'双中性ICIR':>11} {'市值暴露':>9}")
    for name, fn in FACTORS:
        try:
            sig = fn(panel).reindex(panel.index)
            fw = sig.unstack()
            raw_ir = icir_of_long(sig, fwd)
            size_sig = lm.stack().reindex(sig.index)
            size_exp = cross_corr(sig, size_sig)
            fw_dn = size_orthogonalize(industry_demean(fw, ind_map), mv_wide)
            dn_ir = icir_of_long(fw_dn.stack().reindex(panel.index), fwd)
            print(f"{name:<14} {raw_ir:+.3f} {dn_ir:+.3f} {size_exp:+.3f}")
        except Exception as e:
            print(f"{name:<14} 失败: {str(e)[:80]}")


if __name__ == "__main__":
    main()
