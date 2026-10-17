# -*- coding: utf-8 -*-
"""data/build_stock_info.py —— 汇总股票基础信息 → bars_tdx.db 的 stock_info 表

来源（全部本地已有，零成本）：
  stock_basic.db.stock_basic  → code, name, industry, ipo_date, out_date, status
  datayes_basic.db.sec_delisted → ticker/exchangeCD/delistDate（退市日，权威）
  datayes_basic.db.sec_listed   → 上市股清单
  industry.db.sw_index          → 申万行业（可选）
输出：bars_tdx.db 的 stock_info 表：
  code, name, industry, ipo_date, delist_date, status, is_delisted
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
C = Path(r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant\data\cache")


def norm(c):
    """统一成 xxx.SZ / xxx.SH / xxx.BJ"""
    s = str(c).strip().upper().replace("XSHE", "SZ").replace("XSHG", "SH").replace("XBEI", "BJ")
    if "." in s:
        n, e = s.split(".")[:2]
        return f"{n.zfill(6)}.{e}"
    if s.startswith(("SZ", "SH", "BJ")):
        return f"{s[2:].zfill(6)}.{s[:2]}"
    return f"{s.zfill(6)}"


def main():
    # 1. 项目 stock_basic.db
    con = sqlite3.connect(str(C / "stock_basic.db"))
    sb = pd.read_sql("SELECT * FROM stock_basic", con)
    con.close()
    sb["code"] = sb["code"].map(norm)
    print(f"stock_basic.db: {len(sb):,} 行, 字段 {list(sb.columns)}")
    sb = sb.rename(columns={"industry": "industry", "ipo_date": "ipo_date",
                            "out_date": "out_date_stale", "status": "status"})

    # 2. 通联退市清单（权威退市日）
    con = sqlite3.connect(str(C / "datayes_basic.db"))
    de = pd.read_sql("SELECT ticker, exchangeCD, secShortName, listDate, delistDate FROM sec_delisted", con)
    ls = pd.read_sql("SELECT ticker, exchangeCD, secShortName, listDate FROM sec_listed", con)
    con.close()
    for d in (de, ls):
        d["code"] = d.apply(
            lambda r: f"{str(r['ticker']).zfill(6)}." +
                      ("SZ" if r["exchangeCD"] == "XSHE" else
                       "SH" if r["exchangeCD"] == "XSHG" else
                       "BJ" if r["exchangeCD"] == "XBEI" else "XX"), axis=1)
    # 只保留沪深北
    de = de[de["code"].str.endswith((".SZ", ".SH", ".BJ"))]
    ls = ls[ls["code"].str.endswith((".SZ", ".SH", ".BJ"))]
    print(f"通联退市清单（沪深北）: {len(de):,} 行")
    print(f"通联上市清单（沪深北）: {len(ls):,} 行")

    # 3. 合并
    info = pd.DataFrame({"code": sorted(set(sb["code"]) | set(de["code"]) | set(ls["code"]))})
    info = info.merge(sb[["code", "name", "industry", "ipo_date", "out_date_stale", "status"]],
                      on="code", how="left")
    info = info.merge(de[["code", "secShortName", "delistDate"]].rename(
        columns={"secShortName": "name_yes_de", "delistDate": "delist_date"}),
        on="code", how="left")
    info = info.merge(ls[["code", "secShortName", "listDate"]].rename(
        columns={"secShortName": "name_yes_ls", "listDate": "list_date_yes"}),
        on="code", how="left")

    # 补名称：优先项目 name，其次通联
    info["name"] = info["name"].fillna(info["name_yes_de"]).fillna(info["name_yes_ls"])
    info["is_delisted"] = info["delist_date"].notna().astype(int)
    # status 统一为 listed / delisted（原 stock_basic.status 是数字/其他值，统一化）
    info["status_final"] = info["is_delisted"].map({1: "delisted", 0: "listed"})

    out = info[["code", "name", "industry", "ipo_date", "delist_date",
                "status_final", "is_delisted"]].rename(columns={"status_final": "status"})
    out = out.dropna(subset=["code"])

    con = sqlite3.connect(str(C / "bars_tdx.db"))
    out.to_sql("stock_info", con, if_exists="replace", index=False)
    con.execute("CREATE INDEX IF NOT EXISTS idx_si_code ON stock_info(code)")
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM stock_info").fetchone()[0]
    n_del = con.execute("SELECT COUNT(*) FROM stock_info WHERE is_delisted=1").fetchone()[0]
    con.close()

    print(f"\nstock_info 表：{n:,} 行")
    print(f"  含退市日（is_delisted=1）: {n_del:,}")
    print(f"  名称缺失: {out['name'].isna().sum():,}")
    print(f"  行业缺失: {out['industry'].isna().sum():,}")
    print(f"\n样例：\n{out.head(5).to_string(index=False)}")
    print(f"\n退市股样例：\n{out[out['is_delisted'] == 1].head(5).to_string(index=False)}")


if __name__ == "__main__":
    main()
