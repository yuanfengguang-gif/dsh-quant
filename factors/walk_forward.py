# -*- coding: utf-8 -*-
"""factors/walk_forward.py —— 前向模拟盘（D-07 样本外验证，纸面盘非实盘）

读 config/portfolio.yaml 冻结参数，在 [forward.start, 数据最新交易日] 窗口上跑 6 环节组合：
  L1 合成信号 → L5 硬过滤 → L4 行业×市值中性 → L2 Top15 → L3 等权 → L6 Regime 择时
输出：前向净超额/夏普/回撤 + 月度超额 + 当前 Top15 持仓（含股票名）+ 最新择时态 + 预警。

口径：T+1 open 买入 + 一字板过滤 + 成本 0.176%；基准 = 等权全市场。
用法：python factors/walk_forward.py [--out logs/walk_forward.json]
"""
import argparse
import json
import sqlite3
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

from factors.import_qf_pool import load_panel, forward_returns, cross_sectional_ics
from factors.portfolio_builder import (build_and_backtest, FACTOR_FNS, FAMILY,
                                       regime_position, composite_signal)

CACHE = BASE / "data" / "cache"


def load_config():
    with open(BASE / "config" / "portfolio.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_name_map():
    con = sqlite3.connect(f"file:{CACHE / 'stock_basic.db'}?mode=ro", uri=True)
    m = {r[0].split(".")[0]: r[1] for r in con.execute(
        "SELECT code, name FROM stock_basic").fetchall()}
    con.close()
    return m


def rolling_icir(factor_sig, fwd, window=20):
    """因子滚动 ICIR（最新值），用于失效预警。"""
    ics = cross_sectional_ics(factor_sig, fwd)
    if len(ics) < window // 2:
        return None
    r = ics.rolling(window, min_periods=window // 2)
    v = (r.mean() / r.std()).dropna()
    return float(v.iloc[-1]) if len(v) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(BASE / "logs" / "walk_forward.json"))
    args = ap.parse_args()

    cfg = load_config()
    names = [f["name"] for f in cfg["factors"]]
    directions = {f["name"]: f["direction"] for f in cfg["factors"]}
    pf = cfg["portfolio"]
    fwd_start = str(cfg["forward"]["start"])  # yaml 会把 2026-01-02 解析成 date，转字符串

    print("加载面板（bars.db 全量 2019+，供因子 warmup）...", flush=True)
    panel = load_panel("data/cache/bars.db", start="2019-01-01")
    latest = str(panel.index.get_level_values(0).max())[:10]
    print(f"面板 {panel.shape}，最新交易日 {latest}", flush=True)

    fwd = forward_returns(panel)

    # 前向回测（冻结方向）
    r = build_and_backtest(
        panel, names, topn=pf["topn"], rebalance=pf["rebalance"],
        start=fwd_start, end=latest,
        factor_weighting=pf["factor_weighting"], pos_weighting=pf["pos_weighting"],
        neutral=pf["neutral"], regime_on=pf["regime_on"],
        hard_filter_on=pf["hard_filter_on"], directions=directions)

    m, bm = r["metrics"], r["bench_metrics"]
    print("\n=== 前向模拟盘（样本外）===", flush=True)
    print(f"窗口 {fwd_start} ~ {latest}", flush=True)
    print(f"年化 {m['annual_return']:+.2%} | 基准 {bm['annual_return']:+.2%} "
          f"| 净超额 {r['excess_annual']:+.2%}", flush=True)
    print(f"夏普 {m['sharpe']:.2f} | 回撤 {m['max_drawdown']:.2%} | 样本 {m['n_days']} 天", flush=True)
    print(f"换手 {r['turnover']:.2%} | 调仓 {r['n_rebal']} 次 | 择时均仓 {r['regime_mean']:.2f}", flush=True)

    # 三级回撤控制触发记录
    dd_log = r.get("dd_log", [])
    print(f"\n=== 三级回撤控制触发记录（{len(dd_log)} 次仓位切换）===", flush=True)
    for e in dd_log[:20]:
        print(f"  {e['date']}  回撤 {e['dd']:+.1%} → 仓位 {e['仓位']:.0%}", flush=True)
    if not dd_log:
        print("  （未触发，回撤始终未超 5%）", flush=True)

    # 月度超额
    monthly = {}
    for ym, g in r["net_ret"].groupby(r["net_ret"].index.to_period("M")):
        b = r["bench"].loc[g.index]
        monthly[str(ym)] = round(float((1 + g).prod() - (1 + b).prod()), 4)
    print("月度净超额:", flush=True)
    for k, v in monthly.items():
        print(f"  {k}: {v:+.2%}", flush=True)

    # 当前 Top15 持仓（最新信号，含股票名）
    score = r["score"]
    top = score.iloc[-1].dropna().nlargest(pf["topn"])
    name_map = load_name_map()
    holdings = [{"code": c, "name": name_map.get(c.split(".")[0], ""),
                 "score": round(float(v), 4)} for c, v in top.items()]
    print(f"\n=== 当前 Top{len(holdings)} 持仓信号（最新交易日 {score.index[-1].date()}）===", flush=True)
    for h in holdings:
        print(f"  {h['code']:<10} {h['name']:<10} score={h['score']:+.4f}", flush=True)

    # 最新择时态
    closes = panel["close"].unstack().sort_index()
    reg = regime_position(closes)
    reg_now = float(reg.iloc[-1])
    state = "多头满仓" if reg_now >= 0.999 else "空头减半"
    print(f"\n最新 Regime 择时态：{state}（仓位乘数 {reg_now:.2f}）", flush=True)

    # 预警
    warns = []
    dd = m["max_drawdown"]
    risk = cfg["risk"]
    dd_warn = risk.get("drawdown_warning", 0.05)
    dd_ctrl = risk.get("drawdown_control", 0.10)
    dd_circuit = risk.get("drawdown_circuit", 0.15)
    if dd < -dd_circuit:
        warns.append(f"回撤 {dd:.1%} 触达熔断线 -{dd_circuit:.0%}（减至{risk.get('circuit_position', 0.30):.0%}仓位）")
    elif dd < -dd_ctrl:
        warns.append(f"回撤 {dd:.1%} 触达控制线 -{dd_ctrl:.0%}（停止新开仓·减仓）")
    elif dd < -dd_warn:
        warns.append(f"回撤 {dd:.1%} 触达警戒线 -{dd_warn:.0%}（降低新开仓）")
    # 因子失效预警
    for name in names:
        sig = FACTOR_FNS[name](panel).reindex(panel.index) * directions[name]
        icir = rolling_icir(sig, fwd, 20)
        if icir is not None and icir < risk["factor_icir_fail"]:
            warns.append(f"因子 {name} 滚动20日ICIR={icir:+.3f} < {risk['factor_icir_fail']}（失效预警）")
    print(f"\n预警（{len(warns)} 条）:", flush=True)
    for w in warns:
        print(f"  ⚠ {w}", flush=True)
    if not warns:
        print("  无", flush=True)

    out = {
        "validated_at": str(pd.Timestamp.now())[:19],
        "window": {"start": fwd_start, "end": latest},
        "factors": names,
        "metrics": {k: round(v, 6) if isinstance(v, (int, float)) else v for k, v in m.items()},
        "bench_annual": round(bm["annual_return"], 6),
        "excess_annual": round(r["excess_annual"], 4),
        "turnover": round(r["turnover"], 4),
        "n_rebal": r["n_rebal"],
        "regime_mean": round(r["regime_mean"], 4),
        "monthly_excess": monthly,
        "holdings": holdings,
        "regime_now": {"state": state, "multiplier": reg_now},
        "warnings": warns,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已存：{args.out}")


if __name__ == "__main__":
    main()
