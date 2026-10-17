# -*- coding: utf-8 -*-
"""risk/dedup_by_returns.py —— 因子去重（用回测档案的逐日收益相关性）

思路：两个因子如果「组合层净值曲线」高度相关，说明提供的是**同一份信息**，不该都留在池子里。
     用档案里的日收益序列算 Pearson 相关，比用原始因子值更贴近"最终用处"。
判定：|ρ| ≥ 0.7 → 视为重复，保留其中全期年化更高者。

用法：python risk/dedup_by_returns.py [--thresh 0.7]
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--thresh", type=float, default=0.7)
    ap.add_argument("--only", default="", help="逗号分隔 name 子串，只在这些因子里去重")
    args = ap.parse_args()
    only = [x.strip() for x in args.only.split(",") if x.strip()]

    data = {}
    for f in sorted(ARCH.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        name = d.get("name") or ""
        if only and not any(k in name for k in only):
            continue
        rets = d.get("returns") or []
        if len(rets) < 400:
            continue
        data[name] = {
            "series": {r["date"]: r["ret"] for r in rets},
            "ann": (d.get("metrics") or {}).get("annual_return"),
            "sharpe": (d.get("metrics") or {}).get("sharpe"),
            "verdict": d.get("verdict"),
        }
    print(f"可比档案 {len(data)} 个\n")
    names = list(data)
    pairs = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            sa, sb = data[a]["series"], data[b]["series"]
            common = sorted(set(sa) & set(sb))
            if len(common) < 300:
                continue
            x = np.array([sa[d] for d in common])
            y = np.array([sb[d] for d in common])
            rho = float(np.corrcoef(x, y)[0, 1])
            pairs.append((abs(rho), rho, a, b, len(common)))

    pairs.sort(reverse=True)
    print(f"{'因子A':24s}{'因子B':24s}{'ρ':>8s}{'共同天数':>9s}")
    print("=" * 68)
    dup = []
    for ar, rho, a, b, n in pairs:
        if ar >= args.thresh:
            dup.append((a, b, rho))
            print(f"{a[:23]:24s}{b[:23]:24s}{rho:>8.3f}{n:>9,}  ⚠️重复")

    # 贪心保留：按全期年化降序，丢弃与已保留者 |ρ|≥阈值 的因子
    ranked = sorted(data, key=lambda k: -(data[k]["ann"] or -9))
    keep, drop = [], []
    for k in ranked:
        clash = None
        for kk in keep:
            for ar, rho, a, b, n in pairs:
                if ar >= args.thresh and {a, b} == {k, kk}:   # ★必须过阈值才算冲突
                    clash = (kk, rho)
                    break
            if clash:
                break
        if clash:
            drop.append((k, clash[0], clash[1]))
        else:
            keep.append(k)

    print("\n" + "=" * 68)
    print(f"保留 {len(keep)} 个（按全期年化降序，剔除 |ρ|≥{args.thresh} 的重复）:")
    for k in keep:
        print(f"  ✅ {k:26s} 年化 {data[k]['ann']:>7.2%} 夏普 {data[k]['sharpe']:>5.2f} ({data[k]['verdict']})")
    if drop:
        print(f"\n剔除 {len(drop)} 个:")
        for k, kk, rho in drop:
            print(f"  ✂️ {k:26s} 与 {kk} ρ={rho:+.3f}")

    out = BASE / "logs" / "dedup_by_returns.json"
    out.write_text(json.dumps({"keep": keep, "drop": drop,
                               "pairs": [{"a": a, "b": b, "rho": r} for _, r, a, b, _ in pairs[:60]]},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已存：{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
