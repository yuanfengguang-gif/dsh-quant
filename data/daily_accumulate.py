# -*- coding: utf-8 -*-
"""data/daily_accumulate.py —— 每日累积任务（解决两个数据边界）

每日跑一次，把「快照型」数据逐日累积成历史序列：
  1. lhb 机构席位统计（stock_lhb_jgstatistic_em，近一月快照 → 逐日累积）→ lhb.db lhb_jg_snap
  2. 涨停池/炸板/跌停（stock_zt_pool_em 等，当日 → 逐日累积）→ limitup.db（补齐历史）

用法（每日定时，如 19:15 链后）：
  python data/daily_accumulate.py [--date 20261013]
"""
import argparse
import sqlite3
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import akshare as ak
import pandas as pd

CACHE = BASE / "data" / "cache"


def _append(df: pd.DataFrame, db: str, table: str):
    con = sqlite3.connect(str(CACHE / db))
    df.to_sql(table, con, if_exists="append", index=False)
    con.close()


def accumulate_lhb_jg(day: str):
    """lhb 机构席位统计（近一月快照）→ lhb.db lhb_jg_snap。"""
    try:
        df = ak.stock_lhb_jgstatistic_em(symbol="近一月")
        df.columns = [str(c).strip() for c in df.columns]
        keep = {"代码": "code", "机构买入次数": "jg_buy_cnt", "机构卖出次数": "jg_sell_cnt",
                "机构净买额": "jg_net_amt", "机构买入额": "jg_buy_amt"}
        df = df.rename(columns={k: v for k, v in keep.items() if k in df.columns})
        df = df[[v for v in keep.values() if v in df.columns]].copy()
        df["code"] = df["code"].astype(str).str.zfill(6)
        df["snap_date"] = day
        _append(df, "lhb.db", "lhb_jg_snap")
        print(f"  lhb 机构席位快照: {len(df)} 行 → lhb.db lhb_jg_snap", flush=True)
    except Exception as e:
        print(f"  lhb 机构席位快照失败: {str(e)[:100]}", flush=True)


def accumulate_limitup(day: str):
    """当日涨停/炸板/跌停池 → limitup.db（补齐历史）。"""
    d = day.replace("-", "")
    for fn, table in [(ak.stock_zt_pool_em, "zt_pool"),
                      (ak.stock_zt_pool_zbgc_em, "zbgc_pool"),
                      (ak.stock_zt_pool_dtgc_em, "dtgc_pool")]:
        try:
            df = fn(date=d)
            if df is not None and not df.empty:
                df["date"] = day
                df["code"] = df["代码"].astype(str).str.zfill(6)
                _append(df, "limitup.db", table)
                print(f"  {table}: {len(df)} 行 → limitup.db", flush=True)
        except Exception as e:
            print(f"  {table} 失败: {str(e)[:80]}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat())
    args = ap.parse_args()
    print(f"每日累积（{args.date}）...", flush=True)
    accumulate_lhb_jg(args.date)
    accumulate_limitup(args.date)
    print("完成", flush=True)


if __name__ == "__main__":
    main()
