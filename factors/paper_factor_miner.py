# -*- coding: utf-8 -*-
"""factors/paper_factor_miner.py —— 「论文 → 因子」挖掘功能（论文挖因子）

把经济学/金融学论文的机制，翻译成 AlphaGPT 公式语言（特征+算子，逆波兰式），
复用 formula_miner.py 的验证链（ICIR 海选 → 去重闸门 → 组合层 T+1 裁决）。

用法：
  python factors/paper_factor_miner.py --selftest          # 手写论文对应公式验证管线（不花 LLM）
  python factors/paper_factor_miner.py --per-paper 6       # LLM 逐篇论文生成 6 条候选
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from factors.formula_miner import (
    FEATURE_BUILDERS, FEATURES, OP_ARITY, OPS_IMPL,
    validate, execute, to_prefix, forbid_check,
    score_icir, max_anchor_corr, build_anchors,
    load_panel, forward_returns,
    load_api_key, call_llm, extract_formulas,
    MAX_FORMULA_LEN, MIN_ICIR, MAX_ANCHOR_CORR, MIN_COVERAGE,
)
from factors.combo_validate import combo_validate_sig, DEFAULT_TOPN, DEFAULT_REBALANCE, DEFAULT_START, DEFAULT_END

CATALOG = BASE / "factors" / "paper_catalog.json"
GEN_SYSTEM = "你是量化因子研究员。把经济学论文机制翻译成逆波兰式 alpha 公式，只输出 JSON。"


def load_catalog():
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def build_paper_prompt(paper, per_paper, anchor_desc):
    feat = ", ".join(sorted(FEATURES))
    ops = " ".join(sorted(OP_ARITY))
    lines = [
        f"把下面这篇经济学论文的核心机制，翻译成 {per_paper} 个可计算的 alpha 因子公式（逆波兰式）。",
        "",
        f"论文：{paper['title']}（{paper['authors']}）",
        f"核心机制：{paper['mechanism']}",
        f"目标因子：{paper['factor']}",
    ]
    if paper.get("feat_hint"):
        lines.append(f"建议特征方向：{paper['feat_hint']}")
    lines += [
        "",
        f"可用特征叶子（arity=0）：{feat}",
        f"可用算子：{ops}",
        "",
        "规则：",
        f"1. 每条公式 = 逆波兰 token 序列，长度 ≤ {MAX_FORMULA_LEN}，合法表达式树（叶子数 = 内部节点数 + 1）。",
        "2. 逆波兰式求值：遇特征压栈，遇算子弹 arity 个操作数计算后压回；终栈恰 1 个值。",
        "3. 公式必须体现论文机制（不是随手拼），机制需可解释。",
        "4. 避免：常量因子、未来函数、与下列池内锚点高度同构的公式。",
        f"5. 已入池锚点（相关>0.5 会淘汰）：{anchor_desc}",
        "",
        "输出严格 JSON 数组（不要解释文字）：",
        '[{"formula": ["EP", "BP", "DIV", "TS_RANK20"], "机制": "一句话经济逻辑"}]',
    ]
    return "\n".join(lines)


def run_paper_pipeline(panel, fwd, feat_mats, anchors, close_wide, topn, rebalance,
                       candidates, paper_id, icir_only=False):
    """对一篇论文的候选公式走验证链。返回结果列表。"""
    results = []
    batch_sigs = []
    for c in candidates:
        tokens = c.get("formula")
        if not isinstance(tokens, list) or not tokens:
            results.append({"formula": tokens, "error": "空公式"})
            continue
        sig, err = execute(tokens, feat_mats, panel.index)
        if err:
            results.append({"formula": tokens, "prefix": to_prefix(tokens), "error": err})
            continue
        sc = score_icir(sig, fwd)
        if sc is None:
            results.append({"formula": tokens, "prefix": to_prefix(tokens), "error": "IC 样本不足"})
            continue
        cov = float(sig.notna().mean())
        corr = max_anchor_corr(sig, anchors, None if icir_only else close_wide, topn)
        direction = 1 if sc["ic"] >= 0 else -1
        if cov < MIN_COVERAGE:
            results.append({"prefix": to_prefix(tokens), "icir": round(sc["icir"], 3),
                            "cov": round(cov, 3), "corr": round(corr, 3), "gate": "覆盖率不足"})
            continue
        if abs(sc["icir"]) < MIN_ICIR:
            results.append({"prefix": to_prefix(tokens), "icir": round(sc["icir"], 3),
                            "cov": round(cov, 3), "corr": round(corr, 3), "gate": "ICIR不足"})
            continue
        if corr > MAX_ANCHOR_CORR:
            results.append({"prefix": to_prefix(tokens), "icir": round(sc["icir"], 3),
                            "cov": round(cov, 3), "corr": round(corr, 3), "gate": "同构淘汰"})
            continue
        batch_corr = 0.0
        if batch_sigs:
            batch_corr = max_anchor_corr(sig, {f"b{i}": s for i, s in enumerate(batch_sigs)}, close_wide, topn)
        if batch_corr > MAX_ANCHOR_CORR:
            results.append({"prefix": to_prefix(tokens), "icir": round(sc["icir"], 3),
                            "corr": round(corr, 3), "gate": "批内同构"})
            continue
        if icir_only:
            results.append({"prefix": to_prefix(tokens), "icir": round(sc["icir"], 3),
                            "cov": round(cov, 3), "corr": round(corr, 3), "gate": "过海选(ICIR)"})
            continue
        try:
            r = combo_validate_sig(f"pp_{to_prefix(tokens)[:18]}", sig, panel,
                                   topn=topn, rebalance=rebalance, start=DEFAULT_START,
                                   end=DEFAULT_END, direction=direction)
            m = r["metrics"]
            if r["verdict"] == "有效" and batch_sigs is not None:
                batch_sigs.append(sig)
            results.append({"prefix": to_prefix(tokens), "icir": round(sc["icir"], 3),
                            "cov": round(cov, 3), "corr": round(corr, 3), "gate": "过海选",
                            "verdict": r["verdict"], "净超额": round(r["excess_annual"], 4),
                            "夏普": round(m["sharpe"], 3), "回撤": round(m["max_drawdown"], 3)})
        except Exception as e:
            results.append({"prefix": to_prefix(tokens), "icir": round(sc["icir"], 3),
                            "corr": round(corr, 3), "gate": f"组合层异常:{str(e)[:60]}"})
    return results


SELFTEST_PAPER_FORMULAS = {
    "B1": [(["EP", "BP", "DIV", "TS_RANK20"], "价值：EP/BP 比值时序rank"),
           (["SUE", "ACCEL", "ADD", "TS_RANK20"], "盈利超预期+加速度")],
    "B4": [(["BP", "VOLAT", "DIV"], "价值/波动：低波价值"),
           (["EP", "NEG"], "盈利收益率（价值）")],
    "B5": [(["VOLAT", "NEG"], "低波动"),
           (["RET", "STD20"], "收益波动zscore")],
    "C1": [(["TURN", "NEG"], "低换手（关注度反转代理）"),
           (["VOL_CHG", "NEG", "RET", "SUB"], "量能回落+收益反转")],
    "D5": [(["RET5", "RET20", "SUB"], "短期动量差（非参数阈值）"),
           (["TREND", "VOLAT", "DIV"], "趋势/波动比")],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--icir-only", action="store_true", help="只跑 ICIR 海选+去重（快），跳过组合层验证")
    ap.add_argument("--per-paper", type=int, default=6)
    ap.add_argument("--topn", type=int, default=DEFAULT_TOPN)
    ap.add_argument("--rebalance", default=DEFAULT_REBALANCE)
    ap.add_argument("--out", default=str(BASE / "logs" / "paper_factor_miner_results.json"))
    args = ap.parse_args()

    catalog = load_catalog()
    papers = catalog["papers"]

    # 分两组：可公式化 vs 需新数据
    expressible = [p for p in papers if p.get("expressible")]
    not_expressible = [p for p in papers if not p.get("expressible")]

    print("加载面板 + fwd + 特征 + 锚点...", flush=True)
    panel = load_panel("data/cache/bars.db", start="2021-01-01")
    fwd = forward_returns(panel)
    close_wide = panel["close"].unstack()
    feat_mats = {}
    for name, fn in FEATURE_BUILDERS.items():
        try:
            feat_mats[name] = fn(panel).reindex(panel.index)
        except Exception as e:
            print(f"  特征 {name} 失败: {str(e)[:80]}", flush=True)
    anchors = build_anchors(panel)
    anchor_desc = ", ".join(anchors.keys())
    print(f"面板 {panel.shape}，特征 {len(feat_mats)}，锚点 {len(anchors)}", flush=True)

    api_key = None
    if not args.selftest:
        api_key = load_api_key()

    all_results = {}
    for p in expressible:
        pid = p["id"]
        print(f"\n===== 论文 {pid} {p['title']} =====", flush=True)
        if args.selftest:
            cands = [{"formula": f, "机制": m} for f, m in SELFTEST_PAPER_FORMULAS.get(pid, [])]
        else:
            prompt = build_paper_prompt(p, args.per_paper, anchor_desc)
            kept = []
            for attempt in range(3):
                try:
                    reply = call_llm([{"role": "system", "content": GEN_SYSTEM},
                                      {"role": "user", "content": prompt}], api_key)
                except Exception as e:
                    print(f"  LLM 失败: {e}", flush=True)
                    break
                batch = extract_formulas(reply)
                errs = [c for c in batch if not (isinstance(c.get("formula"), list) and validate(c["formula"]))]
                kept = [c for c in batch if isinstance(c.get("formula"), list) and validate(c["formula"])]
                if not errs or attempt == 2:
                    break
                prompt += "\n\n⚠️ 非法公式请重新生成（合法逆波兰式）：" + str(errs[:6])
            cands = kept
            print(f"  LLM 有效候选 {len(cands)} 条", flush=True)

        results = run_paper_pipeline(panel, fwd, feat_mats, anchors, close_wide,
                                     args.topn, args.rebalance, cands, pid, icir_only=args.icir_only)
        for c, r in zip(cands, results):
            r["机制"] = c.get("机制", "")
            r["论文"] = f"{pid} {p['title']}"
        all_results[pid] = results
        for r in results:
            line = f"  {r.get('prefix','?'):<28} icir={r.get('icir','NA')} "
            line += f"组合层={r['verdict']} 净超额={r.get('净超额',0):+.2%} 夏普={r.get('夏普',0)}" if "verdict" in r else f"→ {r.get('gate', r.get('error',''))}"
            print(line, flush=True)

    # 汇总
    passed = [(pid, r) for pid, rs in all_results.items() for r in rs if r.get("verdict") == "有效"]
    print(f"\n===== 汇总：{len(expressible)} 篇可公式化论文，{len(passed)} 个公式过组合层 =====")
    for pid, r in passed:
        print(f"  ★ [{pid}] {r['prefix']} 净超额{r['净超额']:+.2%} 夏普{r['夏普']}")

    # 需新数据的论文 → 通联因子库映射建议
    print(f"\n===== 需新数据的论文（{len(not_expressible)} 篇）→ 建议用通联因子库 =====")
    for p in not_expressible:
        print(f"  [{p['id']}] {p['title']}：{p.get('note', p['factor'])}")

    out = {
        "expressible_results": all_results,
        "passed_combo": [{"paper": pid, **r} for pid, r in passed],
        "not_expressible": not_expressible,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"结果已存：{args.out}")


if __name__ == "__main__":
    main()
