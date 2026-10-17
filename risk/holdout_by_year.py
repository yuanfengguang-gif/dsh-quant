# -*- coding: utf-8 -*-
"""risk/holdout_by_year.py —— 分年度 holdout 检验（用回测档案里的逐日收益）

为什么需要：页面上的「有效」只是全期净超额>0 且夏普≥0.5 的筛选阈值。
真正的稳健性要看**分年度**：三段（2010-2015 / 2016-2020 / 2021-2026）是否同号。

数据来源：output/backtest_archive/*.json 里的 `returns`（逐日）与 `benchmark`
          —— 不需要重新加载面板，秒级完成。

用法：python risk/holdout_by_year.py [--min-days 200]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent.parent
ARCH = BASE / "output" / "backtest_archive"

SEGMENTS = [("2010-2015", 2010, 2015), ("2016-2020", 2016, 2020), ("2021-2026", 2021, 2026)]


def ann(arr):
    if len(arr) < 20:
        return None
    nav = float(np.prod(1.0 + arr))
    yrs = len(arr) / 252.0
    return nav ** (1.0 / yrs) - 1.0 if yrs > 0 else None


def sharpe(arr):
    if len(arr) < 20:
        return None
    sd = float(np.std(arr, ddof=1))
    return float(np.mean(arr) / sd * np.sqrt(252)) if sd > 0 else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-days", type=int, default=200)
    args = ap.parse_args()

    files = sorted(ARCH.glob("*.json"))
    print(f"档案 {len(files)} 个\n")
    rows = []
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        rets = d.get("returns") or []
        if len(rets) < args.min_days:
            continue
        dates = [r["date"] for r in rets]
        r = np.array([r["ret"] for r in rets], dtype=float)
        yrs = np.array([int(x[:4]) for x in dates])
        seg = {}
        for label, a, b in SEGMENTS:
            m = (yrs >= a) & (yrs <= b)
            seg[label] = ann(r[m]) if m.sum() >= 100 else None
        vals = [v for v in seg.values() if v is not None]
        pos = sum(1 for v in vals if v > 0)
        rows.append({
            "name": d.get("name"), "verdict": d.get("verdict"),
            "ann_all": ann(r), "sharpe_all": sharpe(r),
            "seg": seg, "n_ok": pos, "n_seg": len(vals),
            "all_pos": (pos == len(vals) and len(vals) == 3),
            "years": f"{dates[0][:4]}-{dates[-1][:4]}",
        })

    print(f"{'因子':22s}{'档案判定':8s}{'全期年化':>9s}{'夏普':>7s}"
          f"{'2010-15':>10s}{'2016-20':>10s}{'2021-26':>10s}  三段同号")
    print("=" * 96)
    for r in sorted(rows, key=lambda x: -(x["ann_all"] or -9)):
        s = r["seg"]
        def f(v):
            return f"{v:>9.1%}" if v is not None else f"{'—':>9s}"
        mark = "✅" if r["all_pos"] else ("⚠️" if r["n_ok"] >= 2 else "❌")
        print(f"{str(r['name'])[:21]:22s}{str(r['verdict']):8s}{f(r['ann_all'])}"
              f"{r['sharpe_all'] if r['sharpe_all'] is None else round(r['sharpe_all'],2):>7}"
              f"{f(s['2010-2015'])}{f(s['2016-2020'])}{f(s['2021-2026'])}  "
              f"{mark} {r['n_ok']}/{r['n_seg']}  ({r['years']})")

    solid = [r for r in rows if r["all_pos"]]
    print("\n" + "=" * 96)
    print(f"三段全部为正（真·稳健）: {len(solid)} 个")
    for r in solid:
        print(f"  ✅ {r['name']}: 全期 {r['ann_all']:.1%}/夏普 {r['sharpe_all']:.2f}")

    out = BASE / "logs" / "holdout_by_year.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n结果已存：{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
