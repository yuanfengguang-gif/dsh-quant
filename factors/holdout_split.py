# -*- coding: utf-8 -*-
"""factors/holdout_split.py —— 分年度 holdout（D-07 样本外/衰减检测）

冻结 8 因子组合（config/portfolio.yaml）在多个「训练/验证」切分上验证样本外表现：
  对每个切分点 split：训练窗 = [backtest.start, split]，验证窗 = [split, backtest.end]。
  ——验证窗只用冻结参数跑，不重选因子、不重定参，看净超额/夏普是否仍为正、是否衰减。

另输出分年度净超额（全窗 2021-2025 逐年），检测 alpha 是否随时间衰减。
用法：python factors/holdout_split.py [--out logs/holdout_split.json]
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from factors.import_qf_pool import load_panel
from factors.portfolio_builder import build_and_backtest


def load_config():
    with open(BASE / "config" / "portfolio.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(BASE / "logs" / "holdout_split.json"))
    args = ap.parse_args()

    cfg = load_config()
    names = [f["name"] for f in cfg["factors"]]
    directions = {f["name"]: f["direction"] for f in cfg["factors"]}
    pf = cfg["portfolio"]
    bt = cfg["backtest"]
    bt_start, bt_end = str(bt["start"]), str(bt["end"])
    splits = [str(s) for s in cfg["holdout"]["splits"]]  # yaml 解析成 date，转字符串

    print("加载面板（bars.db 全量 2019+）...", flush=True)
    panel = load_panel("data/cache/bars.db", start="2019-01-01")
    print(f"面板 {panel.shape}", flush=True)

    def run(start, end, label):
        r = build_and_backtest(
            panel, names, topn=pf["topn"], rebalance=pf["rebalance"],
            start=start, end=end,
            factor_weighting=pf["factor_weighting"], pos_weighting=pf["pos_weighting"],
            neutral=pf["neutral"], regime_on=pf["regime_on"],
            hard_filter_on=pf["hard_filter_on"], directions=directions)
        m, bm = r["metrics"], r["bench_metrics"]
        print(f"  {label:<28} 年化 {m['annual_return']:+.2%} | 基准 {bm['annual_return']:+.2%} "
              f"| 净超额 {r['excess_annual']:+.2%} | 夏普 {m['sharpe']:.2f} | 回撤 {m['max_drawdown']:.2%}", flush=True)
        return {"label": label, "start": start, "end": end,
                "annual": round(m["annual_return"], 6), "bench_annual": round(bm["annual_return"], 6),
                "excess": round(r["excess_annual"], 4), "sharpe": round(m["sharpe"], 3),
                "drawdown": round(m["max_drawdown"], 4), "n_days": m["n_days"]}

    print("\n=== 分年度 holdout（冻结 8 因子组合，验证窗不重选不重定参）===", flush=True)
    rows = []
    # 全样本参考（= 组合构建训练窗）
    rows.append(run(bt_start, bt_end, "全样本(参考)"))
    # 各切分点：验证窗 = [split, end]
    for sp in splits:
        rows.append(run(sp, bt_end, f"验证窗[{sp}~{bt_end}]"))

    # 分年度净超额（全窗逐年）
    print("\n=== 分年度净超额（全窗 2021-2025，衰减检测）===", flush=True)
    r_full = build_and_backtest(
        panel, names, topn=pf["topn"], rebalance=pf["rebalance"],
        start=bt_start, end=bt_end,
        factor_weighting=pf["factor_weighting"], pos_weighting=pf["pos_weighting"],
        neutral=pf["neutral"], regime_on=pf["regime_on"],
        hard_filter_on=pf["hard_filter_on"], directions=directions)
    yearly = {}
    for y, g in r_full["net_ret"].groupby(r_full["net_ret"].index.year):
        b = r_full["bench"].loc[g.index]
        yearly[str(y)] = round(float((1 + g).prod() - (1 + b).prod()), 4)
    for y, v in yearly.items():
        print(f"  {y}: {v:+.2%}", flush=True)

    out = {
        "validated_at": str(pd.Timestamp.now())[:19],
        "factors": names,
        "splits": rows,
        "yearly_excess": yearly,
        "params": {"topn": pf["topn"], "rebalance": str(pf["rebalance"])},
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已存：{args.out}")


if __name__ == "__main__":
    main()
