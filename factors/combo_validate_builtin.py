# -*- coding: utf-8 -*-
"""factors/combo_validate_builtin.py — 内置因子第二层组合裁决

把仓库内置因子（turn_low / lowvol_60 / near_high_250 / mom_20 / mom_120）逐个跑
第二层（组合层 T+1 裁决，combo_validate_sig），验证它们在「开源仓库 2019+ 数据」下
到底成不成立（不等于私有主系统 2010-2026 的实证数字）。

用法：
  python factors/combo_validate_builtin.py [--topn 20 --rebalance 40 --start 2020-06-01 --end 2025-12-31]
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

from factors.import_qf_pool import load_panel
from factors.bootstrap_pool import BUILTIN
from factors.combo_validate import combo_validate_sig, DEFAULT_TOPN, DEFAULT_REBALANCE, DEFAULT_START, DEFAULT_END


def main():
    ap = argparse.ArgumentParser(description="内置因子第二层组合裁决")
    ap.add_argument("--topn", type=int, default=DEFAULT_TOPN)
    ap.add_argument("--rebalance", default=DEFAULT_REBALANCE)
    ap.add_argument("--start", default=DEFAULT_START)
    ap.add_argument("--end", default=DEFAULT_END)
    ap.add_argument("--panel-db", default="data/cache/bars.db")
    args = ap.parse_args()
    if isinstance(args.rebalance, str) and args.rebalance.isdigit():
        args.rebalance = int(args.rebalance)

    print("加载面板（bars.db 全量）...", flush=True)
    panel = load_panel(args.panel_db, start="2019-01-01")
    print(f"面板 {panel.shape}", flush=True)

    rows = []
    for name, fn, sign, cn, cat, usage in BUILTIN:
        try:
            raw = fn(panel).astype(float)                    # date × code 原始值
            sig = raw.stack().reindex(panel.index)           # (date, code) 原始值
            r = combo_validate_sig(name, sig, panel, topn=args.topn,
                                   rebalance=args.rebalance, start=args.start,
                                   end=args.end, direction=sign)
            m = r["metrics"]
            rows.append({
                "因子": name, "方向": f"{r['direction']:+d}", "结论": r["verdict"],
                "年化": f"{m['annual_return']:+.1%}",
                "净超额": f"{r['excess_annual']:+.2%}",
                "夏普": f"{m['sharpe']:.2f}",
                "回撤": f"{m['max_drawdown']:.1%}",
                "icir120": r["health"]["icir_120"],
                "换手": f"{r['capacity']['turnover']:.0%}",
                "ADV分位": r["capacity"]["adv_pct"],
            })
            print(f"  {name:<14s} 结论={r['verdict']} 年化={m['annual_return']:+.1%} "
                  f"净超额={r['excess_annual']:+.2%} 夏普={m['sharpe']:.2f} "
                  f"icir120={r['health']['icir_120']}", flush=True)
        except Exception as e:
            print(f"  {name:<14s} 失败: {e}", flush=True)

    print("\n=== 内置因子第二层裁决汇总 ===")
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
