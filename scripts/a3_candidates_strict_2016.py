# -*- coding: utf-8 -*-
"""scripts/a3_candidates_strict_2016.py —— A3 五条候选在 P0 锁定口径（2016+）下的回测

候选（A3 初筛里 ICIR20>0.2、ICIR120>0.1、IC 均值>0 的 5 条）：
  B4_BP+sue / B1_EP+BP / B4_BP*accel+rev / C5_max3_vol / C1_turn+volchg
每个都走 factors/strict_validate.py（ADV≥0.5 池内重选 + Top20 + 20日 + 中性化 + 配置成本），
并归档用于后续 |ρ| 去重。

用法：python scripts/a3_candidates_strict_2016.py
产物：reports/a3_candidates_2016.json + output/backtest_archive/*_strict_t20_*.json
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

from factors.import_qf_pool import load_panel, forward_returns
from factors.formula_miner import FEATURE_BUILDERS, validate, execute
from factors.strict_validate import strict_backtest, STRICT
from factors.window_config import get_window

CANDIDATES = [
    ("B4_BP+sue", "BP SUE ADD TS_RANK20"),
    ("B1_EP+BP", "EP BP ADD TS_RANK20"),
    ("B4_BP*accel+rev", "BP ACCEL MUL REV_YOY ADD TS_RANK20"),
    ("C5_max3_vol", "RET MAX3 VOLAT DIV NEG"),
    ("C1_turn+volchg", "TURN VOL_CHG ADD TS_RANK20 NEG"),
]


def verdict(ann: float, sharpe: float, excess: float) -> str:
    if ann > 0 and sharpe > 0.5 and excess > 0:
        return "有效"
    return "观察" if ann > 0 else "无效"


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="逗号分隔候选名，只跑这些")
    ap.add_argument("--tag", default="", help="输出文件后缀")
    args = ap.parse_args()
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    todo = [t for t in CANDIDATES if (not only or t[0] in only)]

    pstart = get_window()["panel_load_start"]
    print(f"加载面板（start={pstart}）...", flush=True)
    panel = load_panel("data/cache/bars.db", start=pstart)
    fwd = forward_returns(panel)
    print(f"面板 {panel.shape}", flush=True)

    print("构建 15 个特征叶子 ...", flush=True)
    feat = {}
    for k, fn in FEATURE_BUILDERS.items():
        try:
            feat[k] = fn(panel)
        except Exception as e:
            print(f"  ✘ {k}: {str(e)[:60]}", flush=True)
    print(f"  成功 {len(feat)}/{len(FEATURE_BUILDERS)}", flush=True)

    rows = []
    for name, formula in todo:
        toks = formula.split()
        try:
            if not validate(toks):
                raise RuntimeError("语法非法")
            sig, err = execute(toks, feat, panel.index)
            if err:
                raise RuntimeError(err)
            sig = pd.Series(sig).reindex(panel.index)
            print(f"  {name:<18s} 回测中（覆盖 {sig.notna().mean():.1%}）...", flush=True)
            r = strict_backtest(name, sig, panel, fwd=fwd, archive_result=True)
            m = r["metrics"]
            v = verdict(m["annual_return"], m["sharpe"], m["excess_annual"])
            rows.append({
                "因子": name, "公式": formula, "结论": v,
                "年化": m["annual_return"], "净超额": m["excess_annual"], "夏普": m["sharpe"],
                "回撤": m["max_drawdown"], "Calmar": m["calmar"], "回撤天数": m["dd_days_max"],
                "2016-2020": m["seg_2016_2020"], "2021-2026": m["seg_2021_2026"],
                "闸门": ("PASS" if r["gate_audit"]["passed"] else "FAIL"),
                "候选池min": r["gate_audit"]["candidate_min"],
                "归档": r.get("archive"),
            })
            print(f"    → {v} 年化 {m['annual_return']:+.2%} 超额 {m['excess_annual']:+.2%} "
                  f"夏普 {m['sharpe']:.2f} Calmar {m['calmar']}", flush=True)
        except Exception as e:
            rows.append({"因子": name, "公式": formula, "结论": f"失败:{str(e)[:80]}"})
            print(f"    ✘ {str(e)[:100]}", flush=True)

    out = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "standard": STRICT,
        "rows": rows,
    }
    rp = BASE / "reports" / f"a3_candidates_2016{args.tag}.json"
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("\n=== A3 五条候选（2016+ 锁定口径）===")
    print(pd.DataFrame(rows).to_string(index=False))
    print(f"\n结果已存：{rp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
