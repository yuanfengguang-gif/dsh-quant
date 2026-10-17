# -*- coding: utf-8 -*-
"""data/fetcher_advanced.py —— 高级数据 fetcher（对齐 a-stock-data 的 4 个关键端点）

数据源（与 a-stock-data 同源）：
  lhb       龙虎榜每日明细 + 机构买卖统计（东财，akshare 封装）→ data/cache/lhb.db
  limitup   涨停池/炸板池/跌停池（东财，akshare 封装）→ data/cache/limitup.db
  valuation 日频 PE/PB/PS/PCF + 换手率 + 停牌 + ST（baostock）→ data/cache/valuation.db
  industry  申万一级/二级行业列表（申万，akshare 封装）→ data/cache/industry.db

用途：解锁主系统最强因子族所需数据——涨停族(limup_ex_5/limup_ex_ret_20)、
资金族(lhb_jg_cnt_20)、价值族(bp=1/PB)。

用法：
  python data/fetcher_advanced.py lhb --start 20260101 --end 20261012
  python data/fetcher_advanced.py limitup --start 20260101 --end 20261012
  python data/fetcher_advanced.py valuation [--codes 000001,600519] [--start 2016-01-01]
  python data/fetcher_advanced.py industry
"""
import argparse
import sqlite3
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import akshare as ak
import pandas as pd

CACHE = BASE / "data" / "cache"


def _conn(db: str) -> sqlite3.Connection:
    CACHE.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(CACHE / db))


def _to_sql(df: pd.DataFrame, db: str, table: str, pk: list):
    con = _conn(db)
    df.to_sql(table, con, if_exists="replace", index=False)
    con.close()
    print(f"  {table}: {len(df)} 行 → {CACHE/db}", flush=True)


# --------------------------------------------------------------------------- #
# 1. 龙虎榜
# --------------------------------------------------------------------------- #
def fetch_lhb(start: str, end: str):
    """龙虎榜每日明细（东财）。start/end 格式 YYYYMMDD。"""
    print(f"拉取龙虎榜 {start} ~ {end} ...", flush=True)
    df = ak.stock_lhb_detail_em(start_date=start, end_date=end)
    if df.empty:
        print("  无数据", flush=True)
        return
    df.columns = [c.strip() for c in df.columns]
    keep = {
        "代码": "code", "名称": "name", "上榜日": "date", "解读": "jiedu",
        "收盘价": "close", "涨跌幅": "pct_chg", "龙虎榜净买额": "net_buy",
        "龙虎榜买入额": "buy", "龙虎榜卖出额": "sell", "龙虎榜成交额": "total",
        "换手率": "turnover", "流通市值": "float_mv", "上榜原因": "reason",
    }
    df = df.rename(columns=keep)[[v for v in keep.values() if v in df.rename(columns=keep).columns]]
    df["code"] = df["code"].astype(str).str.zfill(6)
    _to_sql(df, "lhb.db", "lhb_detail", ["code", "date"])


def fetch_lhb_jgmmtj(start: str, end: str):
    """机构买卖每日统计（东财）——机构净买/净卖，lhb_jg_cnt 类因子的直接输入。"""
    print(f"拉取机构买卖统计 {start} ~ {end} ...", flush=True)
    try:
        df = ak.stock_lhb_jgmmtj_em(start_date=start, end_date=end)
        if df.empty:
            print("  无数据", flush=True)
            return
        df.columns = [c.strip() for c in df.columns]
        keep = {"代码": "code", "名称": "name", "交易日期": "date",
                "龙虎榜成交额": "total", "龙虎榜净买额": "net_buy",
                "机构买入额": "inst_buy", "机构卖出额": "inst_sell",
                "机构净买额": "inst_net", "机构买入占总成交额比": "inst_buy_ratio",
                "机构卖出占总成交额比": "inst_sell_ratio", "上榜原因": "reason"}
        df = df.rename(columns=keep)[[v for v in keep.values() if v in df.rename(columns=keep).columns]]
        df["code"] = df["code"].astype(str).str.zfill(6)
        _to_sql(df, "lhb.db", "lhb_inst", ["code", "date"])
    except Exception as e:
        print(f"  机构统计失败（可忽略）: {str(e)[:100]}", flush=True)


# --------------------------------------------------------------------------- #
# 2. 涨停池
# --------------------------------------------------------------------------- #
def _ymd_to_dash(s: str) -> str:
    """YYYYMMDD → YYYY-MM-DD（bars.db 口径）"""
    s = str(s)
    return f"{s[:4]}-{s[4:6]}-{s[6:]}" if len(s) == 8 and "-" not in s else s


def _fetch_zt_dates(start: str, end: str, fn, table: str, desc: str):
    """按交易日逐日拉涨停/炸板/跌停池。交易日历取 bars.db。"""
    s, e = _ymd_to_dash(start), _ymd_to_dash(end)
    con = sqlite3.connect(f"file:{CACHE/'bars.db'}?mode=ro", uri=True)
    dates = [r[0] for r in con.execute(
        "SELECT DISTINCT date FROM daily_bar WHERE date>=? AND date<=? ORDER BY date",
        (s, e))]
    con.close()
    if not dates:
        print("  无交易日", flush=True)
        return
    print(f"  {desc}: {len(dates)} 个交易日", flush=True)
    frames = []
    for d in dates:
        try:
            df = fn(date=d.replace("-", ""))  # akshare 涨停池用 YYYYMMDD
            if df is not None and not df.empty:
                df["date"] = d
                frames.append(df)
        except Exception:
            pass
        time.sleep(0.3)
    if not frames:
        print("  无数据", flush=True)
        return
    out = pd.concat(frames, ignore_index=True)
    out["code"] = out["代码"].astype(str).str.zfill(6)
    _to_sql(out, "limitup.db", table, ["code", "date"])


def fetch_limitup(start: str, end: str):
    print(f"拉取涨停池 {start} ~ {end} ...", flush=True)
    _fetch_zt_dates(start, end, ak.stock_zt_pool_em, "zt_pool", "涨停池")
    _fetch_zt_dates(start, end, ak.stock_zt_pool_zbgc_em, "zbgc_pool", "炸板池")
    _fetch_zt_dates(start, end, ak.stock_zt_pool_dtgc_em, "dtgc_pool", "跌停池")


# --------------------------------------------------------------------------- #
# 3. 估值历史（baostock）
# --------------------------------------------------------------------------- #
def _bs_code(c: str) -> str:
    """6 位代码 → baostock 格式（sh.600000 / sz.000001 / bj.xxxxxx）。"""
    c = str(c).split(".")[0].zfill(6)
    if c.startswith("6"):
        return f"sh.{c}"
    if c.startswith(("0", "3")):
        return f"sz.{c}"
    if c.startswith(("4", "8", "92")):
        return f"bj.{c}"
    return f"sh.{c}"


def fetch_valuation(codes=None, start="2019-01-01", end=None):
    import baostock as bs
    end = end or pd.Timestamp.now().strftime("%Y-%m-%d")
    lg = bs.login()
    if lg.error_code != "0":
        print(f"  baostock 登录失败: {lg.error_msg}", flush=True)
        return
    print(f"拉取估值历史（baostock）{start} ~ {end} ...", flush=True)
    if codes is None:
        con = sqlite3.connect(f"file:{CACHE/'bars.db'}?mode=ro", uri=True)
        codes = [r[0].split(".")[0] for r in con.execute(
            "SELECT DISTINCT code FROM daily_bar WHERE code GLOB '[0-9][0-9][0-9][0-9][0-9][0-9].*'")]
        con.close()
    # 断点续跑：跳过已入库的 code
    done = set()
    dbp = CACHE / "valuation.db"
    if dbp.exists():
        try:
            con = sqlite3.connect(dbp)
            done = {r[0] for r in con.execute("SELECT DISTINCT code FROM valuation")}
            con.close()
        except Exception:
            pass
    fields = "date,code,close,peTTM,pbMRQ,psTTM,pcfNcfTTM,turn,tradestatus,isST"
    todo = [c for c in codes if str(c).split(".")[0].zfill(6) not in done]
    print(f"  待拉 {len(todo)} 只（已入库 {len(done)} 只）", flush=True)
    batch = []
    for i, c in enumerate(todo):
        try:
            rs = bs.query_history_k_data_plus(_bs_code(c), fields, start_date=start, end_date=end,
                                              frequency="d", adjustflag="2")
            rows = []
            while rs.error_code == "0" and rs.next():
                rows.append(rs.get_row_data())
            if rows:
                df = pd.DataFrame(rows, columns=fields.split(","))
                df["code"] = str(c).split(".")[0].zfill(6)
                batch.append(df)
        except Exception as e:
            if (i + 1) % 100 == 0:
                print(f"    [{i+1}] {c} 失败: {str(e)[:60]}", flush=True)
        # 每 200 只增量写库（断点续跑 + 释放内存 + 降频防挂起）
        if (i + 1) % 200 == 0:
            if batch:
                out = pd.concat(batch, ignore_index=True)
                con = _conn("valuation.db")
                out.to_sql("valuation", con, if_exists="append", index=False)
                con.close()
                batch = []
            print(f"    {i+1}/{len(todo)} 已处理", flush=True)
            time.sleep(1)
    if batch:
        out = pd.concat(batch, ignore_index=True)
        con = _conn("valuation.db")
        out.to_sql("valuation", con, if_exists="append", index=False)
        con.close()
        batch = []
    bs.logout()
    con = sqlite3.connect(CACHE / "valuation.db")
    total = con.execute("SELECT COUNT(*) FROM valuation").fetchone()[0]
    con.close()
    print(f"  valuation 总计 {total:,} 行 → {CACHE/'valuation.db'}", flush=True)


# --------------------------------------------------------------------------- #
# 4. 申万行业
# --------------------------------------------------------------------------- #
def fetch_industry():
    print("拉取申万行业列表 ...", flush=True)
    d1 = ak.sw_index_first_info()
    d1["level"] = "L1"
    d2 = ak.sw_index_second_info()
    d2["level"] = "L2"
    out = pd.concat([d1, d2], ignore_index=True)
    _to_sql(out, "industry.db", "sw_index", ["行业代码"])


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("lhb"); p1.add_argument("--start", required=True); p1.add_argument("--end", required=True)
    p2 = sub.add_parser("limitup"); p2.add_argument("--start", required=True); p2.add_argument("--end", required=True)
    p3 = sub.add_parser("valuation"); p3.add_argument("--codes"); p3.add_argument("--start", default="2010-01-01")
    sub.add_parser("industry")
    args = ap.parse_args()

    if args.cmd == "lhb":
        fetch_lhb(args.start, args.end)
        fetch_lhb_jgmmtj(args.start, args.end)
    elif args.cmd == "limitup":
        fetch_limitup(args.start, args.end)
    elif args.cmd == "valuation":
        codes = args.codes.split(",") if args.codes else None
        fetch_valuation(codes=codes, start=args.start)
    elif args.cmd == "industry":
        fetch_industry()


if __name__ == "__main__":
    main()
