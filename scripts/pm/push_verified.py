# -*- coding: utf-8 -*-
"""scripts/pm/push_verified.py —— PM 专用：提交 + 推送 + 自检（一条命令）

设计原则：**push 命令返回 0 不等于远端已更新**。
本机已发生过一次漏推（commit 62fe820），所以推送必须"推完再验"。

做的事：
    1) 可选：git add -A + commit -m
    2) git push origin master（失败自动重试，默认 4 次）
    3) git fetch origin
    4) 比对 git rev-parse HEAD 与 origin/master
    5) 输出表格；hash 不一致则列出未推送提交并返回退出码 1

用法：
    python scripts/pm/push_verified.py -m "提交说明"     # 提交+推送+自检
    python scripts/pm/push_verified.py --verify-only     # 只自检（不提交不推送）
    python scripts/pm/push_verified.py --remote origin --branch master
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent.parent.parent


def git(*args: str, timeout: int = 300) -> tuple[int, str]:
    r = subprocess.run(["git"] + list(args), cwd=BASE, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=timeout)
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    return r.returncode, (out + ("\n" + err if err else "")).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-m", "--message", default=None, help="提交说明（给了就 add+commit）")
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--branch", default="master")
    ap.add_argument("--retries", type=int, default=4)
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()

    rows = []

    def add(step: str, status: str, detail: str):
        rows.append((step, status, detail))

    # ---------- 1) 提交 ----------
    if args.message and not args.verify_only:
        git("add", "-A")
        rc, out = git("status", "--porcelain")
        if not out:
            add("提交", "SKIP", "无改动可提交")
        else:
            rc, out = git("commit", "-m", args.message)
            short = ""
            for line in out.splitlines():
                if "files changed" in line or "file changed" in line:
                    short = line.strip()
                    break
            add("提交", "OK" if rc == 0 else "FAIL", short or out.splitlines()[0][:80] if out else "")

    # ---------- 2) 推送 ----------
    if not args.verify_only:
        ok = False
        last_err = ""
        for i in range(1, args.retries + 1):
            rc, out = git("push", args.remote, args.branch, timeout=600)
            if rc == 0:
                ok = True
                add("推送", "OK", f"第 {i} 次成功")
                break
            last_err = out.splitlines()[-1][:90] if out else "unknown"
            time.sleep(4)
        if not ok:
            add("推送", "FAIL", f"{args.retries} 次均失败：{last_err}")

    # ---------- 3) 自检：主判据用 ls-remote（不下载对象，抗网络抖动）----------
    rc_l, local = git("rev-parse", "HEAD")
    local = local.strip()

    remote = ""
    ls_err = ""
    for attempt in range(3):
        rc, out = git("ls-remote", args.remote, f"refs/heads/{args.branch}", timeout=90)
        if rc == 0 and out:
            remote = out.split()[0]
            break
        ls_err = (out or "").splitlines()[-1][:90] if out else "empty"
        time.sleep(3)

    if not remote:
        add("自检", "FAIL", f"ls-remote 三次失败：{ls_err}")
    elif local == remote:
        add("自检", "OK", f"远端 {remote[:8]} == 本地")
    else:
        add("自检", "FAIL", f"本地 {local[:8]} ≠ 远端 {remote[:8]}")

    # 辅助：ahead/behind（需 fetch，失败不致命）
    ahead = behind = ""
    fetched = False
    try:
        rc_f, _ = git("fetch", args.remote, "--quiet", timeout=120)
        fetched = (rc_f == 0)
    except Exception:
        fetched = False
    if fetched:
        rc, out = git("rev-list", "--left-right", "--count", f"{args.remote}/{args.branch}...HEAD")
        if rc == 0 and out:
            behind, ahead = (out.split() + ["", ""])[:2]
            add("差距", "OK" if (ahead == "0" and behind == "0") else "FAIL",
                f"远端领先 {behind} / 本地领先 {ahead}")
        unpushed: list[str] = []
        rc, out = git("log", "--oneline", f"{args.remote}/{args.branch}..HEAD")
        if rc == 0 and out:
            unpushed = out.splitlines()
            add("未推送提交", "FAIL", f"{len(unpushed)} 个")
        else:
            add("未推送提交", "OK", "无")
    else:
        add("差距", "SKIP", "fetch 超时/失败，已用 ls-remote 代替主判据")
        unpushed = []

    # ---------- 输出 ----------
    print("=" * 92)
    print(f"推送自检  本地={local[:8]}  远端={remote[:8]}  分支={args.remote}/{args.branch}")
    print("=" * 92)
    print(f"  {'步骤':12s}{'状态':8s}说明")
    print("  " + "-" * 86)
    bad = 0
    for step, status, detail in rows:
        icon = {"OK": "✅", "FAIL": "❌", "SKIP": "—"}.get(status, "?")
        if status == "FAIL":
            bad += 1
        print(f"  {step:12s}{icon} {status:6s}{detail}")
    if unpushed:
        print("\n  未推送的提交：")
        for line in unpushed[:10]:
            print("    " + line)
    print("=" * 92)
    if bad == 0:
        print("✅ 推送完整：远端与本地一致")
        return 0
    print("❌ 推送不完整 —— 不要对外声称已完成")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
