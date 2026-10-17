# -*- coding: utf-8 -*-
"""data/tdx_daily_update.py —— 通达信每日增量更新（幂等 + 断点追赶）

设计要点：
  1) 幂等：先读库里 max(date)，再算缺口；重复跑不会重复写（INSERT OR REPLACE）
  2) 追赶：无论漏跑 1 天还是 30 天，一次补齐 (max_date, latest_trade_date] 全部交易日
  3) 断点：每批提交，中断后下次自动从断点继续（以库里 max_date 为准）
  4) 元数据快照：每日落一条 stock_info 快照 → 从今天起积累「历史 ST / 指数归属」序列
  5) 日志：写入 update_log 表（运行时间/缺口/写入行数/状态）

用法：
  python data/tdx_daily_update.py                 # 增量补到最新
  python data/tdx_daily_update.py --init 2010-01-01   # 首次全量（从指定日起）
  python data/tdx_daily_update.py --dry-run       # 只看缺口，不下载
"""
import argparse
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from tdxaidata import tqs

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = Path(r"D:\Programs\DSH Projects\DSH Quant")
DB = BASE / "data" / "cache" / "bars_tdx.db"        # 行情主库
META_DB = BASE / "data" / "cache" / "tdx_meta.db"    # 元数据库
TABLE = "daily_bar"

# 通达信字段 -> 我的列名（单位换算在写入时处理）
FIELDS = ["Open", "High", "Low", "Close", "Volume", "Amount"]
UNIV_BATCH = 200          # 每批股票数
SNAPSHOT_COLS = ["IsSTGP", "IsQuitGP", "BelongHS300", "BelongHSGT", "BelongRZRQ"]


def log(con, **kw):
    con.execute("""CREATE TABLE IF NOT EXISTS update_log (
        run_at TEXT, mode TEXT, max_before TEXT, latest TEXT, missing_days INTEGER,
        rows_written INTEGER, status TEXT, note TEXT)""")
    con.execute("INSERT INTO update_log VALUES (?,?,?,?,?,?,?,?)",
                (kw.get("run_at"), kw.get("mode"), kw.get("max_before"), kw.get("latest"),
                 kw.get("missing_days"), kw.get("rows_written"), kw.get("status"), kw.get("note")))
    con.commit()


def get_latest_trade_date(days_back=120):
    """取今天及往前 N 天的最后交易日"""
    today = datetime.now()
    start = (today - timedelta(days=days_back)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    for mkt in ("SH", "SZ"):
        try:
            d = tqs.get_trading_dates(market=mkt, start_time=start, end_time=end)
            if d and not isinstance(d, str):
                return max(str(x) for x in d)
        except Exception:
            continue
    return None


def fetch_universe():
    """全市场股票列表（market=5 全市场）"""
    try:
        lst = tqs.get_stock_list(5, 0)
        return [str(c) for c in lst] if not isinstance(lst, str) else []
    except Exception:
        return []


def fetch_bars(codes, start, end):
    """批量下载 [start, end] 区间日线，返回 tidy DataFrame"""
    frames = []
    ok = fail = 0
    for i in range(0, len(codes), UNIV_BATCH):
        b = codes[i:i + UNIV_BATCH]
        try:
            r = tqs.get_market_data(field_list=FIELDS, stock_list=b, period="1d",
                                    start_time=start, end_time=end)
            if not isinstance(r, dict) or not r:
                fail += 1
                continue
            # r: {'Open': DataFrame(index=date, columns=code), ...}
            parts = {}
            for k, v in r.items():
                if hasattr(v, "stack"):
                    s = v.stack()
                    s.name = k.lower()
                    parts[k.lower()] = s
            if parts:
                df = pd.concat(parts.values(), axis=1).reset_index()
                df.columns = ["date", "code"] + list(parts.keys())
                frames.append(df)
                ok += 1
            else:
                fail += 1
        except Exception:
            fail += 1
    if not frames:
        return pd.DataFrame(), ok, fail
    big = pd.concat(frames, ignore_index=True)
    big["date"] = pd.to_datetime(big["date"]).dt.strftime("%Y-%m-%d")
    return big, ok, fail


_META_CACHE = None


def load_meta_maps():
    """从 tdx_meta.db 取「流通股本(万股)」与「当前 ST 标记」，供增量行算 turn / is_st
    ★2026-10-17 修复（DS-01）：原实现 turn 恒 None、is_st 恒 0
    turn 口径与历史段完全一致：小数比率 = 成交量(股) / 流通股本(股)（ActiveCapital 单位=万股）
    """
    global _META_CACHE
    if _META_CACHE is not None:
        return _META_CACHE
    cap, st = {}, {}
    try:
        con = sqlite3.connect(f"file:{META_DB.as_posix()}?mode=ro", uri=True, timeout=10)
        for code, ac, iss in con.execute("SELECT code, ActiveCapital, IsSTGP FROM stock_info_tdx"):
            try:
                cap[code] = float(ac)
            except (TypeError, ValueError):
                continue
            st[code] = 1 if str(iss).strip() == "1" else 0
        con.close()
        print(f"  元数据: 流通股本 {len(cap):,} 只 / ST {sum(st.values()):,} 只")
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️ 元数据读取失败（turn/is_st 将留空）: {e}")
    _META_CACHE = (cap, st)
    return _META_CACHE


def write_bars(con, df, source="tdx_api"):
    """写入 daily_bar（单位换算 + 幂等）"""
    if df.empty:
        return 0
    out = df.copy()
    # 单位换算：Volume 股（原始即为股）、Amount 万元 → 元
    if "amount" in out.columns:
        out["amount"] = pd.to_numeric(out["amount"], errors="coerce") * 10000.0
    for c in ("open", "high", "low", "close", "volume"):
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.sort_values(["code", "date"])
    out["preclose"] = out.groupby("code")["close"].shift(1)
    # ★批内首日兜底：原实现批内 shift 使每批首日 preclose/pct_chg 恒 NaN
    _miss = out["preclose"].isna()
    if _miss.any():
        prev = {}
        try:
            con_ro = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=10)
            for code in out.loc[_miss, "code"].unique():
                d0 = out.loc[out["code"] == code, "date"].min()
                r = con_ro.execute(
                    "SELECT close FROM daily_bar WHERE code=? AND adjust=? AND date<? "
                    "ORDER BY date DESC LIMIT 1", (code, "unadj", d0)).fetchone()
                if r and r[0]:
                    prev[code] = r[0]
            con_ro.close()
        except Exception:  # noqa: BLE001
            pass
        if prev:
            out.loc[_miss, "preclose"] = out.loc[_miss, "code"].map(prev)
    out["pct_chg"] = out["close"] / out["preclose"] - 1.0
    out["change"] = out["close"] - out["preclose"]
    # ★turn：成交量(股) / 流通股本(股)，与历史段同口径（小数比率）
    cap_map, st_map = load_meta_maps()
    s_cap = out["code"].map(cap_map)
    out["turn"] = pd.to_numeric(out["volume"], errors="coerce") / (s_cap * 10000.0)
    out.loc[~(s_cap > 0), "turn"] = None
    # ★is_st：当前状态（历史段由 patch_is_st / is_st_inferred 负责）
    out["is_st"] = out["code"].map(st_map).fillna(0).astype(int)
    out["adjust"] = "unadj"
    out["source"] = source
    # 完整性自检（避免再次静默劣化）
    n = len(out)
    n_turn = int(out["turn"].isna().sum())
    n_pre = int(out["preclose"].isna().sum())
    if n and n_turn == n:
        print("  ⚠️ turn 全空：检查 tdx_meta.stock_info_tdx.ActiveCapital")
    elif n_turn:
        print(f"  ⚠️ turn 缺失 {n_turn}/{n} 行（可能新股无股本）")
    if n and n_pre == n:
        print("  ⚠️ preclose 全空：库里无前一日收盘")
    cols = [r[1] for r in con.execute(f"PRAGMA table_info({TABLE})")]
    for c in cols:
        if c not in out.columns:
            out[c] = None
    out = out[[c for c in cols if c in out.columns]]
    out.to_sql("_tmp_inc", con, if_exists="replace", index=False)
    con.execute(f"INSERT OR REPLACE INTO {TABLE} SELECT * FROM _tmp_inc")
    con.execute("DROP TABLE IF EXISTS _tmp_inc")
    con.commit()
    return len(out)


def snapshot_meta(con_meta, trade_date):
    """落一条元数据快照（ST / 退市 / 指数归属）→ 积累历史序列"""
    try:
        codes = fetch_universe()
        if not codes:
            return 0
        rows = []
        for i in range(0, len(codes), UNIV_BATCH):
            b = codes[i:i + UNIV_BATCH]
            try:
                r = tqs.get_stock_info_batch(b)
                if isinstance(r, dict):
                    for code, v in r.items():
                        if isinstance(v, dict) and v:
                            d = {"snapshot_date": trade_date, "code": code}
                            for c in SNAPSHOT_COLS:
                                d[c] = v.get(c)
                            d["name"] = v.get("Name") or v.get("SecShortName")
                            rows.append(d)
            except Exception:
                continue
        if not rows:
            return 0
        # ★DS-04 修复（2026-10-17）：批量接口 get_stock_info_batch 返回的 IsSTGP 不可靠
        #   （实测全市场只有 1 只为 '1'，而 stock_info_tdx 里有 201 只）
        #   → 一律用 stock_info_tdx.IsSTGP 覆盖，保证 ST 快照可信、PIT 序列能正常积累
        try:
            _st = {c for (c,) in con_meta.execute(
                "SELECT code FROM stock_info_tdx WHERE IsSTGP='1'")}
            for _r in rows:
                _r["IsSTGP"] = "1" if _r.get("code") in _st else "0"
            print(f"  快照 ST 以 stock_info_tdx 为准：{len(_st)} 只")
        except Exception as _e:
            print(f"  ⚠️ ST 覆盖失败（沿用接口值）: {_e}")
        df = pd.DataFrame(rows)
        # ★DS-04 修复（2026-10-17）：原来用 `INSERT OR REPLACE INTO ... SELECT * FROM _tmp_snap`，
        #   依赖 df 列序与表列序一致 —— 实际不一致，导致 name/IsSTGP/IsQuitGP 等**全部错位**
        #   （快照里 name 存着 '1'，IsSTGP 只有 1 只为 '1'，全线是垃圾）。
        #   → 改为显式列名 + 显式选列，杜绝顺序依赖。
        SNAP_COLS_ORDER = ["snapshot_date", "code", "name", "IsSTGP", "IsQuitGP",
                           "BelongHS300", "BelongHSGT", "BelongRZRQ"]
        for _c in SNAP_COLS_ORDER:
            if _c not in df.columns:
                df[_c] = None
        df = df[SNAP_COLS_ORDER]
        df.to_sql("_tmp_snap", con_meta, if_exists="replace", index=False)
        con_meta.execute("""CREATE TABLE IF NOT EXISTS stock_info_snapshot (
            snapshot_date TEXT, code TEXT, name TEXT, IsSTGP TEXT, IsQuitGP TEXT,
            BelongHS300 TEXT, BelongHSGT TEXT, BelongRZRQ TEXT, PRIMARY KEY (snapshot_date, code))""")
        _cols = ", ".join(SNAP_COLS_ORDER)
        con_meta.execute(
            f"INSERT OR REPLACE INTO stock_info_snapshot ({_cols}) SELECT {_cols} FROM _tmp_snap")
        con_meta.execute("DROP TABLE IF EXISTS _tmp_snap")
        con_meta.commit()
        return len(df)
    except Exception as e:
        print(f"  ⚠️ 快照失败: {e}")
        return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", default=None, help="首次全量起始日 YYYY-MM-DD")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-meta", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    con = sqlite3.connect(str(DB))
    con.execute("PRAGMA synchronous=OFF")
    if not con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)).fetchone():
        print(f"❌ 表 {TABLE} 不存在，请先导入历史数据")
        return

    # 1) 库里最新日期
    row = con.execute(f"SELECT MAX(date) FROM {TABLE}").fetchone()
    max_before = row[0] if row and row[0] else None
    print(f"库里最新日期: {max_before}")

    # 2) 最新交易日
    latest = get_latest_trade_date()
    print(f"最新交易日: {latest}")
    if not latest:
        print("❌ 无法获取交易日历")
        log(con, run_at=datetime.now().isoformat(), mode="daily", max_before=max_before,
            latest=None, missing_days=0, rows_written=0, status="fail", note="交易日历获取失败")
        return

    latest_iso = f"{latest[:4]}-{latest[4:6]}-{latest[6:]}"

    # 3) 算缺口
    if args.init:
        start_iso = args.init
        mode = "init"
    elif max_before:
        start_iso = (datetime.strptime(max_before, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        mode = "daily"
    else:
        start_iso = "2010-01-01"
        mode = "init"

    if start_iso > latest_iso:
        print(f"✅ 已是最新（缺口为空）")
        log(con, run_at=datetime.now().isoformat(), mode=mode, max_before=max_before,
            latest=latest_iso, missing_days=0, rows_written=0, status="ok", note="无缺口")
        con.close()
        return

    # 交易日列表（用于报告缺口天数）
    try:
        td = tqs.get_trading_dates(market="SH",
                                   start_time=start_iso.replace("-", ""),
                                   end_time=latest)
        td = [str(x) for x in td] if not isinstance(td, str) else []
    except Exception:
        td = []
    print(f"缺口区间: {start_iso} ~ {latest_iso}，交易日 {len(td)} 天")
    if args.dry_run:
        print(f"[dry-run] 交易日: {td[:20]}{' ...' if len(td) > 20 else ''}")
        con.close()
        return

    # 4) 下载补齐
    codes = fetch_universe()
    print(f"全市场 {len(codes):,} 只，开始批量下载 …")
    df, ok, fail = fetch_bars(codes, start_iso.replace("-", ""), latest)
    n = write_bars(con, df)
    print(f"  成功批 {ok} / 失败批 {fail}，写入 {n:,} 行")

    # 5) 元数据快照（为未来积累历史 ST 序列）
    n_snap = 0
    if not args.skip_meta:
        cm = sqlite3.connect(str(META_DB))
        n_snap = snapshot_meta(cm, latest_iso)
        cm.close()
        print(f"  元数据快照 {n_snap:,} 行（{latest_iso}）")

    # 6) 日志
    new_max = con.execute(f"SELECT MAX(date) FROM {TABLE}").fetchone()[0]
    log(con, run_at=datetime.now().isoformat(), mode=mode, max_before=max_before,
        latest=latest_iso, missing_days=len(td), rows_written=n,
        status="ok" if fail == 0 else "partial",
        note=f"ok_batch={ok},fail_batch={fail},snapshot={n_snap},new_max={new_max}")
    con.close()
    print(f"\n✅ 完成：{max_before} → {new_max}，写入 {n:,} 行，耗时 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
