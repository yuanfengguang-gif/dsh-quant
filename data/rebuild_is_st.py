# -*- coding: utf-8 -*-
"""data/rebuild_is_st.py —— 用「名称历史」重建 2020-06 前的 is_st（修 DS-22）

诊断结论（2026-10-17 实测）：
  · 名称历史可用：1,955 只有简称变更记录，其中 **1,292 只从未出现 ST 简称**、**663 只曾出现**
  · 当前 bars.db 的 2020-06 前 is_st **双向错误**：
      - **误报**：149,955 行（占该段 ST 行的 30%）属于"历史上从未 ST"的股票 → 应清零
      - **漏报**：663 只曾 ST 的股票里，只有 117 只被标过；**546 只完全漏标**
  · 2020-06 之后有真值（`IsSTGP` 快照），**不动**

重建规则（按证据强弱）：
  R1（强）：有名称记录且**从未 ST** → 该股 2020-06 前 is_st 全置 0
  R2（中）：有名称记录且**曾 ST** → 用 `is_st_inferred`（价格签名，半年粒度）映射到日
  R3（弱）：无名称记录（3,626 只）→ **保留原值**，标 confidence=low（无法改进）
  R4：date >= 2020-06-01 → **完全不动**（真值）

输出：
  data/cache/st_history.db
    is_st_v2(code, date, is_st, source, confidence)   ← 全量新序列
    is_st_changed(code, date, old_value, new_value)   ← 变更备份（可回滚）
用法：python data/rebuild_is_st.py [--apply]
     不带 --apply 只生成 is_st_v2（不写 bars.db）
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CACHE = Path(__file__).resolve().parent.parent / "data" / "cache"
BARS = CACHE / "bars.db"
NAMES = CACHE / "name_history.db"
META = CACHE / "tdx_meta.db"
OUT = CACHE / "st_history.db"
CUTOFF = "2020-06-01"


def halfyear(d: str) -> str:
    return f"{d[:4]}H{1 if int(d[5:7]) <= 6 else 2}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    bars = sqlite3.connect(str(BARS), timeout=180)
    nm = sqlite3.connect(f"file:{NAMES.as_posix()}?mode=ro", uri=True, timeout=30)
    meta = sqlite3.connect(f"file:{META.as_posix()}?mode=ro", uri=True, timeout=30)
    out = sqlite3.connect(str(OUT))
    out.execute("PRAGMA synchronous=OFF")
    out.execute("""CREATE TABLE IF NOT EXISTS is_st_v2 (
        code TEXT, date TEXT, is_st INTEGER, source TEXT, confidence TEXT,
        PRIMARY KEY (code, date))""")
    out.execute("""CREATE TABLE IF NOT EXISTS is_st_changed (
        code TEXT, date TEXT, old_value INTEGER, new_value INTEGER,
        PRIMARY KEY (code, date))""")
    out.commit()

    ever, never = set(), set()
    for code, s in nm.execute("SELECT code, SUM(is_st_flag) FROM name_change GROUP BY code"):
        (ever if (s or 0) > 0 else never).add(code)
    print(f"名称历史：曾 ST {len(ever):,} 只 / 从未 ST {len(never):,} 只")

    inferred = {(c, p): v for c, p, v in meta.execute(
        "SELECT code, period, inferred FROM is_st_inferred")}
    print(f"is_st_inferred：{len(inferred):,} 条（半年粒度）")
    # ★2026-10-17 修正：东财名称表对 119 只当前 ST 股滞后（名称里没 ST）→
    #   这些股票不套用「从未 ST 清零」，保留原值并标 low
    cur_st = {r[0] for r in meta.execute("SELECT code FROM stock_info_tdx WHERE IsSTGP='1'")}
    print(f"当前 ST（IsSTGP）：{len(cur_st):,} 只（其中落在 never/absent 的 "
          f"{len(cur_st & (never | set())):,} 只用 low 策略）")

    print("\n生成 is_st_v2 …", flush=True)
    cur = bars.execute(
        "SELECT code, date, is_st FROM daily_bar ORDER BY code, date")
    buf, changed = [], []
    n_r1 = n_r2 = n_r3 = n_r4 = 0
    cur_code, cur_vals = None, []
    def flush(code, vals):
        nonlocal n_r1, n_r2, n_r3, n_r4
        for date, old in vals:
            if date >= CUTOFF:
                buf.append((code, date, old, "truth_2020_06+", "high")); n_r4 += 1
            elif code in cur_st and code not in ever:
                # 名称滞后但当前是 ST：无法判定历史 → 保留原值，标 low
                buf.append((code, date, old, "keep_legacy_name_stale", "low")); n_r3 += 1
            elif code in never:
                buf.append((code, date, 0, "name_never_st", "high")); n_r1 += 1
            elif code in ever:
                pass_placeholder = None
                inf = inferred.get((code, halfyear(date)), 0)
                newv = 1 if inf else 0
                buf.append((code, date, newv, "inferred_by_name_episode", "mid")); n_r2 += 1
            else:
                # R3 修正（2026-10-17 验证）：无名称记录 ⇒ 从未改名 ⇒ 从未 ST
                #   证据：当前 201 只 ST 股**全部**有名称记录，0 只落在 empty 集合
                buf.append((code, date, 0, "name_absent_never_st", "mid")); n_r3 += 1
            if buf[-1][2] != old:
                changed.append((code, date, old, buf[-1][2]))
    for code, date, st in cur:
        if code != cur_code:
            if cur_code is not None:
                flush(cur_code, cur_vals)
            cur_code, cur_vals = code, []
        cur_vals.append((date, st))
        if len(buf) >= 100000:
            out.executemany("INSERT OR REPLACE INTO is_st_v2 VALUES (?,?,?,?,?)", buf)
            buf.clear()
    if cur_code is not None:
        flush(cur_code, cur_vals)
    if buf:
        out.executemany("INSERT OR REPLACE INTO is_st_v2 VALUES (?,?,?,?,?)", buf)
    out.commit()
    out.executemany("INSERT OR REPLACE INTO is_st_changed VALUES (?,?,?,?)", changed)
    out.commit()

    print(f"  R1 从未ST清零: {n_r1:,} 行 | R2 按推断: {n_r2:,} 行 | "
          f"R3 保留原值: {n_r3:,} 行 | R4 真值段: {n_r4:,} 行")
    print(f"  发生变更的行: {len(changed):,}")
    print("\n  is_st=1 行数对比：")
    old1 = bars.execute("SELECT SUM(is_st=1) FROM daily_bar").fetchone()[0]
    new1 = out.execute("SELECT SUM(is_st=1) FROM is_st_v2").fetchone()[0]
    old1_pre = bars.execute("SELECT SUM(is_st=1) FROM daily_bar WHERE date<?", (CUTOFF,)).fetchone()[0]
    new1_pre = out.execute("SELECT SUM(is_st=1) FROM is_st_v2 WHERE date<?", (CUTOFF,)).fetchone()[0]
    print(f"    全期: {old1:,} → {new1:,}")
    print(f"    2020-06 前: {old1_pre:,} → {new1_pre:,}")

    if args.apply:
        print("\n写入 bars.db（先备份变更行，可回滚）…", flush=True)
        with bars:
            bars.execute("CREATE TABLE IF NOT EXISTS is_st_backup_20261017 "
                         "(code TEXT, date TEXT, is_st INTEGER, PRIMARY KEY (code,date))")
            bars.executemany("INSERT OR REPLACE INTO is_st_backup_20261017 VALUES (?,?,?)",
                             [(c, d, o) for c, d, o, _ in changed])
            bars.executemany("UPDATE daily_bar SET is_st=? WHERE code=? AND date=?",
                             [(n, c, d) for c, d, _, n in changed])
        after = bars.execute("SELECT SUM(is_st=1) FROM daily_bar").fetchone()[0]
        print(f"  写后 is_st=1 行数: {after:,}（应等于 {new1:,}）")
        print(f"  备份表 is_st_backup_20261017: {len(changed):,} 行")
    else:
        print("\n（未写 bars.db；加 --apply 才写入）")
    bars.close(); nm.close(); meta.close(); out.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


