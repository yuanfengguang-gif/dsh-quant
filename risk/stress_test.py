# -*- coding: utf-8 -*-
"""risk/stress_test.py —— 组合压力测试（层4 风控收尾）

把冻结的 8 因子组合（config/portfolio.yaml）放到历史危机窗口，看它扛不扛得住：
  2021-02 核心资产抱团崩 / 2022-01~04 俄乌+加息熊市 / 2024-01~02 微盘股+雪球
输出：每个危机窗口的组合 vs 基准 累计收益 + 窗口内最大回撤。

口径：与 walk_forward 一致（8 因子等权 + 中性 + 硬过滤 + 择时 + 三级回撤 + 个股止损）。
数据边界：bars.db 2019+，危机窗口只能覆盖 2021 起（2020 疫情在回测 warmup 前，测不了，如实披露）。
用法：python risk/stress_test.py [--out logs/stress_test.json]
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

# 危机窗口（均落在 2019+ 数据内、且过了 60 日 warmup）
CRISIS_WINDOWS = [
    ("2021 核心资产抱团崩", "2021-02-18", "2021-03-09"),
    ("2022 俄乌+加息熊市", "2022-01-04", "2022-04-26"),
    ("2024 微盘股+雪球", "2024-01-02", "2024-02-05"),
    ("2024 持续阴跌", "2024-06-01", "2024-09-18"),
]


def window_metrics(net_ret, bench, start, end):
    """窗口内累计收益 + 窗口内最大回撤（从窗口自身峰值算）。"""
    pr = net_ret[(net_ret.index >= start) & (net_ret.index <= end)]
    br = bench[(bench.index >= start) & (bench.index <= end)]
    if len(pr) < 2:
        return None
    port_ret = float((1 + pr).prod() - 1)
    bench_ret = float((1 + br).prod() - 1)
    nav_p = (1 + pr).cumprod()
    dd_p = float((nav_p / nav_p.cummax() - 1).min())
    nav_b = (1 + br).cumprod()
    dd_b = float((nav_b / nav_b.cummax() - 1).min())
    return {"组合收益": round(port_ret, 4), "基准收益": round(bench_ret, 4),
            "超额": round(port_ret - bench_ret, 4),
            "组合回撤": round(dd_p, 4), "基准回撤": round(dd_b, 4),
            "天数": len(pr)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(BASE / "logs" / "stress_test.json"))
    args = ap.parse_args()

    cfg = yaml.safe_load((BASE / "config" / "portfolio.yaml").read_text(encoding="utf-8"))
    names = [f["name"] for f in cfg["factors"]]
    directions = {f["name"]: f["direction"] for f in cfg["factors"]}
    pf = cfg["portfolio"]
    bt = cfg["backtest"]

    print("加载面板 + 跑全样本组合（8 因子 + 全风控）...", flush=True)
    panel = load_panel("data/cache/bars.db", start="2019-01-01")
    r = build_and_backtest(
        panel, names, topn=pf["topn"], rebalance=pf["rebalance"],
        start=str(bt["start"]), end=str(bt["end"]),
        factor_weighting=pf["factor_weighting"], pos_weighting=pf["pos_weighting"],
        neutral=pf["neutral"], regime_on=pf["regime_on"],
        hard_filter_on=pf["hard_filter_on"], directions=directions, stop_loss=True)

    net_ret, bench = r["net_ret"], r["bench"]
    m = r["metrics"]
    print(f"全样本(2020-06~2025-12): 净超额 {r['excess_annual']:+.2%} 夏普 {m['sharpe']:.2f} 回撤 {m['max_drawdown']:.2%}", flush=True)

    print("\n=== 压力测试：危机窗口的组合 vs 基准 ===", flush=True)
    print(f"{'窗口':<22} {'组合收益':>8} {'基准收益':>8} {'超额':>8} {'组合回撤':>8} {'基准回撤':>8}", flush=True)
    rows = []
    for name, s, e in CRISIS_WINDOWS:
        wm = window_metrics(net_ret, bench, s, e)
        if wm is None:
            print(f"{name:<22} 数据不足（窗口内 <2 交易日）", flush=True)
            continue
        print(f"{name:<22} {wm['组合收益']:>+8.1%} {wm['基准收益']:>+8.1%} {wm['超额']:>+8.1%} "
              f"{wm['组合回撤']:>8.1%} {wm['基准回撤']:>8.1%}", flush=True)
        rows.append({"窗口": name, "start": s, "end": e, **wm})

    # 全样本整体 + 前向参考
    out = {
        "validated_at": str(pd.Timestamp.now())[:19],
        "全样本": {"净超额": round(r["excess_annual"], 4), "夏普": round(m["sharpe"], 3),
                   "回撤": round(m["max_drawdown"], 4)},
        "crisis_windows": rows,
        "note": "数据边界 bars.db 2019+：2020 疫情在回测 warmup 前测不了；危机窗口只覆盖 2021 起。",
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已存：{args.out}")


if __name__ == "__main__":
    main()
