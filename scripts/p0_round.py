# -*- coding: utf-8 -*-
"""scripts/p0_round.py —— P0 四项任务一次性执行（2026-10-17）

任务 1：成本口径核对（定义表 + 0/1/2 倍理论 vs 实测，误差 < 0.5pp/年）
任务 2：流动性闸门自检（池内重选；候选池 ≥1500、持仓数 == TopN）
任务 3：锁定口径（strict_validate 默认值 + 参数指纹）
任务 4：剔除泡沫年份（同一口径重跑 start=2016-01-01）

产物：reports/p0_cost_gate_strict.json
用法：python scripts/p0_round.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from factors.import_qf_pool import load_panel, forward_returns, cross_sectional_ics
from factors.cost_model import describe as cost_describe, annual_cost, rates
from factors.strict_validate import strict_backtest, STRICT
from factors.validate_all_factors import FACTORS

reg = {n: fn for n, fn, _d in FACTORS}


def z_cs(s, clip=3.0):
    m = s.groupby(level=0).transform("mean")
    sd = s.groupby(level=0).transform("std")
    return ((s - m) / (sd + 1e-9)).clip(-clip, clip)


def main() -> int:
    print("=== 任务 1：成本定义 ===", flush=True)
    desc = cost_describe()
    for k, v in desc.items():
        print(f"  {k}: {v}")
    print(f"  单边买入 {rates('2026-10-17')['buy']:.4%} / 卖出 {rates('2026-10-17')['sell']:.4%} "
          f"/ 一次完整换手 {rates('2026-10-17')['round_trip']:.4%}（2020 年口径 "
          f"{rates('2020-01-02')['round_trip']:.4%}）", flush=True)

    from factors.window_config import get_window
    pstart = get_window()["panel_load_start"]
    print(f"\n加载面板（start={pstart}）...", flush=True)
    panel = load_panel("data/cache/bars.db", start=pstart)
    fwd = forward_returns(panel)
    print(f"面板 {panel.shape}", flush=True)

    bp = pd.Series(reg["bp_value"](panel)).reindex(panel.index)
    tm = pd.Series(reg["turn_mid_prox"](panel)).reindex(panel.index)
    d_bp = 1 if float(cross_sectional_ics(bp, fwd).mean()) >= 0 else -1
    d_tm = 1 if float(cross_sectional_ics(tm, fwd).mean()) >= 0 else -1
    bp, tm = bp * d_bp, tm * d_tm
    signals = {
        "bp_value": bp,
        "combo_z": (z_cs(bp) + z_cs(tm)) / 2.0,
    }

    runs = {}
    for name, sig in signals.items():
        for start in ("2010-01-01", "2016-01-01"):
            key = f"{name}@{start[:4]}"
            print(f"\n=== 严格回测 {key}（Top{STRICT['topn']} / {STRICT['rebalance']}日 / "
                  f"中性化={STRICT['neutral']} / ADV≥{STRICT['adv_gate']}）===", flush=True)
            r = strict_backtest(name, sig, panel, start=start, end="2026-10-16", fwd=fwd)
            runs[key] = r
            m = r["metrics"]
            print(f"  年化 {m['annual_return']:+.2%} 净超额 {m['excess_annual']:+.2%} "
                  f"夏普 {m['sharpe']:.3f} 回撤 {m['max_drawdown']:.1%} Calmar {m['calmar']} "
                  f"回撤持续 {m['dd_days_max']} 交易日", flush=True)
            g = r["gate_audit"]
            print(f"  闸门自检: 候选池 min={g['candidate_min']} 中位={g['candidate_median']:.0f} "
                  f"持仓 min={g['holdings_min']} 满仓天数={g['full_holdings_days']}/{g['days']} "
                  f"→ {'PASS' if g['passed'] else 'FAIL'}", flush=True)

    # ---- 成本审计：实测 vs 理论 ----
    print("\n=== 任务 1 验收：成本影响 实测 vs 理论 ===", flush=True)
    audit = {}
    for key, r in runs.items():
        m = r["metrics"]
        measured = float(m["annual_0x_cost"] - m["annual_1x_cost"])
        theory = float(m["cost_theory_1x"])
        err = abs(measured - theory) * 100
        audit[key] = {"measured_1x_pp": round(measured * 100, 2),
                      "theory_1x_pp": round(theory * 100, 2),
                      "abs_err_pp": round(err, 2), "passed": bool(err < 0.5)}
        print(f"  {key:16s} 实测 {measured*100:5.2f}pp  理论 {theory*100:5.2f}pp  "
              f"误差 {err:4.2f}pp  {'PASS' if err < 0.5 else 'FAIL'}", flush=True)

    gate_all = all(r["gate_audit"]["passed"] for r in runs.values())
    cost_all = all(v["passed"] for v in audit.values())
    fp_all = all("fingerprint" in r and r["fingerprint"].get("engine") for r in runs.values())

    out = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "locked_standard": dict(STRICT),
        "cost_definition": desc,
        "runs": runs,
        "cost_audit": audit,
        "p0_pass": {"task1_cost": cost_all, "task2_gate": gate_all,
                    "task3_fingerprint": fp_all, "task4_2016_reported": True},
        "notes": [
            "成本口径：买卖分边；印花税按成交日分段（2023-08-28 前 0.1%，之后 0.05%）",
            "旧口径 COST=0.176% 单边×2=0.352%：2023-08 前真实 0.354%（巧合接近），2023-08 后真实 0.304%（高估 0.048pp）",
            "流动性闸门为池内重选：先屏蔽 ADV<0.5 与 ST，再在合格池打分选 TopN",
        ],
    }
    rp = BASE / "reports" / "p0_cost_gate_strict.json"
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print("\n=== 任务 4：2016 起（剔除泡沫年份）===")
    for k in ("bp_value@2016", "combo_z@2016"):
        m = runs[k]["metrics"]
        print(f"  {k:16s} 年化 {m['annual_return']:+.2%} 净超额 {m['excess_annual']:+.2%} "
              f"夏普 {m['sharpe']:.3f} 回撤 {m['max_drawdown']:.1%} Calmar {m['calmar']} "
              f"回撤持续 {m['dd_days_max']} 日")

    print("\n=== P0 结论 ===")
    print(f"  task1 成本: {'PASS' if cost_all else 'FAIL'} | task2 闸门: {'PASS' if gate_all else 'FAIL'} "
          f"| task3 指纹: {'PASS' if fp_all else 'FAIL'} | task4 2016: reported")
    print(f"  结果已存：{rp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
