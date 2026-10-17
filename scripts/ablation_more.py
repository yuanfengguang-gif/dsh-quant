# -*- coding: utf-8 -*-
"""scripts/ablation_more.py —— 补充对照：调仓周期 / ST+流动性过滤 / 容量 / 成本 / 中盘基准

上一轮（ablation_combo.py）只扫了 TopN × 中性化。本脚本补四项：
  1) 调仓周期：20 / 40 / 60 交易日
  2) 过滤开关：ST 剔除 + 流动性后 5% 剔除（同时开/关）
  3) 容量：篮子 20 日均成交额的全市场分位（0=最差流动性）
  4) 成本敏感性：0× / 1× / 2× 成本下的年化
  5) 基准隔离：中性化组合的选股偏中盘（市值分位≈0.4），
     因此额外给出「中盘等权基准」的超额，判断它是不是只是中盘 beta。

固定：窗口 config/backtest_window.yaml、TopN=20、T+1 开盘、一字板过滤。
信号：bp_value（最稳单因子）与 combo_z（最强组合）。

用法：python scripts/ablation_more.py
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
from factors.validate_all_factors import FACTORS

reg = {n: fn for n, fn, _d in FACTORS}
SEGMENTS = [(2010, 2015), (2016, 2020), (2021, 2026)]


def rank_cs(s):
    return s.groupby(level=0).rank(pct=True)


def z_cs(s, clip=3.0):
    m = s.groupby(level=0).transform("mean")
    sd = s.groupby(level=0).transform("std")
    return ((s - m) / (sd + 1e-9)).clip(-clip, clip)


def seg_ann(net, a, b):
    r = net[(net.index.year >= a) & (net.index.year <= b)]
    return float(np.prod(1 + r) ** (252 / len(r)) - 1) if len(r) > 20 else None


def adv_percentile(adv_wide, score, topn, dates):
    """篮子 20 日均成交额的中位数 → 在最后一个交易日全市场分位。"""
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


def size_pct_of_picks(mv_rank, score, topn, dates):
    vals = []
    for d in dates:
        if d not in score.index or d not in mv_rank.index:
            continue
        picks = score.loc[d].dropna().nlargest(topn).index
        r = mv_rank.loc[d].reindex(picks).dropna()
        if len(r):
            vals.append(float(r.median()))
    return float(np.mean(vals)) if vals else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topn", type=int, default=20)
    ap.add_argument("--signals", default="bp_value,combo_z")
    ap.add_argument("--rebal", default="20,40,60")
    ap.add_argument("--min-adv", type=float, default=0.0,
                    help="只允许 ADV 分位≥该值的股票入选（0=不限制；0.5=流动性前 50%）")
    ap.add_argument("--only-neutral", action="store_true", help="只跑中性化版本")
    ap.add_argument("--only-filter", action="store_true", help="只跑开过滤版本")
    ap.add_argument("--out", default="logs/ablation_more.json")
    args = ap.parse_args()
    topn = args.topn
    names = [x.strip() for x in args.signals.split(",") if x.strip()]

    from factors.window_config import get_window
    pstart = get_window()["panel_load_start"]
    panel = load_panel("data/cache/bars.db", start=pstart)
    fwd = forward_returns(panel)
    print(f"面板 {panel.shape}", flush=True)

    win = ((panel.index.get_level_values(0) >= DEFAULT_START)
           & (panel.index.get_level_values(0) <= DEFAULT_END))
    p = panel[win]
    closes = p["close"].unstack().sort_index()
    opens = p["open"].unstack().sort_index()
    highs = p["high"].unstack().sort_index()

    # 基准
    bench_ew = closes.pct_change().fillna(0).mean(axis=1)
    mv_wide = load_mv_wide(closes.index, closes.columns)
    mv_rank = mv_wide.rank(axis=1, pct=True)
    mid_mask = (mv_rank > 1 / 3) & (mv_rank <= 2 / 3)
    bench_mid = closes.pct_change().where(mid_mask).mean(axis=1)
    print(f"回测切片 {closes.shape[0]} 日 × {closes.shape[1]} 只", flush=True)

    # 过滤掩码
    st_mask = (p["is_st"].unstack().reindex(index=closes.index, columns=closes.columns) == 1)
    adv_wide = p["amount"].unstack().rolling(20, min_periods=20).mean()
    illiquid = adv_wide.rank(axis=1, pct=True) <= 0.05
    if args.min_adv > 0:
        illiquid = illiquid | (adv_wide.rank(axis=1, pct=True) < args.min_adv)
    rebals = [int(x) for x in args.rebal.split(",") if x.strip()]
    neus = (True,) if args.only_neutral else (False, True)
    filts = (True,) if args.only_filter else (False, True)
    print(f"ST 掩码命中 {st_mask.values.mean():.2%}；流动性后 5% 掩码命中 {illiquid.values.mean():.2%}", flush=True)

    ind_map = load_industry_map()

    # 信号
    sigs = {}
    for n in ("bp_value", "turn_mid_prox"):
        s = pd.Series(reg[n](panel)).reindex(panel.index)
        d = 1 if float(cross_sectional_ics(s, fwd).mean()) >= 0 else -1
        sigs[n] = s * d
    combo_signals = {
        "bp_value": sigs["bp_value"],
        "combo_z": (z_cs(sigs["bp_value"]) + z_cs(sigs["turn_mid_prox"])) / 2.0,
    }
    name_map = {"bp_value": "bp_value", "combo_z": "combo_z"}

    rows = []
    for nm in names:
        s = combo_signals[name_map[nm]]
        base_score = _build_score(s[win], 1).reindex(closes.index)
        for filt in filts:
            sc_f = base_score
            if filt:
                sc_f = base_score.where(~(st_mask | illiquid))
            for neu in neus:
                sc = neutralize(sc_f.copy(), ind_map, mv_wide) if neu else sc_f
                for reb in rebals:
                    print(f"  {nm:10s} filter={filt!s:5s} neutral={neu!s:5s} rebal={reb:2d} ...", flush=True)
                    ret = _period_backtest(closes, opens, highs, sc.reindex(closes.index), topn, rebalance=reb)
                    rd = _rebalance_dates(sc.index, reb)
                    to = _turnover(sc, topn, rd)
                    cost_total = period_cost(to, dates=[d for d in rd if d in ret.index])
                    base = ret - cost_total / max(len(ret), 1)
                    m = compute_metrics(base)
                    bm = compute_metrics(bench_ew.loc[base.index])
                    mid = compute_metrics(bench_mid.loc[base.index])
                    ann = float(m["annual_return"])
                    ad = adv_percentile(adv_wide, sc, topn, rd)
                    sp = size_pct_of_picks(mv_rank, sc, topn, rd)
                    c0 = compute_metrics(ret)["annual_return"]
                    c2 = compute_metrics(ret - 2 * cost_total / max(len(ret), 1))["annual_return"]
                    rows.append({
                        "因子": nm, "过滤": "ST+流动性" if filt else "无",
                        "中性化": "有" if neu else "无", "调仓": reb,
                        "年化": round(ann, 4),
                        "超额_全市场": round(ann - float(bm["annual_return"]), 4),
                        "超额_中盘": round(ann - float(mid["annual_return"]), 4),
                        "夏普": round(float(m["sharpe"]), 3),
                        "回撤": round(float(m["max_drawdown"]), 4),
                        "换手": round(float(to), 3),
                        "ADV分位": (round(ad, 3) if ad is not None else None),
                        "选股市值分位": (round(sp, 3) if sp is not None else None),
                        "年化_零成本": round(float(c0), 4),
                        "年化_双倍成本": round(float(c2), 4),
                        **{f"{a}-{b}": (round(seg_ann(base, a, b), 4) if seg_ann(base, a, b) is not None else None)
                           for a, b in SEGMENTS},
                    })

    out = {"window": {"start": DEFAULT_START, "end": DEFAULT_END, "panel_load_start": pstart},
           "topn": topn, "min_adv": args.min_adv, "rows": rows,
           "note": "超额_中盘 = 组合年化 - 同一窗口内中盘（市值分位 1/3~2/3）等权基准年化；成本 1x≈0.4%/期双边"}
    pth = BASE / args.out
    pth.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    df = pd.DataFrame(rows)
    print("\n=== 补充对照表 ===")
    cols = ["因子", "过滤", "中性化", "调仓", "年化", "超额_全市场", "超额_中盘", "夏普", "回撤", "换手", "ADV分位", "选股市值分位"]
    print(df[cols].to_string(index=False))
    print(f"\n结果已存：{pth}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
