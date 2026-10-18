# -*- coding: utf-8 -*-
"""scripts/pm/audit_citations.py —— 数字溯源校验器（防"美化/编造"的核心机制）

原理：
  要求实现方报告中**每个数字都带出处标注**：
      −1.59%  [src: p0_cost_gate_strict.json#runs."bp_value@2016".metrics.net_excess]
  本脚本解析报告里所有 [src: 文件#路径] 标注，回到 JSON 里取值比对：
      · 数值对不上 → FAIL（可能美化、可能手抄错）
      · 路径不存在 → FAIL（可能编造）
      · 全部对上   → PASS

  这样"编一个好看的数"在物理上不可能——因为那个数必须在 JSON 里真实存在。

用法：
    python scripts/pm/audit_citations.py reports/R3-0_演习报告.md
    python scripts/pm/audit_citations.py reports/*.md --tol 1e-3
    python scripts/pm/audit_citations.py --list          # 只列出所有引用

标注语法：
    [src: <相对 reports/ 或项目根的 json 文件名>#<路径>]
    路径支持：a.b.c / a."带空格的键".c / a[0].b

退出码：0 = 全部可核；1 = 有对不上/找不到
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent.parent.parent

# [src: file.json#path.to.value]
CITE_RE = re.compile(r"\[src:\s*([^#\]]+?)\s*#\s*([^\]]+?)\s*\]")
# 数字（含可选千分位、百分号、负号、科学计数）
NUM_RE = re.compile(r"[-+]?\d[\d,]*\.?\d*(?:[eE][-+]?\d+)?%?")


TOKEN_RE = re.compile(r'"([^"]*)"|\[(\d+)\]|([^.\[\]"]+)')


def resolve_path(obj, path: str):
    """按 a.b."c d".e / a[0].b 解析 JSON 路径（正则分词，支持引号键/数组索引）"""
    cur = obj
    for m in TOKEN_RE.finditer(path):
        quoted, index, plain = m.group(1), m.group(2), m.group(3)
        if quoted is not None:
            key = quoted
        elif index is not None:
            i = int(index)
            if not isinstance(cur, list) or i >= len(cur):
                raise KeyError(f"索引 {i} 越界或非数组")
            cur = cur[i]
            continue
        else:
            key = plain.strip()
            if not key:
                continue
        if isinstance(cur, list):
            raise KeyError(f"期望对象但遇到数组，键 {key!r}")
        if key not in cur:
            raise KeyError(f"键 {key!r} 不存在")
        cur = cur[key]
    return cur


def parse_number(s: str):
    s = s.strip().rstrip("%").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def find_json(name: str, md_dir: Path) -> Path | None:
    """在若干候选位置找 JSON"""
    cands = [md_dir / name, BASE / "reports" / name, BASE / "logs" / name, BASE / name]
    for c in cands:
        if c.is_file():
            return c
    return None


def audit(md: Path, tol: float, list_only: bool) -> tuple[int, int, int]:
    text = md.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    ok = bad = 0
    cache: dict[Path, dict] = {}
    print(f"\n{'=' * 100}\n校验: {md.relative_to(BASE) if md.is_relative_to(BASE) else md}\n{'=' * 100}")
    print(f"  {'行':>5s}  {'报告值':>16s}  {'JSON值':>16s}  出处")
    print("  " + "-" * 96)
    for ln, line in enumerate(lines, 1):
        for m in CITE_RE.finditer(line):
            jname, jpath = m.group(1).strip(), m.group(2).strip()
            jf = find_json(jname, md.parent)
            if jf is None:
                print(f"  {ln:>5d}  {'—':>16s}  {'—':>16s}  ❌ 找不到文件 {jname}")
                bad += 1
                continue
            if jf not in cache:
                try:
                    cache[jf] = json.loads(jf.read_text(encoding="utf-8"))
                except Exception as e:
                    print(f"  {ln:>5d}  {'—':>16s}  {'—':>16s}  ❌ JSON 解析失败 {jf.name}: {e}")
                    bad += 1
                    cache[jf] = {}
            try:
                actual = resolve_path(cache[jf], jpath)
            except Exception as e:
                print(f"  {ln:>5d}  {'—':>16s}  {'—':>16s}  ❌ 路径错 {jpath}: {e}")
                bad += 1
                continue

            if list_only:
                print(f"  {ln:>5d}  {'—':>16s}  {str(actual)[:16]:>16s}  {jf.name}#{jpath}")
                continue

            # 从「引用之前的文字」里取最后一个数字作为报告值
            prefix = line[:m.start()]
            nums = NUM_RE.findall(prefix)
            claimed = parse_number(nums[-1]) if nums else None
            if claimed is None or not isinstance(actual, (int, float)):
                print(f"  {ln:>5d}  {'(无数值)':>16s}  {str(actual)[:16]:>16s}  {jf.name}#{jpath}")
                ok += 1
                continue
            # 百分比：报告 −1.59% vs JSON −0.0159
            a, c = float(actual), claimed
            if abs(a) < 1.5 and abs(c) > 1.5:
                c = c / 100.0
            diff = abs(a - c)
            if diff <= tol:
                ok += 1
                print(f"  {ln:>5d}  {claimed:>16.6g}  {a:>16.6g}  ✅ {jf.name}#{jpath}")
            else:
                bad += 1
                print(f"  {ln:>5d}  {claimed:>16.6g}  {a:>16.6g}  ❌ 差 {diff:.3g}  {jf.name}#{jpath}")
    return ok, bad, 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--tol", type=float, default=1e-3, help="容差（默认 1e-3）")
    ap.add_argument("--list", action="store_true", help="只列出引用不比对")
    args = ap.parse_args()

    total_ok = total_bad = 0
    for f in args.files:
        p = Path(f) if Path(f).is_absolute() else (BASE / f)
        if not p.is_file():
            print(f"[SKIP] 不存在: {f}")
            continue
        o, b, _ = audit(p, args.tol, args.list)
        total_ok += o
        total_bad += b

    print("\n" + "=" * 100)
    if total_ok + total_bad == 0:
        print("⚠️ 没有找到任何 [src: ...] 标注 —— 按纪律 R11 视为不合规")
        return 1
    print(f"可核 {total_ok} 项 | 对不上/找不到 {total_bad} 项")
    print("结论：" + ("✅ 全部数字可溯源" if total_bad == 0 else "❌ 有数字无法溯源，报告不可信"))
    return 0 if total_bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
