# -*- coding: utf-8 -*-
"""scripts/rebuild36_strict_2016.py —— 用锁定口径重建因子档案（2016-01-01 起）

与旧轮次的区别（本轮关键变化）：
  · 样本起点 **2016-01-01**（不是 2010-2026）
  · 全部走 factors/strict_validate.py：ADV≥0.5 池内重选 + Top20 + 20日调仓 + 中性化 + 配置化成本
  · 每个因子归档时带参数指纹与闸门自检结果

用法：python scripts/rebuild36_strict_2016.py
产物：reports/rebuild36_strict_2016.json + output/backtest_archive/*_strict_t20_*.json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import argparse
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from factors.import_qf_pool import load_panel, forward_returns
from factors.strict_validate import strict_backtest, STRICT
from factors.validate_all_factors import FACTORS, CATEGORY
from factors.window_config import get_window


def verdict(ann: float, sharpe: float, excess: float) -> str:
    if ann > 0 and sharpe > 0.5 and excess > 0:
        return "有效"
    return "观察" if ann > 0 else "无效"


def z_cs(s, clip: float = 3.0):
    m = s.groupby(level=0).transform("mean")
    sd = s.groupby(level=0).transform("std")
    return ((s - m) / (sd + 1e-9)).clip(-clip, clip)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="逗号分隔因子名，只跑这些（分批并行用）")
    ap.add_argument("--tag", default="", help="输出文件名后缀，如 _half1")
    args = ap.parse_args()
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    todo = [t for t in FACTORS if (not only or t[0] in only)]

    pstart = get_window()["panel_load_start"]
    print(f"加载面板（start={pstart}，评估窗口 {STRICT['start']} ~ {STRICT['end']}）...", flush=True)
    panel = load_panel("data/cache/bars.db", start=pstart)
    fwd = forward_returns(panel)
    print(f"面板 {panel.shape}", flush=True)

    rows = []
    captured = {}
    for name, fn, _d in todo:
        try:
            print(f"  {name:<18s} ...", flush=True)
            sig = pd.Series(fn(panel)).reindex(panel.index)
            if name in ("bp_value", "turn_mid_prox"):
                captured[name] = sig
            r = strict_backtest(name, sig, panel, fwd=fwd, archive_result=True)
            m = r["metrics"]
            v = verdict(m["annual_return"], m["sharpe"], m["excess_annual"])
            rows.append({
                "因子": name, "族": CATEGORY.get(name, "其他"), "结论": v,
                "年化": m["annual_return"], "净超额": m["excess_annual"], "夏普": m["sharpe"],
                "回撤": m["max_drawdown"], "Calmar": m["calmar"], "回撤天数": m["dd_days_max"],
                "换手": m["turnover_per_period"], "ADV分位": m["adv_pct"],
                "2016-2020": m["seg_2016_2020"], "2021-2026": m["seg_2021_2026"],
                "闸门": ("PASS" if r["gate_audit"]["passed"] else "FAIL"),
                "候选池min": r["gate_audit"]["candidate_min"],
                "指纹": r["fingerprint"]["engine"] + "/" + r["fingerprint"]["window"]["start"],
                "归档": r.get("archive"),
            })
            print(f"    → {v} 年化 {m['annual_return']:+.2%} 超额 {m['excess_annual']:+.2%} "
                  f"夏普 {m['sharpe']:.2f} Calmar {m['calmar']} 闸门 "
                  f"{'PASS' if r['gate_audit']['passed'] else 'FAIL'}", flush=True)
        except Exception as e:
            rows.append({"因子": name, "族": CATEGORY.get(name, "其他"), "结论": f"失败:{str(e)[:80]}"})
            print(f"    ✘ {str(e)[:100]}", flush=True)

    # A1 校验用：combo_z（2 因子 z-score 合成）同口径跑一遍（不计入 36 因子统计）
    if "bp_value" in captured and "turn_mid_prox" in captured:
        try:
            print("  combo_z（2因子合成） ...", flush=True)
            comb = (z_cs(captured["bp_value"]) + z_cs(captured["turn_mid_prox"])) / 2.0
            r = strict_backtest("combo_z", comb, panel, fwd=fwd, archive_result=True)
            m = r["metrics"]
            v = verdict(m["annual_return"], m["sharpe"], m["excess_annual"])
            rows.append({
                "因子": "combo_z", "族": "组合", "结论": v,
                "年化": m["annual_return"], "净超额": m["excess_annual"], "夏普": m["sharpe"],
                "回撤": m["max_drawdown"], "Calmar": m["calmar"], "回撤天数": m["dd_days_max"],
                "换手": m["turnover_per_period"], "ADV分位": m["adv_pct"],
                "2016-2020": m["seg_2016_2020"], "2021-2026": m["seg_2021_2026"],
                "闸门": ("PASS" if r["gate_audit"]["passed"] else "FAIL"),
                "候选池min": r["gate_audit"]["candidate_min"],
                "指纹": r["fingerprint"]["engine"] + "/" + r["fingerprint"]["window"]["start"],
                "归档": r.get("archive"),
            })
            print(f"    → {v} 年化 {m['annual_return']:+.2%} 超额 {m['excess_annual']:+.2%} "
                  f"夏普 {m['sharpe']:.2f} Calmar {m['calmar']}", flush=True)
        except Exception as e:
            rows.append({"因子": "combo_z", "族": "组合", "结论": f"失败:{str(e)[:80]}"})
            print(f"    ✘ combo_z {str(e)[:100]}", flush=True)

    core = [r for r in rows if r.get("因子") != "combo_z"]
    ok = [r for r in core if r.get("结论") in ("有效", "观察", "无效")]
    valid = [r for r in ok if r["结论"] == "有效"]
    out = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "standard": STRICT,
        "n_total": len(core), "n_evaluated": len(ok),
        "n_valid": len(valid), "valid_names": [r["因子"] for r in valid],
        "combo_z": next((r for r in rows if r.get("因子") == "combo_z"), None),
        "rows": rows,
    }
    rp = BASE / "reports" / f"rebuild36_strict_2016{args.tag}.json"
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    df = pd.DataFrame(rows)
    print("\n=== 2016+ 锁定口径下因子池 ===")
    cols = ["因子", "族", "结论", "年化", "净超额", "夏普", "回撤", "Calmar", "闸门"]
    print(df[[c for c in cols if c in df.columns]].to_string(index=False))
    print(f"\n有效 {len(valid)} / {len(ok)}：{[r['因子'] for r in valid]}")
    print(f"结果已存：{rp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
