# -*- coding: utf-8 -*-
"""factors/baseline_control.py — 方向 2：基线对照（校准三层验证管道）

拿公开因子库（Alpha158/191 代表）+ 主系统已证伪赛道的「已知弱因子」，跑第一层
（截面 |ICIR|≥0.3 门票），确认管道能正确把它们拒掉（校准正确）而不是放行（太松）。
同时放 1 个「已知有效但日频 IC 弱」的防守因子（turn_low），验证第一层的盲区 → 佐证分流规则必要。

用法：python factors/baseline_control.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from factors.import_qf_pool import load_panel, _run_factor, cross_sectional_ics, forward_returns, MIN_ICIR

# 已知弱因子（覆盖主系统已证伪赛道）+ 1 个防守对照
BASELINE = {
    # 真动量（已证伪）
    "momentum_20": "def factor(panel):\n    c=panel['close']\n    return c.groupby(level='code').transform(lambda s: s/s.shift(20)-1)",
    "momentum_60": "def factor(panel):\n    c=panel['close']\n    return c.groupby(level='code').transform(lambda s: s/s.shift(60)-1)",
    # 池内反转（已证伪）
    "reversal_20": "def factor(panel):\n    c=panel['close']\n    return -(c.groupby(level='code').transform(lambda s: s/s.shift(20)-1))",
    # 波动率结构（已证伪）
    "vol_ratio_5_60": "def factor(panel):\n    r=panel['close'].groupby(level='code').pct_change()\n    v5=r.groupby(level='code').transform(lambda s: s.rolling(5).std())\n    v60=r.groupby(level='code').transform(lambda s: s.rolling(60).std())\n    return v5/(v60+1e-9)",
    # 量价背离（已证伪）
    "amt_price_divergence": "def factor(panel):\n    ar=panel['amount'].groupby(level='date').rank(pct=True)\n    rr=panel['pct_chg'].groupby(level='date').rank(pct=True)\n    return ar-rr",
    # 振幅
    "amplitude": "def factor(panel):\n    return (panel['high']-panel['low'])/panel['close'].replace(0, np.nan)",
    # 换手率原始值
    "turnover_raw": "def factor(panel):\n    return panel['turn']",
    # 收益偏度（已证伪）
    "skew_20": "def factor(panel):\n    r=panel['close'].groupby(level='code').pct_change()\n    return r.groupby(level='code').transform(lambda s: s.rolling(20, min_periods=15).skew())",
    # RSI14
    "rsi14": "def factor(panel):\n    d=panel['close'].groupby(level='code').diff()\n    up=d.clip(lower=0).groupby(level='code').transform(lambda s: s.rolling(14).mean())\n    dn=(-d.clip(upper=0)).groupby(level='code').transform(lambda s: s.rolling(14).mean())\n    return up/(up+dn+1e-9)",
    # 放量（已证伪放量回升）
    "volume_ratio_20": "def factor(panel):\n    v=panel['volume']\n    return v/(v.groupby(level='code').transform(lambda s: s.rolling(20).mean())+1e-9)",
    # 开盘跳空
    "gap_open": "def factor(panel):\n    prev=panel['close'].groupby(level='code').shift(1)\n    return panel['open']/prev-1",
    # 日内收益
    "intraday_ret": "def factor(panel):\n    return panel['close']/panel['open']-1",
    # 防守对照（已知组合层有效、日频 IC 弱）
    "turn_low_defensive": "def factor(panel):\n    t=panel['turn'].groupby(level='code').transform(lambda s: s.rolling(20, min_periods=20).mean())\n    return -t",
}


def main():
    print("加载面板...", flush=True)
    panel = load_panel("data/cache/bars.db", start="2019-01-01")
    fwd = forward_returns(panel)
    print(f"面板 {panel.shape}，第一层门槛 |ICIR|≥{MIN_ICIR}", flush=True)

    rows = []
    for name, code in BASELINE.items():
        try:
            sig = _run_factor(code, panel)
            ics = cross_sectional_ics(sig, fwd)
            ic = float(ics.mean())
            ir = float(ic / ics.std()) if ics.std() > 1e-12 else 0.0
            cov = float(sig.notna().mean())
            verdict = "❌拒" if abs(ir) < MIN_ICIR else "⚠️放行"
            rows.append((name, round(ic, 5), round(ir, 3), round(cov, 3), verdict))
            print(f"  {name:<22s} ic={ic:+.5f} icir={ir:+.3f} cov={cov:.2f} {verdict}", flush=True)
        except Exception as e:
            print(f"  {name:<22s} 失败: {str(e)[:80]}", flush=True)

    n_reject = sum(1 for r in rows if r[4] == "❌拒")
    n_pass = sum(1 for r in rows if r[4] == "⚠️放行")
    print(f"\n=== 基线对照：{len(rows)} 个已知弱因子 → 拒绝 {n_reject} / 放行 {n_pass} ===")
    print(f"结论：放行 {n_pass} 个（应为 0，说明管道校准正确；turn_low 放行/拒绝均属预期，见注释）")


if __name__ == "__main__":
    main()
