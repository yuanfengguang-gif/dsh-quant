# -*- coding: utf-8 -*-
"""risk/audit_bars_gap.py —— 主库「历史丢行」审计（D-1 的常驻回归闸门）

背景（2026-10-16 质量报告 §3）：
  bars.db（生产主库，仅 qfq 行）相对 bars_tdx.db 缺 673,001 个 (code,date)。
  根因：data/import_tdx.py 的 apply_qfq() 用
      SELECT ... FROM adj_factor WHERE qfq_factor > 0  +  merge(how="inner")
  而 adj_factor.qfq_factor 在 2017 年前大量为非正值（全库 738,755 行 = 4.0%），
  于是这些 (code,date) 不再生成 qfq 行，且不报错 → 茅台等长历史股 2017 年前在主库为空。

用法：
  python risk/audit_bars_gap.py            # 打印审计表；有缺口时退出码 1
  python risk/audit_bars_gap.py --json     # 附 JSON 输出
"""
from __future__ import annotations

import argparse
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
TDX = CACHE / "bars_tdx.db"
LOGS = BASE / "logs"
SPOT = ["600519.SH", "000651.SZ", "600809.SH", "000858.SZ", "600309.SH"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if not TDX.exists():
        print(f"源库不存在，跳过：{TDX}")
        return 0

    rep: dict = {"ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    con = sqlite3.connect(f"file:{BARS.as_posix()}?mode=ro", uri=True, timeout=30)
    con.execute(f"ATTACH 'file:{TDX.as_posix()}?mode=ro' AS t")

    rep["bars_rows"] = con.execute("SELECT COUNT(*) FROM main.daily_bar").fetchone()[0]
    rep["tdx_rows"] = con.execute("SELECT COUNT(*) FROM t.daily_bar").fetchone()[0]
    rep["bars_qfq_rows"] = con.execute(
        "SELECT COUNT(*) FROM main.daily_bar WHERE adjust='qfq'").fetchone()[0]

    missing = con.execute("""
        SELECT COUNT(*) FROM t.daily_bar a
        LEFT JOIN main.daily_bar b ON b.code=a.code AND b.date=a.date AND b.adjust='qfq'
        WHERE b.code IS NULL""").fetchone()[0]
    rep["missing_rows"] = missing

    print("=" * 70)
    print(f"主库丢行审计  {rep['ts']}")
    print("=" * 70)
    print(f"bars.db 总行数 : {rep['bars_rows']:,}（其中 qfq {rep['bars_qfq_rows']:,}）")
    print(f"bars_tdx 行数  : {rep['tdx_rows']:,}")
    print(f"缺失 (code,date): {missing:,}")

    rep["by_year"] = []
    print("\n逐年缺口（bars_tdx 有、bars.db 无）:")
    for y, miss, codes in con.execute("""
            SELECT substr(a.date,1,4) y, COUNT(*), COUNT(DISTINCT a.code)
            FROM t.daily_bar a
            LEFT JOIN main.daily_bar b ON b.code=a.code AND b.date=a.date AND b.adjust='qfq'
            WHERE b.code IS NULL GROUP BY y ORDER BY y"""):
        rep["by_year"].append({"year": y, "missing": miss, "codes": codes})
        print(f"   {y}: 缺 {miss:>7,} 行, 涉及 {codes:>5} 只")

    rep["top_missing"] = []
    print("\n缺失最多的 10 只股票:")
    for code, miss, mn, mx in con.execute("""
            SELECT a.code, COUNT(*), MIN(a.date), MAX(a.date)
            FROM t.daily_bar a
            LEFT JOIN main.daily_bar b ON b.code=a.code AND b.date=a.date AND b.adjust='qfq'
            WHERE b.code IS NULL GROUP BY a.code ORDER BY 2 DESC LIMIT 10"""):
        rep["top_missing"].append({"code": code, "missing": miss, "from": mn, "to": mx})
        print(f"   {code}: 缺 {miss:>6,} 行 ({mn} ~ {mx})")

    rep["spot"] = {}
    print("\n重点个股在主库的起始日 vs 源库:")
    for code in SPOT:
        b_first = con.execute("SELECT MIN(date) FROM main.daily_bar WHERE code=? AND adjust='qfq'",
                              (code,)).fetchone()[0]
        t_first = con.execute("SELECT MIN(date) FROM t.daily_bar WHERE code=?", (code,)).fetchone()[0]
        rep["spot"][code] = {"bars_first": b_first, "tdx_first": t_first}
        flag = "✅" if b_first == t_first else "🔴 缺早期历史"
        print(f"   {flag} {code}: bars.db {b_first} | bars_tdx {t_first}")

    nf = con.execute("SELECT SUM(CASE WHEN qfq_factor<=0 THEN 1 ELSE 0 END), COUNT(*) "
                     "FROM t.adj_factor").fetchone()
    rep["negative_factor_rows"] = nf[0]
    rep["factor_rows"] = nf[1]
    print(f"\nadj_factor 非正因子行: {nf[0]:,} / {nf[1]:,} ({nf[0]/nf[1]*100:.1f}%)"
          f"  ← 与丢行规模同数量级（疑似根因）")
    con.close()

    LOGS.mkdir(exist_ok=True)
    out = LOGS / f"audit_bars_gap_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告: {out}")
    if args.json:
        print(json.dumps(rep, ensure_ascii=False)[:800])
    if missing:
        print(f"\n❌ 审计未通过：主库缺 {missing:,} 行（详见质量报告 D-1）")
        return 1
    print("\n✅ 审计通过：无 (code,date) 缺口")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
