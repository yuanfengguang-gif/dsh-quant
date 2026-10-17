# -*- coding: utf-8 -*-
"""scripts/ablation_combo.py —— 组合实验的对照（消融）测试

回答三个问题：
  1) 单因子与组合是否真的同引擎同参数？（是：全部走 combo_validate 的同一套 _build_score / _period_backtest / 成本模型）
  2) 中性化有没有影响？—— combo_validate 本身**不做中性化**；本脚本额外跑一版
     「行业 demean + log(流通市值) 正交化」（复用 factors/portfolio_builder.neutralize），两版对照。
  3) TopN 差异有没有影响？—— 同一信号在 TopN=10/20/50 下分别回测。

设计（只改一个变量）：
  · 固定：窗口 config/backtest_window.yaml、40 交易日调仓、T+1 开盘、一字板过滤、成本 0.4%/期（双边）
  · 变动：{bp_value, turn_mid_prox, combo_rank, combo_z} × {未中性化, 中性化} × {Top10, Top20, Top50}
  · 不写回测档案（避免污染 /backtest 页面），结果落 logs/ablation_combo.json

用法：
    python scripts/ablation_combo.py
    python scripts/ablation_combo.py --tops 10,20,50 --neutral both
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from factors.import_qf_pool import load_panel, forward_returns, cross_sectional_ics
from factors.combo_validate import (
    _build_score, _rebalance_dates, _turnover, DEFAULT_START, DEFAULT_END,
)
from factors.cost_model import period_cost
from factors.portfolio_builder import load_industry_map, load_mv_wide, neutralize
from backtest.bt_runner import _period_backtest
from backtest.bt_report import compute_metrics

SEGMENTS = [(2010, 2015), (2016, 2020), (2021, 2026)]


def _rank_cs(s):
    return s.groupby(level=0).rank(pct=True)


def _z_cs(s, clip=3.0):
    m = s.groupby(level=0).transform("mean")
    sd = s.groupby(level=0).transform("std")
    return ((s - m) / (sd + 1e-9)).clip(-clip, clip)


def _seg_ann(net, a, b):
    r = net[(net.index.year >= a) & (net.index.year <= b)]
    return float(np.prod(1.0 + r) ** (252.0 / len(r)) - 1.0) if len(r) > 20 else None


def _run(score, closes, opens, highs, bench, topn, rebalance):
    score = score.reindex(closes.index)
    ret = _period_backtest(closes, opens, highs, score, topn, rebalance=rebalance)
    rdates = _rebalance_dates(score.index, rebalance)
    turnover = _turnover(score, topn, rdates)
    n_periods = len(rdates) or 1
    net = ret - period_cost(turnover, dates=rdates) / max(len(ret), 1)
    m = compute_metrics(net)
    bm = compute_metrics(bench.loc[net.index])
    segs = {f"{a}-{b}": _seg_ann(net, a, b) for a, b in SEGMENTS}
    return {
        "topn": topn, "年化": round(float(m["annual_return"]), 4),
        "净超额": round(float(m["annual_return"] - bm["annual_return"]), 4),
        "夏普": round(float(m["sharpe"]), 3),
        "最大回撤": round(float(m["max_drawdown"]), 4),
        "换手": round(float(turnover), 3),
        **{k: (round(v, 4) if v is not None else None) for k, v in segs.items()},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tops", default="10,20,50")
    ap.add_argument("--neutral", choices=["both", "off", "on"], default="both")
    ap.add_argument("--rebalance", type=int, default=40)
    args = ap.parse_args()
    tops = [int(x) for x in args.tops.split(",") if x.strip()]
    variants = {"off": [False], "on": [True], "both": [False, True]}[args.neutral]

    from factors.validate_all_factors import FACTORS
    reg = {n: fn for n, fn, _d in FACTORS}

    try:
        from factors.window_config import get_window
        pstart = get_window()["panel_load_start"]
    except Exception:
        pstart = "2008-12-01"

    print(f"加载面板（start={pstart}）...", flush=True)
    panel = load_panel("data/cache/bars.db", start=pstart)
    print(f"面板 {panel.shape}", flush=True)
    fwd = forward_returns(panel)

    win = ((panel.index.get_level_values(0) >= DEFAULT_START)
           & (panel.index.get_level_values(0) <= DEFAULT_END))
    p = panel[win]
    closes = p["close"].unstack().sort_index()
    opens = p["open"].unstack().sort_index()
    highs = p["high"].unstack().sort_index()
    bench = closes.pct_change().fillna(0).mean(axis=1)
    print(f"回测切片 {closes.shape[0]} 日 × {closes.shape[1]} 只", flush=True)

    # ---- 信号（全样本算、切窗口用）----
    sigs = {}
    dirs = {}
    for n in ("bp_value", "turn_mid_prox"):
        print(f"计算 {n} ...", flush=True)
        s = pd.Series(reg[n](panel)).reindex(panel.index)
        d = 1 if float(cross_sectional_ics(s, fwd).mean()) >= 0 else -1
        sigs[n] = s * d
        dirs[n] = d
    ics_bp = sigs["bp_value"]
    ics_tm = sigs["turn_mid_prox"]
    sigs["combo_rank"] = (_rank_cs(ics_bp) + _rank_cs(ics_tm)) / 2.0
    sigs["combo_z"] = (_z_cs(ics_bp) + _z_cs(ics_tm)) / 2.0
    dirs["combo_rank"] = dirs["combo_z"] = 1

    # ---- 中性化所需数据 ----
    ind_map = load_industry_map()
    mv_wide = load_mv_wide(closes.index, closes.columns)
    print(f"行业映射 {len(ind_map)} 只；市值面板 {mv_wide.shape}", flush=True)

    rows = []
    for name, s in sigs.items():
        score_raw = _build_score(s[win], dirs[name]).reindex(closes.index)
        scores = {"未中性化": score_raw}
        if True in variants:
            print(f"中性化 {name} ...", flush=True)
            scores["中性化"] = neutralize(score_raw.copy(), ind_map, mv_wide).reindex(closes.index)
        for tag, sc in scores.items():
            if (tag == "中性化") and (False in variants and True not in variants):
                continue
            if (tag == "未中性化") and (True in variants and False not in variants):
                continue
            for topn in tops:
                print(f"  回测 {name:14s} {tag:6s} Top{topn:<3d} ...", flush=True)
                r = _run(sc, closes, opens, highs, bench, topn, args.rebalance)
                rows.append({"因子": name, "中性化": tag, **r})
                print(f"    → 年化 {r['年化']:+.2%} 超额 {r['净超额']:+.2%} 夏普 {r['夏普']:.2f} 回撤 {r['最大回撤']:.1%}", flush=True)

    out = {
        "window": {"start": DEFAULT_START, "end": DEFAULT_END, "panel_load_start": pstart},
        "rebalance": args.rebalance, "cost_model": "config/costs.yaml（买卖分边 + 分段印花税）",
        "note": "combo_validate 本身不中性化；'中性化'=portfolio_builder.neutralize（行业 demean + log circ_mv 正交）",
        "rows": rows,
    }
    pth = BASE / "logs" / "ablation_combo.json"
    pth.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    df = pd.DataFrame(rows)
    print("\n=== 消融表 ===")
    print(df.to_string(index=False))
    print(f"\n结果已存：{pth}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
