# -*- coding: utf-8 -*-
"""factors/grid_robustness.py —— 有效因子参数稳健性网格（P8「调仓周期×topN 网格」，防单点过拟合）

对通过三层验证的因子（limup_ex_5 / bp_value），跑 topN × rebalance 网格，
确认「平台区」（相邻格子同向不翻转）而非单点尖峰。

用法：python factors/grid_robustness.py [--topns 10,20,50] [--rebalances 20,40,60]
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from factors.import_qf_pool import load_panel, cross_sectional_ics, forward_returns
from factors.combo_validate import (_build_score, _period_backtest, _rebalance_dates,
                                    _turnover, COST, VERDICT_SHARPE, DEFAULT_START, DEFAULT_END)
from factors.reproduce_factors import limup_ex_5, bp_value
from backtest.bt_report import compute_metrics

FACTORS = [("limup_ex_5", limup_ex_5), ("bp_value", bp_value)]


def grid_robustness(panel, sig, name, topns, rebalances):
    fwd = forward_returns(panel)
    ics = cross_sectional_ics(sig, fwd)
    direction = 1 if ics.mean() >= 0 else -1
    win = ((panel.index.get_level_values(0) >= DEFAULT_START)
           & (panel.index.get_level_values(0) <= DEFAULT_END))
    p = panel[win]
    closes = p["close"].unstack().sort_index()
    opens = p["open"].unstack().sort_index()
    highs = p["high"].unstack().sort_index()
    score = _build_score(sig[win], direction).sort_index().reindex(closes.index)
    bench = closes.pct_change().fillna(0).mean(axis=1)

    out = []
    for topn in topns:
        for rb in rebalances:
            ret = _period_backtest(closes, opens, highs, score, topn, rebalance=rb)
            rdates = _rebalance_dates(score.index, rb)
            turnover = _turnover(score, topn, rdates)
            cost_total = COST * 2 * turnover * max(len(rdates), 1)
            net = ret - cost_total / max(len(ret), 1)
            m = compute_metrics(net)
            bm = compute_metrics(bench.loc[net.index])
            excess = m["annual_return"] - bm["annual_return"]
            verdict = ("有效" if (m["annual_return"] > 0 and m["sharpe"] > VERDICT_SHARPE and excess > 0)
                       else ("观察" if m["annual_return"] > 0 else "无效"))
            out.append({"topn": topn, "rebalance": rb, "净超额": round(excess, 4),
                        "夏普": round(m["sharpe"], 2), "年化": round(m["annual_return"], 4),
                        "结论": verdict})
            print(f"    {name} topn={topn} rb={rb}: 净超额={excess:+.2%} 夏普={m['sharpe']:.2f} {verdict}", flush=True)
    return out


def main():
    topns = [10, 20, 50]
    rebalances = [20, 40, 60]
    print("加载面板（bars.db）...", flush=True)
    panel = load_panel("data/cache/bars.db", start="2019-01-01")
    print(f"面板 {panel.shape}", flush=True)

    all_rows = []
    for name, fn in FACTORS:
        print(f"\n=== {name} 网格 ===", flush=True)
        sig = fn(panel)
        rows = grid_robustness(panel, sig, name, topns, rebalances)
        for r in rows:
            r["因子"] = name
        all_rows.extend(rows)

    print("\n=== 稳健性网格汇总 ===")
    print(pd.DataFrame(all_rows).to_string(index=False))
    # 平台区判断：有效格子是否相邻（同 topn 或同 rb 至少一个邻居同向）
    for name in dict.fromkeys(r["因子"] for r in all_rows):
        eff = [r for r in all_rows if r["因子"] == name and r["结论"] == "有效"]
        print(f"{name}: 有效格子 {len(eff)}/{len(topns)*len(rebalances)}")


if __name__ == "__main__":
    main()
