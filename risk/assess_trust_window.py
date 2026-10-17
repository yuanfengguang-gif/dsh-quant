# -*- coding: utf-8 -*-
"""risk/assess_trust_window.py —— DS-17：用新库重评「数据可信起点」

产出：年份 × 6 项指标的可信度表 + 结论（主回测窗口建议从哪年起）
指标：
  ① 行情完整性：当年行数 / 股票数 / close 缺失率
  ② 换手率：turn 缺失率（旧铁律③说 2019 前缺失，新源是否仍成立）
  ③ 估值：pe_ttm / pb 缺失率
  ④ 市值：circ_mv 缺失率 + hist_mv_new 当年月份数
  ⑤ PIT：CSMAR 年报 publish_date 非空率（按 fiscal year）
  ⑥ 退市股覆盖：当年「真实 A 股」中被 bars 覆盖的比例（幸存者偏差）

用法：python risk/assess_trust_window.py
输出：logs/trust_window_<ts>.json + output/TRUST_WINDOW_<date>.md
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent.parent
CACHE = BASE / "data" / "cache"
NEW_BARS = CACHE / "tdx_qfq.db"
BASE_DB = CACHE / "tdx_base.db"
MV = CACHE / "hist_mv_new.db"
FIN = CACHE / "finance_csmar.db"
DAY = CACHE / "datayes_basic.db"


def main() -> int:
    con = sqlite3.connect(f"file:{BASE_DB.as_posix()}?mode=ro", uri=True, timeout=60)
    con.execute(f"ATTACH DATABASE '{(NEW_BARS).as_posix()}' AS q")
    con.execute(f"ATTACH DATABASE '{(MV).as_posix()}' AS mv")
    con.execute(f"ATTACH DATABASE '{(FIN).as_posix()}' AS f")
    con.execute(f"ATTACH DATABASE '{(DAY).as_posix()}' AS d")

    print("① 行情/换手/估值/市值 按年 …", flush=True)
    bars = {}
    for r in con.execute("""
        SELECT substr(date,1,4) y, COUNT(*), COUNT(DISTINCT code),
               SUM(close IS NULL), SUM(turnover IS NULL), SUM(pe_ttm IS NULL),
               SUM(pb IS NULL), SUM(circ_mv IS NULL)
        FROM daily GROUP BY y ORDER BY y"""):
        y, n, codes, nc, nt, npe, npb, nmv = r
        bars[y] = {"rows": n, "codes": codes,
                   "close_null": nc, "turn_null": nt, "pe_null": npe,
                   "pb_null": npb, "mv_null": nmv}

    print("② hist_mv_new 月度覆盖 …", flush=True)
    mv_months = {r[0]: r[1] for r in con.execute(
        "SELECT substr(month,1,4), COUNT(DISTINCT month) FROM mv.hist_mv GROUP BY 1")}
    mv_codes = {r[0]: r[1] for r in con.execute(
        "SELECT substr(month,1,4), COUNT(DISTINCT code) FROM mv.hist_mv GROUP BY 1")}

    print("③ PIT（CSMAR publish_date）…", flush=True)
    pit = {r[0]: (r[1], r[2]) for r in con.execute("""
        SELECT substr(period,1,4) y, COUNT(*),
               SUM(CASE WHEN publish_date IS NOT NULL AND publish_date<>'' THEN 1 ELSE 0 END)
        FROM f.fin_core GROUP BY y""")}

    print("④ 退市股覆盖（幸存者偏差）…", flush=True)
    secs = {}
    for tbl in ("sec_listed", "sec_delisted"):
        for ticker, exch, ld, dd in con.execute(
                f"SELECT ticker, exchangeCD, listDate, delistDate FROM d.{tbl}"):
            t = str(ticker or "").strip()
            if not (len(t) == 6 and t.isdigit()) or t.startswith(("200", "900")):
                continue
            if str(exch or "").upper() not in ("XSHG", "XSHE", "XBSE", "NEEQ"):
                continue
            cur = secs.setdefault(t, {"list": None, "delist": None})
            if ld and (cur["list"] is None or str(ld) < cur["list"]):
                cur["list"] = str(ld)[:10]
            if dd:
                v = str(dd)[:10]
                if cur["delist"] is None or v > cur["delist"]:
                    cur["delist"] = v
    have = {r[0] for r in con.execute("SELECT DISTINCT code FROM q.daily_bar")}
    cover = {}
    for y in sorted(bars):
        yi = int(y)
        truth = {t for t, v in secs.items()
                 if v["list"] and v["list"] <= f"{yi}-12-31"
                 and (not v["delist"] or v["delist"] >= f"{yi}-01-01")}
        if not truth:
            continue
        hit = sum(1 for t in truth
                  if (t + ".SH" if t[0] in "69" else t + ".SZ") in have)
        cover[y] = (len(truth), hit, round(hit / len(truth) * 100, 1))

    # ---- 汇总表 ----
    rows = []
    for y in sorted(bars):
        b = bars[y]
        n = b["rows"] or 1
        pit_pop = pit.get(y)
        pit_rate = round(pit_pop[1] / pit_pop[0] * 100, 1) if pit_pop and pit_pop[0] else None
        cv = cover.get(y)
        rows.append({
            "year": y, "rows": b["rows"], "codes": b["codes"],
            "close_null_pct": round(100 * b["close_null"] / n, 3),
            "turn_null_pct": round(100 * b["turn_null"] / n, 3),
            "pe_null_pct": round(100 * b["pe_null"] / n, 2),
            "pb_null_pct": round(100 * b["pb_null"] / n, 3),
            "mv_null_pct": round(100 * b["mv_null"] / n, 3),
            "mv_months": mv_months.get(y, 0), "mv_codes": mv_codes.get(y, 0),
            "pit_publish_pct": pit_rate,
            "survivor_truth": cv[0] if cv else None,
            "survivor_hit": cv[1] if cv else None,
            "survivor_cov_pct": cv[2] if cv else None,
        })

    print("\n" + "=" * 118)
    print(f"{'年':5s}{'行数':>10s}{'股票':>6s}{'close缺':>8s}{'turn缺':>8s}{'pe缺':>7s}"
          f"{'pb缺':>7s}{'市值缺':>8s}{'mv月':>5s}{'PIT%':>7s}{'退市覆盖%':>10s}  判定")
    print("=" * 118)
    for r in rows:
        problems = []
        if r["close_null_pct"] > 1:
            problems.append("close缺")
        if r["turn_null_pct"] > 1:
            problems.append("turn缺")
        if r["pe_null_pct"] > 30:
            problems.append("pe缺")
        if r["mv_months"] < 12:
            problems.append("mvd月")
        if r["pit_publish_pct"] is not None and r["pit_publish_pct"] < 80:
            problems.append("PIT弱")
        if r["survivor_cov_pct"] is not None and r["survivor_cov_pct"] < 90:
            problems.append("幸存者偏差")
        verdict = "✅" if not problems else "⚠️ " + "/".join(problems)
        print(f"{r['year']:5s}{r['rows']:>10,}{r['codes']:>6}{r['close_null_pct']:>8.2f}"
              f"{r['turn_null_pct']:>8.2f}{r['pe_null_pct']:>7.1f}{r['pb_null_pct']:>7.2f}"
              f"{r['mv_null_pct']:>8.2f}{r['mv_months']:>5}{str(r['pit_publish_pct']):>7}"
              f"{str(r['survivor_cov_pct']):>10}  {verdict}")

    # 结论：第一个「连续 3 年无问题」的年份
    good = [r["year"] for r in rows
            if r["close_null_pct"] <= 1 and r["turn_null_pct"] <= 1
            and r["mv_months"] >= 12
            and (r["survivor_cov_pct"] or 0) >= 90]
    start = None
    for i in range(len(good) - 2):
        if int(good[i + 1]) == int(good[i]) + 1 and int(good[i + 2]) == int(good[i]) + 2:
            start = good[i]
            break
    print("\n" + "=" * 118)
    print(f"无问题年份: {good}")
    print(f"建议主回测起点（连续 3 年无问题的第一年）: **{start}**")

    out = BASE / "logs" / f"trust_window_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps({"ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                               "rows": rows, "clean_years": good,
                               "suggested_start": start},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"JSON: {out}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
