# -*- coding: utf-8 -*-
"""data/build_st_history.py —— 重建历史 ST 区间（方案 A 的对齐算法）

输入：name_history.db（简称序列，含 is_st_flag）+ bars.db（行情）
输出：data/cache/st_history.db
      st_interval(code, start_date, end_date, method, confidence)
      st_check(code, n_st_episodes_name, n_st_episodes_price, agree)

算法（两路证据交叉）：
  ①「价格签名」：ST 股涨跌停 ±5% → 20 日滚动窗口内 max|pct| ≤ 5.2% 且曾出现 |pct| ≥ 4.5%
     的连续区间判为 ST-疑似；只要出现过 |pct| > 5.5% 就**确定不是 ST**
  ②「名称序列」：简称里 ST 段的数量 = 该股历史上应有的 ST 次数
  ③ 对齐：若 ①的段数 == ②的段数 → 1:1 赋日期（confidence=high）；
     若不等 → 采用 ①（confidence=low），并记录差数

用法：python data/build_st_history.py
"""
from __future__ import annotations

import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CACHE = Path(__file__).resolve().parent.parent / "data" / "cache"
BARS = CACHE / "bars.db"
NAMES = CACHE / "name_history.db"
OUT = CACHE / "st_history.db"

WIN = 20          # 滚动窗口（交易日）
ST_MAX = 0.052    # 窗口内最大单日涨跌幅上限（ST 为 5%）
LIMIT_HIT = 0.045 # 认定"打过 5% 板"的下限
NON_ST = 0.055    # 只要超过这个就确定不是 ST


def main() -> int:
    if OUT.exists():
        OUT.unlink()
    out = sqlite3.connect(str(OUT))
    out.execute("""CREATE TABLE st_interval (
        code TEXT, start_date TEXT, end_date TEXT, method TEXT, confidence TEXT,
        PRIMARY KEY (code, start_date))""")
    out.execute("""CREATE TABLE st_check (
        code TEXT PRIMARY KEY, n_name_episodes INTEGER, n_price_episodes INTEGER,
        agree INTEGER, n_days INTEGER)""")
    out.commit()

    bars = sqlite3.connect(f"file:{BARS.as_posix()}?mode=ro", uri=True, timeout=90)
    nm = sqlite3.connect(f"file:{NAMES.as_posix()}?mode=ro", uri=True, timeout=30)

    # 名称序列 → 应有 ST 段数（连续 is_st_flag=1 的段数）
    seq = defaultdict(list)
    for code, s, f in nm.execute("SELECT code, seq, is_st_flag FROM name_change ORDER BY code, seq"):
        seq[code].append(f)
    name_eps = {}
    for code, flags in seq.items():
        n = 0
        prev = 0
        for f in flags:
            if f and not prev:
                n += 1
            prev = f
        name_eps[code] = n

    codes = [r[0] for r in bars.execute("SELECT DISTINCT code FROM daily_bar ORDER BY code")]
    print(f"待处理 {len(codes):,} 只（仅对「曾出现 ST 简称」的股票建区间）")

    n_int = 0
    stats = {"high": 0, "low": 0}
    for i, code in enumerate(codes, 1):
        need = name_eps.get(code, 0)
        if need == 0:
            continue
        rows = bars.execute(
            "SELECT date, pct_chg FROM daily_bar WHERE code=? AND pct_chg IS NOT NULL ORDER BY date",
            (code,)).fetchall()
        if len(rows) < WIN + 5:
            continue
        dates = [r[0] for r in rows]
        pcts = [abs(r[1]) for r in rows]
        # 滚动窗口判定
        flag = []
        for j in range(len(pcts)):
            lo = max(0, j - WIN + 1)
            w = pcts[lo:j + 1]
            mx, hit = max(w), max(w)
            flag.append(1 if (mx <= ST_MAX and hit >= LIMIT_HIT) else 0)
        # 提取连续段（至少 20 天）
        intervals = []
        k = 0
        while k < len(flag):
            if flag[k] == 1:
                s = k
                while k < len(flag) and flag[k] == 1:
                    k += 1
                if k - s >= 20:
                    intervals.append((dates[s], dates[k - 1]))
            else:
                k += 1
        agree = 1 if len(intervals) == need else 0
        conf = "high" if agree else "low"
        stats[conf] += 1
        for s, e in intervals:
            out.execute("INSERT OR REPLACE INTO st_interval VALUES (?,?,?,?,?)",
                        (code, s, e, "price_signature", conf))
            n_int += 1
        out.execute("INSERT OR REPLACE INTO st_check VALUES (?,?,?,?,?)",
                    (code, need, len(intervals), agree, len(rows)))
        if i % 500 == 0:
            out.commit()
            print(f"  [{i}/{len(codes)}] 区间 {n_int:,}", flush=True)
    out.commit()

    # 统计
    tot = out.execute("SELECT COUNT(*) FROM st_check").fetchone()[0]
    ag = out.execute("SELECT SUM(agree) FROM st_check").fetchone()[0] or 0
    print(f"\n曾出现 ST 简称的股票: {tot:,} 只")
    print(f"  段数一致（high）: {ag:,} = {ag/max(tot,1)*100:.1f}%")
    print(f"  段数不一致（low）: {tot-ag:,}")
    print(f"  生成 ST 区间: {n_int:,} 段")
    print("\n按年分布（区间起始年）:")
    for y, k in out.execute(
            "SELECT substr(start_date,1,4), COUNT(*) FROM st_interval GROUP BY 1 ORDER BY 1"):
        print(f"  {y}: {k}")
    print(f"\n库: {OUT}")
    bars.close(); nm.close(); out.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
