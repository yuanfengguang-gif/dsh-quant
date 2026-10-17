# -*- coding: utf-8 -*-
"""factors/combo_portfolio.py —— 多因子组合层（第三优先）

把通过三层验证的有效因子等权组合（各因子截面 rank 取均值），跑组合层 T+1 回测，
看分散化组合是否比单因子更稳、超额更大。

用法：python factors/combo_portfolio.py [--topn 20 --rebalance 40]
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

from factors.import_qf_pool import load_panel, forward_returns, cross_sectional_ics
from factors.combo_validate import (_build_score, _period_backtest, _rebalance_dates,
                                    _turnover, COST, VERDICT_SHARPE, DEFAULT_START, DEFAULT_END)
from factors.reproduce_factors import limup_ex_5, bp_value, sue, f_score
from backtest.bt_report import compute_metrics

# 有效因子（三层验证通过者）及其方向
EFFECTIVE = [
    ("limup_ex_5", limup_ex_5, -1),    # 涨停后反转（情绪）
    ("bp_value", bp_value, 1),          # 低PB价值（价值）
    ("sue", sue, 1),                    # 盈利超预期（成长）
    ("f_score", f_score, 1),            # 质量（roe）
]


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

    # 逐因子算信号 + 方向 + rank
    ranks = []
    for name, fn, direction in EFFECTIVE:
        try:
            sig = fn(panel)
            ics = cross_sectional_ics(sig, fwd)
            d = direction if direction is not None else (1 if ics.mean() >= 0 else -1)
            r = (sig * d).unstack().rank(axis=1, pct=True)
            ranks.append(r)
            print(f"  {name}: 方向 {d:+d} 覆盖率 {sig.notna().mean():.1%}", flush=True)
        except Exception as e:
            print(f"  {name}: 失败 {str(e)[:80]}", flush=True)

    if not ranks:
        print("无可组合因子", flush=True)
        return
    # 等权组合（各因子 rank 取均值）
    combo = sum(ranks) / len(ranks)

    # 切片 + 回测
    win = ((panel.index.get_level_values(0) >= DEFAULT_START)
           & (panel.index.get_level_values(0) <= DEFAULT_END))
    p = panel[win]
    closes = p["close"].unstack().sort_index()
    opens = p["open"].unstack().sort_index()
    highs = p["high"].unstack().sort_index()
    score = combo.sort_index().reindex(closes.index)
    bench = closes.pct_change().fillna(0).mean(axis=1)

    print(f"\n=== 多因子组合（{len(ranks)} 因子等权）top{topn}/调仓{rebalance} ===", flush=True)
    ret = _period_backtest(closes, opens, highs, score, topn, rebalance=rebalance)
    rdates = _rebalance_dates(score.index, rebalance)
    turnover = _turnover(score, topn, rdates)
    cost_total = COST * 2 * turnover * max(len(rdates), 1)
    net = ret - cost_total / max(len(ret), 1)
    m = compute_metrics(net)
    bm = compute_metrics(bench.loc[net.index])
    excess = m["annual_return"] - bm["annual_return"]
    verdict = ("有效" if (m["annual_return"] > 0 and m["sharpe"] > VERDICT_SHARPE and excess > 0)
               else ("观察" if m["annual_return"] > 0 else "无效"))
    print(f"年化 {m['annual_return']:+.2%} | 基准 {bm['annual_return']:+.2%} | 净超额 {excess:+.2%}")
    print(f"夏普 {m['sharpe']:.2f} | 回撤 {m['max_drawdown']:.2%} | 换手 {turnover:.0%} | 结论 {verdict}")

    # 分年度净超额
    print("\n分年度净超额:")
    for y, g in net.groupby(net.index.year):
        b = bench.loc[g.index]
        gy = (1 + g).prod() - 1
        by = (1 + b).prod() - 1
        print(f"  {y}: {gy-by:+.2%}")

    # 归档
    from backtest.bt_report import archive
    slug = f"combo_4factor_t{topn}"
    params = {"name": "多因子组合(涨停+价值+成长+质量)", "strategy": "combo_portfolio",
              "topn": topn, "rebalance": rebalance,
              "factors": [n for n, _, _ in EFFECTIVE],
              "note": "limup_ex_5(-1)+bp_value(+1)+sue(+1)+f_score(+1) 等权 rank 组合，T+1 open + 一字板 + 成本"}
    arch = archive(net, params=params, benchmark=bench.loc[net.index], name=slug,
                   category="策略", factors=[n for n, _, _ in EFFECTIVE],
                   verdict=verdict, save_html=False)
    print(f"\n归档: {arch['json_path']}")


if __name__ == "__main__":
    main()
