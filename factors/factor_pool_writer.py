# -*- coding: utf-8 -*-
"""factors/factor_pool_writer.py — 第三层：三件套登记（实盘接入）

把通过「第一层（截面门票）+ 第二层（组合层 T+1 裁决）」的因子，写成主系统 scan.py
消费的三件套 → 主系统下次 scan 免改代码自动吸收（信号族归类/有效性标注/信号分加权）。

三件套契约（严格对齐 factors/opportunities/scan.py 的消费字段）：
  1. daily_scores/daily_{date}_{ts}.csv     列 = date, code, {factor}_rank, ...
     （rank 0-1 截面分位，好因子 rank 大；build_factor_backtest_db 用 c.endswith('_rank') 识别）
  2. health/health_{date}_{ts}.csv          列 = factor, icir20, icir60, icir120, status
     （scan.py load_factor_health 读 factor/icir120/status）
  3. factor_manifest_{date}_{ts}.json       {date, n_factors, health_date, factors:[
       {code, category, icir_60, direction, status, usage, name_cn}]}
     （scan.py load_factor_manifest 读 code/category/icir_60/direction/status/usage/name_cn；
       category 走 factors/signal_family.category_to_family 归族）

铁律⑨ 写保护免疫：时间戳文件名 + 消费端 glob mtime 最新。

用法：
  from factors.factor_pool_writer import write_pool
  write_pool([{ "code": "turn_low", "name_cn": "低换手防守", "category": "量价",
                "direction": -1, "status": "有效", "usage": "防守主力",
                "icir_20": ..., "icir_60": ..., "icir_120": ...,
                "rank": <当日截面 0-1 rank Series, index=股票代码> }], data_date="2026-08-14")
"""
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent.parent
OUT_DIR = BASE / "data" / "factorpool" / "output"
DAILY_DIR = OUT_DIR / "daily_scores"
HEALTH_DIR = OUT_DIR / "health"


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def write_daily_scores(factors: list, data_date: str, ts: str = None, out_dir=DAILY_DIR) -> str:
    """写当日 daily_scores：date, code, {factor}_rank, ...
    ★code 列保留 .SH/.SZ 后缀——scan.py load_daily_ranks 要求 code 含 '.'（无后缀整行跳过），
    且 build_factor_backtest_db 用 code 与 bars.db（带后缀）做 join。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = ts or _ts()
    codes = sorted({c for f in factors for c in f.get("rank", pd.Series(dtype=float)).index})
    daily = pd.DataFrame({"date": data_date, "code": codes})
    for f in factors:
        col = f"{f['code']}_rank"
        daily[col] = daily["code"].map(f.get("rank", pd.Series(dtype=float))).round(6)
    p = out_dir / f"daily_{data_date}_{ts}.csv"
    daily.to_csv(p, index=False, encoding="utf-8")
    return str(p)


def write_health(factors: list, data_date: str, ts: str = None, out_dir=HEALTH_DIR) -> str:
    """写当日 health：factor, icir20, icir60, icir120, status"""
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = ts or _ts()
    rows = [{
        "factor": f["code"],
        "icir20": f.get("icir_20"),
        "icir60": f.get("icir_60"),
        "icir120": f.get("icir_120"),
        "status": f.get("status", "有效"),
    } for f in factors]
    p = out_dir / f"health_{data_date}_{ts}.csv"
    pd.DataFrame(rows).to_csv(p, index=False, encoding="utf-8")
    return str(p)


def write_manifest(factors: list, data_date: str, ts: str = None, out_dir=OUT_DIR) -> str:
    """写当日 factor_manifest：{date, n_factors, health_date, factors:[...]}"""
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = ts or _ts()
    payload = {
        "date": data_date,
        "n_factors": len(factors),
        "health_date": data_date,
        "factors": [{
            "code": f["code"],
            "name_cn": f.get("name_cn", f["code"]),
            "category": f.get("category", "量价"),
            "icir_60": f.get("icir_60"),
            "direction": f.get("direction", 1),
            "status": f.get("status", "有效"),
            "usage": f.get("usage", ""),
        } for f in factors],
    }
    p = out_dir / f"factor_manifest_{data_date}_{ts}.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)


def write_pool(factors: list, data_date: str) -> dict:
    """写三件套（daily_scores + health + manifest），返回三文件路径。"""
    ts = _ts()
    return {
        "daily_scores": write_daily_scores(factors, data_date, ts=ts),
        "health": write_health(factors, data_date, ts=ts),
        "manifest": write_manifest(factors, data_date, ts=ts),
    }


if __name__ == "__main__":
    # 自测：写一个假因子三件套到 output（验证格式，不污染真实因子池）
    import numpy as np
    demo_rank = pd.Series(np.linspace(0, 1, 10),
                          index=[f"{600000 + i}" for i in range(10)])
    demo = [{
        "code": "demo_factor", "name_cn": "演示因子", "category": "量价",
        "direction": 1, "status": "有效", "usage": "自测",
        "icir_20": 0.5, "icir_60": 0.6, "icir_120": 0.7, "rank": demo_rank,
    }]
    paths = write_pool(demo, data_date="2026-01-01")
    for k, v in paths.items():
        print(f"{k}: {v}")
