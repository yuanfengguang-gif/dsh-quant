# -*- coding: utf-8 -*-
"""data/import_csmar.py —— 导入 CSMAR（国泰安）财务数据核心字段

源：
  D:\\BaiduNetdiskDownload\\A股上市公司财务数据（1990-2026.3.31）\\年度最终合并.csv（949 列）
  ...\\季度合并.csv（季度，含单季/累计）
输出：data/cache/finance_csmar.db → fin_core（年度）+ fin_core_q（季度）
关键：保留「年报公布日期」做 PIT；只保留报表类型=A（合并报表）
"""
import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SRC = Path(r"D:\BaiduNetdiskDownload\A股上市公司财务数据（1990-2026.3.31）")
DB = Path(r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant\data\cache\finance_csmar.db")

# 中文列名 → 英文列名（核心字段）
MAP = {
    "证券代码": "code_raw", "年份": "year", "季度日期": "qdate",
    "股票简称": "name", "报表类型编码": "report_type",
    "行业代码": "industry_code", "行业名称": "industry_name", "年报公布日期": "publish_date",
    "营业总收入": "total_revenue", "营业收入": "revenue", "营业成本": "cost",
    "销售费用": "sell_exp", "管理费用": "admin_exp", "研发费用": "rd_exp", "财务费用": "fin_exp",
    "净利润": "net_profit", "归属于母公司所有者的净利润": "np_parent",
    "基本每股收益": "eps", "稀释每股收益": "diluted_eps",
    "资产总计": "total_assets", "股东权益合计": "equity",
    "流动资产合计": "current_assets", "流动负债合计": "current_liab",
    "非流动资产合计": "noncurrent_assets", "非流动负债合计": "noncurrent_liab",
    "应收账款净额": "ar", "存货净额": "inventory", "少数股东权益": "minority_equity",
    "经营活动产生的现金流量净额": "ocf",
    "资产负债率": "debt_ratio", "加权平均净资产收益率": "roe_weighted",
    "净资产收益率（ROE）A": "roe_a", "总资产净利润率(ROA)A": "roa_a",
    "营业毛利率": "gross_margin", "研发费用率": "rd_ratio",
    "净利润增长率A": "np_growth", "营业收入增长率A": "rev_growth",
    "总资产增长率A": "asset_growth",
    "应收账款周转率A": "ar_turnover", "存货周转率A": "inv_turnover",
    "员工数目": "employees",
}


def norm_code(s):
    c = str(s).strip().zfill(6)
    if c.startswith(("6", "9")):
        return f"{c}.SH"
    if c.startswith(("4", "8")):
        return f"{c}.BJ"
    return f"{c}.SZ"


def import_file(csv_path, table, chunksize=200000, period_col="年份"):
    if not csv_path.exists():
        print(f"❌ 文件不存在: {csv_path}")
        return
    print(f"\n=== 导入 {csv_path.name} → {table} ===")
    con = sqlite3.connect(str(DB))
    con.execute("PRAGMA synchronous=OFF")
    total, kept = 0, 0
    first = True
    reader = pd.read_csv(csv_path, encoding="utf-8-sig", chunksize=chunksize,
                         low_memory=False, dtype={"证券代码": str})
    for i, chunk in enumerate(reader):
        total += len(chunk)
        # 只保留合并报表（A）
        if "报表类型编码" in chunk.columns:
            chunk = chunk[chunk["报表类型编码"].astype(str).str.upper().str.startswith("A")]
        use = {k: v for k, v in MAP.items() if k in chunk.columns}
        if not use:
            print(f"  ⚠️ 第{i+1}批未匹配到核心列")
            continue
        out = chunk[list(use.keys())].rename(columns=use).copy()
        out["code"] = out["code_raw"].map(norm_code)
        out = out.drop(columns=["code_raw"])
        # 会计期间：年度表用「年份」，季度表用「季度日期」
        if "qdate" in out.columns:
            out["period"] = pd.to_datetime(out["qdate"], errors="coerce").dt.strftime("%Y-%m-%d")
            out = out.drop(columns=["qdate"])
        elif "year" in out.columns:
            out["period"] = out["year"].astype(str).str[:4] + "-12-31"
        else:
            out["period"] = None
        out = out.dropna(subset=["period"])
        if out.empty:
            continue
        out.to_sql(table, con, if_exists="append" if not first else "replace", index=False)
        con.commit()
        first = False
        kept += len(out)
        print(f"  批{i+1}: 读 {len(chunk):,} 保留 {len(out):,}（累计 {kept:,}）", flush=True)
    # 去重 + 索引
    con.execute(f"""DELETE FROM {table} WHERE rowid NOT IN
                    (SELECT MAX(rowid) FROM {table} GROUP BY code, period)""")
    con.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_code ON {table}(code)")
    con.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_period ON {table}(period)")
    con.commit()
    n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"  完成：{n:,} 行（读入 {total:,}）")
    con.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--which", default="year", choices=["year", "quarter", "both"])
    args = ap.parse_args()
    DB.parent.mkdir(parents=True, exist_ok=True)

    if args.which in ("year", "both"):
        import_file(SRC / "年度最终合并.csv", "fin_core")
    if args.which in ("quarter", "both"):
        import_file(SRC / "季度合并.csv", "fin_core_q")

    con = sqlite3.connect(str(DB))
    print("\n" + "=" * 60)
    for t in [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]:
        n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
        print(f"  {t}: {n:,} 行, {len(cols)} 列")
    print(f"\n库：{DB}")
    con.close()


if __name__ == "__main__":
    main()
