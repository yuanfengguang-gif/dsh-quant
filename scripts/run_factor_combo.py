# -*- coding: utf-8 -*-
"""scripts/run_factor_combo.py —— 多因子等权 rank 合成 + 组合层 T+1 回测

用途：把因子池里的有效因子合成为一个组合（默认 bp_value + turn_mid_prox），
      并逐个单因子跑同一口径作对照。

口径（完全复用 factors.combo_validate_sig，不另写一套）：
  · 因子方向：按全样本截面 RankIC 均值定符号（与 combo_validate_sig 同约定）
  · 合成方式：各因子先做**逐日截面 pct rank**，再等权平均（对量纲/异常值稳健）
  · 回测：TopN 等权 + 40 交易日调仓 + T+1 开盘 + 一字板过滤 + 双边成本 0.4%/期
  · 窗口：config/backtest_window.yaml（2010-01-01 ~ 2026-10-16，面板 2008-12-01 预热）

用法：
    python scripts/run_factor_combo.py --factors bp_value,turn_mid_prox
    python scripts/run_factor_combo.py --factors bp_value,turn_mid_prox,margin_chg_20
    python scripts/run_factor_combo.py --factors bp_value,turn_mid_prox --no-singles

输出：
    output/backtest_archive/{name}_t20.json     单因子 + 组合（前端 /backtest 可见）
    logs/run_factor_combo_{tag}.json            对照表
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from factors.import_qf_pool import load_panel, forward_returns, cross_sectional_ics
from factors.combo_validate import (
    combo_validate_sig, DEFAULT_TOPN, DEFAULT_REBALANCE, DEFAULT_START, DEFAULT_END,
)


def _rank_cs(s: pd.Series) -> pd.Series:
    """逐日截面 pct rank（0~1），NaN 保持 NaN。"""
    return s.groupby(level=0).rank(pct=True)


def _z_cs(s: pd.Series, clip: float = 3.0) -> pd.Series:
    """逐日截面 z-score（clip ±clip），保留因子内的相对强弱，避免 rank 头部饱和。
    注意：rank 在尾部/头部会压平差异（最便宜的 20 只 rank 都≈1），
    合成时容易被另一个因子主导——这正是 bp+turn 等权组合被 turn 牵着走的原因。"""
    m = s.groupby(level=0).transform("mean")
    sd = s.groupby(level=0).transform("std")
    return ((s - m) / (sd + 1e-9)).clip(-clip, clip)


def _row(label: str, r: dict, cov: float) -> dict:
    m = r["metrics"]
    return {
        "因子": label,
        "结论": r["verdict"],
        "方向": f"{r['direction']:+d}",
        "覆盖率": round(cov, 4),
        "ICIR20": round(r["health"]["icir_20"], 3),
        "ICIR120": round(r["health"]["icir_120"], 3),
        "年化": round(m["annual_return"], 4),
        "净超额": round(r["excess_annual"], 4),
        "夏普": round(m["sharpe"], 3),
        "最大回撤": round(m["max_drawdown"], 4),
        "换手": round(r["capacity"]["turnover"], 3),
        "归档": r.get("archive"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--factors", default="bp_value,turn_mid_prox",
                    help="逗号分隔的因子名（须在 factors/validate_all_factors.py 的 FACTORS 注册表内）")
    ap.add_argument("--tag", default="", help="组合命名（默认 combo_<因子名拼接>）")
    ap.add_argument("--topn", type=int, default=DEFAULT_TOPN)
    ap.add_argument("--rebalance", default=DEFAULT_REBALANCE)
    ap.add_argument("--no-singles", action="store_true", help="只跑组合，不跑单因子对照")
    ap.add_argument("--weights", default="", help="逗号分隔权重，顺序对应 --factors；留空=等权")
    ap.add_argument("--method", choices=["rank", "zscore"], default="rank",
                    help="合成方式：rank=逐日 pct rank 平均（默认）；zscore=逐日 z-score 平均（保留强弱幅度）")
    args = ap.parse_args()

    names = [x.strip() for x in args.factors.split(",") if x.strip()]
    if not names:
        print("没有指定因子")
        return 2

    # 因子注册表（唯一来源，不在此另建清单）
    from factors.validate_all_factors import FACTORS
    reg = {n: fn for n, fn, _d in FACTORS}
    unknown = [n for n in names if n not in reg]
    if unknown:
        print(f"未注册的因子：{unknown}\n可选：{sorted(reg)}")
        return 2

    try:
        from factors.window_config import get_window
        pstart = get_window()["panel_load_start"]
    except Exception:
        pstart = "2008-12-01"

    print(f"加载面板（start={pstart}）...", flush=True)
    panel = load_panel("data/cache/bars.db", start=pstart)
    print(f"面板 {panel.shape}", flush=True)

    fwd = forward_returns(panel)
    sigs, meta = {}, {}
    for n in names:
        print(f"计算因子 {n} ...", flush=True)
        sig = reg[n](panel)
        sig = pd.Series(sig).reindex(panel.index)
        cov = float(sig.notna().mean())
        ics = cross_sectional_ics(sig, fwd)
        d = 1 if float(ics.mean()) >= 0 else -1
        sigs[n] = sig * d
        meta[n] = {"direction": d, "coverage": cov, "ic_mean": float(ics.mean())}
        print(f"  {n}: 覆盖 {cov:.1%} 方向 {d:+d} 全样本 IC 均值 {ics.mean():+.4f}", flush=True)

    # 等权 rank 合成（可用 --weights 指定配比）
    w = [float(x) for x in args.weights.split(",")] if args.weights else [1.0] * len(names)
    if len(w) != len(names):
        print(f"权重个数 {len(w)} 与因子个数 {len(names)} 不一致")
        return 2
    wsum = sum(w) or 1.0
    _trans = _rank_cs if args.method == "rank" else _z_cs
    combo = sum(wi * _trans(sigs[n]) for wi, n in zip(w, names)) / wsum
    _suffix = ("_w" + "_".join(f"{x:g}" for x in w)) if args.weights else ""
    if args.method == "zscore":
        _suffix += "_z"
    tag = args.tag or ("combo_" + "_".join(names) + _suffix)
    combo_cov = float(combo.notna().mean())
    print(f"合成信号 {tag}（method={args.method}）：覆盖 {combo_cov:.1%}", flush=True)

    rows = []
    if not args.no_singles:
        for n in names:
            print(f"组合层回测（单因子）{n} ...", flush=True)
            r = combo_validate_sig(n, sigs[n], panel, topn=args.topn, rebalance=args.rebalance,
                                   start=DEFAULT_START, end=DEFAULT_END)
            rows.append(_row(n, r, meta[n]["coverage"]))
            print(f"  {n}: {r['verdict']} 净超额 {r['excess_annual']:+.2%} 夏普 {r['metrics']['sharpe']:.2f}", flush=True)

    print(f"组合层回测（合成）{tag} ...", flush=True)
    rc = combo_validate_sig(tag, combo, panel, topn=args.topn, rebalance=args.rebalance,
                            start=DEFAULT_START, end=DEFAULT_END)
    rows.append(_row(tag, rc, combo_cov))
    print(f"  {tag}: {rc['verdict']} 净超额 {rc['excess_annual']:+.2%} 夏普 {rc['metrics']['sharpe']:.2f}", flush=True)

    out = {
        "window": {"start": DEFAULT_START, "end": DEFAULT_END, "panel_load_start": pstart},
        "topn": args.topn, "rebalance": args.rebalance,
        "factors": [{"name": n, **meta[n]} for n in names],
        "weights": w,
        "method": args.method,
        "weights_note": "cross-sectional weighted average of rank / zscore",
        "rows": rows,
    }
    p = BASE / "logs" / f"run_factor_combo_{tag}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    df = pd.DataFrame(rows)
    print("\n=== 对照表 ===")
    print(df.to_string(index=False))
    print(f"\n结果已存：{p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
