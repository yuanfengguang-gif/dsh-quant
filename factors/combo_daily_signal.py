# -*- coding: utf-8 -*-
"""factors/combo_daily_signal.py —— 组合每日信号（第三优先：组合上每日信号链）

计算 3 个有效因子（涨停+价值+成长）当日截面 rank 均值 → 输出今日主力组合候选 topN，
供每日信号链（live_api「主力参考」层）消费。

用法：python factors/combo_daily_signal.py [--topn 20] [--out logs/combo_signal_latest.json]
"""
import argparse
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import pandas as pd

from factors.import_qf_pool import load_panel, forward_returns, cross_sectional_ics
from factors.reproduce_factors import limup_ex_5, bp_value, sue

EFFECTIVE = [("limup_ex_5", limup_ex_5, -1), ("bp_value", bp_value, 1), ("sue", sue, 1)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topn", type=int, default=20)
    ap.add_argument("--out", default="logs/combo_signal_latest.json")
    args = ap.parse_args()

    print("加载面板...", flush=True)
    panel = load_panel("data/cache/bars.db", start="2019-01-01")
    fwd = forward_returns(panel)
    data_date = str(panel.index.get_level_values(0).max())[:10]

    ranks = []
    for name, fn, direction in EFFECTIVE:
        sig = fn(panel)
        ics = cross_sectional_ics(sig, fwd)
        d = direction if direction is not None else (1 if ics.mean() >= 0 else -1)
        ranks.append((sig * d).unstack().rank(axis=1, pct=True))
        print(f"  {name}: 方向 {d:+d}", flush=True)

    combo = sum(ranks) / len(ranks)
    latest = combo.loc[data_date].dropna().sort_values(ascending=False).head(args.topn)
    top = [{"code": c.split(".")[0], "score": round(float(v), 4)} for c, v in latest.items()]

    out = {"date": data_date, "strategy": "combo_3factor",
           "factors": [n for n, _, _ in EFFECTIVE], "topn": args.topn, "candidates": top}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{data_date} 主力组合候选 top{args.topn}（涨停+价值+成长组合）:", flush=True)
    for t in top:
        print(f"  {t['code']}: {t['score']:.4f}", flush=True)
    print(f"信号文件: {args.out}", flush=True)


if __name__ == "__main__":
    main()
