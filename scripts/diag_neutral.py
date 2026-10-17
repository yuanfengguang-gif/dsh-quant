# -*- coding: utf-8 -*-
"""scripts/diag_neutral.py —— 中性化消融的可信度诊断

背景：ablation_combo 显示「中性化后的组合」年化 27-32%、夏普 1.0-1.15，
      而单因子中性化后只有 0.8 左右。这种跃升必须先排除伪影：
  · 中性化后选出的股票是否变成极端小市值（行业 demean + log市值正交 ≠ 抹掉市值暴露）
  · 中性化是否把样本数砍掉一大截（NaN 扩散）
  · 与未中性化的 Top20 重叠多少
  · 行业集中度是否升高

用法：python scripts/diag_neutral.py
"""
from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from factors.import_qf_pool import load_panel, forward_returns, cross_sectional_ics
from factors.combo_validate import _build_score, _rebalance_dates, DEFAULT_START, DEFAULT_END
from factors.portfolio_builder import load_industry_map, load_mv_wide, neutralize
from factors.validate_all_factors import FACTORS

reg = {n: fn for n, fn, _d in FACTORS}


def rank_cs(s):
    return s.groupby(level=0).rank(pct=True)


def z_cs(s, clip=3.0):
    m = s.groupby(level=0).transform("mean")
    sd = s.groupby(level=0).transform("std")
    return ((s - m) / (sd + 1e-9)).clip(-clip, clip)


def main() -> int:
    from factors.window_config import get_window
    pstart = get_window()["panel_load_start"]
    panel = load_panel("data/cache/bars.db", start=pstart)
    fwd = forward_returns(panel)
    win = ((panel.index.get_level_values(0) >= DEFAULT_START)
           & (panel.index.get_level_values(0) <= DEFAULT_END))
    p = panel[win]
    closes = p["close"].unstack().sort_index()

    bp = pd.Series(reg["bp_value"](panel)).reindex(panel.index)
    tm = pd.Series(reg["turn_mid_prox"](panel)).reindex(panel.index)
    d_bp = 1 if float(cross_sectional_ics(bp, fwd).mean()) >= 0 else -1
    d_tm = 1 if float(cross_sectional_ics(tm, fwd).mean()) >= 0 else -1
    bp, tm = bp * d_bp, tm * d_tm
    combo = (rank_cs(bp) + rank_cs(tm)) / 2.0

    score_raw = _build_score(combo[win], 1).reindex(closes.index)
    ind_map = load_industry_map()
    mv_wide = load_mv_wide(closes.index, closes.columns)
    score_neu = neutralize(score_raw.copy(), ind_map, mv_wide).reindex(closes.index)

    logmv = np.log(mv_wide)
    rdates = _rebalance_dates(score_raw.index, 40)
    rdates = [d for d in rdates if d in score_raw.index]

    rows = []
    for d in rdates:
        a = score_raw.loc[d].dropna()
        b = score_neu.loc[d].dropna()
        if len(a) < 100 or len(b) < 100:
            continue
        topa = a.nlargest(20).index
        topb = b.nlargest(20).index
        lm = logmv.loc[d]
        # 截面相关性：中性化后与 log 市值应≈0
        corr_b = float(np.corrcoef(b.values, lm.reindex(b.index).values)[0, 1]) if lm.reindex(b.index).notna().sum() > 100 else np.nan
        # 市值分位（在全市场中的 pct rank，1=最大）
        mv_rank = lm.rank(pct=True)
        rows.append({
            "date": d,
            "n_raw": len(a), "n_neu": len(b),
            "corr_neu_mv": corr_b,
            "mv_pct_top_raw": float(mv_rank.reindex(topa).mean()),
            "mv_pct_top_neu": float(mv_rank.reindex(topb).mean()),
            "overlap": len(set(topa) & set(topb)) / 20.0,
            "ind_n_raw": int(pd.Series([ind_map.get(str(c).split('.')[0], "?") for c in topa]).nunique()),
            "ind_n_neu": int(pd.Series([ind_map.get(str(c).split('.')[0], "?") for c in topb]).nunique()),
        })

    df = pd.DataFrame(rows)
    print(f"调仓日样本 {len(df)}")
    print("\n=== 均值 ===")
    for c in ["n_raw", "n_neu", "corr_neu_mv", "mv_pct_top_raw", "mv_pct_top_neu", "overlap", "ind_n_raw", "ind_n_neu"]:
        print(f"  {c:18s} {df[c].mean():.3f}")
    print("\n=== 分年度（市值分位：1=最大）===")
    df["year"] = pd.to_datetime(df["date"]).dt.year
    g = df.groupby("year")[["mv_pct_top_raw", "mv_pct_top_neu", "overlap", "corr_neu_mv"]].mean().round(3)
    print(g.to_string())
    print("\n判读：若 mv_pct_top_neu 明显低于 raw，说明中性化后选股实际偏小市值（伪影）；")
    print("      corr_neu_mv 应≈0，若不为 0 说明中性化实现有问题。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
