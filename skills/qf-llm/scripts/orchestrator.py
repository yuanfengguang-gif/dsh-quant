# -*- coding: utf-8 -*-
"""QF-LLM 编排器：autoresearch 式自主因子挖掘主循环。

每轮流程（对应视频第六节）：
1. 读三样：研究规程(program.md) + 研究记忆(memory) + 因子池(pool)
2. 拼 prompt → 直连 LLM(DeepSeek) 生成 N 个候选因子（Python 代码）
3. 逐个进沙箱执行
4. 固定评分 + 硬门控（综合分 + 多样性相关性）
5. 达标且不撞老因子的进池，其余淘汰
6. AI 写本轮研究总结 → 追加进记忆 → 下一轮站在上一轮肩膀上

用法：
    python orchestrator.py --data panel.parquet --program program.md \
        --rounds 50 --per-round 10 --out runs/
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
import urllib.request
import datetime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scoring import score as score_factor  # noqa: E402
from sandbox import run as sandbox_run  # noqa: E402

ENV_FILE = r"C:\Users\Administrator\dsh-desktop\.env"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"


# --------------------------------------------------------------------------- #
# 环境 / 数据
# --------------------------------------------------------------------------- #
def load_api_key() -> str:
    """API Key 唯一来源：C:\\Users\\Administrator\\dsh-desktop\\.env（全局规则）。"""
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                os.environ.setdefault(k, v)
    key = os.environ.get("DSH_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or ""
    if not key:
        raise RuntimeError(f"未找到 DSH_API_KEY / DEEPSEEK_API_KEY，请检查 {ENV_FILE}")
    return key


def load_panel(path: str) -> pd.DataFrame:
    """加载行情面板。约定 schema：MultiIndex (date, code)，
    列至少含 close / pct_chg（可选 open/high/low/volume/amount/turn/is_st）。"""
    if path.endswith(".parquet"):
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)
    if not isinstance(df.index, pd.MultiIndex):
        raise ValueError("面板必须是 MultiIndex (date, code)，请先 set_index")
    return df


def forward_returns(panel: pd.DataFrame) -> pd.Series:
    """T+1 严格口径前向标签（对齐 deepseek-harness-quant 消费端 forward_returns）：
    t 日收盘出信号 → t+1 日开盘买入 → t+2 日开盘卖出（open-to-open），
    并剔除 t+1 日一字板涨停（high==low 且 pct_chg>0，买不进）的样本。
    若面板缺 open/high/low 列，回退到次日 close-to-close（pct_chg.shift(-1)）。"""
    if "pct_chg" not in panel.columns:
        raise ValueError("面板缺少 pct_chg 列")
    if {"open", "high", "low"}.issubset(panel.columns):
        op = panel["open"]
        fwd = op.groupby(level=1, sort=False).shift(-2) / op.groupby(level=1, sort=False).shift(-1) - 1.0
        oneline = ((panel["high"] == panel["low"]) & (panel["pct_chg"] > 0)).astype(bool)
        oneline_next = oneline.groupby(level=1, sort=False).shift(-1).fillna(False).astype(bool)
        return fwd.where(~oneline_next)
    return panel["pct_chg"].groupby(level=1, sort=False).shift(-1)


# --------------------------------------------------------------------------- #
# LLM
# --------------------------------------------------------------------------- #
def call_llm(messages: list[dict], api_key: str, model="deepseek-chat",
             temperature=0.7, max_tokens=8000) -> str:
    payload = {
        "model": model, "messages": messages,
        "temperature": temperature, "max_tokens": max_tokens,
    }
    req = urllib.request.Request(
        DEEPSEEK_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        j = json.loads(r.read().decode("utf-8"))
    return j["choices"][0]["message"]["content"]


def extract_factors(text: str) -> list[str]:
    """从 LLM 回复里抽取所有含 def factor 的 python 代码块。"""
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, flags=re.S)
    if not blocks:
        blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)$", text, flags=re.S)
    out = [b for b in blocks if "def factor" in b]
    return out


# --------------------------------------------------------------------------- #
# prompt
# --------------------------------------------------------------------------- #
GEN_SYSTEM = (
    "你是量化因子挖掘研究员。按研究规程，用 numpy/pandas 编写候选 alpha 因子。"
    "每个因子用一个 ```python 代码块，定义 def factor(panel)->pd.Series："
    "panel 是多索引(date,code) DataFrame，列含 open/high/low/close/volume/amount/turn/pct_chg/is_st；"
    "返回与 panel.index 对齐的截面得分 Series。np/pd 已注入，无需 import。"
    "禁止：未来函数(shift(-1))、IO、除 numpy/pandas 外的库、与池内因子高相关的换皮因子。"
)

SUMMARY_SYSTEM = (
    "你是量化因子挖掘研究员的记忆系统。根据本轮结果，写一份简短研究总结，"
    "包含：哪些有效、哪些无效、下一步少碰什么多做什么、发现的新方向。"
    "总结会被读回用于下一轮，要求信息密度高、可执行。"
)


def build_gen_prompt(program: str, memory: str, pool_desc: str, per_round: int) -> str:
    return (
        "以下是研究规程(program.md)：\n" + program + "\n\n"
        "以下是已入池因子的可读描述（避免重复/高相关）：\n" + (pool_desc or "（空）") + "\n\n"
        "以下是历史研究记忆（教训与方向）：\n" + (memory or "（空）") + "\n\n"
        f"请生成 {per_round} 个彼此低相关、且与池内因子低相关的候选因子代码块。"
    )


# --------------------------------------------------------------------------- #
# 主循环
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description="QF-LLM autoresearch 式因子挖掘编排器")
    ap.add_argument("--data", required=True, help="行情面板 parquet/csv（MultiIndex date,code）")
    ap.add_argument("--program", default="program.md", help="研究规程文件路径")
    ap.add_argument("--rounds", type=int, default=50)
    ap.add_argument("--per-round", type=int, default=10)
    ap.add_argument("--out", default="runs")
    ap.add_argument("--model", default="deepseek-chat")
    ap.add_argument("--timeout", type=float, default=30.0)
    args = ap.parse_args()

    api_key = load_api_key()
    panel = load_panel(args.data)
    fwd = forward_returns(panel)
    # 面板只序列化一次，复用给所有沙箱调用（8M 行 pickle 较慢）
    panel_pkl = os.path.join(tempfile.gettempdir(), "qfllm_panel.pkl")
    panel.to_pickle(panel_pkl)

    program = open(args.program, encoding="utf-8").read() if os.path.exists(args.program) else ""
    os.makedirs(args.out, exist_ok=True)

    pool_signals: list[pd.Series] = []   # 已入池因子信号
    pool_records: list[dict] = []        # 已入池因子元信息
    memory: str = ""                     # 研究记忆（累积总结）

    for rnd in range(1, args.rounds + 1):
        pool_desc = "\n".join(
            f"- {rec['name']}: rank_ic={rec['rank_ic']:.3f} icir={rec['ic_ir']:.2f}"
            for rec in pool_records
        )
        prompt = build_gen_prompt(program, memory, pool_desc, args.per_round)
        try:
            reply = call_llm(
                [{"role": "system", "content": GEN_SYSTEM},
                 {"role": "user", "content": prompt}],
                api_key, model=args.model, temperature=0.7,
            )
        except Exception as e:
            print(f"[round {rnd}] LLM 调用失败: {e}", flush=True)
            time.sleep(2)
            continue

        codes = extract_factors(reply)
        round_log = {"round": rnd, "candidates": [], "kept": [], "summary": ""}

        for i, code in enumerate(codes):
            name = f"r{rnd}_f{i}"
            try:
                sig = sandbox_run(code, panel_path=panel_pkl, timeout=args.timeout)
                res = score_factor(sig, fwd, pool_signals)
            except Exception as e:
                round_log["candidates"].append({"name": name, "error": str(e)[:300]})
                continue

            res["name"] = name
            res["code"] = code
            round_log["candidates"].append(dict(res))  # 保留 code 供导入器复用因子代码
            if res["pass"]:
                kept_sig = sig if res["direction"] == 1 else -sig
                pool_signals.append(kept_sig)
                pool_records.append(res)
                round_log["kept"].append(name)
            print(f"[round {rnd}] {name}: total={res['total']:.3f} "
                  f"ic={res['rank_ic']:.3f} icir={res['ic_ir']:.2f} corr={res['max_corr']:.2f} "
                  f"{'KEEP' if res['pass'] else 'drop'}", flush=True)

        # 本轮研究总结 → 追加记忆
        try:
            summary = call_llm(
                [{"role": "system", "content": SUMMARY_SYSTEM},
                 {"role": "user", "content": json.dumps([{k: v for k, v in c.items() if k != "code"} for c in round_log["candidates"]], ensure_ascii=False)}],
                api_key, model=args.model, temperature=0.3, max_tokens=1000,
            )
        except Exception:
            summary = ""
        round_log["summary"] = summary
        memory = (memory + f"\n\n[第{rnd}轮] " + summary).strip()

        with open(os.path.join(args.out, f"round_{rnd:03d}.json"), "w", encoding="utf-8") as f:
            json.dump(round_log, f, ensure_ascii=False, indent=2)
        with open(os.path.join(args.out, "pool.json"), "w", encoding="utf-8") as f:
            json.dump(
                pool_records,  # 保留 code 供导入器复用因子代码
                f, ensure_ascii=False, indent=2,
            )

        try:
            from dashboard import generate_report
            rpt = os.path.join(os.path.dirname(os.path.abspath(args.out)), "report.html")
            generate_report(args.out, rpt)
        except Exception as e:
            print(f"[round {rnd}] 看板生成失败: {e}", flush=True)

    print(f"\n完成 {args.rounds} 轮，入池 {len(pool_records)} 个因子。结果在 {args.out}/", flush=True)


if __name__ == "__main__":
    main()
