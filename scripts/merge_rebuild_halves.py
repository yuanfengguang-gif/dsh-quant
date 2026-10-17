# -*- coding: utf-8 -*-
"""scripts/merge_rebuild_halves.py —— 合并两半重建结果

读取 reports/rebuild36_strict_2016_half1.json 与 _half2.json，
合并 rows、去重（同因子取一条）、重算有效/观察/无效计数，
输出 reports/rebuild36_strict_2016.json（供 summarize_A_round.py 使用）。
"""
from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
R = BASE / "reports"


def main() -> int:
    rows, combo = [], None
    for name in ("rebuild36_strict_2016_half1.json", "rebuild36_strict_2016_half2.json"):
        p = R / name
        if not p.exists():
            print(f"缺失 {p}")
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        rows.extend(d.get("rows") or [])
        if d.get("combo_z"):
            combo = d["combo_z"]

    seen, merged = set(), []
    for r in rows:
        key = r.get("因子")
        if key in seen:
            continue
        seen.add(key)
        merged.append(r)

    core = [r for r in merged if r.get("因子") != "combo_z"]
    valid = [r for r in core if r.get("结论") == "有效"]
    watch = [r for r in core if r.get("结论") == "观察"]
    invalid = [r for r in core if r.get("结论") == "无效"]
    errored = [r for r in core if str(r.get("结论", "")).startswith("失败")]

    out = {
        "standard": (json.loads((R / "rebuild36_strict_2016_half1.json").read_text(encoding="utf-8")).get("standard")
                     if (R / "rebuild36_strict_2016_half1.json").exists() else {}),
        "n_total": len(core), "n_evaluated": len(valid) + len(watch) + len(invalid),
        "n_valid": len(valid), "valid_names": [r["因子"] for r in valid],
        "invalid_names": [r["因子"] for r in invalid],
        "errored": [r["因子"] for r in errored],
        "combo_z": combo,
        "rows": merged,
    }
    p = R / "rebuild36_strict_2016.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"合并 {len(merged)} 条（其中 combo_z={'有' if combo else '无'}）→ {p}")
    print(f"有效 {len(valid)}：{[r['因子'] for r in valid]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
