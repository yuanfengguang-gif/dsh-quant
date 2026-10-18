# -*- coding: utf-8 -*-
"""scripts/pm/check_delivery.py —— 交付台账校验器（PM 侧）

设计目标：**不依赖对方的自报**，直接检查 GitHub 远端（origin/master）的真实内容。

检查方式全部走 git plumbing，读的是**远端树**而不是工作区：
    git fetch origin
    git rev-parse origin/master                    → 远端 HEAD
    git merge-base --is-ancestor <hash> origin/master → 某提交是否已在远端
    git cat-file -e  origin/master:<path>          → 文件是否在远端
    git cat-file -s  origin/master:<path>          → 远端文件字节数
    git show origin/master:<path>                  → 远端文件内容（做关键词检查）

用法：
    python scripts/pm/check_delivery.py                 # 查全部轮次
    python scripts/pm/check_delivery.py --round R2      # 只查某轮
    python scripts/pm/check_delivery.py --watch 300     # 每 5 分钟查一次（等对方推送）

退出码：0 = 该轮全部通过；1 = 有缺失
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent.parent.parent
MANIFEST = BASE / "reports" / "delivery_manifest.json"


def git(*args: str) -> tuple[int, str]:
    r = subprocess.run(["git"] + list(args), cwd=BASE, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "").strip()


def remote_head() -> str:
    git("fetch", "origin", "--quiet")
    rc, out = git("rev-parse", "origin/master")
    return out if rc == 0 else ""


def file_in_remote(path: str) -> tuple[bool, int, str]:
    """返回 (存在, 字节数, sha256)；全部基于远端树"""
    rc, _ = git("cat-file", "-e", f"origin/master:{path}")
    if rc != 0:
        return False, 0, ""
    rc, size = git("cat-file", "-s", f"origin/master:{path}")
    rc2, content = git("show", f"origin/master:{path}")
    sha = hashlib.sha256(content.encode("utf-8", "replace")).hexdigest()[:16]
    return True, int(size or 0), sha


def file_in_worktree(path: str) -> tuple[bool, int]:
    p = BASE / path
    if not p.is_file():
        return False, 0
    return True, p.stat().st_size


def check_round(rnd: dict, head: str, manifest: dict) -> list[dict]:
    rows = []
    # 1) must_commits
    for h in rnd.get("must_commits") or []:
        rc, _ = git("merge-base", "--is-ancestor", h, "origin/master")
        rows.append({"kind": "commit", "item": h,
                     "status": "OK" if rc == 0 else "MISSING",
                     "detail": "已在远端历史中" if rc == 0 else "不在远端历史中"})

    # 2) files
    for f in rnd.get("files") or []:
        if isinstance(f, str):
            f = {"path": f}
        path = f["path"]
        min_b = f.get("min_bytes", 1)
        exists, size, sha = file_in_remote(path)
        if not exists:
            w_exists, w_size = file_in_worktree(path)
            rows.append({"kind": "file", "item": path, "status": "MISSING",
                         "detail": f"远端无（本地{'有 ' + str(w_size) + 'B' if w_exists else '也没有'}）"})
        elif size < min_b:
            rows.append({"kind": "file", "item": path, "status": "TOO_SMALL",
                         "detail": f"{size}B < 期望≥{min_b}B"})
        else:
            rows.append({"kind": "file", "item": path, "status": "OK",
                         "detail": f"{size}B sha={sha}"})
    return rows


def check_content(content_checks: list[dict], round_name: str) -> list[dict]:
    rows = []
    for c in content_checks:
        if c.get("round") != round_name:
            continue
        path = c["path"]
        rc, content = git("show", f"origin/master:{path}")
        if rc != 0:
            rows.append({"kind": "content", "item": path, "status": "MISSING",
                         "detail": "远端无此文件，跳过内容检查"})
            continue
        missing = [k for k in c.get("must_contain", []) if k not in content]
        if missing:
            rows.append({"kind": "content", "item": path, "status": "FAIL",
                         "detail": f"缺少关键词 {missing}（{c.get('why','')}）"})
        else:
            rows.append({"kind": "content", "item": path, "status": "OK",
                         "detail": f"关键词齐（{c.get('why','')}）"})
    return rows


def check_pm_files(manifest: dict) -> list[dict]:
    """单写者文件是否被实现方篡改：对比远端 vs 本地工作区"""
    rows = []
    for path in manifest.get("pm_owned_files") or []:
        r_exists, r_size, r_sha = file_in_remote(path)
        w_exists, w_size = file_in_worktree(path)
        if not w_exists:
            rows.append({"kind": "pm_owned", "item": path, "status": "SKIP",
                         "detail": "本地不存在，跳过"})
            continue
        # 归一化行尾后再比对（CRLF/LF 差异不算篡改）
        w_text = (BASE / path).read_bytes().decode("utf-8", "replace").replace("\r\n", "\n")
        w_sha = hashlib.sha256(w_text.encode("utf-8")).hexdigest()[:16]
        w_size = len(w_text.encode("utf-8"))
        if not r_exists:
            rows.append({"kind": "pm_owned", "item": path, "status": "NOT_PUSHED",
                         "detail": "本地有但远端无（PM 未推送？）"})
        elif r_sha != w_sha and r_size != w_size:
            rows.append({"kind": "pm_owned", "item": path, "status": "DIFF",
                         "detail": f"远端 {r_size}B/{r_sha} ≠ 本地 {w_size}B/{w_sha}"})
        else:
            rows.append({"kind": "pm_owned", "item": path, "status": "OK",
                         "detail": f"{r_size}B 一致"})
    return rows


def print_table(rows: list[dict], title: str) -> int:
    print(f"\n=== {title} ===")
    if not rows:
        print("  （无项目）")
        return 0
    print(f"  {'类型':10s}{'项目':46s}{'状态':10s}说明")
    print("  " + "-" * 100)
    bad = 0
    for r in rows:
        icon = {"OK": "✅", "MISSING": "❌", "TOO_SMALL": "⚠️", "FAIL": "❌",
                "DIFF": "⚠️", "NOT_PUSHED": "⚠️", "SKIP": "—"}.get(r["status"], "?")
        if r["status"] in ("MISSING", "FAIL"):
            bad += 1
        print(f"  {r['kind']:10s}{r['item'][:45]:46s}{icon} {r['status']:8s}{r['detail']}")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", default=None, help="只查某轮（如 R2）")
    ap.add_argument("--watch", type=int, default=0, help="轮询秒数：每隔 N 秒重查，直到通过")
    args = ap.parse_args()

    if not MANIFEST.exists():
        print(f"[ERROR] 台账不存在: {MANIFEST}")
        return 2
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    deadline = time.time() + args.watch
    attempt = 0
    while True:
        attempt += 1
        head = remote_head()
        print("=" * 104)
        print(f"交付校验  第 {attempt} 次   远端 HEAD = {head[:8] if head else '(读取失败)'}   "
              f"台账更新 {manifest.get('updated')}")
        print("=" * 104)

        total_bad = 0
        rounds = [r for r in manifest["rounds"] if not args.round or r["round"] == args.round]
        for rnd in rounds:
            rows = check_round(rnd, head, manifest)
            rows += check_content(manifest.get("content_checks") or [], rnd["round"])
            total_bad += print_table(rows, f"{rnd['round']}｜{rnd.get('desc','')}（owner={rnd.get('owner')}）")

        total_bad += print_table(check_pm_files(manifest), "单写者文件一致性（PM 所有）")

        print("\n" + "=" * 104)
        if total_bad == 0:
            print("✅ 本轮交付完整，可以进入 PM 判读")
            return 0
        print(f"❌ 有 {total_bad} 项未通过")
        if args.watch and time.time() < deadline:
            print(f"   {args.watch} 秒内每 30 秒重查…（Ctrl+C 退出）")
            time.sleep(30)
            continue
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
