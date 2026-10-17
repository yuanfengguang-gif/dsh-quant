# -*- coding: utf-8 -*-
"""data/build_qfq_from_events.py —— 用「除权明细」自算复权因子并重建前复权库（修 DS-20）

为什么不再用「后复权因子 zip」：实测该因子**不是纯事件乘数**（末次除权后仍漂移 +1.63%），
用它构造的 qfq 与事件法相比偏差最高 ~30%。

算法（教科书）：
  对每个除权事件（ex_date）：
    理论除权价 theo = (Pc − B/10 + (A/10)×Pa) / (1 + S/10 + A/10)
        Pc=除权日前收盘（停牌则取之前最近交易日收盘）, B=派息(元/10股),
        S=送股(股/10股), A=配股(股/10股), Pa=配股价
    事件乘数 k = Pc / theo  (>1)
  累计：prefix(t) = Π_{事件日 ≤ t} k ；total = Π_全部 k
  前复权乘数：f(t) = prefix(t) / total      （末次除权之后 = 1.0，无假漂移）
  前复权价：qfq = raw × f

输入：data/cache/tdx_base.db（原始价）+ data/cache/tdx_dividends.db（除权明细）
      现 bars.db（沿用 is_st + 尾部 10-12~10-16 增量行）
输出：data/cache/bars_events.db（schema 与 bars.db.daily_bar 一致）
用法：python data/build_qfq_from_events.py [--limit N]
"""
from __future__ import annotations

import argparse
import bisect
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CACHE = Path(__file__).resolve().parent.parent / "data" / "cache"
BASE_DB = CACHE / "tdx_base.db"
DIV = CACHE / "tdx_dividends.db"
CUR = CACHE / "bars.db"
OUT = CACHE / "bars_events.db"

DDL = """CREATE TABLE IF NOT EXISTS daily_bar (
    code TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, preclose REAL,
    volume REAL, amount REAL, turn REAL, pct_chg REAL, is_st INTEGER,
    adjust TEXT, source TEXT, PRIMARY KEY (code, date))"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    t0 = time.time()
    if OUT.exists():
        OUT.unlink()

    base = sqlite3.connect(f"file:{BASE_DB.as_posix()}?mode=ro", uri=True, timeout=60)
    div = sqlite3.connect(f"file:{DIV.as_posix()}?mode=ro", uri=True, timeout=60)
    cur = sqlite3.connect(f"file:{CUR.as_posix()}?mode=ro", uri=True, timeout=60)
    out = sqlite3.connect(str(OUT))
    out.execute("PRAGMA journal_mode=MEMORY")
    out.execute("PRAGMA synchronous=OFF")
    out.execute("PRAGMA cache_size=-800000")
    out.execute(DDL)
    out.commit()

    # 除权事件按股票分组
    ev = defaultdict(list)
    for code, d, b, s, a, pa in div.execute(
            "SELECT code, ex_date, bonus, share_bonus, allotment, allot_price "
            "FROM dividend ORDER BY code, ex_date"):
        ev[code].append((d, float(b or 0), float(s or 0), float(a or 0), float(pa or 0)))
    print(f"除权事件：{len(ev):,} 只股票有记录")

    codes = [r[0] for r in base.execute("SELECT DISTINCT code FROM daily ORDER BY code")]
    if args.limit:
        codes = codes[: args.limit]
    print(f"待生成 {len(codes):,} 只 → {OUT}")

    n_rows = n_ev_used = 0
    no_event = 0
    for i, code in enumerate(codes, 1):
        rows = base.execute(
            "SELECT date, open, high, low, close, pre_close, volume, amount, turnover "
            "FROM daily WHERE code=? ORDER BY date", (code,)).fetchall()
        if not rows:
            continue
        dates = [r[0] for r in rows]
        events = ev.get(code, [])
        # 计算每个事件的 k
        ks, k_dates = [], []
        for d, B, S, A, Pa in events:
            j = bisect.bisect_left(dates, d)
            if j < len(dates) and dates[j] == d:
                Pc = rows[j][5] or (rows[j - 1][4] if j > 0 else None)
            else:
                Pc = rows[j - 1][4] if j > 0 else None   # 停牌：用之前最近收盘
            if not Pc:
                continue
            theo = (Pc - B / 10.0 + A / 10.0 * Pa) / (1.0 + S / 10.0 + A / 10.0)
            if theo <= 0:
                continue
            ks.append(Pc / theo)
            k_dates.append(d)
        if not events:
            no_event += 1
        total = 1.0
        for k in ks:
            total *= k
        prefix, p = [], 1.0
        for k in ks:
            p *= k
            prefix.append(p)
        n_ev_used += len(ks)

        # is_st 沿用现库
        st_map = dict(cur.execute(
            "SELECT date, is_st FROM daily_bar WHERE code=? AND adjust='qfq'", (code,)).fetchall())

        buf, prev_close = [], None
        for date, o, hi, lo, c, pc_raw, vol, amt, tor in rows:
            idx = bisect.bisect_right(k_dates, date) - 1
            f = (prefix[idx] / total) if idx >= 0 else (1.0 / total)
            qc = c * f if c is not None else None
            qo = o * f if o is not None else None
            qh = hi * f if hi is not None else None
            ql = lo * f if lo is not None else None
            pc = (qc / prev_close - 1.0) if (qc and prev_close) else None
            buf.append((code, date, qo, qh, ql, qc, prev_close, vol, amt,
                        (tor / 100.0) if tor is not None else None, pc,
                        int(st_map.get(date) or 0), "qfq", "tdx_events"))
            prev_close = qc
        out.executemany(
            "INSERT OR REPLACE INTO daily_bar VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", buf)
        out.commit()
        n_rows += len(buf)
        if i % 300 == 0 or i == len(codes):
            el = time.time() - t0
            print(f"  [{i}/{len(codes)}] {n_rows:,} 行  事件 {n_ev_used:,}  {el:.0f}s", flush=True)

    # 尾部增量（10-12~10-16）：现库已有，直接搬（该区间无除权 → qfq=raw）
    moved = 0
    out.execute(f"ATTACH DATABASE '{CUR.as_posix()}' AS c")
    rows2 = out.execute("""
        SELECT c2.code, c2.date, c2.open, c2.high, c2.low, c2.close, c2.preclose, c2.volume,
               c2.amount, c2.turn, c2.pct_chg, c2.is_st, 'qfq', c2.source
        FROM c.daily_bar c2
        LEFT JOIN main.daily_bar n ON n.code=c2.code AND n.date=c2.date
        WHERE c2.adjust='qfq' AND c2.date > (SELECT MAX(date) FROM main.daily_bar)
          AND n.code IS NULL""").fetchall()
    if rows2:
        out.executemany("INSERT OR REPLACE INTO daily_bar VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows2)
        out.commit()
        moved = len(rows2)

    out.execute("CREATE INDEX IF NOT EXISTS idx_qfq_date ON daily_bar(date)")
    out.commit()
    n = out.execute("SELECT COUNT(*) FROM daily_bar").fetchone()[0]
    c = out.execute("SELECT COUNT(DISTINCT code) FROM daily_bar").fetchone()[0]
    rng = out.execute("SELECT MIN(date), MAX(date) FROM daily_bar").fetchone()
    neg = out.execute("SELECT COUNT(*) FROM daily_bar WHERE close<=0").fetchone()[0]
    print(f"\n完成: {n:,} 行 / {c:,} 只 / {rng[0]} ~ {rng[1]}")
    print(f"用到事件 {n_ev_used:,} 个 | 无除权股票 {no_event:,} 只 | 尾部增量搬入 {moved:,} 行 | 负价 {neg}")
    print(f"库: {OUT}  ({OUT.stat().st_size/1024/1024/1024:.2f} GiB)")
    base.close(); div.close(); cur.close(); out.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
