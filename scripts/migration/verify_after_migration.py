# -*- coding: utf-8 -*-
"""output/migration/verify_after_migration.py —— 新机验收脚本

用法（在新电脑上、项目目录内执行）：
    python output\migration\verify_after_migration.py

逐项检查：目录结构 / Python 与依赖 / 7 个核心库的行数与最新日期 / 通达信技能 DLL /
          API 配置 / 计划任务 / 门户端口。全部通过才算迁移成功。
不修改任何数据，只读。
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ★若新机路径不同，只改这一行
ROOT = Path(__file__).resolve().parent.parent.parent
CACHE = ROOT / "data" / "cache"

PASS, FAIL, WARN = [], [], []


def ok(msg):
    PASS.append(msg)
    print(f"  [OK]   {msg}")


def bad(msg):
    FAIL.append(msg)
    print(f"  [FAIL] {msg}")


def warn(msg):
    WARN.append(msg)
    print(f"  [WARN] {msg}")


def check_env():
    print("\n1) Python 与依赖")
    v = sys.version_info
    if v.major == 3 and v.minor >= 11:
        ok(f"Python {sys.version.split()[0]}")
    else:
        bad(f"Python {sys.version.split()[0]}（建议 3.13，至少 3.11）")
    for mod in ("pandas", "numpy", "yaml", "requests", "scipy", "sklearn", "matplotlib"):
        try:
            m = __import__(mod)
            ok(f"{mod} {getattr(m, '__version__', '?')}")
        except Exception as e:
            bad(f"{mod} 缺失（{str(e)[:40]}）")


def check_tree():
    print("\n2) 目录结构")
    need = ["data", "factors", "risk", "deck", "config", "docs", "output", "logs",
            "backtest", "strategy", "validation"]
    for d in need:
        (ok if (ROOT / d).is_dir() else bad)(f"{d}/")
    for f in ["AGENTS.md", "CORE_ISSUE_TRACKER.md", "config/backtest_window.yaml",
              "factors/window_config.py", "data/cache.py"]:
        (ok if (ROOT / f).exists() else bad)(f)


def check_dbs():
    print("\n3) 核心数据库（行数 + 最新日期）")
    # 优先读随代码提交的 scripts/migration/data_inventory.json（output/ 不进 Git）
    inv = ROOT / "scripts" / "migration" / "data_inventory.json"
    if not inv.exists():
        inv = ROOT / "output" / "migration" / "data_inventory.json"
    if not inv.exists():
        warn("data_inventory.json 缺失，跳过行数比对")
        return
    exp = {r["file"]: r for r in json.loads(inv.read_text(encoding="utf-8"))}
    # 表 → 日期列（★表名以实际库为准：tdx_base 是 daily/tables，tdx_capital 是 capital_daily）
    DATE_COL = {"bars.db": ("daily_bar", "date"), "valuation.db": ("valuation", "date"),
                "hist_mv.db": ("hist_mv", "month"), "finance.db": ("finance_report", "period"),
                "tdx_finance.db": ("fin_tdx", "period"), "rzrq.db": ("rzrq", "date"),
                "lhb.db": ("lhb_detail", "date"), "st_history.db": ("is_st_v2", "date"),
                "tdx_base.db": ("daily", "date"), "tdx_capital.db": ("capital_daily", "date")}
    for name, meta in exp.items():
        if meta.get("tier") == "archive":
            continue
        p = CACHE / name
        if not p.exists():
            # 原机上本就不存在的库（如 policy.db）只警告，不判失败
            if not meta.get("exists", True):
                warn(f"{name} 缺失（原机也不存在，无需迁移）")
            else:
                (bad if meta.get("tier") == "essential" else warn)(f"{name} 缺失")
            continue
        size_mb = round(p.stat().st_size / 1024 / 1024, 1)
        drift = abs(size_mb - meta.get("size_mb", 0)) / max(meta.get("size_mb", 1), 1)
        if drift > 0.05:
            warn(f"{name} 体积偏差 {drift*100:.1f}%（本机 {size_mb} MB vs 原 {meta.get('size_mb')} MB）")
        try:
            con = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True, timeout=60)
            tbl, dcol = DATE_COL.get(name, (None, None))
            if tbl:
                tabs = [r[0] for r in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")]
                if tbl not in tabs:
                    warn(f"{name} 无表 {tbl}（实际 {tabs[:4]}）")
                    con.close()
                    continue
                n, d0, d1 = con.execute(f"SELECT COUNT(*), MIN({dcol}), MAX({dcol}) FROM {tbl}").fetchone()
                ok(f"{name:22s} {n:>10,} 行  {d0} ~ {d1}")
                exp_rows = (meta.get("row_check") or {}).get(tbl)
                if exp_rows and abs(n - exp_rows) / max(exp_rows, 1) > 0.01:
                    warn(f"  └ 行数偏差 {(n-exp_rows)/exp_rows*100:+.1f}% vs 原机 {exp_rows:,}")
            else:
                # 完整性检查
                ic = con.execute("PRAGMA integrity_check").fetchone()[0]
                ok(f"{name:22s} integrity={ic}, {size_mb} MB")
            con.close()
        except Exception as e:
            bad(f"{name} 打开失败: {str(e)[:60]}")


def check_external():
    print("\n4) 项目外依赖")
    home = Path(os.environ.get("USERPROFILE", r"C:\Users\Administrator"))
    skill = home / ".dsh" / "skills" / "tdx-aidata"
    if skill.is_dir():
        dlls = list(skill.rglob("*.dll"))
        ok(f"通达信技能 {skill}  ({len(dlls)} 个 DLL)")
        if not dlls:
            warn("未找到 DLL（mfc100/msvcp100 等），通达信 API 可能不可用")
    else:
        bad(f"通达信技能缺失：{skill}（必须整目录拷贝）")
    if (home / ".dsh" / "lib").is_dir():
        ok(".dsh/lib 存在")
    env = home / "dsh-desktop" / ".env"
    (ok if env.exists() else warn)(f"API 配置 {env}")
    for sub in ("lib",):
        if (skill / sub).is_dir():
            ok(f"通达信技能子目录 {sub}/")


def check_tasks():
    print("\n5) 计划任务（可选，需在 Windows 上运行）")
    if os.name != "nt":
        warn("非 Windows，跳过")
        return
    try:
        import subprocess
        out = subprocess.run(["schtasks", "/query", "/fo", "csv"],
                             capture_output=True, text=True, errors="replace").stdout
        for t in ("DSHQuant-TDX-DailyUpdate", "LWQuant-DailyPipeline", "LWQuant-DeckGuard"):
            (ok if t in out else warn)(f"计划任务 {t}")
    except Exception as e:
        warn(f"无法查询计划任务: {str(e)[:50]}")


def check_portal():
    print("\n6) 门户服务")
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:8787/", timeout=5) as r:
            ok(f"端口 8787 HTTP {r.status}")
    except Exception:
        warn("8787 未启动（先运行：python -u deck\\deck_server.py）")


def main():
    print("=" * 74)
    print(f"迁移验收 · 项目根目录 = {ROOT}")
    print("=" * 74)
    check_env()
    check_tree()
    check_dbs()
    check_external()
    check_tasks()
    check_portal()
    print("\n" + "=" * 74)
    print(f"通过 {len(PASS)} | 警告 {len(WARN)} | 失败 {len(FAIL)}")
    if FAIL:
        print("\n失败项（必须修复）：")
        for f in FAIL:
            print("  - " + f)
    if WARN:
        print("\n警告项（可接受但需知情）：")
        for w in WARN:
            print("  - " + w)
    print("=" * 74)
    print("结论：" + ("✅ 迁移成功，可用" if not FAIL else "❌ 还有失败项，见上"))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
