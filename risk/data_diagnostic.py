# -*- coding: utf-8 -*-
"""risk/data_diagnostic.py —— 全面数据诊断（逐库盘点 + 量化已知缺陷 + 数据源可靠性评估）

只读，SQL 聚合，输出 report/data_diagnostic_report.{md,json}。
覆盖：bars.db（源/年份/量额/ST/qfq复权）、finance.db（字段/期间）、hist_mv、stock_basic。
用法：python risk/data_diagnostic.py
"""
import json
import sqlite3
import sys
import warnings
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = Path(__file__).resolve().parent.parent
CACHE = BASE / "data" / "cache"


def _conn(db):
    return sqlite3.connect(f"file:{CACHE / db}?mode=ro", uri=True)


def _one(con, sql, args=()):
    try:
        return con.execute(sql, args).fetchone()
    except Exception as e:
        return ("ERR", str(e))


def diag_bars():
    """bars.db：源/年份/量额/ST/复权。"""
    con = _conn("bars.db")
    out = {}
    out["全表"] = _one(con, "SELECT COUNT(*), COUNT(DISTINCT code), MIN(date), MAX(date) FROM daily_bar")
    out["按source"] = [
        {"source": r[0], "rows": r[1], "date_range": f"{r[2]}~{r[3]}",
         "amount缺失率": f"{r[4]/r[1]*100:.1f}%", "avg_volume": round(r[5], 0) if r[5] else None}
        for r in con.execute("""SELECT source, COUNT(*), MIN(date), MAX(date),
            SUM(CASE WHEN amount IS NULL OR amount=0 THEN 1 ELSE 0 END),
            AVG(volume)
            FROM daily_bar GROUP BY source""").fetchall()]
    # 逐年股票数 + amount 缺失率
    out["逐年"] = [
        {"year": r[0], "rows": r[1], "stocks": r[2],
         "amount缺失率": f"{r[3]/r[1]*100:.1f}%" if r[1] else "0%"}
        for r in con.execute("""SELECT substr(date,1,4), COUNT(*), COUNT(DISTINCT code),
            SUM(CASE WHEN amount IS NULL OR amount=0 THEN 1 ELSE 0 END)
            FROM daily_bar GROUP BY substr(date,1,4) ORDER BY 1""").fetchall()]
    # is_st 分布
    out["is_st"] = _one(con, "SELECT is_st, COUNT(*) FROM daily_bar WHERE is_st!=0")
    out["is_st_非0行数"] = _one(con, "SELECT COUNT(*) FROM daily_bar WHERE is_st!=0")[0]
    # qfq 复权：pct_chg 与 close/preclose 偏差（量化除权日影响）
    dev = _one(con, """SELECT COUNT(*), AVG(ABS(pct_chg - (close/preclose-1)*100))
        FROM daily_bar WHERE preclose>0 AND pct_chg IS NOT NULL
        AND ABS(pct_chg - (close/preclose-1)*100) > 0.5""")
    out["qfq_preclose偏差"] = {"行数": dev[0], "占比": f"{dev[0]/13420592*100:.1f}%", "平均偏差pp": round(dev[1], 3) if dev[1] else None}
    con.close()
    return out


def diag_finance():
    con = _conn("finance.db")
    out = {}
    out["全表"] = _one(con, "SELECT COUNT(*), COUNT(DISTINCT code), MIN(period), MAX(period) FROM finance_report")
    out["source"] = con.execute("SELECT source, COUNT(*) FROM finance_report GROUP BY source").fetchall()
    cols = ["net_profit", "revenue", "sq_net_profit", "sq_net_yoy", "sq_revenue", "sq_rev_yoy", "eps", "roe"]
    out["字段null率"] = {}
    for c in cols:
        n = _one(con, f"SELECT COUNT(*) FROM finance_report WHERE {c} IS NULL")[0]
        tot = _one(con, "SELECT COUNT(*) FROM finance_report")[0]
        out["字段null率"][c] = f"{n/tot*100:.1f}%"
    con.close()
    return out


def diag_hist_mv():
    con = _conn("hist_mv.db")
    out = {}
    out["全表"] = _one(con, "SELECT COUNT(*), COUNT(DISTINCT code), MIN(month), MAX(month) FROM hist_mv")
    out["逐年股票数"] = con.execute(
        "SELECT substr(month,1,4), COUNT(DISTINCT code) FROM hist_mv GROUP BY substr(month,1,4) ORDER BY 1").fetchall()
    con.close()
    return out


def diag_stock_basic():
    con = _conn("stock_basic.db")
    out = {}
    out["全表"] = _one(con, "SELECT COUNT(*), COUNT(DISTINCT code) FROM stock_basic")
    out["name含ST"] = _one(con, "SELECT COUNT(*) FROM stock_basic WHERE name LIKE '%ST%'")[0]
    out["name含退"] = _one(con, "SELECT COUNT(*) FROM stock_basic WHERE name LIKE '%退%'")[0]
    out["out_date非空(已退市)"] = _one(con, "SELECT COUNT(*) FROM stock_basic WHERE out_date IS NOT NULL AND out_date!=''")[0]
    out["industry覆盖"] = _one(con, "SELECT COUNT(*) FROM stock_basic WHERE industry IS NOT NULL AND industry!=''")[0]
    con.close()
    return out


def diag_st_cross():
    """交叉校验：stock_basic name 含 ST 的股票，在 bars.db 里 is_st 标记了多少（一次聚合，避免逐只扫描）。"""
    con_b = _conn("bars.db")
    con_s = _conn("stock_basic.db")
    st_names = set(r[0] for r in con_s.execute("SELECT code FROM stock_basic WHERE name LIKE '%ST%'").fetchall())

    def norm(c):
        c = str(c).strip()
        return c.split(".")[0].zfill(6) if "." in c else c.zfill(6)

    st6 = sorted({norm(c) for c in st_names})
    ph = ",".join("?" * len(st6))
    in_bars = con_b.execute(
        f"SELECT COUNT(DISTINCT substr(code,1,6)) FROM daily_bar WHERE substr(code,1,6) IN ({ph})",
        st6).fetchone()[0]
    flagged = con_b.execute(
        f"SELECT COUNT(DISTINCT substr(code,1,6)) FROM daily_bar WHERE is_st=1 AND substr(code,1,6) IN ({ph})",
        st6).fetchone()[0]
    con_b.close()
    con_s.close()
    return {
        "stock_basic_name含ST": len(st6),
        "其中在bars.db有行情": in_bars,
        "is_st被正确标记的股票数": flagged,
        "漏标率": f"{(1 - flagged / max(in_bars, 1)) * 100:.1f}%" if in_bars else "N/A",
        "结论": "is_st 几乎全 0（F-1 未修复）" if flagged <= max(in_bars, 1) * 0.05 else "is_st 基本正常",
    }


def main():
    res = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "bars": diag_bars(),
        "finance": diag_finance(),
        "hist_mv": diag_hist_mv(),
        "stock_basic": diag_stock_basic(),
        "st_cross": diag_st_cross(),
    }
    out_dir = BASE / "report"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"data_diagnostic_report_{ts}.json"
    json_path.write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    # 打印
    print("=" * 70)
    print("全面数据诊断报告")
    print("=" * 70)
    print("\n【1】bars.db（行情）")
    print(f"  全表: {res['bars']['全表']}")
    print("  按 source:")
    for r in res["bars"]["按source"]:
        print(f"    {r['source']:<10} {r['rows']:>10,} 行  {r['date_range']}  amount缺失 {r['amount缺失率']}  avg_volume {r['avg_volume']}")
    print("  逐年（year rows stocks amount缺失率）:")
    for r in res["bars"]["逐年"]:
        print(f"    {r['year']}: {r['rows']:>9,} 行 / {r['stocks']:>5} 只 / amount缺失 {r['amount缺失率']}")
    print(f"  is_st: 非0 共 {res['bars']['is_st_非0行数']} 行（F-1 全0缺陷）")
    print(f"  qfq复权偏差: {res['bars']['qfq_preclose偏差']}")

    print("\n【2】finance.db（财报）")
    print(f"  全表: {res['finance']['全表']}")
    print(f"  source: {res['finance']['source']}")
    print(f"  字段 null 率: {res['finance']['字段null率']}")

    print("\n【3】hist_mv.db（流通市值）")
    print(f"  全表: {res['hist_mv']['全表']}")
    print(f"  逐年股票数: {res['hist_mv']['逐年股票数']}")

    print("\n【4】stock_basic.db（基础信息）")
    print(f"  全表: {res['stock_basic']['全表']}")
    print(f"  name含ST: {res['stock_basic']['name含ST']} | name含退: {res['stock_basic']['name含退']} | "
          f"out_date非空: {res['stock_basic']['out_date非空(已退市)']} | industry覆盖: {res['stock_basic']['industry覆盖']}")

    print("\n【5】ST 交叉校验")
    for k, v in res["st_cross"].items():
        print(f"  {k}: {v}")

    print(f"\n结果已存: {json_path}")


if __name__ == "__main__":
    main()
