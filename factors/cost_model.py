# -*- coding: utf-8 -*-
"""factors/cost_model.py —— 交易成本模型（唯一口径，配置驱动）

为什么要有这个模块：
  旧代码把 0.026%+0.05%+0.1% = 0.176% 当作「单边」费率，再在回测里 ×2 = 0.352%。
  真实费率（买卖分边）：
    · 2023-08-28 前：佣金 .052 + 过户 .002 + 滑点 .2 + 印花税 .1（卖出）= **0.354%**
      → 旧口径 0.352% 恰好接近（把 0.05% 印花双边计 0.1%，与当时真实 0.1% 巧合相等）
    · 2023-08-28 后：印花税降为 0.05% → 真实 **0.304%** → 旧口径高估 0.048pp
  所以旧口径不是"低估"，而是**用错误的构成碰巧对上了旧税率**；一旦税率变化就偏了，
  且无法表达"卖出单边"这一事实。本模块改为买卖分边 + 分段印花税。

本模块的口径（全部可在 config/costs.yaml 改）：
  · 费率按**成交金额**加权，不是按票数
  · 买入单边 = 佣金 + 过户费 + 滑点
  · 卖出单边 = 佣金 + 过户费 + 滑点 + 印花税（印花税按成交日查分段表）
  · 一次调仓换掉 turnover 比例的持仓 → 卖出 turnover + 买入 turnover 两笔成交
  · 最低佣金 5 元/笔不逐笔模拟（回测无逐笔金额），只用 min_commission 披露

用法：
    from factors.cost_model import rates, period_cost, annual_cost, describe
    rates("2020-01-02")            # {'buy':..., 'sell':..., 'round_trip':...}
    period_cost(0.616, dates=rdates)   # 一次调仓的成本占净值比例
    describe()                     # 成本定义表（写报告用）
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

DEFAULTS = {
    "commission": 0.00026,
    "transfer_fee": 0.00001,
    "slippage": 0.001,
    "min_commission": 5.0,
    "stamp_duty_schedule": [
        {"until": "2023-08-27", "rate": 0.001},
        {"since": "2023-08-28", "rate": 0.0005},
    ],
}

_CFG = Path(__file__).resolve().parent.parent / "config" / "costs.yaml"
_cache: dict | None = None


def load_config() -> dict:
    """读 config/costs.yaml；缺失/异常回落 DEFAULTS（不崩溃）。"""
    global _cache
    if _cache is not None:
        return _cache
    cfg = dict(DEFAULTS)
    if _CFG.exists():
        try:
            import yaml
            raw = yaml.safe_load(_CFG.read_text(encoding="utf-8")) or {}
            for k in ("commission", "transfer_fee", "slippage", "min_commission"):
                if raw.get(k) is not None:
                    cfg[k] = float(raw[k])
            if raw.get("stamp_duty_schedule"):
                cfg["stamp_duty_schedule"] = raw["stamp_duty_schedule"]
        except Exception:
            pass
    _cache = cfg
    return cfg


def _as_date(d) -> date:
    if d is None:
        return date.today()
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    return datetime.strptime(str(d)[:10], "%Y-%m-%d").date()


def stamp_rate(on=None) -> float:
    """印花税（卖出单边）：按成交日查分段表。"""
    cfg = load_config()
    d = _as_date(on)
    for row in cfg["stamp_duty_schedule"]:
        if row.get("until") and d <= _as_date(row["until"]):
            return float(row["rate"])
        if row.get("since") and d >= _as_date(row["since"]):
            return float(row["rate"])
    return float(cfg["stamp_duty_schedule"][-1]["rate"])


def rates(on=None) -> dict:
    """单边费率：买入 / 卖出 / 一次完整换手（卖+买）。"""
    cfg = load_config()
    base = cfg["commission"] + cfg["transfer_fee"] + cfg["slippage"]
    buy = base
    sell = base + stamp_rate(on)
    return {"buy": buy, "sell": sell, "round_trip": buy + sell}


def period_cost(turnover: float, dates=None, multiplier: float = 1.0) -> float:
    """一次调仓的成本（占组合净值比例）。

    turnover = 本次换掉的持仓比例（0~1）；一次换仓 = 卖出 turnover + 买入 turnover。
    dates 给出调仓日列表时，按每个调仓日的印花税率分别计算（2023-08-28 前后不同）。
    """
    if dates:
        ds = [d for d in dates]
        if not ds:
            return 0.0
        total = 0.0
        for d in ds:
            r = rates(d)
            total += (r["buy"] + r["sell"]) * turnover
        return float(total * multiplier)
    r = rates(None)
    return float((r["buy"] + r["sell"]) * turnover * multiplier)


def annual_cost(turnover_per_period: float, periods_per_year: float, on=None, multiplier: float = 1.0) -> float:
    """年化成本（算术近似）：单次换手 × 每年调仓次数 × 单次全换手成本。"""
    return float(rates(on)["round_trip"] * turnover_per_period * periods_per_year * multiplier)


def describe() -> dict:
    """成本定义表（写报告/文档用）。"""
    cfg = load_config()
    r_now = rates("2026-10-17")
    r_old = rates("2020-01-02")
    return {
        "source": str(_CFG),
        "basis": "按成交金额加权（不是按票数）",
        "sides": "买卖分开计价：买入=佣金+过户费+滑点；卖出=买入+印花税",
        "commission": cfg["commission"],
        "transfer_fee": cfg["transfer_fee"],
        "slippage": cfg["slippage"],
        "min_commission": cfg["min_commission"],
        "min_commission_note": "逐笔 5 元最低佣金未在回测中模拟（无逐笔金额），仅对极小资金有影响",
        "stamp_schedule": cfg["stamp_duty_schedule"],
        "round_trip_2026": round(r_now["round_trip"], 6),
        "round_trip_2020": round(r_old["round_trip"], 6),
        "example": {
            "full_turnover_2026_pct": round(r_now["round_trip"] * 100, 4),
            "full_turnover_2020_pct": round(r_old["round_trip"] * 100, 4),
            "old_code_0_352_pct_note": (
                "旧口径 0.176% 单边×2=0.352%：2023-08 前真实 0.354%（巧合接近），"
                "2023-08 后真实 0.304%（高估 0.048pp）"
            ),
        },
    }


if __name__ == "__main__":
    import json
    print(json.dumps(describe(), ensure_ascii=False, indent=2))
