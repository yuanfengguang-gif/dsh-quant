# -*- coding: utf-8 -*-
"""scripts/merge_candidates.py —— 合并候选主结果与补跑结果"""
from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
R = BASE / "reports"


def main() -> int:
    merged = {}
    for name in ("a3_candidates_2016.json", "a3_candidates_2016_retry.json"):
        p = R / name
        if p.exists():
            for r in json.loads(p.read_text(encoding="utf-8")).get("rows") or []:
                k = r.get("因子")
                failed = str(r.get("结论", "")).startswith("失败")
                prev = merged.get(k)
                if prev is None or not failed or str(prev.get("结论", "")).startswith("失败"):
                    merged[k] = r
    merged = list(merged.values())
    p = R / "a3_candidates_2016.json"
    p.write_text(json.dumps({"rows": merged}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"候选合并 {len(merged)} 条 → {p}")
    for r in merged:
        print(f"  {r['因子']:<18s} {r.get('结论')} 年化 {r.get('年化', 0):+.2%} 夏普 {r.get('夏普', 0):.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
