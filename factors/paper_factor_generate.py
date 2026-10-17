# -*- coding: utf-8 -*-
"""factors/paper_factor_generate.py —— 论文 → 因子公式（只生成，不验证）

按用户要求：论文挖的因子先只生成公式并保存，等通联市场数据下载完毕后再统一验证。
本脚本只调 LLM 把论文机制翻译成公式（可计算公式语言 / 因子定义描述），不加载面板、不跑验证链。

用法：
  python factors/paper_factor_generate.py --out logs/paper_factors_generated.json
"""
import argparse
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from factors.formula_miner import (
    FEATURES, OP_ARITY, load_api_key, call_llm, extract_formulas, MAX_FORMULA_LEN,
)

CATALOG = BASE / "factors" / "paper_catalog.json"
GEN_SYSTEM = "你是量化因子研究员。把论文机制翻译成因子公式/定义，只输出 JSON。"


def build_prompt(paper):
    feat = ", ".join(sorted(FEATURES))
    ops = " ".join(sorted(OP_ARITY))
    if paper.get("expressible"):
        return (
            f"把下面论文的核心机制，翻译成 {paper.get('n_formulas', 3)} 个可计算的 alpha 因子公式（逆波兰式）。\n\n"
            f"论文：{paper['title']}（{paper['authors']}）\n"
            f"核心机制：{paper['mechanism']}\n"
            f"目标因子：{paper['factor']}\n"
            + (f"建议特征方向：{paper['feat_hint']}\n" if paper.get("feat_hint") else "")
            + f"\n可用特征叶子：{feat}\n可用算子：{ops}\n\n"
            f"规则：每条公式 = 逆波兰 token 序列，长度 ≤ {MAX_FORMULA_LEN}，合法表达式树。"
            "公式必须体现论文机制，机制可解释。\n\n"
            '输出 JSON 数组：[{"formula": ["EP","BP","DIV","TS_RANK20"], "机制": "一句话"}]'
        )
    else:
        return (
            f"把下面论文的可转因子，写成「因子定义 + 所需数据 + 计算思路」（本论文需要另类数据，"
            f"暂不能用行情/财务特征表达）。\n\n"
            f"论文：{paper['title']}（{paper['authors']}）\n"
            f"核心机制：{paper['mechanism']}\n"
            f"目标因子：{paper['factor']}\n"
            f"备注：{paper.get('note', '')}\n\n"
            '输出 JSON 数组：[{"factor_name": "因子英文名", "定义": "因子计算公式/口径", '
            '"所需数据": "需要什么数据源", "方向": "正/负/待定", "机制": "一句话"}]'
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(BASE / "logs" / "paper_factors_generated.json"))
    ap.add_argument("--per-paper", type=int, default=3)
    args = ap.parse_args()

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    papers = catalog["papers"]
    for p in papers:
        p["n_formulas"] = args.per_paper

    api_key = load_api_key()
    results = []
    for p in papers:
        pid = p["id"]
        print(f"\n===== 论文 {pid} {p['title']} =====", flush=True)
        prompt = build_prompt(p)
        got = []
        for attempt in range(3):
            try:
                reply = call_llm([{"role": "system", "content": GEN_SYSTEM},
                                  {"role": "user", "content": prompt}], api_key)
            except Exception as e:
                print(f"  LLM 失败: {e}", flush=True)
                break
            got = extract_formulas(reply)
            if got:
                break
            print(f"  第 {attempt+1} 次解析失败，重试…", flush=True)
        entry = {
            "paper_id": pid,
            "title": p["title"],
            "authors": p["authors"],
            "mechanism": p["mechanism"],
            "target_factor": p["factor"],
            "expressible": p.get("expressible", False),
            "formulas": got,
        }
        results.append(entry)
        print(f"  生成 {len(got)} 条", flush=True)
        for g in got:
            print(f"    {json.dumps(g, ensure_ascii=False)[:150]}", flush=True)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已保存：{args.out}")


if __name__ == "__main__":
    main()
