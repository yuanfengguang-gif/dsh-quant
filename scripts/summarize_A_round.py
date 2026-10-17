# -*- coding: utf-8 -*-
"""scripts/summarize_A_round.py —— 汇总轨道 A（2016+ 锁定口径）的四项结果

读取：
  reports/rebuild36_strict_2016.json
  reports/a3_candidates_2016.json
  reports/dedup_candidates_2016.json
输出：
  reports/A_round_2016_summary.json + 控制台表格

用法：python scripts/summarize_A_round.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent.parent
R = BASE / "reports"


def load(name):
    p = R / name
    if not p.exists():
        print(f"缺失：{p}")
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    rb = load("rebuild36_strict_2016.json")
    cd = load("a3_candidates_2016.json")
    dd = load("dedup_candidates_2016.json")
    if not rb:
        return 1

    core = [x for x in rb["rows"] if x.get("因子") != "combo_z"]
    valid = [x for x in core if x.get("结论") == "有效"]
    watch = [x for x in core if x.get("结论") == "观察"]
    invalid = [x for x in core if x.get("结论") == "无效"]
    errored = [x for x in core if str(x.get("结论", "")).startswith("失败")]

    print("=" * 78)
    print("A2）36 因子在 2016+ 锁定口径下的结果")
    print("=" * 78)
    print(f"  样本 {len(core)} 个：有效 {len(valid)} / 观察 {len(watch)} / 无效 {len(invalid)} / 失败 {len(errored)}")
    print(f"  有效名单：{[x['因子'] for x in valid]}")
    if watch:
        print(f"  观察名单：{[x['因子'] for x in watch]}")

    print("\n" + "=" * 78)
    print("A3）三个原入池因子")
    print("=" * 78)
    pool3 = ["bp_value", "turn_mid_prox", "margin_chg_20"]
    rows3 = []
    for name in pool3:
        x = next((r for r in core if r.get("因子") == name), None)
        if not x:
            rows3.append({"因子": name, "状态": "缺失"})
            continue
        seg1, seg2 = x.get("2016-2020"), x.get("2021-2026")
        ok = (x["净超额"] > 0 and x["夏普"] >= 0.5 and (seg1 or 0) > 0 and (seg2 or 0) > 0)
        rows3.append({
            "因子": name, "结论": x["结论"], "年化": x["年化"], "净超额": x["净超额"],
            "夏普": x["夏普"], "回撤": x["回撤"], "Calmar": x["Calmar"],
            "回撤天数": x["回撤天数"], "2016-2020": seg1, "2021-2026": seg2,
            "闸门": x["闸门"], "达标": bool(ok),
        })
        print(f"  {name:<16s} {x['结论']:<3s} 年化 {x['年化']:+.2%} 超额 {x['净超额']:+.2%} "
              f"夏普 {x['夏普']:.3f} 回撤 {x['回撤']:.1%} Calmar {x['Calmar']} "
              f"三段 {seg1:.1%}/{seg2:.1%} 归因 {'达标' if ok else '不达标'}")

    combo = rb.get("combo_z")
    if combo:
        print("\n  [A1 参照] combo_z（2因子合成）同口径："
              f"年化 {combo['年化']:+.2%} 超额 {combo['净超额']:+.2%} "
              f"夏普 {combo['夏普']:.3f} 回撤 {combo['回撤']:.1%} Calmar {combo['Calmar']}")

    print("\n" + "=" * 78)
    print("A4）A3 五条候选 vs 新池 |ρ| 去重")
    print("=" * 78)
    a4 = (dd or {}).get("rows", [])
    for row in a4:
        if row.get("状态"):
            print(f"  {row['候选']:<18s} {row['状态']}")
        else:
            print(f"  {row['候选']:<18s} max|ρ|={row['max_abs_rho']:.3f} vs {row['对方因子']:<18s} "
                  f"→ {row['判定']}")

    out = {
        "window": "2016-01-01 ~ 2026-10-16",
        "standard": rb.get("standard"),
        "A2": {"n_total": len(core), "n_valid": len(valid),
               "valid_names": [x["因子"] for x in valid],
               "watch_names": [x["因子"] for x in watch],
               "invalid_names": [x["因子"] for x in invalid],
               "errored": [x["因子"] for x in errored]},
        "A3": rows3,
        "combo_z": combo,
        "A4": a4,
    }
    p = R / "A_round_2016_summary.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n汇总已存：{p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
