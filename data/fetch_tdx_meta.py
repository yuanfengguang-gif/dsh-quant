# -*- coding: utf-8 -*-
"""data/fetch_tdx_meta.py —— 用通达信 API 补齐项目缺的基础数据

下载清单（单进程内完成，成本 ≈ 1 积分）：
  M1 全市场股票列表（沪/深/北）
  M2 全市场基础信息批量（IsSTGP/IsQuitGP/BelongHS300/J_*财务快照）
  M3 指数成分股（上证50/沪深300/中证500/中证1000/创业板指/科创50）
  M4 板块列表 + 板块成分（行业/概念）
  M5 除权除息明细（全市场，复权校验）
  M6 股本信息（全市场）
输出：data/cache/tdx_meta.db
用法：python data/fetch_tdx_meta.py [--skip-divid] [--skip-gb]
"""
import argparse
import sqlite3
import sys
import time
from pathlib import Path

import pandas as pd
from tdxaidata import tqs

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DB = Path(r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant\data\cache\tdx_meta.db")

MAIN_INDEX = {
    "000016.SH": "上证50",
    "000300.SH": "沪深300",
    "000905.SH": "中证500",
    "000852.SH": "中证1000",
    "399006.SZ": "创业板指",
    "000688.SH": "科创50",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-divid", action="store_true")
    ap.add_argument("--skip-gb", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB))

    # ---------- M1 全市场股票列表（market=5 全市场；list_type=1 含名称）----------
    print("=" * 66)
    print("M1 全市场股票列表")
    print("=" * 66)
    all_codes, rows = [], []
    try:
        lst = tqs.get_stock_list(5, 1)          # 5=全市场, 1=返回带名称
        if not isinstance(lst, str):
            for it in lst:
                if isinstance(it, dict):
                    c, n = it.get("Code"), it.get("Name")
                else:
                    c, n = str(it), None
                if c:
                    rows.append({"code": c, "name": n,
                                 "market": c.split(".")[-1] if "." in c else "?"})
                    all_codes.append(c)
    except Exception as e:
        print(f"  ❌ {type(e).__name__}: {e}")
    # 兜底：分批取
    if not all_codes:
        for mkt, name in [(0, "SH"), (1, "SZ"), (2, "BJ")]:
            try:
                l2 = tqs.get_stock_list(mkt, 0)
                l2 = list(l2) if not isinstance(l2, str) else []
                print(f"  {name}: {len(l2):,}")
                for c in l2:
                    rows.append({"code": c, "name": None, "market": name})
                all_codes.extend(l2)
            except Exception:
                pass
    df_uni = pd.DataFrame(rows).drop_duplicates(subset=["code"])
    df_uni.to_sql("universe", con, if_exists="replace", index=False)
    con.commit()
    print(f"  合计 {len(df_uni):,} 只（含名称 {df_uni['name'].notna().sum():,}）→ 表 universe")
    for mk in ("SH", "SZ", "BJ"):
        print(f"    {mk}: {(df_uni['market'] == mk).sum():,}")

    if not all_codes:
        print("❌ 股票列表为空，终止")
        con.close()
        return

    # ---------- M2 全市场基础信息批量 ----------
    print("\n" + "=" * 66)
    print("M2 全市场基础信息（IsSTGP / IsQuitGP / 指数归属 / 财务快照）")
    print("=" * 66)
    info_rows, batch = [], 200
    for i in range(0, len(all_codes), batch):
        b = all_codes[i:i + batch]
        try:
            r = tqs.get_stock_info_batch(b)
            if isinstance(r, dict):
                for code, v in r.items():
                    if isinstance(v, dict) and v:
                        d = {"code": code}
                        d.update({k: str(val) for k, val in v.items()})
                        info_rows.append(d)
        except Exception as e:
            if i < batch * 2:
                print(f"  批{i//batch} ❌ {type(e).__name__}: {e}")
        if i % (batch * 10) == 0:
            print(f"  进度 {i+len(b):,}/{len(all_codes):,}  已收 {len(info_rows):,}  "
                  f"耗时 {time.time()-t0:.0f}s", flush=True)
    if info_rows:
        df_info = pd.DataFrame(info_rows)
        df_info.to_sql("stock_info_tdx", con, if_exists="replace", index=False)
        con.commit()
        print(f"  ✅ {len(df_info):,} 行 × {len(df_info.columns)} 列 → 表 stock_info_tdx")
        for c in ("IsSTGP", "IsQuitGP", "BelongHS300", "BelongRZRQ", "BelongHSGT"):
            if c in df_info.columns:
                n = (df_info[c].astype(str) == "1").sum()
                print(f"    {c}=1: {n:,} 只")

    # ---------- M3 指数成分股 ----------
    print("\n" + "=" * 66)
    print("M3 指数成分股")
    print("=" * 66)
    idx_rows = []
    for ic, iname in MAIN_INDEX.items():
        try:
            mem = tqs.get_zzgz_stocklist(ic, 0)
            mem = list(mem) if not isinstance(mem, str) else []
            print(f"  {iname}（{ic}）: {len(mem)} 只")
            for c in mem:
                idx_rows.append({"index_code": ic, "index_name": iname, "code": c})
        except Exception as e:
            print(f"  {iname}: ❌ {type(e).__name__}: {e}")
    if idx_rows:
        pd.DataFrame(idx_rows).to_sql("index_member", con, if_exists="replace", index=False)
        con.commit()
        print(f"  ✅ {len(idx_rows):,} 条成分记录 → 表 index_member")

    # ---------- M4 板块列表 + 成分 ----------
    print("\n" + "=" * 66)
    print("M4 板块列表 + 成分股")
    print("=" * 66)
    try:
        secs = tqs.get_sector_list()
        secs = list(secs) if not isinstance(secs, str) else []
        print(f"  板块数: {len(secs):,}")
        pd.DataFrame({"sector_code": secs}).to_sql("sector", con, if_exists="replace", index=False)
        con.commit()
        sec_rows = []
        for i, sc in enumerate(secs):
            try:
                mem = tqs.get_stock_list_in_sector(sc)
                mem = list(mem) if not isinstance(mem, str) else []
                for c in mem:
                    sec_rows.append({"sector_code": sc, "code": c})
            except Exception:
                pass
            if i % 50 == 0:
                print(f"    板块成分进度 {i}/{len(secs)}，累计 {len(sec_rows):,}  耗时 {time.time()-t0:.0f}s",
                      flush=True)
        if sec_rows:
            pd.DataFrame(sec_rows).to_sql("sector_member", con, if_exists="replace", index=False)
            con.commit()
            print(f"  ✅ {len(sec_rows):,} 条板块成分 → 表 sector_member")
    except Exception as e:
        print(f"  ❌ {type(e).__name__}: {e}")

    # ---------- M5 除权除息 ----------
    if not args.skip_divid:
        print("\n" + "=" * 66)
        print("M5 除权除息明细（全市场）")
        print("=" * 66)
        div_rows = []
        for i, c in enumerate(all_codes):
            try:
                d = tqs.get_divid_factors(c)
                if isinstance(d, pd.DataFrame) and len(d):
                    d = d.reset_index()
                    d["code"] = c
                    div_rows.append(d)
            except Exception:
                pass
            if i % 200 == 0:
                print(f"  进度 {i:,}/{len(all_codes):,}，累计 {sum(len(x) for x in div_rows):,}  "
                      f"耗时 {time.time()-t0:.0f}s", flush=True)
        if div_rows:
            big = pd.concat(div_rows, ignore_index=True)
            big.to_sql("divid_factor", con, if_exists="replace", index=False)
            con.commit()
            print(f"  ✅ {len(big):,} 行 → 表 divid_factor")

    # ---------- M6 股本 ----------
    if not args.skip_gb:
        print("\n" + "=" * 66)
        print("M6 股本信息（全市场）")
        print("=" * 66)
        gb_rows = []
        for i, c in enumerate(all_codes):
            try:
                g = tqs.get_gb_info(c, 0, 1)
                if isinstance(g, list):
                    for r in g:
                        gb_rows.append({"code": c, **{k: v for k, v in r.items()}})
            except Exception:
                pass
            if i % 200 == 0:
                print(f"  进度 {i:,}/{len(all_codes):,}，累计 {len(gb_rows):,}  "
                      f"耗时 {time.time()-t0:.0f}s", flush=True)
        if gb_rows:
            pd.DataFrame(gb_rows).to_sql("gb_info", con, if_exists="replace", index=False)
            con.commit()
            print(f"  ✅ {len(gb_rows):,} 行 → 表 gb_info")

    # ---------- 汇总 ----------
    print("\n" + "=" * 66)
    print("汇总")
    print("=" * 66)
    for t in [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]:
        n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t}: {n:,} 行")
    con.close()
    print(f"\n库：{DB}")
    print(f"总耗时 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
