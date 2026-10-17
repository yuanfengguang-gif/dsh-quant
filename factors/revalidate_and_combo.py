# -*- coding: utf-8 -*-
"""factors/revalidate_and_combo.py —— 重验 3 个 bug 因子 + 防守成分正交组合测试

1. 重验 chip_concentration / lowvol_60 / vol_contract（之前代码 bug 未测到）
2. turn_std20 / wr14 与基线防守组合（turn_mid_prox + amihud）的正交增量测试

用法：python factors/revalidate_and_combo.py [--topn 20 --rebalance 40]
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

from factors.import_qf_pool import load_panel, forward_returns, cross_sectional_ics, cross_corr
from factors.combo_validate import (combo_validate_sig, _period_backtest, _rebalance_dates,
                                    _turnover, COST, DEFAULT_START, DEFAULT_END)
from factors.reproduce_factors import turn_mid_prox
from factors.validate_all_factors import (chip_concentration, lowvol_60, vol_contract,
                                          turn_std20, wr14, amihud)
from backtest.bt_report import compute_metrics


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--topn", type=int, default=20)
    ap.add_argument("--rebalance", default=40)
    args = ap.parse_args()
    topn, rebalance = args.topn, args.rebalance
    if isinstance(rebalance, str) and rebalance.isdigit():
        rebalance = int(rebalance)

    print("加载面板...", flush=True)
    panel = load_panel("data/cache/bars.db", start="2019-01-01")
    fwd = forward_returns(panel)

    # ==================== 1. 重验 3 个 bug 因子 ====================
    print("=== 1. 重验 3 个 bug 因子 ===", flush=True)
    for name, fn in [("chip_concentration", chip_concentration),
                     ("lowvol_60", lowvol_60),
                     ("vol_contract", vol_contract)]:
        try:
            sig = fn(panel).reindex(panel.index)
            r = combo_validate_sig(name, sig, panel, topn=topn, rebalance=rebalance,
                                   start=DEFAULT_START, end=DEFAULT_END, direction=None)
            m = r["metrics"]
            print(f"  {name:<18} {r['verdict']} icir120={r['health']['icir_120']:+.3f} "
                  f"净超额={r['excess_annual']:+.2%} 夏普={m['sharpe']:.2f} 回撤={m['max_drawdown']:.1%}",
                  flush=True)
        except Exception as e:
            print(f"  {name:<18} 失败: {str(e)[:100]}", flush=True)

    # ==================== 2. 防守成分正交组合测试 ====================
    print("\n=== 2. 防守成分正交组合测试 ===", flush=True)

    def build_rank(name, fn, direction):
        sig = fn(panel).reindex(panel.index)
        ics = cross_sectional_ics(sig, fwd)
        d = direction if direction is not None else (1 if ics.mean() >= 0 else -1)
        return (sig * d).unstack().rank(axis=1, pct=True), d

    ranks = {}
    for n, fn, d in [("turn_mid_prox", turn_mid_prox, None),
                     ("amihud", amihud, None),
                     ("turn_std20", turn_std20, None),
                     ("wr14", wr14, None)]:
        try:
            ranks[n], dd = build_rank(n, fn, d)
            print(f"  {n}: 方向 {dd:+d}", flush=True)
        except Exception as e:
            print(f"  {n}: 失败 {str(e)[:80]}", flush=True)

    # 正交性
    tm, ah = turn_mid_prox(panel), amihud(panel)
    print("\n  正交性（逐日截面 Spearman）:", flush=True)
    for n, s in [("turn_std20", turn_std20(panel)), ("wr14", wr14(panel))]:
        print(f"    {n:<12} vs turn_mid_prox {cross_corr(s, tm):+.3f} | vs amihud {cross_corr(s, ah):+.3f}",
              flush=True)

    # 组合回测
    win = ((panel.index.get_level_values(0) >= DEFAULT_START)
           & (panel.index.get_level_values(0) <= DEFAULT_END))
    p = panel[win]
    closes = p["close"].unstack().sort_index()
    opens = p["open"].unstack().sort_index()
    highs = p["high"].unstack().sort_index()
    bench = closes.pct_change().fillna(0).mean(axis=1)

    combos = {
        "基线 turn_mid+amihud": ["turn_mid_prox", "amihud"],
        "+turn_std20": ["turn_mid_prox", "amihud", "turn_std20"],
        "+wr14": ["turn_mid_prox", "amihud", "wr14"],
        "+两者": ["turn_mid_prox", "amihud", "turn_std20", "wr14"],
    }
    print(f"\n  组合回测（等权 rank，top{topn}/调仓{rebalance}）:", flush=True)
    for cn, names in combos.items():
        combo = sum(ranks[n] for n in names) / len(names)
        score = combo.sort_index().reindex(closes.index)
        ret = _period_backtest(closes, opens, highs, score, topn, rebalance=rebalance)
        rdates = _rebalance_dates(score.index, rebalance)
        turnover = _turnover(score, topn, rdates)
        cost_total = COST * 2 * turnover * max(len(rdates), 1)
        net = ret - cost_total / max(len(ret), 1)
        m = compute_metrics(net)
        bm = compute_metrics(bench.loc[net.index])
        excess = m["annual_return"] - bm["annual_return"]
        print(f"    {cn:<22} 净超额 {excess:+.2%} 夏普 {m['sharpe']:.2f} 回撤 {m['max_drawdown']:.1%}",
              flush=True)


if __name__ == "__main__":
    main()
