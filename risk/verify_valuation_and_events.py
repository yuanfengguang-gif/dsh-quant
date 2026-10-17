# -*- coding: utf-8 -*-
"""risk/verify_valuation_and_events.py —— 补强 V1（估值全市场重算）+ V2（除权事件反查）

V1 估值重算：
  PE_ttm = 总市值 / 归母净利TTM      （净利TTM = 最近 4 个单季 sq_net_profit 之和）
  PB     = 收盘价 / 每股净资产        （每股净资产 = tdx_finance.FN004）
  与 valuation.db 的 peTTM / pbMRQ 逐只对比

V2 除权事件反查：
  在 bars.db 里找 |pct_chg| 超板块涨跌停幅度的行（即"跳空"），
  逐行检查 tdx_dividends 是否在该日有除权事件：
    · 有事件 → 说明是除权（qfq 已处理，正常）
    · 无事件 → 真实异动（新股首日/ST转换/复牌/退市整理）或**漏事件**
  输出按原因分类的分布。

用法：python risk/verify_valuation_and_events.py
"""
from __future__ import annotations

import sqlite3
import sys
from collections import Counter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

C = r"D:\Programs\DSH Projects\DSH Quant\data\cache"


def main() -> int:
    con = sqlite3.connect(f"file:{C}\\bars.db?mode=ro", uri=True, timeout=90)
    con.execute(f"ATTACH DATABASE '{C.replace(chr(92),'/')}/valuation.db' AS v")
    con.execute(f"ATTACH DATABASE '{C.replace(chr(92),'/')}/tdx_base.db' AS k")
    con.execute(f"ATTACH DATABASE '{C.replace(chr(92),'/')}/finance.db' AS f")
    con.execute(f"ATTACH DATABASE '{C.replace(chr(92),'/')}/tdx_finance.db' AS tf")
    con.execute(f"ATTACH DATABASE '{C.replace(chr(92),'/')}/tdx_dividends.db' AS dv")

    # ---------- V1 估值重算 ----------
    print("=" * 100)
    print("V1 估值全市场重算（2026-10-09）")
    print("=" * 100)
    D = "2026-10-09"
    # 净利 TTM：最近 4 个单季之和（按 period 倒序取 4 期）
    ttm = {}
    rows = con.execute("""
        SELECT code, period, sq_net_profit FROM f.finance_report
        WHERE sq_net_profit IS NOT NULL AND period <= ? ORDER BY code, period DESC""", (D,)).fetchall()
    cnt = Counter()
    for code, per, sq in rows:
        if cnt[code] < 4:
            ttm[code] = ttm.get(code, 0.0) + (sq or 0)
            cnt[code] += 1
    # 每股净资产（最新期）
    bps = {}
    for code, per, b in con.execute(
            "SELECT code, period, bps FROM tf.fin_tdx WHERE bps IS NOT NULL ORDER BY code, period"):
        bps[code] = b
    # 总市值（亿元）
    mv = {r[0]: r[1] for r in con.execute(
        "SELECT code, total_mv/10000.0 FROM k.daily WHERE date=?", (D,))}

    pe_dev, pb_dev, n_pe, n_pb = [], [], 0, 0
    for code, pe_v, pb_v, close in con.execute(
            "SELECT code, peTTM, pbMRQ, close FROM v.valuation WHERE date=?", (D,)):
        c6 = code[:6]
        t = ttm.get(c6)
        m = mv.get(code)
        if pe_v and pe_v > 0 and t and m and t > 0:
            pe_calc = m / t
            if pe_calc > 0:
                pe_dev.append(abs(pe_calc - pe_v) / pe_v * 100)
                n_pe += 1
        b = bps.get(code)
        if pb_v and pb_v > 0 and b and b > 0 and close:
            pb_calc = close / b
            pb_dev.append(abs(pb_calc - pb_v) / pb_v * 100)
            n_pb += 1
    for name, devs in (("PE_TTM", pe_dev), ("PB", pb_dev)):
        if devs:
            devs.sort()
            ok1 = sum(1 for x in devs if x < 1)
            ok5 = sum(1 for x in devs if x < 5)
            print(f"  {name:8s} n={len(devs):>5,} | 偏差<1%: {ok1/len(devs)*100:>5.1f}% | "
                  f"<5%: {ok5/len(devs)*100:>5.1f}% | 中位 {devs[len(devs)//2]:>6.2f}% | "
                  f"P90 {devs[int(len(devs)*0.9)]:>7.2f}%")
        else:
            print(f"  {name}: 无可比样本")

    # ---------- V2 除权事件反查 ----------
    print("\n" + "=" * 100)
    print("V2 除权事件反查：跳空行是否都有对应除权事件")
    print("=" * 100)
    ev = {(r[0], r[1]) for r in con.execute(
        "SELECT code, ex_date FROM dv.dividend")}
    print(f"  除权事件库：{len(ev):,} 条")

    q = """
    SELECT code, date, pct_chg FROM main.daily_bar
    WHERE pct_chg IS NOT NULL AND (
          (code LIKE '68%' AND ABS(pct_chg)>0.21) OR
          (code LIKE '30%' AND ABS(pct_chg)>0.21) OR
          (code LIKE '%.BJ' AND ABS(pct_chg)>0.31) OR
          (code NOT LIKE '68%' AND code NOT LIKE '30%' AND code NOT LIKE '%.BJ' AND ABS(pct_chg)>0.11))
    """
    jumps = con.execute(q).fetchall()
    covered = [j for j in jumps if (j[0], j[1]) in ev]
    uncov = [j for j in jumps if (j[0], j[1]) not in ev]
    print(f"  跳空行 {len(jumps):,} 行 | 有除权事件 {len(covered):,} ({len(covered)/max(len(jumps),1)*100:.1f}%) | "
          f"无事件 {len(uncov):,}")

    # 无事件行的原因分类
    by_year = Counter(j[1][:4] for j in uncov)
    big = Counter()
    for code, date, pc in uncov:
        if abs(pc) > 0.5:
            big["|涨跌|>50%（新股/复牌/退市整理）"] += 1
        elif abs(pc) > 0.3:
            big["30-50%"] += 1
        elif abs(pc) > 0.21:
            big["21-30%"] += 1
        else:
            big["11-21%"] += 1
    print(f"  无事件行的幅度分布: {dict(big)}")
    print(f"  按年（前 10）: {by_year.most_common(10)}")

    # 抽样看几只
    print("\n  抽样（无事件的跳空行）:")
    for code, date, pc in uncov[:8]:
        prev = con.execute("SELECT close FROM main.daily_bar WHERE code=? AND date<? "
                           "ORDER BY date DESC LIMIT 1", (code, date)).fetchone()
        cur = con.execute("SELECT close FROM main.daily_bar WHERE code=? AND date=?", (code, date)).fetchone()
        print(f"    {code} {date}: pct={pc*100:+.2f}%  {prev[0] if prev else None} → {cur[0] if cur else None}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
