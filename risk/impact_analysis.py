# -*- coding: utf-8 -*-
"""risk/impact_analysis.py —— 数据源切换影响面分析（新旧库差异 + 引用盘点）"""
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = Path(r"D:\Programs\DSH Projects\DSH Quant")
CACHE = BASE / "data" / "cache"

# ---- 1. 扫描所有 py 的数据库引用 ----
PAT_DB = re.compile(r"""["']([^"']*?(?:bars|finance|hist_mv|stock_basic|valuation|industry|lhb|rzrq|consensus|limitup|finance_quality|tdx_meta|bars_tdx|finance_csmar)[^"']*?\.db)["']""")
PAT_SQL = re.compile(r"""(?:FROM|JOIN|INTO|UPDATE)\s+([a-zA-Z_][a-zA-Z0-9_]*)""", re.I)
PAT_ADJ = re.compile(r"""adjust\s*=\s*['"](\w+)['"]""", re.I)

db_refs = defaultdict(list)
sql_tables = defaultdict(int)
adj_filters = defaultdict(list)
files_scanned = 0

for f in BASE.rglob("*.py"):
    if any(x in str(f) for x in ("\\.git", "__pycache__", "\\risk\\_", "\\node_modules")):
        continue
    try:
        txt = f.read_text(encoding="utf-8", errors="replace")
    except Exception:
        continue
    files_scanned += 1
    for m in PAT_DB.finditer(txt):
        db_refs[m.group(1)].append(str(f.relative_to(BASE)))
    for m in PAT_SQL.finditer(txt):
        sql_tables[m.group(1).lower()] += 1
    for m in PAT_ADJ.finditer(txt):
        adj_filters[m.group(1)].append(str(f.relative_to(BASE)))

print("=" * 74)
print("一、数据库引用统计")
print("=" * 74)
print(f"扫描 {files_scanned} 个 py 文件\n")
for db, fl in sorted(db_refs.items(), key=lambda x: -len(x[1])):
    uniq = sorted(set(fl))
    print(f"  {db:38s} {len(fl):>4} 处 / {len(uniq):>3} 个文件")
    if len(uniq) <= 6:
        for u in uniq:
            print(f"        - {u}")
    else:
        for u in uniq[:5]:
            print(f"        - {u}")
        print(f"        ... 另 {len(uniq)-5} 个")

print("\n" + "=" * 74)
print("二、SQL 表依赖（出现次数 Top 20）")
print("=" * 74)
for t, n in sorted(sql_tables.items(), key=lambda x: -x[1])[:20]:
    print(f"  {t:34s} {n:>4} 次")

print("\n" + "=" * 74)
print("三、adjust 过滤条件（兼容性关键）")
print("=" * 74)
for v, fl in adj_filters.items():
    print(f"  adjust='{v}': {len(fl)} 处，{len(set(fl))} 个文件")
    for u in sorted(set(fl))[:8]:
        print(f"      - {u}")

# ---- 4. 新旧库结构对比 ----
print("\n" + "=" * 74)
print("四、新旧库结构差异")
print("=" * 74)
import sqlite3
for name in ["bars.db", "bars_tdx.db"]:
    p = CACHE / name
    if not p.exists():
        print(f"  {name}: 不存在")
        continue
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    print(f"\n  [{name}]  {p.stat().st_size/1024/1024:.0f} MB")
    for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        try:
            n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except Exception:
            n = -1
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
        print(f"    {t}: {n:,} 行, {len(cols)} 列")
        print(f"      列: {cols}")
        if t == "daily_bar":
            r = con.execute("SELECT MIN(date),MAX(date) FROM daily_bar").fetchone()
            print(f"      日期: {r[0]} ~ {r[1]}")
            for a in con.execute("SELECT adjust, COUNT(*) FROM daily_bar GROUP BY adjust"):
                print(f"      adjust={a[0]}: {a[1]:,}")
    con.close()
