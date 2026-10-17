# -*- coding: utf-8 -*-
"""factors/validate_new_factors.py —— 11 个新挖因子初步筛除（层2 因子验证第一步）

从定向挖掘结果里取「组合层有效」的公式，用现有数据（2019+）做一次干净的独立复验：
  ICIR → 组合层(净超额/夏普) → 分年度净超额（衰减检测）
目的：筛掉明显无效/不稳定的因子，留下「值得等通联复验」的清单。

诚实标注：本结论基于现有数据（is_st 全0/退市股缺失/qfq 复权偏差），仅作初步筛除，
最终入池需等通联数据修复后复验（对应 D-02 / A-06）。
用法：python factors/validate_new_factors.py [--out logs/new_factors_screening.json]
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from factors.import_qf_pool import load_panel, forward_returns, cross_sectional_ics
from factors.combo_validate import combo_validate_sig, DEFAULT_START, DEFAULT_END
from factors.formula_miner import FEATURE_BUILDERS, execute, to_prefix

LOGS = BASE / "logs"


def load_new_formulas():
    """读两族定向挖掘结果，取「有效」公式（按 prefix 去重）。"""
    formulas = {}
    for name in ["formula_miner_directed_value.json", "formula_miner_directed_growth.json"]:
        p = LOGS / name
        if not p.exists():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        for r in data:
            if r.get("verdict") == "有效" and isinstance(r.get("formula"), list):
                formulas[r["prefix"]] = {"formula": r["formula"], "来源": "价值" if "value" in name else "成长"}
    return formulas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(LOGS / "new_factors_screening.json"))
    args = ap.parse_args()

    formulas = load_new_formulas()
    print(f"读入 {len(formulas)} 个去重后的有效公式", flush=True)

    print("加载面板 + 特征叶子...", flush=True)
    panel = load_panel("data/cache/bars.db", start="2019-01-01")
    fwd = forward_returns(panel)
    feat_mats = {}
    for name, fn in FEATURE_BUILDERS.items():
        try:
            feat_mats[name] = fn(panel).reindex(panel.index)
        except Exception:
            pass
    print(f"特征就绪 {len(feat_mats)}/{len(FEATURE_BUILDERS)}", flush=True)

    rows = []
    for prefix, info in formulas.items():
        tokens = info["formula"]
        sig, err = execute(tokens, feat_mats, panel.index)
        if err:
            print(f"  {prefix:<28} 执行失败: {err}", flush=True)
            continue
        ics = cross_sectional_ics(sig, fwd)
        icir = float(ics.mean() / (ics.std() + 1e-12)) if len(ics) >= 30 else 0.0
        r = combo_validate_sig(f"new_{prefix[:15]}", sig, panel, topn=20, rebalance=40,
                               start=DEFAULT_START, end=DEFAULT_END, direction=None)
        m = r["metrics"]
        # 分年度净超额（找正年数/负年数）
        yearly = r["yearly_excess"]
        pos_years = sum(1 for v in yearly.values() if v["excess"] > 0)
        neg_years = sum(1 for v in yearly.values() if v["excess"] <= 0)
        rows.append({
            "prefix": prefix, "来源": info["来源"], "icir": round(icir, 3),
            "verdict": r["verdict"], "净超额": round(r["excess_annual"], 4),
            "夏普": round(m["sharpe"], 3), "回撤": round(m["max_drawdown"], 3),
            "正年数": pos_years, "负年数": neg_years,
        })
        print(f"  {prefix:<28} ICIR={icir:+.3f} 净超额={r['excess_annual']:+.2%} "
              f"夏普={m['sharpe']:.2f} 正年{pos_years}/负年{neg_years}", flush=True)

    # 排序 + 结论
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("净超额", ascending=False)
        print("\n=== 初步筛除结果（净超额降序）===", flush=True)
        print(df.to_string(index=False), flush=True)
        # 筛除建议：净超额<=0 或 正年数<负年数 的淘汰
        keep = df[(df["净超额"] > 0) & (df["正年数"] >= df["负年数"])]
        drop = df[(df["净超额"] <= 0) | (df["正年数"] < df["负年数"])]
        print(f"\n建议保留 {len(keep)} 个 / 淘汰 {len(drop)} 个（净超额<=0 或 正年<负年）", flush=True)
        if len(drop):
            print("淘汰:", ", ".join(drop["prefix"].tolist()), flush=True)
    else:
        keep, drop = pd.DataFrame(), pd.DataFrame()

    out = {
        "validated_at": str(pd.Timestamp.now())[:19],
        "factors": rows,
        "keep": keep["prefix"].tolist() if not keep.empty else [],
        "drop": drop["prefix"].tolist() if not drop.empty else [],
        "note": "基于现有数据(2019+)的初步筛除，最终入池需等通联数据修复后复验（D-02/A-06）",
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已存：{args.out}")


if __name__ == "__main__":
    main()
