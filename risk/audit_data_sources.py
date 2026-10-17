# -*- coding: utf-8 -*-
"""risk/audit_data_sources.py —— 全项目数据源引用审计（新库 vs 程序引用）

目的（2026-10-16 用户要求）：
  本项目把数据底座从「多个免费源」切换为「通达信（外部一次性导入 + API 增量）」，
  为此新建了若干库；旧的免费源库准备停用。本脚本回答：
    1) 项目里有哪些 .db，哪些属于「新库（通达信时代）」、哪些是「旧库（待停）」
    2) 每一处**代码**引用了哪些 .db、在哪一行（文档提及单独统计，不混淆）
    3) 引用与文件是否匹配：旧库仍被代码引用 / 引用了不存在的库 / 新库无人用

用法：python risk/audit_data_sources.py [--json-only]
输出：logs/data_source_audit_<时间戳>.json
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent.parent
LOGS = BASE / "logs"
SELF = Path(__file__).resolve()
SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".pnpm", "parquet", "dist", "build"}
CODE_EXT = {".py", ".ps1", ".cmd", ".bat", ".js", ".html"}
DOC_EXT = {".md", ".json", ".yaml", ".yml", ".txt", ".ini", ".toml"}
DB_RE = re.compile(r"([A-Za-z0-9_\-]+\.db)\b")
# 误抓噪音：属性名/变量名，不是库文件名
NOISE = {"self.db", "cache.db", "args.db", "l.db", "r.db", "con.db", "c.db", "db", "meta.db"}

NEW_DBS = {
    "bars.db":          "主行情库（已原地切换为通达信 qfq，2000-2026，1,570 万行）",
    "bars_tdx.db":      "通达信源/中间库（qfq 15.67M + unadj 0.70M + adj_factor 1,848 万）",
    "tdx_meta.db":      "通达信元数据（universe/stock_info_tdx/index_member/sector/每日快照/is_st_inferred）",
    "finance_csmar.db": "CSMAR 财务（fin_core 年度 / fin_core_q 季度，含 publish_date）",
    "datayes_basic.db": "通联基础清单（sec_listed / sec_delisted 退市股清单，免费接口）",
}
OLD_DBS = {
    "finance.db":         "老财报 akshare 摘要 319K 行（无披露日）→ 应由 finance_csmar.db 取代",
    "stock_basic.db":     "旧基础信息 5,561 行 → 应由 tdx_meta.universe/stock_info_tdx 取代",
    "hist_mv.db":         "月频市值 381K 行 → 可由通达信股本+行情自算",
    "valuation.db":       "估值 PE/PB/换手/isST（baostock，2020-06 起）→ 部分可由通达信 get_more_info 取代",
    "finance_quality.db": "财务质量 12,375 行（baostock/tushare 双源）→ 可能由 CSMAR 指标取代",
    "lhb.db":             "龙虎榜（东财）→ 通达信无对应，不能停",
    "limitup.db":         "涨停/炸板池（东财）→ 通达信无对应，不能停",
    "industry.db":        "申万行业 162 行 → 通达信 get_sector_list 可部分取代",
    "rzrq.db":            "融资融券 619 万行（东财）→ 通达信无明细，不能停",
    "consensus.db":       "一致预期（同花顺）→ 通达信无，不能停",
    "bars_incr.db":       "增量写入路由库（当前 0 字节，机制疑似失效）",
    "minute.db":          "分钟线（当前不存在，已改走 parquet）",
}
AUX_DBS = {
    "bars_legacy_backup_20261016.db": "切换前旧库完整备份（回滚用）",
    "bars_tdx_test.db":               "通达信导入测试库",
    "demo_bars.db":                   "开源演示数据",
}


def read_text(p: Path) -> str:
    for enc in ("utf-8", "gbk"):
        try:
            return p.read_text(encoding=enc)
        except Exception:  # noqa: BLE001
            continue
    return p.read_text(encoding="utf-8", errors="replace")


def db_inventory() -> dict:
    inv = {}
    for p in sorted(BASE.glob("**/*.db")):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        rel = str(p.relative_to(BASE)).replace("\\", "/")
        info = {"size_mb": round(p.stat().st_size / 1024 / 1024, 2),
                "mtime": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
                "tables": []}
        try:
            con = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True, timeout=5)
            for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
                n = con.execute(f"SELECT COUNT(*) FROM `{t}`").fetchone()[0]
                cols = [r[1] for r in con.execute(f"PRAGMA table_info(`{t}`)")]
                d = {"name": t, "rows": n}
                if "source" in cols:
                    d["sources"] = dict(con.execute(
                        f"SELECT source, COUNT(*) FROM `{t}` GROUP BY source").fetchall())
                info["tables"].append(d)
            con.close()
        except Exception as exc:  # noqa: BLE001
            info["error"] = str(exc)[:100]
        inv[rel] = info
    return inv


def tier_of(name: str) -> str:
    if name in NEW_DBS:
        return "NEW"
    if name in OLD_DBS:
        return "OLD"
    if name in AUX_DBS:
        return "AUX"
    return "UNKNOWN"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-only", action="store_true")
    args = ap.parse_args()
    t0 = datetime.now()

    inv = db_inventory()
    exists = {Path(p).name for p in inv}

    sites = defaultdict(list)      # db -> [{file, line, kind, snippet}]
    files_scanned = 0
    for p in BASE.glob("**/*"):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext not in CODE_EXT and ext not in DOC_EXT:
            continue
        if any(part in SKIP_DIRS for part in p.parts) or p.resolve() == SELF:
            continue
        rel = str(p.relative_to(BASE)).replace("\\", "/")
        try:
            txt = read_text(p)
        except Exception:  # noqa: BLE001
            continue
        if ".db" not in txt:
            continue
        files_scanned += 1
        kind = "code" if ext in CODE_EXT else "doc"
        for i, line in enumerate(txt.splitlines(), 1):
            for m in DB_RE.finditer(line):
                name = m.group(1)
                if name in NOISE or name.startswith("self."):
                    continue
                sites[name].append({"file": rel, "line": i, "kind": kind,
                                    "snippet": line.strip()[:150]})

    rep = {"ts": t0.strftime("%Y-%m-%d %H:%M:%S"), "files_scanned": files_scanned,
           "new_dbs": NEW_DBS, "old_dbs": OLD_DBS, "aux_dbs": AUX_DBS,
           "db_files": inv, "dbs": {}}

    print("=" * 84)
    print(f"数据源引用审计  {rep['ts']}   扫描 {files_scanned} 个文件")
    print("=" * 84)

    print("\n【一】库文件 → 被引用情况（code=可执行代码 / doc=文档提及）")
    print(f"  {'层级':6s} {'库文件':34s} {'大小MB':>9s} {'代码处':>7s} {'代码文件':>8s} {'文档处':>7s}  备注")
    for name in sorted(set(list(sites) + [Path(p).name for p in inv])):
        t = tier_of(name)
        s = sites.get(name, [])
        code = [x for x in s if x["kind"] == "code"]
        doc = [x for x in s if x["kind"] == "doc"]
        code_files = len({x["file"] for x in code})
        flag = "" if name in exists else "  ⚠文件不存在"
        if any(x["file"].startswith("data/demo/") for x in code) and name == "bars.db":
            flag += " (含 demo 目录)"
        print(f"  {t:6s} {name:34s} {'':>9s} {len(code):>7d} {code_files:>8d} {len(doc):>7d}{flag}")
        rep["dbs"][name] = {"tier": t, "exists": name in exists,
                            "code_sites": len(code), "code_files": code_files,
                            "doc_sites": len(doc),
                            "files": sorted({x["file"] for x in code}),
                            "sites": code[:300]}

    # ---- 判定：按代码文件分类 ----
    per_file = defaultdict(lambda: {"NEW": set(), "OLD": set(), "AUX": set(), "UNKNOWN": set()})
    for name, s in sites.items():
        t = tier_of(name)
        for x in s:
            if x["kind"] == "code":
                per_file[x["file"]][t].add(name)
    pure_old, mixed, pure_new = [], [], []
    for f, d in per_file.items():
        has_new, has_old = bool(d["NEW"]), bool(d["OLD"])
        if has_old and has_new:
            mixed.append(f)
        elif has_old:
            pure_old.append(f)
        elif has_new:
            pure_new.append(f)
    rep["per_file"] = {f: {k: sorted(v) for k, v in d.items()} for f, d in per_file.items()}
    rep["summary"] = {"pure_new_files": sorted(pure_new), "mixed_files": sorted(mixed),
                      "pure_old_files": sorted(pure_old)}

    print("\n【二】按代码文件的迁移状态")
    print(f"  ✅ 只用新库（已切换）      : {len(pure_new):>3} 个文件")
    print(f"  ⚠️ 新+旧混用（半切换）      : {len(mixed):>3} 个文件")
    print(f"  ❌ 只用旧库（未切换）      : {len(pure_old):>3} 个文件")

    def show(title, files):
        if not files:
            return
        print(f"\n  ▼ {title}（{len(files)}）")
        for f in sorted(files):
            d = per_file[f]
            olds = ",".join(sorted(d["OLD"]))
            print(f"    {f:58s} 旧库: {olds}")

    print("\n【三】仍被代码引用的旧库 → 文件清单")
    for db in sorted(OLD_DBS, key=lambda n: -len([x for x in sites.get(n, []) if x["kind"] == "code"])):
        code = [x for x in sites.get(db, []) if x["kind"] == "code"]
        if not code:
            print(f"\n  ✔ {db}: 代码已无引用（仅文档提及）")
            continue
        fl = sorted({x["file"] for x in code})
        print(f"\n  ● {db}  →  {len(code)} 处 / {len(fl)} 个代码文件")
        print(f"    {OLD_DBS[db]}")
        for f in fl[:12]:
            lines = [x["line"] for x in code if x["file"] == f]
            print(f"      {f}:{','.join(map(str, lines[:6]))}")
        if len(fl) > 12:
            print(f"      … 其余 {len(fl)-12} 个文件见 JSON")

    print("\n【四】代码引用了但文件不存在（断链）")
    for name, d in sorted(rep["dbs"].items(), key=lambda kv: -kv[1]["code_sites"]):
        if d["tier"] == "UNKNOWN" and d["code_sites"]:
            print(f"  ⚠ {name:28s} {d['code_sites']:>3} 处 / {d['code_files']:>2} 个文件")

    LOGS.mkdir(exist_ok=True)
    out = LOGS / f"data_source_audit_{t0.strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n完整结果: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
