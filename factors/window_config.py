# -*- coding: utf-8 -*-
"""factors/window_config.py —— 回测/验证窗口的配置读取（配置驱动，不写死）

用途：把原先散落在 9 个文件里的窗口起点/终点收敛到 `config/backtest_window.yaml`。
设计原则（对照项目铁律「全部模块动态化」）：
  · 配置文件缺失/字段缺失 → **回落到原有默认值**，绝不崩溃
  · 不改变任何现有行为：默认值 = 改造前写死的值

用法：
    from factors.window_config import get_window, get_filters
    w = get_window()
    w["start"], w["end"], w["panel_load_start"]
    f = get_filters()
    f["exclude_suspension"] / f["exclude_st"] / f["bj_handling"]

命令行自检：python factors/window_config.py
"""
from __future__ import annotations

from pathlib import Path

DEFAULTS = {
    "start": "2010-01-01",
    "end": "2025-12-31",
    "panel_load_start": "2019-01-01",
    "robustness": {"enabled": False, "start": "2010-01-01", "end": "2025-12-31"},
}
FILTER_DEFAULTS = {
    "exclude_suspension": True,
    "exclude_qfq_suspect": True,
    "exclude_st": True,
    "bj_handling": "keep",
}

_CFG_PATH = Path(__file__).resolve().parent.parent / "config" / "backtest_window.yaml"


def _load() -> dict:
    if not _CFG_PATH.exists():
        return {}
    try:
        import yaml
    except ImportError:
        return {}
    try:
        with open(_CFG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def get_window() -> dict:
    """返回 {'start','end','panel_load_start','robustness'}，缺字段回落默认"""
    w = dict(DEFAULTS)
    raw = (_load().get("window") or {})
    for k, v in raw.items():
        if k == "robustness" and isinstance(v, dict):
            r = dict(DEFAULTS["robustness"])
            r.update(v)
            w["robustness"] = r
        elif v is not None:
            w[k] = v
    return w


def get_filters() -> dict:
    f = dict(FILTER_DEFAULTS)
    raw = (_load().get("filters") or {})
    for k, v in raw.items():
        if k in f and v is not None:
            f[k] = v
    return f


STRICT_DEFAULTS = {
    "start": "2016-01-01",
    "end": "2026-10-16",
    "topn": 20,
    "rebalance": 20,
    "neutral": True,
    "adv_gate": 0.5,
    "min_candidates": 800,
    "min_candidate_ratio": 0.40,
}


def get_strict() -> dict:
    """P0 锁定口径（config/backtest_window.yaml → strict:）；缺字段回落默认。"""
    s = dict(STRICT_DEFAULTS)
    raw = (_load().get("strict") or {})
    for k, v in raw.items():
        if k in s and v is not None:
            s[k] = v
    return s


if __name__ == "__main__":
    import json
    print("config:", _CFG_PATH, "存在" if _CFG_PATH.exists() else "缺失（用默认值）")
    print("window :", json.dumps(get_window(), ensure_ascii=False))
    print("filters:", json.dumps(get_filters(), ensure_ascii=False))
