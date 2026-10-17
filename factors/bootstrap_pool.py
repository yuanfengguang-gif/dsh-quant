# -*- coding: utf-8 -*-
"""factors/bootstrap_pool.py — 建议一：内置已实证因子落三件套（因子池兜底）

定位：因子池（data/factorpool/output/）当前为空，scan.py 的五强共识信号降级。
本脚本用仓库「内置已实证因子」重算 daily_scores + health + manifest 落三件套，
让因子池立即非空、信号共识可用——不必等 qf-llm 挖出通过第一/二层的新因子。

内置因子（factors/factor_engine.py + bt_runner turn_low）：
  turn_low      低换手防守（主系统实证「唯一干净防守 alpha」，2019+ 口径）
  lowvol_60     60 日低波
  near_high_250 接近 52 周高点（唯一 120 日转正）
  mom_20        20 日反转
  mom_120       120 日反转
（rps_120 与 mom_120 同式，剔除；new_high_250 各口径均负，剔除）

诚实披露：
  - turn_low 的 +15.95% 是私有主系统（2010-2026, 18.7M 行）实证；本仓库只有 2019+ 8.4M 行，
    故这里重算的 icir 是「本仓库数据口径」，不等于主系统数字。
  - 本脚本只做「第一层（截面 ICIR + 方向）」；完整「第二层组合层裁决」用 factors/combo_validate.py
    单因子跑。兜底因子 status 按 icir120 阈值标 有效/衰减，供 scan.py 有效性加权参考。

用法：
  python factors/bootstrap_pool.py [--panel-db data/cache/bars.db] [--min-icir120 0.3]
"""
import argparse
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

from factors.import_qf_pool import load_panel, cross_sectional_ics, forward_returns
from factors.factor_engine import FACTOR_FUNCS
from factors.factor_pool_writer import write_pool
from factors.combo_validate import _rolling_icir


def _turn_low_signal(panel: pd.DataFrame) -> pd.DataFrame:
    """低换手防守：20 日均换手（原始值，方向 -1 = 值越小越好），返回 date × code DataFrame。"""
    turn = panel["turn"].unstack()
    t20 = turn.rolling(20, min_periods=20).mean()
    return t20


# 内置因子清单：名称 / 信号函数(panel→date×code 原始值) / 方向 / 中文名 / category / usage
# ★因子名对齐主系统消费端：turn_low→turnover（live_api「防守主力参考」读 turnover_rank）、
#   mom_20→reversal20（scan「五强」读 reversal20_rank）；lowvol_60 保留后缀（60日≠主系统 lowvol 窗口）
BUILTIN = [
    ("turnover", _turn_low_signal, -1, "低换手防守", "量价", "防守主力"),
    ("lowvol_60", lambda p: FACTOR_FUNCS["lowvol_60"](p["close"].unstack()), -1, "60日低波", "反转", "防守"),
    ("near_high_250", lambda p: FACTOR_FUNCS["near_high_250"](p["close"].unstack()), 1, "接近52周高点", "动量", "趋势"),
    ("reversal20", lambda p: FACTOR_FUNCS["mom_20"](p["close"].unstack()), -1, "20日反转", "反转", "反转"),
    ("mom_120", lambda p: FACTOR_FUNCS["mom_120"](p["close"].unstack()), -1, "120日反转", "反转", "反转"),
]


def main():
    ap = argparse.ArgumentParser(description="内置因子落三件套（因子池兜底）")
    ap.add_argument("--panel-db", default="data/cache/bars.db")
    ap.add_argument("--min-icir120", type=float, default=0.3, help="icir120 达标线（≥=有效，< =衰减）")
    args = ap.parse_args()

    print("加载面板（bars.db 全量）...", flush=True)
    panel = load_panel(args.panel_db, start="2019-01-01")
    fwd = forward_returns(panel)
    print(f"面板 {panel.shape}", flush=True)

    factors = []
    for name, fn, sign, cn, cat, usage in BUILTIN:
        try:
            raw = fn(panel).astype(float)                 # date × code 原始值
            sig = (raw * sign).stack().reindex(panel.index)  # 方向化 → (date, code)
            score = (raw * sign).rank(axis=1, pct=True)   # 逐日截面 rank 0-1
            latest_rank = score.iloc[-1].dropna()

            ics = cross_sectional_ics(sig, fwd)
            icir20 = _rolling_icir(ics, 20)
            icir60 = _rolling_icir(ics, 60)
            icir120 = _rolling_icir(ics, 120)
            status = "有效" if (icir120 or 0) >= args.min_icir120 else "衰减"

            factors.append({
                "code": name, "name_cn": cn, "category": cat,
                "direction": sign, "status": status, "usage": usage,
                "icir_20": icir20, "icir_60": icir60, "icir_120": icir120,
                "rank": latest_rank,
            })
            print(f"  {name:<14s} dir={sign:+d} icir20={icir20} icir60={icir60} "
                  f"icir120={icir120} → {status}", flush=True)
        except Exception as e:
            print(f"  {name:<14s} 失败: {e}", flush=True)

    if not factors:
        print("❌ 无可用内置因子")
        sys.exit(2)

    data_date = str(panel.index.get_level_values(0).max())[:10]
    print(f"\n写入三件套（数据日 {data_date}）→ data/factorpool/output/", flush=True)
    paths = write_pool(factors, data_date=data_date)
    print("=== 三件套已写入 ===")
    for k, v in paths.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
