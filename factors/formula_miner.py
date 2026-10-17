# -*- coding: utf-8 -*-
"""factors/formula_miner.py —— AlphaGPT 式「公式语言」因子矿机（本机版）

把 qf-llm 的「自由写 pandas 代码」换成「逆波兰式公式语言」：
  特征叶子（arity 0）+ 算子（内部节点）→ StackVM 解释执行 → 反退化打分 → 去重闸门 → 组合层裁决。

设计要点（对照 alpha-gpt-factor-mining skill + trial-findings.md 13 坑）：
  1. 公式 = 符号化逆波兰 token 序列（禁止数字索引、禁止前缀式混用）。
  2. StackVM 三态返回：合法 / 语法非法 / 实现异常（禁止静默吞异常）。
  3. 反退化：常量因子 std<1e-4 直接淘汰；ICIR 向量化（rank 后逐日 Pearson）。
  4. 去重先于排序：与池内锚点逐日 Spearman >0.5 淘汰 / 0.3-0.5 警示 / <0.3 通过。
  5. 海选只作门票，组合层 combo_validate_sig（净超额>0 且夏普>0.5）才是唯一裁决。

用法：
  python factors/formula_miner.py --selftest              # 手写公式验证管线（不花 LLM）
  python factors/formula_miner.py --per-round 20          # LLM 生成 20 条候选
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import urllib.request
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

from factors.import_qf_pool import load_panel, forward_returns, cross_sectional_ics, cross_corr
from factors.combo_validate import combo_validate_sig, DEFAULT_TOPN, DEFAULT_REBALANCE, DEFAULT_START, DEFAULT_END
from factors.reproduce_factors import bp_value, sue, f_score, turn_mid_prox, limup_ex_5, _limup_flag
from factors.validate_all_factors import amihud, reversal_20, mom_120, near_high_250, sentiment

ENV_FILE = r"C:\Users\Lenovo\dsh-desktop\.env"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"

MAX_FORMULA_LEN = 8          # 短公式优先，防过拟合
MIN_ICIR = 0.1               # 海选粗筛（防守/流动性类因子 alpha 在组合层，放宽到 0.1；组合层才是裁决）
MAX_ANCHOR_CORR = 0.5        # 去重硬闸门
WARN_ANCHOR_CORR = 0.3       # 去重警示
MIN_COVERAGE = 0.3


# ============================ 特征叶子 ============================

def _robust(s: pd.Series) -> pd.Series:
    """截面 robust 归一化（逐日 median/MAD，clip ±5）。"""
    med = s.groupby(level=0).transform("median")
    mad = (s - med).abs().groupby(level=0).transform("median")
    return ((s - med) / (mad + 1e-6)).clip(-5, 5)


def _ts(s: pd.Series, n: int, fn: str = "mean", mp: int = 5) -> pd.Series:
    """逐股时序滚动（返回与输入同 index 的 Series）。"""
    out = getattr(s.groupby(level=1).rolling(n, min_periods=mp), fn)()
    return out.reset_index(level=0, drop=True)


def _feat_ret(p): return _robust(p["pct_chg"])
def _feat_ret5(p): return _robust(p["close"].groupby(level=1).pct_change(5))
def _feat_ret20(p): return _robust(p["close"].groupby(level=1).pct_change(20))
def _feat_vol_chg(p):
    base = _ts(p["volume"], 20)
    return _robust(p["volume"] / base.replace(0, np.nan) - 1)
def _feat_v_ret(p):
    base = _ts(p["volume"], 20)
    return _robust(p["pct_chg"] * (p["volume"] / base.replace(0, np.nan)))
def _feat_trend(p): return _robust(p["close"] / _ts(p["close"], 60, mp=20).replace(0, np.nan) - 1)
def _feat_turn(p): return _robust(_ts(p["turn"], 20))
def _feat_volat(p): return _robust(_ts(p["pct_chg"], 20, "std"))
def _feat_amihud(p):
    return _robust(_ts(p["pct_chg"].abs() / (p["amount"] + 1e-8), 20))
def _feat_limup(p):
    f = _limup_flag(p)
    return _robust(f.groupby(level=1).rolling(5, min_periods=1).sum().reset_index(level=0, drop=True))


CACHE = BASE / "data" / "cache"


# ---- 基本面特征叶子（成长/价值族，读 finance.db，60 日披露延迟） ----

def _fin_raw(p, field):
    """读 finance.db 字段 → 60 日披露延迟 → ffill → 对齐 panel.index（原始值，不 robust）。"""
    con = sqlite3.connect(str(CACHE / "finance.db"))
    fin = pd.read_sql(f"SELECT code, period, {field} FROM finance_report", con)
    con.close()
    fin[field] = pd.to_numeric(fin[field], errors="coerce")
    code_map = {c.split(".")[0]: c for c in p.index.get_level_values("code").unique()}
    fin["code"] = fin["code"].astype(str).str.zfill(6).map(code_map)
    fin = fin.dropna(subset=["code", field])
    fin["eff_date"] = pd.to_datetime(fin["period"]) + pd.Timedelta(days=60)
    m = fin.pivot_table(index="eff_date", columns="code", values=field, aggfunc="last")
    dates = p.index.get_level_values(0).unique().sort_values()
    # PIT 前向填充：union 后再 ffill，确保面板起点之前的 eff_date 也能填充（防全 NaN）
    m = m.reindex(m.index.union(dates)).sort_index().ffill().reindex(dates)
    return m.stack().reindex(p.index)


def _feat_sue(p):
    """SUE：单季盈利超预期（主系统公式，学术 SUE 的 |prev| 简化版）。"""
    return _robust(sue(p).reindex(p.index))


def _feat_bp(p):
    """BP：账面市值比 = 1/PB = (eps/roe)/close（主系统公式）。"""
    return _robust(bp_value(p).reindex(p.index))


def _feat_ep(p):
    """EP：盈利收益率 = eps/close = 1/PE（业界标准）。"""
    eps = _fin_raw(p, "eps")
    return _robust(eps / p["close"])


def _feat_rev_yoy(p):
    """REV_YOY：单季营收同比（主系统字段 sq_rev_yoy）。"""
    return _robust(_fin_raw(p, "sq_rev_yoy"))


def _feat_accel(p):
    """ACCEL：盈利加速度 = 当期单季同比 - 上期单季同比（主系统 accel_factor）。"""
    con = sqlite3.connect(str(CACHE / "finance.db"))
    fin = pd.read_sql("SELECT code, period, sq_net_yoy FROM finance_report", con)
    con.close()
    fin["sq_net_yoy"] = pd.to_numeric(fin["sq_net_yoy"], errors="coerce")
    fin = fin.dropna(subset=["sq_net_yoy"]).sort_values(["code", "period"])
    fin["prev"] = fin.groupby("code")["sq_net_yoy"].shift(1)
    fin["accel"] = fin["sq_net_yoy"] - fin["prev"]
    code_map = {c.split(".")[0]: c for c in p.index.get_level_values("code").unique()}
    fin["code"] = fin["code"].astype(str).str.zfill(6).map(code_map)
    fin = fin.dropna(subset=["code", "accel"])
    fin["eff_date"] = pd.to_datetime(fin["period"]) + pd.Timedelta(days=60)
    m = fin.pivot_table(index="eff_date", columns="code", values="accel", aggfunc="last")
    dates = p.index.get_level_values(0).unique().sort_values()
    m = m.reindex(m.index.union(dates)).sort_index().ffill().reindex(dates)
    return _robust(m.stack().reindex(p.index))


FEATURE_BUILDERS = {
    "RET": _feat_ret, "RET5": _feat_ret5, "RET20": _feat_ret20,
    "VOL_CHG": _feat_vol_chg, "V_RET": _feat_v_ret, "TREND": _feat_trend,
    "TURN": _feat_turn, "VOLAT": _feat_volat, "AMIHUD": _feat_amihud,
    "LIMUP_EX": _feat_limup,
    # 基本面（成长/价值族）
    "SUE": _feat_sue, "ACCEL": _feat_accel, "REV_YOY": _feat_rev_yoy,
    "BP": _feat_bp, "EP": _feat_ep,
}
FEATURES = set(FEATURE_BUILDERS)


# ============================ 算子 ============================

OP_ARITY = {
    "ADD": 2, "SUB": 2, "MUL": 2, "DIV": 2,
    "NEG": 1, "ABS": 1, "SIGN": 1,
    "GATE": 3,
    "JUMP": 1, "DECAY": 1, "DELAY1": 1, "MAX3": 1,
    "DELTA5": 1, "MA20": 1, "STD20": 1, "TS_RANK20": 1,
}


def _lag(x, n):
    return x.groupby(level=1).shift(n)


def _zscore_cs(x):
    m = x.groupby(level=0).transform("mean")
    s = x.groupby(level=0).transform("std")
    return (x - m) / (s + 1e-9)


def _div(x, y):
    return x / (y + 1e-6 * np.sign(y).replace(0, 1))


def _std20(x):
    m = x.groupby(level=1).rolling(20, min_periods=5).mean().reset_index(level=0, drop=True)
    s = x.groupby(level=1).rolling(20, min_periods=5).std().reset_index(level=0, drop=True)
    return (x - m) / (s + 1e-9)


OPS_IMPL = {
    "ADD": lambda a, b: a + b,
    "SUB": lambda a, b: a - b,
    "MUL": lambda a, b: a * b,
    "DIV": _div,
    "NEG": lambda a: -a,
    "ABS": lambda a: a.abs(),
    "SIGN": lambda a: np.sign(a),
    "GATE": lambda c, x, y: x.where(c > 0, y),
    "JUMP": lambda a: np.maximum(_zscore_cs(a) - 3, 0),
    "DECAY": lambda a: a + 0.8 * _lag(a, 1) + 0.6 * _lag(a, 2),
    "DELAY1": lambda a: _lag(a, 1),
    "MAX3": lambda a: pd.concat([a, _lag(a, 1), _lag(a, 2)], axis=1).max(axis=1),
    "DELTA5": lambda a: a - _lag(a, 5),
    "MA20": lambda a: a.groupby(level=1).rolling(20, min_periods=5).mean().reset_index(level=0, drop=True),
    "STD20": _std20,
    "TS_RANK20": lambda a: a.groupby(level=1).rolling(20, min_periods=5).rank(pct=True).reset_index(level=0, drop=True),
}


# ============================ 校验 / 执行 ============================

def validate(tokens):
    """栈模拟：叶子 +1，算子 -arity+1，终栈 == 1。"""
    stack = 0
    for t in tokens:
        if t in FEATURES:
            stack += 1
        elif t in OP_ARITY:
            a = OP_ARITY[t]
            if stack < a:
                return False
            stack = stack - a + 1
        else:
            return False
    return stack == 1


def to_prefix(tokens):
    if not validate(tokens):
        return "INVALID"
    stack = []
    for t in tokens:
        if t in FEATURES:
            stack.append(t)
        else:
            arity = OP_ARITY[t]
            args = [stack.pop() for _ in range(arity)][::-1]
            stack.append(f"{t}({','.join(args)})")
    return stack[0]


def execute(tokens, feat_mats, panel_index):
    """三态返回：(Series, None) 合法 / (None, '语法非法') / (None, '实现异常: ...')。"""
    if not validate(tokens):
        return None, "语法非法"
    if len(tokens) > MAX_FORMULA_LEN:
        return None, f"超长 {len(tokens)}>{MAX_FORMULA_LEN}"
    fb = forbid_check(tokens)
    if fb:
        return None, f"同构冗余:{fb}"
    stack = []
    try:
        for t in tokens:
            if t in feat_mats:
                stack.append(feat_mats[t])
            else:
                arity = OP_ARITY[t]
                args = [stack.pop() for _ in range(arity)][::-1]
                res = OPS_IMPL[t](*args)
                res = res.replace([np.inf, -np.inf], [1.0, -1.0]).fillna(0.0)
                stack.append(res)
        if len(stack) != 1:
            return None, "栈残留"
        out = stack[0].reindex(panel_index)
        if float(out.std()) < 1e-4:
            return None, "常量因子"
        return out, None
    except Exception as e:
        return None, f"实现异常: {type(e).__name__}: {e}"


# ============================ LLM ============================

def load_api_key():
    if os.path.exists(ENV_FILE):
        for line in open(ENV_FILE, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    key = os.environ.get("DSH_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or ""
    if not key:
        raise RuntimeError(f"未找到 API key：{ENV_FILE}")
    return key


def call_llm(messages, api_key, model="deepseek-chat", temperature=0.7, max_tokens=8000):
    payload = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    req = urllib.request.Request(DEEPSEEK_URL, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode("utf-8"))["choices"][0]["message"]["content"]


GEN_SYSTEM = "你是量化因子挖掘研究员。用逆波兰式公式语言生成 alpha 候选，只输出 JSON。"


def build_gen_prompt(anchor_desc, per_round):
    feat = ", ".join(sorted(FEATURES))
    ops = " ".join(sorted(OP_ARITY))
    return (
        f"用以下公式语言生成 {per_round} 个彼此低相关的 alpha 候选（预测未来收益的截面排序能力）。\n\n"
        f"特征叶子（arity=0）：{feat}\n"
        f"算子（内部节点）：{ops}\n\n"
        "规则：\n"
        f"1. 每条公式 = 逆波兰式 token 序列，长度 ≤ {MAX_FORMULA_LEN}，必须是合法表达式树（叶子数 = 内部节点数 + 1）。\n"
        "2. 逆波兰式求值：遇特征压栈，遇算子弹 arity 个操作数计算后压回；终栈恰 1 个值。\n"
        "3. 目标：未来收益的截面排序能力，机制需可解释（如「缩量回调后的反弹动能」「低换手的流动性溢价」）。\n"
        "4. 避免：常量因子（无截面区分度）、未来函数、与下列池内锚点高度同构的公式。\n"
        f"5. 已入池锚点（避免同构，相关>0.5 会淘汰）：{anchor_desc}\n"
        "6. ★特别提醒：换手中枢/低换手族（turn_mid_prox、turnover、amihud、sentiment 变体）已被覆盖且相关高，"
        "别再挖换手水平/偏离类；改挖正交的新结构：波动结构、量价背离、时间序列形态、涨停后形态、估值-质量交叉等。\n\n"
        "输出严格 JSON 数组（不要任何解释文字）：\n"
        '[{"formula": ["RET5", "TREND", "SUB", "STD20", "MUL"], "机制": "一句话经济逻辑"}]\n'
    )


# 短板族定向挖掘主题（成长/价值 = 6 族中最弱两族）
DIRECTED_THEMES = {
    "成长": {
        "feat_hint": "以 SUE / ACCEL / REV_YOY / EP（盈利超预期、盈利加速度、营收同比、盈利收益）为主，"
                     "配 RET/RET5/VOL_CHG/TREND 做确认与时机",
        "mech": "盈利超预期后的盈余漂移(PEAD)、盈利加速度、营收-盈利共振、成长股超跌反弹买点、"
                "盈利动量与价格动量的背离",
        "avoid": "别挖纯量价水平（换手/流动性/趋势水平）——量价族已覆盖",
    },
    "价值": {
        "feat_hint": "以 BP / EP（账面市值比、盈利收益）为主，配 VOLAT/TREND/RET 做安全边际与拐点",
        "mech": "低估值+质量交叉（BP/EP 与稳健性）、价值股均值回归、低估值低波动防御溢价、"
                "BP 与短期超跌的叠加",
        "avoid": "别挖成长动量/高换手/情绪——成长与量价族已覆盖",
    },
}


def build_directed_prompt(anchor_desc, per_round, family):
    """短板族定向挖掘提示词：强调目标族基本面叶子 + 机制，规避已覆盖族。"""
    theme = DIRECTED_THEMES[family]
    feat = ", ".join(sorted(FEATURES))
    ops = " ".join(sorted(OP_ARITY))
    return (
        f"本轮是【{family}族】定向挖掘——{family}族是本因子池最弱的一族，需要补强。\n\n"
        f"用公式语言生成 {per_round} 个彼此低相关的 {family}族 alpha 候选（预测未来收益截面排序）。\n\n"
        f"特征叶子（arity=0）：{feat}\n"
        f"算子（内部节点）：{ops}\n\n"
        f"★{family}族定向要求：\n"
        f"  - 优先特征：{theme['feat_hint']}\n"
        f"  - 目标机制：{theme['mech']}\n"
        f"  - 规避：{theme['avoid']}\n\n"
        "规则：\n"
        f"1. 每条公式 = 逆波兰式 token 序列，长度 ≤ {MAX_FORMULA_LEN}，合法表达式树（叶子数 = 内部节点数 + 1）。\n"
        "2. 逆波兰式求值：遇特征压栈，遇算子弹 arity 个操作数计算后压回；终栈恰 1 个值。\n"
        "3. 避免：常量因子、未来函数、与下列池内锚点高度同构的公式。\n"
        f"4. 已入池锚点（避免同构，相关>0.5 会淘汰）：{anchor_desc}\n\n"
        "输出严格 JSON 数组（不要任何解释文字）：\n"
        '[{"formula": ["SUE", "ACCEL", "ADD", "TS_RANK20"], "机制": "一句话经济逻辑"}]\n'
    )


def generate_candidates(api_key, anchor_desc, per_round, max_retry=3, directed=None):
    """生成候选 + 校验-重试闭环：非法公式带报错重生成（τ=3）。directed=族名（成长/价值）时用定向提示词。"""
    prompt = (build_directed_prompt(anchor_desc, per_round, directed)
              if directed in DIRECTED_THEMES else build_gen_prompt(anchor_desc, per_round))
    kept, errors = [], []
    for attempt in range(max_retry):
        if attempt > 0:
            prompt = (prompt + "\n\n⚠️ 上一批有非法公式，报错如下，请重新生成这些"
                      "（严格合法逆波兰式，长度≤" + str(MAX_FORMULA_LEN) +
                      "，叶子数=内部节点数+1）：\n" + "\n".join(errors[:12]))
        try:
            reply = call_llm([{"role": "system", "content": GEN_SYSTEM},
                              {"role": "user", "content": prompt}], api_key)
        except Exception as e:
            print(f"LLM 调用失败: {e}", flush=True)
            break
        batch = extract_formulas(reply)
        new_errors = []
        for c in batch:
            tokens = c.get("formula")
            if not isinstance(tokens, list) or not tokens:
                new_errors.append("空公式")
            elif not validate(tokens):
                new_errors.append(f"{tokens} 栈不合法")
            else:
                kept.append(c)
        if not new_errors:
            break
        errors = new_errors
        print(f"  第 {attempt + 1} 次生成：{len(batch)} 条，{len(new_errors)} 条非法，重试…", flush=True)
    return kept


def extract_formulas(text):
    """从 LLM 回复解析 JSON 数组 [{formula:[tokens], 机制}]。"""
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    m = re.search(r"\[.*\]", text, flags=re.S)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


# ============================ 打分 / 去重 ============================

def score_icir(sig, fwd):
    ics = cross_sectional_ics(sig, fwd)
    if len(ics) < 30:
        return None
    ic = float(ics.mean())
    ir = float(ic / ics.std()) if ics.std() > 1e-12 else 0.0
    return {"ic": ic, "icir": ir, "n": len(ics)}


def pnl_corr(sig1, sig2, close_wide, topn=20):
    """★行为正交（alpha-foundry 口径）：两个因子 top-N 等权组合的日收益序列 Pearson 相关。

    比截面 Spearman 更接近「真同构」——换窗口/换参数的同构变体，其 top-N 组合 PnL 高度相关，
    而截面因子值相关可能不高。用 PnL 相关才能挡住「换手变体溜进来」。
    """
    r1 = sig1.unstack().rank(axis=1, pct=True)
    r2 = sig2.unstack().rank(axis=1, pct=True)
    n = r1.shape[1]
    thr = 1 - topn / n
    top1 = (r1 >= thr).astype(float)
    top2 = (r2 >= thr).astype(float)
    ret = close_wide.pct_change()
    pnl1 = (ret * top1).sum(axis=1) / top1.sum(axis=1).clip(lower=1)
    pnl2 = (ret * top2).sum(axis=1) / top2.sum(axis=1).clip(lower=1)
    mask = pnl1.notna() & pnl2.notna()
    if int(mask.sum()) < 30:
        return 0.0
    return float(pnl1[mask].corr(pnl2[mask]))


def max_anchor_corr(sig, anchors, close_wide=None, topn=20):
    """与池内锚点的最大同构相关 = max(Spearman 截面相关, pnl 行为相关)。

    双保险：
      - cross_corr(Spearman) 抓「反方向同源」（如 TURN 高换手 vs turn_mid_prox 低换手，Spearman≈-1）
      - pnl_corr(行为) 抓「同向换参变体」（同批股票，组合收益相关）
    两者取最大，任一超阈值都算同构。
    """
    sp = max((abs(cross_corr(sig, a)) for a in anchors.values()), default=0.0)
    if close_wide is not None:
        pn = max((abs(pnl_corr(sig, a, close_wide, topn)) for a in anchors.values()), default=0.0)
        return max(sp, pn)
    return sp


# ============================ 强类型 forbid 表（alpha-foundry 口径） ============================

# 每个算子输出的「类型」（kind），用于 forbid 冗余结构：
#   NORM = 连续值（robust 归一化后，单调），RANKED = 截面 rank（0-1），SIGNED = 仅符号
_OP_KIND = {
    "TS_RANK20": "RANKED", "SIGN": "SIGNED",
    "NEG": "NEG", "ABS": "ABS", "MA20": "NORM", "STD20": "NORM",
    "DECAY": "NORM", "DELAY1": "NORM", "MAX3": "NORM", "DELTA5": "NORM", "JUMP": "NORM",
    "ADD": "NORM", "SUB": "NORM", "MUL": "NORM", "DIV": "NORM", "GATE": "NORM",
}

# forbid 规则：拒绝冗余结构（同构霸榜的生成源头剪枝）
#   TS_RANK20 对严格单调变换不变 → 其子节点是 RANKED/NORM(纯单调) 都算冗余
#   ABS(SIGN(x)) = 常量 1 → 剪
#   NEG(NEG(x)) = 恒等 → 剪
def forbid_check(tokens):
    """返回 None（通过）或拒绝原因。在 execute 前调用。"""
    stack = []
    for t in tokens:
        if t in FEATURES:
            stack.append("NORM")
            continue
        if t not in OP_ARITY:
            return "未知 token"
        arity = OP_ARITY[t]
        if len(stack) < arity:
            return None  # 栈不足，交给 validate 报语法非法
        args = [stack.pop() for _ in range(arity)]
        if t == "TS_RANK20" and args[0] == "RANKED":
            return "TS_RANK20(TS_RANK20) 冗余（rank 的 rank）"
        if t == "ABS" and args[0] == "SIGNED":
            return "ABS(SIGN) 冗余（恒为 1）"
        if t == "NEG" and args[0] == "NEG":
            return "NEG(NEG) 冗余（恒等）"
        stack.append(_OP_KIND.get(t, "NORM"))
    return None


# ============================ 主流程 ============================

def build_anchors(panel):
    anchors = {}
    for name, fn in [("bp_value", bp_value), ("sue", sue), ("f_score", f_score),
                     ("turn_mid_prox", turn_mid_prox), ("limup_ex_5", limup_ex_5),
                     ("amihud", amihud), ("reversal_20", reversal_20), ("mom_120", mom_120),
                     ("near_high_250", near_high_250), ("sentiment", sentiment)]:
        try:
            anchors[name] = fn(panel).reindex(panel.index)
        except Exception as e:
            print(f"  锚点 {name} 失败: {str(e)[:80]}", flush=True)
    return anchors


SELFTEST_FORMULAS = [
    (["TURN", "NEG"], "低换手"),
    (["AMIHUD"], "非流动性"),
    (["RET5", "RET20", "SUB"], "短期动量差"),
    (["TREND", "VOLAT", "DIV"], "趋势/波动"),
    (["RET", "STD20"], "收益波动zscore"),
    (["VOL_CHG", "TS_RANK20"], "量比时序rank"),
    (["RET", "VOL_CHG", "MUL", "MA20"], "量价结合均线"),
]

# ============================ Warm Start GP（gplearn 口径） ============================

# 种子 = 已验证有效的因子（用公式 token 表达）
SEED_FORMULAS = [
    (["AMIHUD"], "非流动性（amihud +20.59%）"),
    (["TURN", "NEG"], "低换手（turn_mid_prox +3.03%）"),
    (["RET20", "NEG"], "20日反转（reversal_20）"),
    (["VOLAT", "NEG"], "低波（lowvol）"),
    (["TREND"], "长期趋势（ma200_trend +14.96%）"),
]


def mutate(tokens, rng):
    """Warm Start GP 变异：从已验证因子起做随机结构变异。
    操作：取反 / 绝对值 / 时序变换 / 加特征 / 乘特征 / 换特征。超长则回退原样。"""
    t = list(tokens)
    op = rng.choice(["neg", "abs", "ts", "add_feat", "mul_feat", "swap_feat"])
    feats = sorted(FEATURES)
    if op == "neg":
        t = t + ["NEG"]
    elif op == "abs":
        t = t + ["ABS"]
    elif op == "ts":
        t = t + [rng.choice(["MA20", "STD20", "DECAY", "DELTA5", "TS_RANK20"])]
    elif op == "add_feat":
        t = t + [rng.choice(feats), "ADD"]
    elif op == "mul_feat":
        t = t + [rng.choice(feats), "MUL"]
    elif op == "swap_feat":
        idx = [i for i, x in enumerate(t) if x in FEATURES]
        if idx:
            i = rng.choice(idx)
            t[i] = rng.choice([f for f in feats if f != t[i]])
    if len(t) > MAX_FORMULA_LEN or not validate(t):
        return tokens
    return t


def warm_start_candidates(n, rng):
    """从种子变异生成 n 条候选（每轮变异 1-2 次）。"""
    import random as _random
    cands = []
    while len(cands) < n:
        base = rng.choice(SEED_FORMULAS)[0]
        t = mutate(base, rng)
        if rng.random() < 0.5:
            t = mutate(t, rng)
        if validate(t) and forbid_check(t) is None:
            cands.append({"formula": t, "机制": f"WarmStart 变异自 {to_prefix(base)}"})
    return cands


def run_candidate(tokens, feat_mats, panel_index, fwd, anchors, panel, topn, rebalance, close_wide=None, batch_sigs=None):
    sig, err = execute(tokens, feat_mats, panel_index)
    if err:
        return {"formula": tokens, "prefix": to_prefix(tokens), "error": err}
    sc = score_icir(sig, fwd)
    if sc is None:
        return {"formula": tokens, "prefix": to_prefix(tokens), "error": "IC 样本不足"}
    cov = float(sig.notna().mean())
    corr = max_anchor_corr(sig, anchors, close_wide, topn)
    direction = 1 if sc["ic"] >= 0 else -1
    if cov < MIN_COVERAGE:
        return {"formula": tokens, "prefix": to_prefix(tokens), "icir": round(sc["icir"], 3),
                "cov": round(cov, 3), "corr": round(corr, 3), "gate": "覆盖率不足"}
    if abs(sc["icir"]) < MIN_ICIR:
        return {"formula": tokens, "prefix": to_prefix(tokens), "icir": round(sc["icir"], 3),
                "cov": round(cov, 3), "corr": round(corr, 3), "gate": "ICIR不足"}
    if corr > MAX_ANCHOR_CORR:
        return {"formula": tokens, "prefix": to_prefix(tokens), "icir": round(sc["icir"], 3),
                "cov": round(cov, 3), "corr": round(corr, 3), "gate": "同构淘汰"}
    # 批内互去重：与同批已入选(有效)候选比，防同一批产出重复因子
    batch_corr = 0.0
    if batch_sigs:
        batch_corr = max_anchor_corr(sig, {f"b{i}": s for i, s in enumerate(batch_sigs)}, close_wide, topn)
    if batch_corr > MAX_ANCHOR_CORR:
        return {"formula": tokens, "prefix": to_prefix(tokens), "icir": round(sc["icir"], 3),
                "cov": round(cov, 3), "corr": round(corr, 3), "批内corr": round(batch_corr, 3),
                "gate": "批内同构淘汰"}
    # 组合层裁决
    try:
        r = combo_validate_sig(f"fm_{to_prefix(tokens)[:20]}", sig, panel,
                               topn=topn, rebalance=rebalance, start=DEFAULT_START,
                               end=DEFAULT_END, direction=direction)
        m = r["metrics"]
        if r["verdict"] == "有效" and batch_sigs is not None:
            batch_sigs.append(sig)  # 入选池，供后续候选批内去重
        return {"formula": tokens, "prefix": to_prefix(tokens), "icir": round(sc["icir"], 3),
                "cov": round(cov, 3), "corr": round(corr, 3), "gate": "过海选",
                "verdict": r["verdict"], "净超额": round(r["excess_annual"], 4),
                "夏普": round(m["sharpe"], 3), "回撤": round(m["max_drawdown"], 3)}
    except Exception as e:
        return {"formula": tokens, "prefix": to_prefix(tokens), "icir": round(sc["icir"], 3),
                "cov": round(cov, 3), "corr": round(corr, 3), "gate": f"组合层异常:{str(e)[:60]}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true", help="手写公式验证管线（不花 LLM）")
    ap.add_argument("--warm-start", type=int, default=0, help="Warm Start GP：从种子变异 N 条候选（叠加在 LLM 候选上）")
    ap.add_argument("--directed", default=None, choices=[None, "成长", "价值"],
                    help="短板族定向挖掘（成长/价值）")
    ap.add_argument("--per-round", type=int, default=20)
    ap.add_argument("--topn", type=int, default=DEFAULT_TOPN)
    ap.add_argument("--rebalance", default=DEFAULT_REBALANCE)
    ap.add_argument("--out", default=str(BASE / "logs" / "formula_miner_results.json"))
    args = ap.parse_args()

    print("加载面板 + fwd 标签...", flush=True)
    panel = load_panel("data/cache/bars.db", start="2019-01-01")
    fwd = forward_returns(panel)
    panel_index = panel.index
    close_wide = panel["close"].unstack()
    print(f"面板 {panel.shape}", flush=True)

    print("构建特征叶子...", flush=True)
    feat_mats = {}
    for name, fn in FEATURE_BUILDERS.items():
        try:
            feat_mats[name] = fn(panel).reindex(panel_index)
        except Exception as e:
            print(f"  特征 {name} 失败: {str(e)[:80]}", flush=True)
    print(f"特征就绪 {len(feat_mats)}/{len(FEATURES)}", flush=True)

    print("构建锚点...", flush=True)
    anchors = build_anchors(panel)
    print(f"锚点就绪 {len(anchors)}", flush=True)

    if args.selftest:
        candidates = [{"formula": f, "机制": c} for f, c in SELFTEST_FORMULAS]
    else:
        api_key = load_api_key()
        anchor_desc = ", ".join(anchors.keys())
        candidates = generate_candidates(api_key, anchor_desc, args.per_round, directed=args.directed)
        print(f"LLM 有效候选 {len(candidates)} 条", flush=True)
        if args.warm_start > 0:
            import random as _random
            ws = warm_start_candidates(args.warm_start, _random)
            candidates += ws
            print(f"Warm Start 变异候选 {len(ws)} 条（叠加）", flush=True)

    results = []
    batch_sigs = []  # 同批已入选(有效)候选信号，用于批内互去重
    for c in candidates:
        tokens = c.get("formula")
        if not isinstance(tokens, list) or not tokens:
            results.append({"formula": tokens, "error": "空公式"})
            continue
        r = run_candidate(tokens, feat_mats, panel_index, fwd, anchors, panel,
                          args.topn, args.rebalance, close_wide, batch_sigs=batch_sigs)
        r["机制"] = c.get("机制", "")
        results.append(r)
        line = f"  {to_prefix(tokens):<28} icir={r.get('icir', 'NA')} "
        if "verdict" in r:
            line += f"组合层={r['verdict']} 净超额={r.get('净超额', 0):+.2%} 夏普={r.get('夏普', 0)}"
        else:
            line += f"→ {r.get('gate', r.get('error', ''))}"
        print(line, flush=True)

    valid = [r for r in results if "icir" in r and abs(r["icir"]) >= MIN_ICIR]
    passed_combo = [r for r in results if r.get("verdict") == "有效"]
    print(f"\n=== {len(results)} 候选：{len(valid)} 过海选 ICIR，{len(passed_combo)} 过组合层 ===")
    for r in passed_combo:
        print(f"  ★ {r['prefix']} 净超额{r['净超额']:+.2%} 夏普{r['夏普']}")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str),
                              encoding="utf-8")
    print(f"结果已存：{args.out}")


if __name__ == "__main__":
    main()
