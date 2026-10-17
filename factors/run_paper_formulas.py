# -*- coding: utf-8 -*-
"""factors/run_paper_formulas.py —— A3：18 个论文公式的 ICIR 初筛（用最新数据）

背景（docs/因子挖掘双路线方案.md A 路线）：
  `output/FACTOR_VERIFICATION_BACKLOG_20261015.md` 里有 **18 个可自算的逆波兰公式**
  （q-factor / 价值复活 / 不确定性 / 关注度 / 彩票 / 非参数门控 六族）。
  `factors/formula_miner.py` 已有 StackVM + 15 个特征叶子 → 可直接求值，无需重写引擎。

本脚本：加载面板 → 构建特征矩阵 → 逐个公式 validate/execute → 算 IC/ICIR/覆盖率/截面退化
        → 输出表格 + JSON（供后续去重与组合层裁决）。

用法：python factors/run_paper_formulas.py [--out logs/paper_icir_2010.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from factors.formula_miner import FEATURE_BUILDERS, validate, execute, to_prefix, FEATURES
from factors.import_qf_pool import load_panel, forward_returns

# ---- 18 个论文公式（逆波兰式，来自 FACTOR_VERIFICATION_BACKLOG_20261015.md）----
PAPERS = [
    ("B1_q-factor",    "REV_YOY SUE ADD TS_RANK20",                  "盈利改善+惊喜"),
    ("B1_EP+BP",       "EP BP ADD TS_RANK20",                        "价值（EP+BP）"),
    ("B1_accel+sue",   "ACCEL SUE ADD TS_RANK20",                    "盈利加速度+惊喜"),
    ("B4_BP+sue",      "BP SUE ADD TS_RANK20",                       "价值×质量交叉"),
    ("B4_EP+accel",    "EP ACCEL ADD TS_RANK20",                     "价值×成长交叉"),
    ("B4_BP*accel+rev", "BP ACCEL MUL REV_YOY ADD TS_RANK20",        "价值×加速×营收共振"),
    ("B5_volat/std",   "VOLAT STD20 DIV",                            "波动率/其标准差"),
    ("B5_vol_up",      "VOL_CHG VOLAT MA20 SUB SIGN VOLAT MUL",       "波动上行方向×水平"),
    ("B5_v_ret",       "V_RET VOLAT DIV TS_RANK20",                  "波动调整收益"),
    ("C1_turn+volchg", "TURN VOL_CHG ADD TS_RANK20 NEG",             "换手+量变（反转）"),
    ("C1_ret5*turn",   "RET5 TURN MUL TS_RANK20 NEG",                "收益×换手（反转）"),
    ("C1_absret*vol",  "RET ABS VOL_CHG MUL TS_RANK20 NEG",          "绝对收益×量变（反转）"),
    ("C5_max3",        "RET MAX3 NEG",                               "低 MAX 溢价"),
    ("C5_max3_ts",     "RET MAX3 TS_RANK20 NEG",                     "MAX 时序排名反转"),
    ("C5_max3_vol",    "RET MAX3 VOLAT DIV NEG",                     "波动标准化 MAX 反转"),
    ("D5_lowvol_mom",  "VOLAT TS_RANK20 RET20 GATE",                 "低波动门控动量"),
    ("D5_sue_rev",     "SUE TS_RANK20 RET5 GATE",                    "SUE 门控反转"),
    ("D5_amihud_rev",  "AMIHUD TS_RANK20 REV_YOY GATE",              "流动性门控反转"),
]

# ---- 铁律 1：禁挖比对（FACTOR_FALSIFICATION_LOG §5.1 / §5.4）----
# 与已证伪因子同逻辑的论文公式不重复验证，只登记跳过原因。
EXCLUDED = {
    "B1_q-factor":  "REV_YOY+SUE = c_factor/sue 同族；两者均在 §5.1 禁挖（holdout 三段未同号）",
    "B1_accel+sue": "ACCEL+SUE = accel_factor/sue 同逻辑；且 accel↔sue 收益 ρ=0.904（§5.3 重复组）",
}


def ic_stats(sig: pd.Series, fwd: pd.Series) -> dict:
    """截面 IC 序列 → ICIR20 / ICIR120 / IC 胜率"""
    df = pd.DataFrame({"s": sig, "f": fwd}).dropna()
    if df.empty:
        return {"icir_20": None, "icir_120": None, "ic_mean": None, "ic_win": None, "n_days": 0}
    ics = df.groupby(level=0).apply(lambda g: g["s"].corr(g["f"], method="spearman")
                                    if len(g) >= 30 else np.nan).dropna()
    if len(ics) < 20:
        return {"icir_20": None, "icir_120": None, "ic_mean": None, "ic_win": None, "n_days": len(ics)}
    def _icir(w):
        if len(ics) < w:
            return None
        r = ics.rolling(w).mean() / (ics.rolling(w).std() + 1e-12)
        return float(r.iloc[-1]) if len(r.dropna()) else None
    return {"icir_20": _icir(20), "icir_120": _icir(120),
            "ic_mean": float(ics.mean()), "ic_win": float((ics > 0).mean()),
            "n_days": int(len(ics))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(BASE / "logs" / "paper_icir_2010.json"))
    args = ap.parse_args()

    try:
        from factors.window_config import get_window
        pstart = get_window()["panel_load_start"]
    except Exception:
        pstart = "2008-12-01"
    print(f"加载面板（start={pstart}）...", flush=True)
    panel = load_panel("data/cache/bars.db", start=pstart)
    print(f"面板 {panel.shape}", flush=True)

    print("构建特征矩阵（15 个）...", flush=True)
    feat = {}
    for k, fn in FEATURE_BUILDERS.items():
        try:
            feat[k] = fn(panel)
        except Exception as e:
            print(f"  ✘ {k}: {str(e)[:80]}")
    print(f"  成功 {len(feat)}/{len(FEATURE_BUILDERS)}", flush=True)

    fwd = forward_returns(panel)
    rows = []
    for name, formula, mech in PAPERS:
        # 铁律 1：先查禁挖清单（FACTOR_FALSIFICATION_LOG §5.1/§5.4），同逻辑不重复挖
        if name in EXCLUDED:
            rows.append({"因子": name, "机制": mech, "公式": formula, "跳过": EXCLUDED[name]})
            print(f"  {name:<18s} [禁挖跳过] {EXCLUDED[name]}", flush=True)
            continue
        toks = formula.split()
        try:
            if not validate(toks):
                raise RuntimeError("语法非法（token 栈不平衡，检查操作数个数）")
            sig, err = execute(toks, feat, panel.index)
            if err:
                raise RuntimeError(err)
            if not isinstance(sig, pd.Series):
                raise RuntimeError("execute 未返回 Series")
            sig = sig.reindex(panel.index)
            # 覆盖率双报：最终信号覆盖 + 原始特征叶子最小覆盖（防止 ADD 的 fillna(0) 抬高名义覆盖）
            leaves = [t for t in toks if t in FEATURES]
            leaf_cov = min((float(feat[t].notna().mean()) for t in leaves), default=None)
            cov = float(sig.notna().mean())
            st = ic_stats(sig, fwd)
            # 截面退化
            try:
                yb = sig.groupby(sig.index.get_level_values(0).year).agg(["std", "nunique"])
                dead = [str(int(y)) for y, r in yb.iterrows() if (r["std"] or 0) == 0 or (r["nunique"] or 0) <= 1]
            except Exception:
                dead = []
            rows.append({"因子": name, "机制": mech, "公式": formula, "前缀": to_prefix(toks),
                         "覆盖率": round(cov, 4),
                         "叶子最小覆盖": (round(leaf_cov, 4) if leaf_cov is not None else None),
                         **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in st.items()},
                         "退化年份": dead})
            ic20 = st["icir_20"]
            print(f"  {name:<18s} cov={cov:>5.1%} leaf_cov={(f'{leaf_cov:.1%}' if leaf_cov is not None else 'n/a'):>6s} "
                  f"icir20={ic20 if ic20 is None else round(ic20,3)} "
                  f"ic_mean={st['ic_mean'] if st['ic_mean'] is None else round(st['ic_mean'],4)} "
                  f"ic_win={st['ic_win'] if st['ic_win'] is None else round(st['ic_win'],3)}", flush=True)
        except Exception as e:
            rows.append({"因子": name, "机制": mech, "公式": formula, "错误": str(e)[:120]})
            print(f"  {name:<18s} ✘ {str(e)[:90]}", flush=True)

    df = pd.DataFrame(rows)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("\n=== 汇总（按 |icir20| 排序）===")
    ok = [r for r in rows if r.get("icir_20") is not None]
    for r in sorted(ok, key=lambda x: -abs(x["icir_20"])):
        print(f"  {r['因子']:<18s} icir20={r['icir_20']:>7.3f} icir120={r['icir_120']} "
              f"ic_mean={r['ic_mean']:>7.4f} 胜率={r['ic_win']:.2f} cov={r['覆盖率']:.0%} "
              + ("⚠️退化:" + ",".join(r["退化年份"][:4]) if r["退化年份"] else ""))
    print(f"\n结果已存：{args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
