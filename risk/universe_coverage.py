# -*- coding: utf-8 -*-
"""risk/universe_coverage.py —— 逐年真实 A 股上市集合 vs bars.db 覆盖（幸存者偏差量化）

背景（HANDOFF.md 第五节 P1《数据底座质量报告》需要披露）：
  「幸存者偏差幅度（2010 年 ~16.5%、2025 年 ~0.9%）」——本轮用可重复脚本重新量化。

方法：
  · 真实上市集合：data/cache/datayes_basic.db 的 sec_listed + sec_delisted
    （含 listDate / delistDate），按「Y 年内曾上市」构造逐年 A 股集合
  · bars 覆盖：bars.db 的 daily_bar 逐年 distinct code
  · 幸存者偏差（当年口径）= 1 - |bars ∩ 真实| / |真实|
  · 同时拆分缺口来源：已退市（幸存者偏差）vs 仍在市（其它缺口）

输出：logs/universe_coverage_<时间戳>.json + 控制台表
用法：python risk/universe_coverage.py
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
BARS = CACHE / "bars.db"
DAY = CACHE / "datayes_basic.db"
LOGS = BASE / "logs"


def is_a_share(ticker: str, exch: str) -> bool:
    t = str(ticker or "").strip()
    if not (len(t) == 6 and t.isdigit()):
        return False
    if t.startswith(("200", "900")):     # B 股
        return False
    return str(exch or "").upper() in ("XSHG", "XSHE", "XBSE", "NEEQ")


def main() -> int:
    t0 = datetime.now()
    d = sqlite3.connect(f"file:{DAY.as_posix()}?mode=ro", uri=True, timeout=20)
    ex = d.execute("SELECT exchangeCD, assetClass, COUNT(*) FROM sec_listed "
                   "GROUP BY 1,2 ORDER BY 3 DESC").fetchall()
    print("sec_listed (exchangeCD, assetClass, n):", ex[:8])

    secs: dict[str, dict] = {}
    for tbl in ("sec_listed", "sec_delisted"):
        for ticker, exch, ld, dd in d.execute(
                f"SELECT ticker, exchangeCD, listDate, delistDate FROM {tbl}"):
            if not is_a_share(ticker, exch):
                continue
            t = str(ticker).strip()
            cur = secs.setdefault(t, {"list": None, "delist": None})
            if ld and (cur["list"] is None or str(ld) < cur["list"]):
                cur["list"] = str(ld)[:10]
            if dd:
                v = str(dd)[:10]
                if cur["delist"] is None or v > cur["delist"]:
                    cur["delist"] = v
    d.close()
    print(f"识别出 A 股证券（含已退市）: {len(secs):,} 只，"
          f"其中已退市 {sum(1 for v in secs.values() if v['delist']):,} 只")

    b = sqlite3.connect(f"file:{BARS.as_posix()}?mode=ro", uri=True, timeout=30)
    bars_by_year: dict[str, set[str]] = {}
    for yr, code in b.execute("SELECT DISTINCT substr(date,1,4), code FROM daily_bar WHERE adjust='qfq'"):
        bars_by_year.setdefault(yr, set()).add(code.split(".")[0])
    b.close()

    rows = []
    print("\n年份  真实A股  bars覆盖  覆盖率   缺口   其中已退市  其中在市")
    for yr in sorted(bars_by_year):
        y = int(yr)
        if y < 2000:
            continue
        y_start, y_end = f"{y}-01-01", f"{y}-12-31"
        truth = {t for t, v in secs.items()
                 if v["list"] and v["list"] <= y_end and (not v["delist"] or v["delist"] >= y_start)}
        if not truth:
            continue
        bars = bars_by_year[yr]
        hit = truth & bars
        miss = truth - bars
        miss_delisted = {t for t in miss if secs[t]["delist"]}
        miss_alive = miss - miss_delisted
        cov = len(hit) / len(truth)
        rows.append({"year": y, "truth": len(truth), "bars": len(bars), "hit": len(hit),
                     "coverage": round(cov, 4), "missing": len(miss),
                     "missing_delisted": len(miss_delisted), "missing_alive": len(miss_alive),
                     "survivorship_bias": round(1 - cov, 4)})
        print(f"{y}  {len(truth):>7,} {len(bars):>8,}  {cov*100:>6.1f}%  {len(miss):>6,}"
              f"  {len(miss_delisted):>10,}  {len(miss_alive):>8,}")

    rep = {"ts": t0.strftime("%Y-%m-%d %H:%M:%S"),
           "method": "datayes sec_listed+sec_delisted 构造逐年 A 股集合 vs bars.db 逐年 distinct code",
           "a_share_total": len(secs),
           "delisted_total": sum(1 for v in secs.values() if v["delist"]),
           "by_year": rows}
    LOGS.mkdir(exist_ok=True)
    out = LOGS / f"universe_coverage_{t0.strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
