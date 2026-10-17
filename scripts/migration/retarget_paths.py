# -*- coding: utf-8 -*-
"""scripts/migration/retarget_paths.py —— 换机/换路径后批量修正硬编码绝对路径

背景：主项目原有 213 处硬编码 C:\\Users\\Administrator。
  经实测只有「每日运行链 2 行」必须改，其余 57 个文件是一次性分析脚本（改了可复用，不改不影响日常）。
  另有 7 个 Windows 计划任务 XML 含绝对路径，需重写后再导入。

【在【新电脑】上、项目根目录内执行】

  1) 先看会改什么（不写盘）：
     python scripts\\migration\\retarget_paths.py --dry-run ^
         --old-project "C:\\Users\\Administrator\\ DSH 量化交易系统\\deepseek-harness-quant" ^
         --new-project "D:\\Programs\\DSH Projects\\DSH Quant" ^
         --old-home    "C:\\Users\\Administrator" ^
         --new-home    "C:\\Users\\<你的用户名>"

  2) 确认无误后真正执行（自动备份 .bak）：
     ... --apply

  3) 只改每日运行链（最小改动，推荐先这样）：
     ... --apply --only-daily

  4) 同时重写计划任务 XML（输出到 output\\migration\\tasks_fixed\\）：
     ... --apply --rewrite-tasks

注意：
  - 路径里的空格会被自动加引号处理（PowerShell 里原本就有引号的不动）
  - 只会替换文本，不会改动文件结构
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 每日运行链（最小必改集）
DAILY = ["data/run_daily_update.ps1", "data/tdx_daily_update.py"]

SKIP_DIRS = ("node_modules", "__pycache__", ".git", "logs", "output/backtest_archive", "data/tdx_factor")


def iter_files(root: Path):
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in (".py", ".ps1", ".yaml", ".yml", ".json", ".xml"):
            continue
        rel = p.relative_to(root).as_posix()
        if any(k in rel for k in SKIP_DIRS) or rel.startswith("output/migration/tasks"):
            continue
        yield p, rel


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None, help="项目根目录，默认本脚本上两级")
    ap.add_argument("--old-project", required=True)
    ap.add_argument("--new-project", required=True)
    ap.add_argument("--old-home", default=r"C:\Users\Lenovo")
    ap.add_argument("--new-home", default=None)
    ap.add_argument("--only-daily", action="store_true")
    ap.add_argument("--rewrite-tasks", action="store_true")
    ap.add_argument("--dry-run", action="store_true", default=False)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if not (args.dry_run or args.apply):
        print("请显式指定 --dry-run 或 --apply")
        return 2
    root = Path(args.root) if args.root else Path(__file__).resolve().parent.parent.parent

    pairs = [(args.old_project, args.new_project)]
    if args.new_home:
        pairs.append((args.old_home, args.new_home))

    print(f"项目根: {root}")
    print(f"替换规则:")
    for o, n in pairs:
        print(f"  「{o}」\n   → 「{n}」")
    print()

    files = list(iter_files(root))
    if args.only_daily:
        files = [(p, r) for p, r in files if r in DAILY]
        print(f"[only-daily] 只处理 {len(files)} 个文件")

    changed = []
    for p, rel in files:
        try:
            txt = p.read_text(encoding="utf-8", errors="surrogateescape")
        except Exception as e:
            print(f"  [SKIP] {rel}: {str(e)[:50]}")
            continue
        orig = txt
        hits = 0
        for o, n in pairs:
            c = txt.count(o)
            if c:
                txt = txt.replace(o, n)
                hits += c
        if hits:
            changed.append((rel, hits))
            print(f"  [{ 'DRY' if args.dry_run else 'FIX'}] {rel:52s} {hits} 处")
            if args.apply:
                bak = p.with_suffix(p.suffix + ".bak")
                if not bak.exists():
                    shutil.copy2(p, bak)
                p.write_text(txt, encoding="utf-8", errors="surrogateescape")

    print(f"\n合计 {len(changed)} 个文件 / {sum(h for _, h in changed)} 处")

    # 重写计划任务 XML
    if args.rewrite_tasks:
        src = root / "output" / "migration" / "tasks"
        dst = root / "output" / "migration" / "tasks_fixed"
        if not src.is_dir():
            print("\n[tasks] 未找到 output/migration/tasks，跳过")
        else:
            dst.mkdir(parents=True, exist_ok=True)
            n = 0
            for f in src.glob("*.xml"):
                t = f.read_text(encoding="utf-8", errors="replace")
                for o, nn in pairs:
                    t = t.replace(o, nn)
                # Python 解释器路径也可能变
                if args.apply:
                    (dst / f.name).write_text(t, encoding="utf-8")
                n += 1
            print(f"\n[tasks] 已重写 {n} 个 XML → {dst}")
            print("        导入：Get-ChildItem output\\migration\\tasks_fixed\\*.xml | %{ schtasks /create /xml $_.FullName /tn $_.BaseName /f }")

    if changed and args.apply:
        print("\n提示：以上文件已生成 .bak 备份，验证无误后可删除。")
        print("必查：python data\\tdx_daily_update.py --help   （确认 import 正常）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
