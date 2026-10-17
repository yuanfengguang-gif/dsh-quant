# -*- coding: utf-8 -*-
"""factors/factor_subset.py —— 因子子集自动选择（决策 #2：相关去冗余 + 正交化边际贡献）

目标：从 15 个有效因子里自动挑出 6~8 个「低相关 + 正交化后仍有边际 IC」的子集，
作为组合构建（portfolio_builder.py）的合成信号输入。

算法（两步，业界/主系统常见做法）：
  ① 相关去冗余：按 |ICIR| 降序，若某因子与已保留因子的 |逐日截面 Spearman| 任一 >= corr_thresh，
     则视为同源冗余丢弃（方向相反的同源也抓得到，因为取绝对值）。
  ② 正交化边际贡献（贪心前向）：从 ICIR 最高者起步，每一步把候选因子对已选因子集做
     逐日截面 OLS 残差化，选「残差 ICIR 绝对值」最大的进子集；当残差 |ICIR| 低于阈值
     或达到 max_k 时停止。

口径：方向按截面 RankIC 符号自动判向（与 combo_validate_sig 一致），先方向化（多=好）再做选择。

用法：python factors/factor_subset.py [--max-k 8 --corr 0.5 --min-marginal 0.03]
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from factors.import_qf_pool import load_panel, forward_returns, cross_sectional_ics, cross_corr
from factors.reproduce_factors import bp_value, sue, f_score, turn_mid_prox
from factors.validate_all_factors import (amihud, mom_120, near_high_250, ma200_trend,
                                          c_factor, accel_factor, a_factor, pead_factor,
                                          kdj_j, ma_bull)

# 15 有效因子（turnover_low ≡ turn_mid_prox，取其一 → 14 个去重候选）
# 方向 None = 自动判向（按 RankIC 符号）
CANDIDATE_FACTORS = [
    ("amihud", amihud, "量价"),
    ("ma200_trend", ma200_trend, "量价"),
    ("f_score", f_score, "质量"),
    ("mom_120", mom_120, "反转"),
    ("bp_value", bp_value, "价值"),
    ("near_high_250", near_high_250, "量价"),
    ("pead_factor", pead_factor, "成长"),
    ("sue", sue, "成长"),
    ("c_factor", c_factor, "成长"),
    ("turn_mid_prox", turn_mid_prox, "量价"),
    ("accel_factor", accel_factor, "成长"),
    ("a_factor", a_factor, "成长"),
    ("kdj_j", kdj_j, "反转"),
    ("ma_bull", ma_bull, "量价"),
]

MAX_K = 8
CORR_THRESH = 0.5
MIN_MARGINAL_ICIR = 0.03


def icir_of(sig: pd.Series, fwd: pd.Series) -> float:
    """ICIR = 逐日截面 RankIC 的均值 / 标准差（方向化后为正）。"""
    ics = cross_sectional_ics(sig, fwd)
    if len(ics) < 30:
        return 0.0
    return float(ics.mean() / (ics.std() + 1e-12))


def _ols_residuals_wide(yw: pd.DataFrame, Xw_list) -> pd.DataFrame:
    """逐日截面 OLS：yw 对 Xw_list（各为 dates×codes 宽表）回归取残差。"""
    out = pd.DataFrame(index=yw.index, columns=yw.columns, dtype=float)
    xs_arr = [X.reindex(index=yw.index, columns=yw.columns) for X in Xw_list]
    for i, d in enumerate(yw.index):
        y = yw.iloc[i].values.astype(float)
        X = np.column_stack([X.iloc[i].values.astype(float) for X in xs_arr])
        mask = np.isfinite(y) & np.isfinite(X).all(axis=1)
        if mask.sum() < X.shape[1] + 3:
            continue
        ym = y[mask]
        Xm = np.column_stack([np.ones(mask.sum()), X[mask]])
        beta, *_ = np.linalg.lstsq(Xm, ym, rcond=None)
        resid = ym - Xm @ beta
        out.iloc[i, np.where(mask)[0]] = resid
    return out


def pairwise_abs_corr(factors: dict) -> pd.DataFrame:
    """因子间 |逐日截面 Spearman| 相关矩阵（向量化：先一次性 rank 宽表，再成对相关）。"""
    names = list(factors)
    wide = {n: factors[n].unstack() for n in names}
    ranked = {n: w.rank(axis=1) for n, w in wide.items()}
    centered = {n: ranked[n].sub(ranked[n].mean(axis=1), axis=0) for n in names}
    M = pd.DataFrame(1.0, index=names, columns=names)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = centered[names[i]], centered[names[j]]
            mask = ranked[names[i]].notna() & ranked[names[j]].notna()
            cov = a.mul(b).where(mask).sum(axis=1)
            denom = (a.pow(2).where(mask).sum(axis=1)
                     * b.pow(2).where(mask).sum(axis=1)).pow(0.5)
            c = (cov / denom).replace([np.inf, -np.inf], np.nan).dropna()
            val = abs(float(c.mean())) if len(c) >= 30 else 0.0
            M.loc[names[i], names[j]] = val
            M.loc[names[j], names[i]] = val
    return M


def select_subset(factors: dict, fwd: pd.Series, max_k=MAX_K, corr_thresh=CORR_THRESH,
                  min_marginal=MIN_MARGINAL_ICIR):
    """① 相关去冗余 + ② 正交化边际贡献贪心前向。返回 (selected_names, trace, corr_matrix)。

    factors: {name: 方向化后的信号 Series（多=好）}。trace: 每步 {name, marginal_icir, note}。
    """
    names = list(factors)
    icir = {n: icir_of(factors[n], fwd) for n in names}
    ranked = sorted(names, key=lambda n: -abs(icir[n]))

    # ① 相关去冗余
    corr = pairwise_abs_corr(factors)
    dedup = []
    for n in ranked:
        if all(corr.loc[n, k] < corr_thresh for k in dedup):
            dedup.append(n)

    # ② 正交化边际贡献贪心前向
    wide = {n: factors[n].unstack() for n in names}
    selected = []
    trace = []
    for step in range(max_k):
        best, best_marg = None, -1.0
        basis = [wide[s] for s in selected]
        for n in dedup:
            if n in selected:
                continue
            resid_wide = _ols_residuals_wide(wide[n], basis) if basis else wide[n]
            resid = resid_wide.stack().reindex(factors[n].index)
            marg = abs(icir_of(resid, fwd))
            if marg > best_marg:
                best, best_marg = n, marg
        if best is None:
            break
        if selected and best_marg < min_marginal:
            trace.append({"step": step + 1, "name": None,
                          "marginal_icir": round(best_marg, 4),
                          "note": f"边际 |ICIR| {best_marg:.3f} < {min_marginal}，停止"})
            break
        selected.append(best)
        trace.append({"step": step + 1, "name": best,
                      "marginal_icir": round(best_marg, 4),
                      "note": f"full_icir={icir[best]:+.3f}"})
    return selected, trace, corr, icir, dedup


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-k", type=int, default=MAX_K)
    ap.add_argument("--corr", type=float, default=CORR_THRESH)
    ap.add_argument("--min-marginal", type=float, default=MIN_MARGINAL_ICIR)
    ap.add_argument("--out", default=str(BASE / "logs" / "factor_subset.json"))
    args = ap.parse_args()

    print("加载面板（bars.db 全量 2019+）...", flush=True)
    panel = load_panel("data/cache/bars.db", start="2019-01-01")
    fwd = forward_returns(panel)
    print(f"面板 {panel.shape}", flush=True)

    print("计算 14 个有效候选因子（方向化）...", flush=True)
    raw = {}
    direction = {}
    for name, fn, fam in CANDIDATE_FACTORS:
        try:
            sig = fn(panel).reindex(panel.index)
            raw[name] = sig
        except Exception as e:
            print(f"  {name} 计算失败: {str(e)[:100]}", flush=True)

    factors = {}
    for name in raw:
        ics = cross_sectional_ics(raw[name], fwd)
        d = 1 if (len(ics) and ics.mean() >= 0) else -1
        direction[name] = d
        factors[name] = raw[name] * d
        print(f"  {name:<14} 方向{d:+d} ICIR={icir_of(factors[name], fwd):+.3f}", flush=True)

    selected, trace, corr, icir, dedup = select_subset(
        factors, fwd, max_k=args.max_k, corr_thresh=args.corr, min_marginal=args.min_marginal)

    print("\n=== ① 相关去冗余后候选 ===", flush=True)
    print("  " + ", ".join(dedup), flush=True)
    print("\n=== ② 正交化边际贡献选择（贪心前向）===", flush=True)
    for t in trace:
        print(f"  第{t['step']}步: {t['name'] or '(停)'}  边际|ICIR|={t['marginal_icir']}  {t['note']}", flush=True)

    print(f"\n=== 最终子集（{len(selected)} 个）===", flush=True)
    fam_of = {name: family for name, _, family in CANDIDATE_FACTORS}
    for n in selected:
        print(f"  {n:<14} 族={fam_of[n]:<4} "
              f"方向={direction[n]:+d} ICIR={icir[n]:+.3f}", flush=True)

    out = {
        "validated_at": str(pd.Timestamp.now())[:19],
        "selected": [{"name": n, "family": fam_of[n],
                      "direction": direction[n], "icir": round(icir[n], 4)} for n in selected],
        "dedup_candidates": dedup,
        "trace": trace,
        "corr_matrix": corr.round(3).to_dict(),
        "params": {"max_k": args.max_k, "corr_thresh": args.corr, "min_marginal": args.min_marginal},
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已存：{args.out}")


if __name__ == "__main__":
    main()
