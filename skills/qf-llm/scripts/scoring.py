# -*- coding: utf-8 -*-
"""QF-LLM 固定评分标准（AI 不可修改）。

综合评分 = w_ic * RankIC + w_ir * ICIR + w_cov * 覆盖率 + w_corr * (-最大相关性)
全部为逐日截面口径；factor 与 forward_ret 必须共享同一 MultiIndex (date, code)。

视频口径：RankIC 看排序准不准，IR 看排序稳不稳，覆盖率看能否覆盖足够多股票，
相关性看与已有因子是否重复；加权作为总评分。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# 默认权重（顺序：RankIC, ICIR, 覆盖率, 相关性惩罚）
DEFAULT_WEIGHTS = (0.4, 0.3, 0.1, -0.2)

# 硬门控阈值（去重闸门对齐工作区 factor-mining-workflow 定稿口径）
SCORE_THRESHOLD = 0.0   # 综合分下限
MIN_COVERAGE = 0.3      # 覆盖率下限
MAX_CORR = 0.5          # >0.5 → 淘汰（同构，必杀线）
PASS_CORR = 0.3         # <0.3 → 通过（干净线）；0.3~0.5 → 警示


def _cross_sectional_ics(factor: pd.Series, forward_ret: pd.Series) -> pd.Series:
    """逐日截面 RankIC（rank 后 Pearson == Spearman），向量化（避免逐日循环）。"""
    df = pd.DataFrame({"f": factor, "r": forward_ret}).dropna()
    if df.empty:
        return pd.Series(dtype=float)
    df = df[~df.index.duplicated(keep="last")]
    fw = df["f"].unstack()
    rw = df["r"].unstack()
    fr = fw.rank(axis=1)
    rr = rw.rank(axis=1)
    mask = fw.notna() & rw.notna()
    fr = fr.where(mask)
    rr = rr.where(mask)
    fz = fr.sub(fr.mean(axis=1), axis=0)
    rz = rr.sub(rr.mean(axis=1), axis=0)
    cov = fz.mul(rz).sum(axis=1)
    ic = cov / (fz.pow(2).sum(axis=1) * rz.pow(2).sum(axis=1)).pow(0.5)
    return ic.replace([np.inf, -np.inf], np.nan).dropna()


def rank_ic(factor: pd.Series, forward_ret: pd.Series) -> float:
    ics = _cross_sectional_ics(factor, forward_ret)
    return float(ics.mean()) if len(ics) else 0.0


def ic_ir(factor: pd.Series, forward_ret: pd.Series) -> float:
    ics = _cross_sectional_ics(factor, forward_ret)
    if len(ics) < 2:
        return 0.0
    std = float(ics.std())
    return float(ics.mean() / std) if std > 1e-12 else 0.0


def coverage(factor: pd.Series) -> float:
    return float(factor.notna().mean()) if len(factor) else 0.0


def max_corr_to_pool(factor: pd.Series, pool: list[pd.Series]) -> float:
    """与池内每个因子的截面 Pearson 相关绝对值的最大值。"""
    best = 0.0
    for p in pool:
        df = pd.DataFrame({"f": factor, "p": p}).dropna()
        if len(df) < 30:
            continue
        c = float(df["f"].corr(df["p"]))
        if not np.isfinite(c):
            continue
        best = max(best, abs(c))
    return best


def score(factor: pd.Series, forward_ret: pd.Series, pool: list | None = None,
          weights: tuple = DEFAULT_WEIGHTS) -> dict:
    """综合评分 + 入池硬门控判定（用 |IC|/|IR| 衡量"准不准/稳不稳"，方向靠取反）。

    返回 dict：rank_ic / ic_ir（带符号）、ic_abs / ir_abs（幅值）、direction（+1/-1）、
    coverage / max_corr / total / pass_score / pass_corr / pass_cov / pass。
    """
    pool = pool or []
    ic = rank_ic(factor, forward_ret)
    ir = ic_ir(factor, forward_ret)
    cov = coverage(factor)
    corr = max_corr_to_pool(factor, pool)

    direction = 1 if ic >= 0 else -1
    ic_abs = abs(ic)
    ir_abs = abs(ir)

    w_ic, w_ir, w_cov, w_corr = weights
    total = w_ic * ic_abs + w_ir * ir_abs + w_cov * cov + w_corr * corr

    pass_score = total >= SCORE_THRESHOLD
    pass_corr = corr < PASS_CORR          # 干净通过线 <0.3
    pass_cov = cov >= MIN_COVERAGE
    corr_state = "通过" if corr < PASS_CORR else ("警示" if corr <= MAX_CORR else "淘汰")
    return {
        "rank_ic": ic, "ic_ir": ir,
        "ic_abs": ic_abs, "ir_abs": ir_abs,
        "direction": direction,
        "coverage": cov, "max_corr": corr,
        "corr_state": corr_state,
        "total": total,
        "pass_score": bool(pass_score),
        "pass_corr": bool(pass_corr),
        "pass_cov": bool(pass_cov),
        "pass": bool(pass_score and pass_corr and pass_cov),
    }
