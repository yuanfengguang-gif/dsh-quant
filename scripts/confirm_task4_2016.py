# -*- coding: utf-8 -*-
"""scripts/confirm_task4_2016.py —— 改门槛后重跑任务 4，确认 2016+ 数字不变

改动只有闸门自检口径（候选池 ≥800 且 ≥40% 可打分），不影响选股与回测；
本脚本重跑 bp_value / combo_z 的 2016+ 结果，与 reports/p0_cost_gate_strict.json 对比。

用法：python scripts/confirm_task4_2016.py
产物：reports/confirm_task4_2016.json
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
from factors.strict_validate import strict_backtest, STRICT
from factors.validate_all_factors import FACTORS

reg = {n: fn for n, fn, _d in FACTORS}


def z_cs(s, clip=3.0):
    m = s.groupby(level=0).transform("mean")
    sd = s.groupby(level=0).transform("std")
    return ((s - m) / (sd + 1e-9)).clip(-clip, clip)


def main() -> int:
    from factors.window_config import get_window
    pstart = get_window()["panel_load_start"]
    panel = load_panel("data/cache/bars.db", start=pstart)
    fwd = forward_returns(panel)

    bp = pd.Series(reg["bp_value"](panel)).reindex(panel.index)
    tm = pd.Series(reg["turn_mid_prox"](panel)).reindex(panel.index)
    d_bp = 1 if float(cross_sectional_ics(bp, fwd).mean()) >= 0 else -1
    d_tm = 1 if float(cross_sectional_ics(tm, fwd).mean()) >= 0 else -1
    sigs = {"bp_value": bp * d_bp, "combo_z": (z_cs(bp * d_bp) + z_cs(tm * d_tm)) / 2.0}

    old = {}
    p0 = BASE / "reports" / "p0_cost_gate_strict.json"
    if p0.exists():
        old = json.loads(p0.read_text(encoding="utf-8")).get("runs", {})

    rows = []
    for name, sig in sigs.items():
        r = strict_backtest(name, sig, panel, start="2016-01-01", fwd=fwd)
        m = r["metrics"]
        prev = (old.get(f"{name}@2016") or {}).get("metrics") or {}
        diff = {}
        for k in ("annual_return", "excess_annual", "sharpe", "max_drawdown"):
            if prev.get(k) is not None:
                diff[k] = round(float(m[k]) - float(prev[k]), 6)
        rows.append({
            "因子": name, "metrics": m, "gate_audit": r["gate_audit"],
            "fingerprint_window": r["fingerprint"]["window"],
            "vs_previous_diff": diff,
            "unchanged": all(abs(v) < 1e-4 for v in diff.values()) if diff else None,
        })
        print(f"  {name:<10s} 年化 {m['annual_return']:+.2%} 超额 {m['excess_annual']:+.2%} "
              f"夏普 {m['sharpe']:.3f} 回撤 {m['max_drawdown']:.1%} Calmar {m['calmar']} "
              f"| 闸门 {'PASS' if r['gate_audit']['passed'] else 'FAIL'} "
              f"(候选 min={r['gate_audit']['candidate_min']}, ratio_min={r['gate_audit']['ratio_min']}) "
              f"| 与上次差异 {diff}")

    out = {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "strict": STRICT, "rows": rows}
    rp = BASE / "reports" / "confirm_task4_2016.json"
    rp.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"结果已存：{rp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
