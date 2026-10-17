# -*- coding: utf-8 -*-
"""scripts/migration/export_parquet_for_miner.py —— 从 bars.db 导出因子挖掘所需的 parquet

背景：ming/ 下的 AI-Quant-Factor-Miner（上游 IIcodehub/AI-Quant-Factor-Miner）
      读的是 parquet，不是我们的 SQLite。列名是它自己定义的（见 config/settings.py）：

  股票 parquet（STOCK_COLUMNS_DESC）：
      TradingDay, SecuCode, PrevClosePrice, OpenPrice, HighPrice, LowPrice,
      ClosePrice, TurnOverVolume, TurnOverValue, TurnOverRate, FloatMarketValue
  指数 parquet（INDEX_COLUMNS_DESC）：
      TradingDay, HS300, ZZ500, ZZ1000, SZ

本脚本负责按这个 schema 导出：
  · 股票：bars.db(daily_bar, qfq) ⨝ tdx_base(daily.circ_mv)  → 按【年】分块写入，内存占用低
  · 指数：沪深300/中证500/中证1000/深证成指，从通达信拉（本地 bars.db 只有沪深300）

用法：
  python scripts\\migration\\export_parquet_for_miner.py                # 全量导出（2010 起）
  python scripts\\migration\\export_parquet_for_miner.py --dry-run      # 只算行数不写文件
  python scripts\\migration\\export_parquet_for_miner.py --start 2015-01-01
  python scripts\\migration\\export_parquet_for_miner.py --turn-unit ratio   # 换手率用小数而非百分数
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

BASE = Path(__file__).resolve().parent.parent.parent
CACHE = BASE / "data" / "cache"
BARS = CACHE / "bars.db"
TDXBASE = CACHE / "tdx_base.db"
DEFAULT_OUT = BASE / "mining" / "AI-Quant-Factor-Miner" / "data"

INDEXES = [("000300.SH", "HS300"), ("000905.SH", "ZZ500"),
           ("000852.SH", "ZZ1000"), ("399001.SZ", "SZ")]

STOCK_SCHEMA = pa.schema([
    ("TradingDay", pa.string()), ("SecuCode", pa.string()),
    ("PrevClosePrice", pa.float64()), ("OpenPrice", pa.float64()),
    ("HighPrice", pa.float64()), ("LowPrice", pa.float64()),
    ("ClosePrice", pa.float64()), ("TurnOverVolume", pa.float64()),
    ("TurnOverValue", pa.float64()), ("TurnOverRate", pa.float64()),
    ("FloatMarketValue", pa.float64()),
])


def export_stock(out: Path, start: str, turn_factor: float, dry: bool) -> int:
    """按年分块导出股票面板，避免一次性把 1,600 万行读进内存"""
    con = sqlite3.connect(f"file:{BARS.as_posix()}?mode=ro", uri=True, timeout=120)
    con.execute(f"ATTACH DATABASE 'file:{TDXBASE.as_posix()}?mode=ro' AS tb")
    years = [r[0] for r in con.execute(
        "SELECT DISTINCT substr(date,1,4) FROM daily_bar WHERE date>=? AND adjust='qfq' ORDER BY 1",
        (start,))]
    print(f"  年份: {years[0]} ~ {years[-1]}（{len(years)} 年）")

    total = 0
    writer = None
    t0 = time.time()
    for y in years:
        sql = """
        SELECT b.date, b.code, b.preclose, b.open, b.high, b.low, b.close,
               b.volume, b.amount, b.turn, t.circ_mv
        FROM daily_bar b
        LEFT JOIN tb.daily t ON t.date = b.date AND t.code = b.code
        WHERE b.adjust='qfq' AND substr(b.date,1,4) = ?
        """
        df = pd.read_sql_query(sql, con, params=(y,))
        if df.empty:
            continue
        out_df = pd.DataFrame({
            "TradingDay": df["date"],
            "SecuCode": df["code"],
            "PrevClosePrice": pd.to_numeric(df["preclose"], errors="coerce"),
            "OpenPrice": pd.to_numeric(df["open"], errors="coerce"),
            "HighPrice": pd.to_numeric(df["high"], errors="coerce"),
            "LowPrice": pd.to_numeric(df["low"], errors="coerce"),
            "ClosePrice": pd.to_numeric(df["close"], errors="coerce"),
            "TurnOverVolume": pd.to_numeric(df["volume"], errors="coerce"),
            "TurnOverValue": pd.to_numeric(df["amount"], errors="coerce"),
            "TurnOverRate": pd.to_numeric(df["turn"], errors="coerce") * turn_factor,
            # tdx_base.circ_mv 单位是万元 → 转成元
            "FloatMarketValue": pd.to_numeric(df["circ_mv"], errors="coerce") * 10000.0,
        })
        n = len(out_df)
        total += n
        print(f"    {y}: {n:>9,} 行  (累计 {total:,}  用时 {time.time()-t0:.0f}s)", flush=True)
        if not dry:
            tbl = pa.Table.from_pandas(out_df, schema=STOCK_SCHEMA, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(out, STOCK_SCHEMA, compression="snappy")
            writer.write_table(tbl)
        del df, out_df
    if writer is not None:
        writer.close()
    con.close()
    return total


def export_index(out: Path, start: str, dry: bool) -> int:
    """指数：本地 bars.db 的 SH.000300 优先（HS300）；其余 3 个尝试通达信，失败则留空。

    注意：通达信 API 需要本机「通达信金融终端」正在运行，否则会长时间重试 →
    因此这里对每个品种做 try/except，任何失败都不阻塞整体导出。
    """
    frames = {}

    # ① 本地 HS300（bars.db 里 source=tdx，已验证与旧 baostock 值一致）
    try:
        con = sqlite3.connect(f"file:{BARS.as_posix()}?mode=ro", uri=True, timeout=60)
        rows = con.execute(
            "SELECT date, close FROM daily_bar WHERE code='SH.000300' ORDER BY date").fetchall()
        con.close()
        if rows:
            ser = pd.Series({d: c for d, c in rows}, dtype="float64")
            frames["HS300"] = ser
            print(f"    HS300    ← 本地 bars.db  {len(ser):,} 行  {rows[0][0]} ~ {rows[-1][0]}")
    except Exception as e:
        print(f"    [警告] 本地 HS300 读取失败: {str(e)[:60]}")

    # ② 其余 3 个走通达信（可选）
    others = [("000905.SH", "ZZ500"), ("000852.SH", "ZZ1000"), ("399001.SZ", "SZ")]
    try:
        sys.path.insert(0, r"C:\Users\Administrator\.dsh\skills\tdx-aidata")
        sys.path.insert(0, r"C:\Users\Administrator\.dsh\skills\tdx-aidata\lib")
        from tdxaidata import tqs
        for tdx_code, col in others:
            if col in frames:
                continue
            try:
                r = tqs.get_market_data(field_list=["Close"], stock_list=[tdx_code], period="1d",
                                        start_time="2005-01-01", end_time="2026-12-31",
                                        dividend_type="none")
                s = r.get("Close")
                if s is None or len(s) == 0:
                    print(f"    [跳过] {col} ({tdx_code}) 无数据")
                    continue
                ser = s.iloc[:, 0] if hasattr(s, "iloc") and s.ndim == 2 else s
                ser.index = pd.to_datetime(ser.index).strftime("%Y-%m-%d")
                frames[col] = pd.to_numeric(ser, errors="coerce")
                print(f"    {col:8s} ← 通达信 {tdx_code}  {len(ser):,} 行")
            except Exception as e:
                print(f"    [跳过] {col}: {str(e)[:60]}")
    except Exception as e:
        print(f"    [警告] 通达信不可用（{str(e)[:50]}）→ ZZ500/ZZ1000/SZ 将留空")
        print("           解决：打开「通达信金融终端」后重跑本脚本即可补齐")

    if not frames:
        print("  [失败] 没有任何指数数据")
        return 0
    idx = pd.DataFrame(frames)
    idx.index.name = "TradingDay"
    idx = idx.loc[idx.index >= start].reset_index()
    for c in ("HS300", "ZZ500", "ZZ1000", "SZ"):
        if c not in idx.columns:
            idx[c] = float("nan")
    idx = idx[["TradingDay", "HS300", "ZZ500", "ZZ1000", "SZ"]]
    filled = [c for c in ("HS300", "ZZ500", "ZZ1000", "SZ") if idx[c].notna().any()]
    print(f"  指数合并 {len(idx):,} 行，有数据的列: {', '.join(filled)}")
    if not dry:
        idx.to_parquet(out, index=False, compression="snappy")
    return len(idx)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2010-01-01")
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT))
    ap.add_argument("--turn-unit", choices=["pct", "ratio"], default="pct",
                    help="TurnOverRate 单位：pct=百分数(0.28)，ratio=小数(0.0028)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    turn_factor = 100.0 if args.turn_unit == "pct" else 1.0

    print(f"输出目录: {out_dir}")
    print(f"起始日期: {args.start} | 换手率单位: {args.turn_unit} (×{turn_factor})")
    print(f"模式: {'DryRun（不写文件）' if args.dry_run else '正式导出'}\n")

    print("[1/2] 股票 parquet（不依赖通达信）")
    n_stock = export_stock(out_dir / "data.parquet", args.start, turn_factor, args.dry_run)

    print("\n[2/2] 指数 parquet（本地优先，通达信可选）")
    n_idx = export_index(out_dir / "index.parquet", args.start, args.dry_run)

    print("\n" + "=" * 60)
    print(f"股票 {n_stock:,} 行 | 指数 {n_idx:,} 行")
    if not args.dry_run:
        for f in ("data.parquet", "index.parquet"):
            p = out_dir / f
            if p.exists():
                print(f"  {f:16s} {p.stat().st_size/1024/1024:>8.1f} MB  → {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
