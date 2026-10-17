# -*- coding: utf-8 -*-
"""factors/strict_validate.py —— 锁定口径的严格回测（2026-10-18 P0 定版 · A 方案）

锁定标准（来源：config/backtest_window.yaml → strict:）：
  样本起点 2016-01-01；TopN=20；20 个交易日调仓；中性化开；
  流动性闸门 ADV 分位 ≥ 0.5 且**池内重选**（先屏蔽不合格股票，再在合格池打分选 TopN）；
  成本 = config/costs.yaml（买卖分边 + 分段印花税）；必报 Calmar 与最大回撤持续天数。

闸门自检（每个调仓日）：
  · 候选池 ≥ 800 只
  · 候选池 ≥ 当日可打分股票的 40%
  · 实际持仓数 == TopN
  任一不满足 → gate_audit.passed=False，结果不得当作有效结论。

参数指纹（缺一项不许出数）：engine/topn/rebalance/neutral/adv_gate/cost/window/universe/gate。

用法：
    from factors.strict_validate import strict_backtest
    r = strict_backtest("bp_value", sig, panel)          # 默认 2016-01-01 起
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from factors.import_qf_pool import load_panel, forward_returns, cross_sectional_ics
from factors.combo_validate import _build_score, _rebalance_dates, _turnover, _adv_pct
from factors.portfolio_builder import load_industry_map, load_mv_wide, neutralize
from factors.cost_model import rates, period_cost, describe as cost_describe
from backtest.bt_runner import _period_backtest
from backtest.bt_report import compute_metrics

try:
    from factors.window_config import get_strict
    _S = get_strict()
except Exception:
    _S = {
        "start": "2016-01-01", "end": "2026-10-16", "topn": 20, "rebalance": 20,
        "neutral": True, "adv_gate": 0.5, "min_candidates": 800, "min_candidate_ratio": 0.40,
    }

STRICT = {
    "start": _S["start"],
    "end": _S["end"],
    "topn": _S["topn"],
    "rebalance": _S["rebalance"],
    "neutral": bool(_S["neutral"]),
    "adv_gate": float(_S["adv_gate"]),
    "min_candidates": int(_S["min_candidates"]),
    "min_candidate_ratio": float(_S["min_candidate_ratio"]),
    "cost_multiplier": 1.0,
}

REQUIRED_FP = ("engine", "topn", "rebalance", "neutral", "adv_gate", "cost", "window", "universe", "gate")

# 窗口级缓存：同一批因子回测时，行业映射 / 市值面板 / ADV 面板只算一次
_CTX: dict = {}


def _cached(key, builder):
    if key not in _CTX:
        _CTX[key] = builder()
    return _CTX[key]


def _adv_pct_from(adv_wide, score, topn, dates):
    """与 combo_validate._adv_pct 同口径，但复用已算好的 ADV 面板。"""
    vals = []
    for d in dates:
        if d not in score.index or d not in adv_wide.index:
            continue
        picks = score.loc[d].dropna().nlargest(topn).index
        row = adv_wide.loc[d].reindex(picks).dropna()
        if len(row):
            vals.append(float(row.median()))
    if not vals:
        return None
    basket = float(np.median(vals))
    last = adv_wide.dropna(how="all").iloc[-1].dropna()
    return float((last < basket).mean()) if len(last) else None


def _dd_stats(nav: pd.Series) -> dict:
    peak = nav.cummax()
    dd = nav / peak - 1.0
    maxdd = float(dd.min())
    under = (nav < peak).to_numpy()
    longest = cur = 0
    for u in under:
        cur = cur + 1 if u else 0
        longest = max(longest, cur)
    return {"max_drawdown": maxdd, "dd_days_max": int(longest)}


def _seg_ann(net: pd.Series, a: int, b: int):
    r = net[(net.index.year >= a) & (net.index.year <= b)]
    return float(np.prod(1 + r) ** (252 / len(r)) - 1) if len(r) > 20 else None


def _fingerprint(topn, rebalance, neutral, adv_gate, cost_mult, start, end, min_cand, min_ratio) -> dict:
    r = rates("2026-10-17")
    fp = {
        "engine": "strict_validate/v1.1",
        "topn": topn,
        "rebalance": rebalance,
        "neutral": bool(neutral),
        "adv_gate": float(adv_gate),
        "cost": {
            "source": "config/costs.yaml",
            "buy": r["buy"], "sell": r["sell"], "round_trip": r["round_trip"],
            "multiplier": float(cost_mult),
            "stamp_schedule": cost_describe()["stamp_schedule"],
        },
        "window": {"start": str(start), "end": str(end)},
        "universe": "bars.db qfq 全A（ST 剔除；流动性闸门 ADV≥%.2f）" % adv_gate,
        "gate": {"min_candidates": int(min_cand), "min_candidate_ratio": float(min_ratio)},
    }
    missing = [k for k in REQUIRED_FP if k not in fp]
    if missing:
        raise RuntimeError(f"参数指纹缺项：{missing}（缺项不许出数）")
    return fp


def strict_backtest(name: str, sig: pd.Series, panel: pd.DataFrame,
                    start: str | None = None, end: str | None = None,
                    topn: int | None = None, rebalance: int | None = None,
                    neutral: bool | None = None, adv_gate: float | None = None,
                    cost_multiplier: float | None = None,
                    fwd: pd.Series | None = None, exclude_st: bool = True,
                    archive_result: bool = False) -> dict:
    """按锁定口径跑一个信号。返回指标 + 闸门自检 + 参数指纹 + 0/1/2 倍成本年化。"""
    start = STRICT["start"] if start is None else start
    end = STRICT["end"] if end is None else end
    topn = STRICT["topn"] if topn is None else topn
    rebalance = STRICT["rebalance"] if rebalance is None else rebalance
    neutral = STRICT["neutral"] if neutral is None else neutral
    adv_gate = STRICT["adv_gate"] if adv_gate is None else adv_gate
    cost_mult = STRICT["cost_multiplier"] if cost_multiplier is None else cost_multiplier

    if fwd is None:
        fwd = forward_returns(panel)
    sig = pd.Series(sig).reindex(panel.index)

    win = ((panel.index.get_level_values(0) >= start)
           & (panel.index.get_level_values(0) <= end))
    p = panel[win]
    closes = p["close"].unstack().sort_index()
    opens = p["open"].unstack().sort_index()
    highs = p["high"].unstack().sort_index()

    # 方向：全样本（含预热）RankIC 符号，与既有引擎同约定
    direction = 1 if float(cross_sectional_ics(sig, fwd).mean()) >= 0 else -1
    score_raw = _build_score(sig[win], direction).reindex(closes.index)

    # 流动性闸门：池内重选（先屏蔽，再选），不是先选后滤
    _wkey = (str(closes.index[0])[:10], str(closes.index[-1])[:10], closes.shape[0], closes.shape[1])
    adv_wide = _cached(("adv",) + _wkey,
                       lambda: p["amount"].unstack().rolling(20, min_periods=20).mean())
    adv_rank = adv_wide.rank(axis=1, pct=True)
    gate = (adv_rank < adv_gate)
    if exclude_st:
        gate = gate | (p["is_st"].unstack().reindex(index=closes.index, columns=closes.columns) == 1)
    score = score_raw.where(~gate)

    if neutral:
        ind_map = _cached("ind", load_industry_map)
        mv_wide = _cached(("mv",) + _wkey, lambda: load_mv_wide(closes.index, closes.columns))
        score = neutralize(score.copy(), ind_map, mv_wide).reindex(closes.index)

    ret = _period_backtest(closes, opens, highs, score, topn, rebalance=rebalance)
    rdates = _rebalance_dates(score.index, rebalance)
    turnover = _turnover(score, topn, rdates)
    _rd_used = [d for d in rdates if d in closes.index]
    cost_base = period_cost(turnover, dates=_rd_used, multiplier=1.0)
    adv_pct = _adv_pct_from(adv_wide, score, topn, rdates)

    def _net(k: float) -> pd.Series:
        return ret - (cost_base * k) / max(len(ret), 1)

    net = _net(cost_mult)
    bench = closes.pct_change().fillna(0).mean(axis=1).loc[net.index]
    m = compute_metrics(net)
    bm = compute_metrics(bench)
    dd = _dd_stats((1 + net).cumprod())
    ann = float(m["annual_return"])
    excess = ann - float(bm["annual_return"])
    calmar = ann / abs(dd["max_drawdown"]) if dd["max_drawdown"] else None

    # 0/1/2 倍成本年化（同一份毛收益，只改成本）
    ann0 = float(compute_metrics(ret)["annual_return"])
    ann1 = float(compute_metrics(_net(1.0))["annual_return"])
    ann2 = float(compute_metrics(_net(2.0))["annual_return"])
    periods_per_year = (len(rdates) / (len(net) / 252.0)) if len(net) else 0.0
    rt_avg = float(np.mean([rates(d)["round_trip"] for d in _rd_used])) if _rd_used else rates(None)["round_trip"]
    theory1 = float(rt_avg * turnover * periods_per_year)

    # 闸门自检：候选池 / 可打分股票 / 实际持仓
    cand, scoreable, hold = [], [], []
    for d in rdates:
        if d not in score.index:
            continue
        sc = score.loc[d].dropna()
        sr = score_raw.loc[d]
        scoreable.append(int(sr.notna().sum()))
        cand.append(int(len(sc)))
        hold.append(int(min(topn, len(sc))))
    min_cand = int(STRICT["min_candidates"])
    min_ratio = float(STRICT["min_candidate_ratio"])
    ratios = [c / s for c, s in zip(cand, scoreable) if s]
    audit = {
        "days": len(cand),
        "candidate_min": min(cand) if cand else 0,
        "candidate_median": float(np.median(cand)) if cand else 0,
        "candidate_max": max(cand) if cand else 0,
        "scoreable_min": min(scoreable) if scoreable else 0,
        "ratio_min": (round(min(ratios), 3) if ratios else None),
        "holdings_min": min(hold) if hold else 0,
        "holdings_max": max(hold) if hold else 0,
        "full_holdings_days": int(sum(1 for h in hold if h == topn)),
        "candidate_abs_days": int(sum(1 for c in cand if c >= min_cand)),
        "candidate_ratio_days": int(sum(1 for r in ratios if r >= min_ratio)),
        "passed": bool(cand and min(cand) >= min_cand and min(ratios) >= min_ratio
                       and all(h == topn for h in hold)),
    }

    res = {
        "name": name,
        "fingerprint": _fingerprint(topn, rebalance, neutral, adv_gate, cost_mult, start, end,
                                    min_cand, min_ratio),
        "metrics": {
            "annual_return": round(ann, 4),
            "excess_annual": round(excess, 4),
            "sharpe": round(float(m["sharpe"]), 3),
            "max_drawdown": round(dd["max_drawdown"], 4),
            "calmar": (round(float(calmar), 3) if calmar is not None else None),
            "dd_days_max": dd["dd_days_max"],
            "turnover_per_period": round(float(turnover), 3),
            "adv_pct": (round(float(adv_pct), 3) if adv_pct is not None else None),
            "periods_per_year": round(float(periods_per_year), 2),
            "n_days": int(len(net)),
            "seg_2010_2015": _seg_ann(net, 2010, 2015),
            "seg_2016_2020": _seg_ann(net, 2016, 2020),
            "seg_2021_2026": _seg_ann(net, 2021, 2026),
            "annual_0x_cost": round(ann0, 4),
            "annual_1x_cost": round(ann1, 4),
            "annual_2x_cost": round(ann2, 4),
            "cost_theory_1x": round(theory1, 4),
            "cost_measured_1x": round(ann0 - ann1, 4),
        },
        "gate_audit": audit,
        "cost": {
            "total_1x": round(float(cost_base), 4),
            "per_year_1x": round(float(cost_base) / (len(net) / 252.0), 4) if len(net) else None,
            "theoretical_1x": round(theory1, 4),
            "rates": rates("2026-10-17"),
        },
    }

    if archive_result:
        import re
        from backtest.bt_report import archive
        verdict = "有效" if (ann > 0 and float(m["sharpe"]) > 0.5 and excess > 0) else ("观察" if ann > 0 else "无效")
        params = {
            "name": f"{name}（strict 2016+）", "strategy": "strict_validate",
            "factors": [name], "verdict": verdict,
            "fingerprint": res["fingerprint"],
            "gate_audit_passed": audit["passed"],
        }
        # 文件名清洗：Windows 不允许 * ? : " < > | 等字符（如 B4_BP*accel+rev）
        slug = re.sub(r'[^0-9A-Za-z_\-\.]', '_', f"{name}_strict_t{topn}")
        arch = archive(net, params=params, benchmark=bench, name=slug,
                       category="因子", factors=[name], verdict=verdict, save_html=False)
        res["archive"] = (arch or {}).get("json_path")

    return res
