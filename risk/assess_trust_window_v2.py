# -*- coding: utf-8 -*-
"""risk/assess_trust_window_v2.py —— DS-17 复评（v2：用切换后的新库事实）

与 v1 的区别（因为数据源换了，结论可能变）：
  · PIT：改用 `tdx_finance.db` 的 `announce_date`（覆盖 100%），不再用 CSMAR（只有 72-78%）
  · 估值/市值：改用 `valuation.db`（2000-04 起）/ `hist_mv.db`（319 个月）
  · 换手：`bars.db.turn`
  · 退市覆盖：同 v1（datayes 真实清单）
新增：**每股收益异常检测**（qfq 日收益超出板块涨跌停幅度的比例）——除权处理是否正确的最强自证

用法：python risk/assess_trust_window_v2.py
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent.parent
CACHE = BASE / "data" / "cache"


def main() -> int:
    con = sqlite3.connect(f"file:{(CACHE / 'bars.db').as_posix()}?mode=ro", uri=True, timeout=60)
    con.execute(f"ATTACH DATABASE '{(CACHE / 'tdx_base.db').as_posix()}' AS k")
    con.execute(f"ATTACH DATABASE '{(CACHE / 'valuation.db').as_posix()}' AS v")
    con.execute(f"ATTACH DATABASE '{(CACHE / 'hist_mv.db').as_posix()}' AS mv")
    con.execute(f"ATTACH DATABASE '{(CACHE / 'tdx_finance.db').as_posix()}' AS f")
    con.execute(f"ATTACH DATABASE '{(CACHE / 'datayes_basic.db').as_posix()}' AS d")

    print("① 行情/换手/估值/市值 按年 …", flush=True)
    bars = {}
    for r in con.execute("""
        SELECT substr(date,1,4) y, COUNT(*), COUNT(DISTINCT code),
               SUM(close IS NULL), SUM(turn IS NULL)
        FROM main.daily_bar GROUP BY y ORDER BY y"""):
        bars[r[0]] = {"rows": r[1], "codes": r[2], "close_null": r[3], "turn_null": r[4]}

    print("② 估值/市值覆盖 …", flush=True)
    pe_null = {r[0]: (r[1], r[2]) for r in con.execute(
        "SELECT substr(date,1,4), COUNT(*), SUM(peTTM IS NULL) FROM v.valuation GROUP BY 1")}
    mv_months = {r[0]: r[1] for r in con.execute(
        "SELECT substr(month,1,4), COUNT(DISTINCT month) FROM mv.hist_mv GROUP BY 1")}

    print("③ PIT（通达信披露日）…", flush=True)
    pit = {r[0]: (r[1], r[2]) for r in con.execute(
        "SELECT substr(period,1,4), COUNT(*), SUM(announce_date IS NOT NULL AND announce_date<>'') "
        "FROM f.fin_tdx GROUP BY 1")}

    print("④ 退市覆盖 …", flush=True)
    secs = {}
    for tbl in ("sec_listed", "sec_delisted"):
        for t, exch, ld, dd in con.execute(
                f"SELECT ticker, exchangeCD, listDate, delistDate FROM d.{tbl}"):
            t = str(t or "").strip()
            if not (len(t) == 6 and t.isdigit()) or t.startswith(("200", "900")):
                continue
            if str(exch or "").upper() not in ("XSHG", "XSHE", "XBSE", "NEEQ"):
                continue
            cur = secs.setdefault(t, {"list": None, "delist": None})
            if ld and (cur["list"] is None or str(ld) < cur["list"]):
                cur["list"] = str(ld)[:10]
            if dd and (cur["delist"] is None or str(dd) > cur["delist"]):
                cur["delist"] = str(dd)[:10]
    have = {r[0] for r in con.execute("SELECT DISTINCT code FROM main.daily_bar")}
    cover = {}
    for y in sorted(bars):
        yi = int(y)
        truth = {t for t, x in secs.items()
                 if x["list"] and x["list"] <= f"{yi}-12-31"
                 and (not x["delist"] or x["delist"] >= f"{yi}-01-01")}
        if truth:
            hit = sum(1 for t in truth if (t + ".SH" if t[0] in "69" else t + ".SZ") in have)
            cover[y] = round(hit / len(truth) * 100, 1)

    print("⑤ 涨跌幅异常（qfq 日收益超 ±11%/±21%/±31%）…", flush=True)
    abnormal = {}
    for y, n, bad in con.execute("""
        SELECT substr(date,1,4) y, COUNT(*),
               SUM(CASE WHEN pct_chg IS NOT NULL AND (
                     (code LIKE '68%' AND ABS(pct_chg)>0.21) OR
                     (code LIKE '30%' AND ABS(pct_chg)>0.21) OR
                     (code LIKE '%.BJ' AND ABS(pct_chg)>0.31) OR
                     (code NOT LIKE '68%' AND code NOT LIKE '30%' AND code NOT LIKE '%.BJ'
                      AND ABS(pct_chg)>0.11)
                   ) THEN 1 ELSE 0 END)
        FROM main.daily_bar WHERE date>='2000-04-03' GROUP BY y ORDER BY y"""):
        abnormal[y] = (n, bad or 0)

    print("\n" + "=" * 128)
    print(f"{'年':5s}{'行数':>10s}{'股票':>6s}{'close缺':>8s}{'turn缺':>7s}{'pe缺%':>7s}"
          f"{'mv月':>5s}{'PIT%':>7s}{'退市%':>7s}{'涨跌幅异常':>10s}  判定")
    print("=" * 128)
    rows = []
    for y in sorted(bars):
        b = bars[y]
        n = max(b["rows"], 1)
        pn = pe_null.get(y)
        pe_pct = round(100 * pn[1] / max(pn[0], 1), 1) if pn else None
        pp = pit.get(y)
        pit_pct = round(100 * pp[1] / max(pp[0], 1), 1) if pp else None
        ab = abnormal.get(y, (0, 0))
        ab_pct = round(100 * ab[1] / max(ab[0], 1), 3)
        probs = []
        if 100 * b["close_null"] / n > 1:
            probs.append("close缺")
        if 100 * b["turn_null"] / n > 1:
            probs.append("turn缺")
        if mv_months.get(y, 0) < 12:
            probs.append("mv月")
        if pit_pct is not None and pit_pct < 95:
            probs.append("PIT弱")
        if (cover.get(y) or 0) < 90:
            probs.append("幸存者")
        if ab_pct > 0.5:
            probs.append("涨跌幅异常")
        flag = "✅" if not probs else "⚠️ " + "/".join(probs)
        rows.append({"year": y, "clean": not probs})
        print(f"{y:5s}{b['rows']:>10,}{b['codes']:>6}{100*b['close_null']/n:>8.2f}"
              f"{100*b['turn_null']/n:>7.2f}{str(pe_pct):>7}{mv_months.get(y,0):>5}"
              f"{str(pit_pct):>7}{str(cover.get(y)):>7}{ab_pct:>9.3f}%  {flag}")

    clean = [r["year"] for r in rows if r["clean"]]
    start = None
    for i in range(len(clean) - 2):
        if int(clean[i + 1]) == int(clean[i]) + 1 and int(clean[i + 2]) == int(clean[i]) + 2:
            start = clean[i]
            break
    print("\n" + "=" * 128)
    print(f"完全无问题年份: {clean}")
    print(f"建议主回测起点（连续 3 年无问题的第一年）: **{start}**")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
