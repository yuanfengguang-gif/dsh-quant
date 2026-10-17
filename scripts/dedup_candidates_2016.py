# -*- coding: utf-8 -*-
"""scripts/dedup_candidates_2016.py —— A3 候选 vs 新池的收益相关性去重（2016+ 锁定口径）

读 output/backtest_archive/*_strict_t20_*.json 里的逐日收益，算 Pearson ρ：
  · 对每个候选，报与「新池其它因子」的最大 |ρ| 及对方名字
  · |ρ| ≥ 0.7 → 判重复（与 §5.1 第③条一致）

用法：python scripts/dedup_candidates_2016.py
产物：reports/dedup_candidates_2016.json
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np

BASE = Path(__file__).resolve().parent.parent
ARCH = BASE / "output" / "backtest_archive"
CANDIDATES = ["B4_BP+sue", "B1_EP+BP", "B4_BP*accel+rev", "C5_max3_vol", "C1_turn+volchg"]
THRESH = 0.7


def main() -> int:
    series, meta = {}, {}
    for f in sorted(ARCH.glob("*_strict_t20_*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        params = d.get("params") or {}
        factors = params.get("factors") or []
        name = factors[0] if factors else d.get("name")
        rets = {r["date"]: float(r["ret"]) for r in (d.get("returns") or [])}
        if len(rets) < 300:
            continue
        # 同因子多次归档时保留最后一份（时间戳最新）
        series[name] = rets
        meta[name] = {"file": f.name, "verdict": d.get("verdict"),
                      "annual": (d.get("metrics") or {}).get("annual_return")}

    pool = [n for n in series if n not in CANDIDATES]
    print(f"档案因子 {len(series)} 个（池 {len(pool)}，候选 {len([n for n in series if n in CANDIDATES])}）\n")

    rows = []
    for c in CANDIDATES:
        if c not in series:
            rows.append({"候选": c, "状态": "无档案"})
            print(f"  {c:<18s} 无档案")
            continue
        best = (0.0, None)
        for p in pool:
            common = sorted(set(series[c]) & set(series[p]))
            if len(common) < 300:
                continue
            x = np.array([series[c][d] for d in common])
            y = np.array([series[p][d] for d in common])
            rho = float(np.corrcoef(x, y)[0, 1])
            if abs(rho) > abs(best[0]):
                best = (rho, p)
        rows.append({
            "候选": c, "max_abs_rho": round(abs(best[0]), 3), "rho": round(best[0], 3),
            "对方因子": best[1], "判定": ("重复" if abs(best[0]) >= THRESH else "不重复"),
            "候选年化": meta[c]["annual"], "候选结论": meta[c]["verdict"],
        })
        print(f"  {c:<18s} max|ρ|={abs(best[0]):.3f} vs {best[1]:<20s} "
              f"→ {'重复' if abs(best[0]) >= THRESH else '不重复'}")

    out = {"generated_at": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "threshold": THRESH, "n_pool": len(pool), "rows": rows}
    rp = BASE / "reports" / "dedup_candidates_2016.json"
    rp.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n结果已存：{rp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
