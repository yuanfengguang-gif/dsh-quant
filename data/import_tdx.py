# -*- coding: utf-8 -*-
"""data/import_tdx.py —— 通达信数据导入（CSV → 新库 bars_tdx.db）

已验证的字段映射与单位换算（基于 2026-10-15 样本验证）：
  日频：code, datetime, open, high, low, close, pre_close, change, pct_chg,
        volume, amount, turnover, turnover_free, volume_ratio, pe, pe_ttm, pb,
        ps, ps_ttm, dv_yield, dv_ttm, total_share, float_share, free_share,
        total_mv, circ_mv
  单位：volume 手→×100=股；amount 千元→×1000=元；turnover %→÷100；pct_chg %→÷100
  复权因子：股票代码, 交易日期(YYYYMMDD), 复权因子

用法：
  python data/import_tdx.py --probe <目录>              # 只探查格式，不导入
  python data/import_tdx.py --src <目录> --kind daily   # 导入日频
  python data/import_tdx.py --src <目录> --kind factor  # 导入复权因子
"""
import argparse
import glob
import os
import sqlite3
import sys
from pathlib import Path

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = Path(__file__).resolve().parent.parent
DEFAULT_DB = BASE / "data" / "cache" / "bars_tdx.db"

# 单位换算系数（来自样本验证：本地/通达信 = 100 / 1000 / 0.01 / 0.01）
UNIT = {
    "volume": 100.0,      # 手 → 股
    "amount": 1000.0,     # 千元 → 元
    "turnover": 0.01,     # % → 小数
    "turnover_free": 0.01,
    "pct_chg": 0.01,
    "change": 1.0,        # 涨跌额，无需换算（元）
}


def read_csv_any(path):
    """读 CSV，自动尝试编码。"""
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:
            continue
    raise RuntimeError(f"无法解析 {path}")


def probe(src):
    """探查源目录结构（文件类型、列名、样例）。"""
    src = Path(src)
    files = sorted(glob.glob(str(src / "**" / "*.csv"), recursive=True))
    print(f"目录 {src}")
    print(f"发现 {len(files)} 个 CSV 文件")
    if not files:
        print("（无 CSV；可能是通达信原生 .day 格式，需另写解析）")
        return
    sizes = {}
    for f in files[:2000]:
        ext_dir = Path(f).parent.name
        sizes[ext_dir] = sizes.get(ext_dir, 0) + 1
    print("\n按目录统计：")
    for k, v in sorted(sizes.items(), key=lambda x: -x[1])[:20]:
        print(f"  {k}: {v} 个文件")
    print("\n样例文件：")
    for f in files[:3]:
        df = read_csv_any(f)
        print(f"\n  {f}")
        print(f"    行数 {len(df)}，列（{len(df.columns)}）：{df.columns.tolist()}")
        print(f"    前 2 行：\n{df.head(2).to_string(index=False)}")


def norm_code(s):
    """统一 code 格式：'sz000063'/'000063.SZ' → '000063.SZ'（项目格式）。"""
    s = str(s).strip().upper()
    if s.startswith("SZ") or s.startswith("SH") or s.startswith("BJ"):
        num, ex = s[2:], s[:2]
        return f"{num.zfill(6)}.{ex}"
    if "." in s:
        num, ex = s.split(".")
        return f"{num.zfill(6)}.{ex.upper()}"
    return s


def _map_one(df):
    """把一个 CSV 的 DataFrame 映射到目标结构（含单位换算）。"""
    cols = {str(c).lower().strip(): c for c in df.columns}

    def col(*names):
        for n in names:
            if n.lower() in cols:
                return cols[n.lower()]
        return None

    c_code, c_date = col("code", "股票代码"), col("datetime", "date", "交易日期")
    if not (c_code and c_date):
        return None
    out = pd.DataFrame({
        "code": df[c_code].map(norm_code),
        "date": pd.to_datetime(df[c_date]).dt.strftime("%Y-%m-%d"),
    })
    simple = {"open": ("open",), "high": ("high",), "low": ("low",), "close": ("close",),
              "preclose": ("pre_close", "preclose"), "change": ("change",)}
    for tgt, srcs in simple.items():
        sc = col(*srcs)
        out[tgt] = pd.to_numeric(df[sc], errors="coerce") if sc else None
    scaled = [
        ("pct_chg", ("pct_chg", "涨跌幅"), UNIT["pct_chg"]),
        ("volume", ("volume", "成交量"), UNIT["volume"]),
        ("amount", ("amount", "成交额"), UNIT["amount"]),
        ("turn", ("turnover", "换手率"), UNIT["turnover"]),
        ("turn_free", ("turnover_free",), UNIT["turnover_free"]),
        ("volume_ratio", ("volume_ratio", "量比"), 1.0),
        ("pe", ("pe",), 1.0), ("pe_ttm", ("pe_ttm",), 1.0), ("pb", ("pb",), 1.0),
        ("ps", ("ps",), 1.0), ("ps_ttm", ("ps_ttm",), 1.0),
        ("dv_yield", ("dv_yield",), 1.0), ("dv_ttm", ("dv_ttm",), 1.0),
        # 股本：通达信单位=万股 → ×10000 = 股
        ("total_share", ("total_share",), 10000.0),
        ("float_share", ("float_share",), 10000.0),
        ("free_share", ("free_share",), 10000.0),
        # 市值：通达信单位=万元 → ×10000 = 元（已验证 circ_mv = float_share × close）
        ("total_mv", ("total_mv",), 10000.0),
        ("circ_mv", ("circ_mv",), 10000.0),
    ]
    for tgt, srcs, mult in scaled:
        sc = col(*srcs)
        out[tgt] = (pd.to_numeric(df[sc], errors="coerce") * mult) if sc else None
    return out.dropna(subset=["code", "date"])


TDX_COLS = ["code", "date", "open", "high", "low", "close", "preclose", "change",
            "pct_chg", "volume", "amount", "turn", "turn_free", "volume_ratio",
            "pe", "pe_ttm", "pb", "ps", "ps_ttm", "dv_yield", "dv_ttm",
            "total_share", "float_share", "free_share", "total_mv", "circ_mv"]


def _ensure_table(con, table="daily_bar"):
    con.execute(f"""CREATE TABLE IF NOT EXISTS {table} (
        code TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL,
        preclose REAL, change REAL, pct_chg REAL, volume REAL, amount REAL,
        turn REAL, turn_free REAL, volume_ratio REAL,
        pe REAL, pe_ttm REAL, pb REAL, ps REAL, ps_ttm REAL,
        dv_yield REAL, dv_ttm REAL,
        total_share REAL, float_share REAL, free_share REAL,
        total_mv REAL, circ_mv REAL,
        is_st INTEGER DEFAULT 0, adjust TEXT DEFAULT 'unadj', source TEXT DEFAULT 'tdx',
        PRIMARY KEY (code, date))""")
    con.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_date ON {table}(date)")


def import_daily_zip(src, db, table="daily_bar"):
    """从「按年 zip（内含每股票 CSV）」导入日频行情 —— 直读 zip 不落盘。"""
    import zipfile

    src = Path(src)
    zips = sorted(glob.glob(str(src / "**" / "*.zip"), recursive=True))
    if not zips:
        print("未找到 zip")
        return
    print(f"发现 {len(zips)} 个 zip → 写入表 {table}")
    con = sqlite3.connect(str(db))
    con.execute("PRAGMA synchronous=OFF")
    con.execute("PRAGMA journal_mode=MEMORY")
    _ensure_table(con, table)
    grand = 0
    for zi, zp in enumerate(zips):
        rows = []
        try:
            with zipfile.ZipFile(zp) as z:
                members = [m for m in z.namelist()
                           if m.lower().endswith(".csv") and "__MACOSX" not in m]
                for m in members:
                    try:
                        df = pd.read_csv(z.open(m), encoding="utf-8-sig", dtype=str)
                    except Exception:
                        try:
                            df = pd.read_csv(z.open(m), encoding="gbk", dtype=str)
                        except Exception:
                            continue
                    o = _map_one(df)
                    if o is not None and len(o):
                        rows.append(o)
        except Exception as e:
            print(f"  ⚠️ {Path(zp).name} 读取失败: {e}")
            continue
        if not rows:
            print(f"  [{zi+1}/{len(zips)}] {Path(zp).name}: 0 行")
            continue
        big = pd.concat(rows, ignore_index=True)
        for c in TDX_COLS:
            if c not in big.columns:
                big[c] = None
        big = big[TDX_COLS]
        big["is_st"] = 0
        big["adjust"] = "unadj"
        big["source"] = "tdx"
        big.to_sql("_tmp", con, if_exists="replace", index=False)
        con.execute(f"INSERT OR REPLACE INTO {table} SELECT * FROM _tmp")
        con.commit()
        grand += len(big)
        print(f"  [{zi+1}/{len(zips)}] {Path(zp).name}: +{len(big):,} 行（累计 {grand:,}）", flush=True)
    con.execute("DROP TABLE IF EXISTS _tmp")
    con.commit()
    con.close()
    print(f"\n导入完成：{grand:,} 行 → {db} [{table}]")


def import_daily(src, db, pattern=None):
    """导入日频行情 CSV。"""
    src = Path(src)
    files = sorted(glob.glob(str(src / (pattern or "**/*.csv")), recursive=True))
    if not files:
        print("未找到日频 CSV")
        return
    con = sqlite3.connect(str(db))
    con.execute("""CREATE TABLE IF NOT EXISTS daily_bar_tdx (
        code TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL,
        preclose REAL, change REAL, pct_chg REAL, volume REAL, amount REAL,
        turn REAL, turn_free REAL, volume_ratio REAL,
        pe REAL, pe_ttm REAL, pb REAL, ps REAL, ps_ttm REAL,
        dv_yield REAL, dv_ttm REAL,
        total_share REAL, float_share REAL, free_share REAL,
        total_mv REAL, circ_mv REAL, PRIMARY KEY (code, date))""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_tdx_daily_date ON daily_bar_tdx(date)")
    total = 0
    for i, f in enumerate(files):
        try:
            df = read_csv_any(f)
        except Exception as e:
            print(f"  ⚠️ {Path(f).name} 读取失败: {e}")
            continue
        cols = {c.lower(): c for c in df.columns}
        # 定位关键列（兼容中英文）
        def col(*names):
            for n in names:
                if n.lower() in cols:
                    return cols[n.lower()]
            return None
        c_code = col("code", "股票代码", "证券代码")
        c_date = col("datetime", "date", "交易日期", "日期")
        if not c_code or not c_date:
            print(f"  ⚠️ {Path(f).name} 缺 code/date 列，跳过")
            continue
        out = pd.DataFrame()
        out["code"] = df[c_code].map(norm_code)
        out["date"] = pd.to_datetime(df[c_date]).dt.strftime("%Y-%m-%d")
        m = {"open": ("open", 1), "high": ("high", 1), "low": ("low", 1),
             "close": ("close", 1), "preclose": ("pre_close", "preclose", 1)}
        for tgt, spec in m.items():
            src_col = col(*spec[:-1])
            out[tgt] = df[src_col] if src_col else None
        out["change"] = df[col("change", "涨跌额")] if col("change", "涨跌额") else None
        for tgt, srcs, mult in [
            ("pct_chg", ("pct_chg", "涨跌幅"), UNIT["pct_chg"]),
            ("volume", ("volume", "成交量"), UNIT["volume"]),
            ("amount", ("amount", "成交额"), UNIT["amount"]),
            ("turn", ("turnover", "换手率"), UNIT["turnover"]),
            ("turn_free", ("turnover_free",), UNIT["turnover_free"]),
            ("volume_ratio", ("volume_ratio", "量比"), 1.0),
            ("pe", ("pe",), 1.0), ("pe_ttm", ("pe_ttm",), 1.0), ("pb", ("pb",), 1.0),
            ("ps", ("ps",), 1.0), ("ps_ttm", ("ps_ttm",), 1.0),
            ("dv_yield", ("dv_yield",), 1.0), ("dv_ttm", ("dv_ttm",), 1.0),
            ("total_share", ("total_share", "总股本"), 1.0),
            ("float_share", ("float_share", "流通股本"), 1.0),
            ("free_share", ("free_share", "自由流通股本"), 1.0),
            ("total_mv", ("total_mv", "总市值"), 1.0),
            ("circ_mv", ("circ_mv", "流通市值"), 1.0),
        ]:
            sc = col(*srcs)
            out[tgt] = (df[sc] * mult) if sc else None
        out = out.dropna(subset=["code", "date"])
        out.to_sql("_tmp_tdx", con, if_exists="replace", index=False)
        con.execute("INSERT OR REPLACE INTO daily_bar_tdx SELECT * FROM _tmp_tdx")
        con.commit()
        total += len(out)
        if (i + 1) % 200 == 0 or i == len(files) - 1:
            print(f"  [{i+1}/{len(files)}] 累计 {total:,} 行", flush=True)
    con.close()
    print(f"\n导入完成：{total:,} 行 → {db}")


def import_factor(src, db):
    """导入复权因子 —— 支持「CSV 目录」或「zip（内含每股票 CSV）」。"""
    import zipfile

    src = Path(src)
    csvs = sorted(glob.glob(str(src / "**/*.csv"), recursive=True))
    zips = sorted(glob.glob(str(src / "**/*.zip"), recursive=True))
    frames = []

    def take(df, fname):
        cols = {str(c).strip(): c for c in df.columns}
        c_code = cols.get("股票代码") or cols.get("code")
        c_date = cols.get("交易日期") or cols.get("date")
        c_fac = cols.get("复权因子") or cols.get("factor")
        if not (c_code and c_date and c_fac):
            return None
        kind = "hfq_factor" if ("后复权" in fname or "hfq" in fname.lower()) else "qfq_factor"
        dt = df[c_date].astype(str).str.strip()
        dt = dt.str.replace("-", "", regex=False)
        return pd.DataFrame({
            "code": df[c_code].map(norm_code),
            "date": pd.to_datetime(dt, format="%Y%m%d", errors="coerce").dt.strftime("%Y-%m-%d"),
            kind: pd.to_numeric(df[c_fac], errors="coerce"),
        }).dropna()

    for f in csvs:
        try:
            df = read_csv_any(f)
        except Exception:
            continue
        s = take(df, Path(f).name)
        if s is not None and len(s):
            frames.append(s)
            print(f"  CSV {Path(f).name}: {len(s):,} 行", flush=True)

    for zp in zips:
        nm = Path(zp).name
        print(f"  读取 zip {nm} …", flush=True)
        try:
            with zipfile.ZipFile(zp) as z:
                members = [m for m in z.namelist()
                           if m.lower().endswith(".csv") and "__MACOSX" not in m]
                for i, m in enumerate(members):
                    try:
                        df = pd.read_csv(z.open(m), encoding="utf-8-sig", dtype=str)
                    except Exception:
                        try:
                            df = pd.read_csv(z.open(m), encoding="gbk", dtype=str)
                        except Exception:
                            continue
                    if len(df.columns) < 3:
                        continue
                    # 统一成三列 code/date/factor（有些文件带表头，有些不带）
                    d2 = df.iloc[:, :3].copy()
                    d2.columns = ["code", "date", "factor"]
                    if len(d2) == 0:
                        continue
                    first = str(d2.iloc[0, 0])
                    if not any(ch.isdigit() for ch in first):
                        d2 = d2.iloc[1:]
                    if len(d2) == 0:
                        continue
                    s = take(d2, nm)
                    if s is not None and len(s):
                        frames.append(s)
                    if (i + 1) % 1500 == 0:
                        print(f"    …{i+1}/{len(members)}", flush=True)
        except Exception as e:
            print(f"  ⚠️ {nm} 读取失败: {e}")
            continue

    if not frames:
        print("未找到复权因子数据")
        return
    allf = pd.concat(frames, ignore_index=True)
    merged = allf.groupby(["code", "date"], as_index=False).last()
    for c in ("qfq_factor", "hfq_factor"):
        if c not in merged.columns:
            merged[c] = None

    con = sqlite3.connect(str(db))
    # ★ 合并已有数据（避免导入后复权时覆盖已导入的前复权）
    try:
        exist = pd.read_sql("SELECT code, date, qfq_factor, hfq_factor FROM adj_factor", con)
        if len(exist):
            before = len(merged)
            merged = pd.concat([exist, merged[["code", "date", "qfq_factor", "hfq_factor"]]],
                               ignore_index=True)
            # 同一 (code,date) 取"非空优先"，两边都有值时取后写入的
            merged["_pri"] = merged["qfq_factor"].notna().astype(int) + merged["hfq_factor"].notna().astype(int)
            merged = merged.sort_values("_pri").groupby(["code", "date"], as_index=False).last()
            merged = merged.drop(columns=["_pri"])
            print(f"  合并已有 {len(exist):,} 行 + 新增 {before:,} 行 → {len(merged):,} 行")
    except Exception:
        pass

    merged[["code", "date", "qfq_factor", "hfq_factor"]].to_sql(
        "adj_factor", con, if_exists="replace", index=False)
    con.execute("CREATE INDEX IF NOT EXISTS idx_af_code ON adj_factor(code)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_af_date ON adj_factor(date)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_af_code_date ON adj_factor(code, date)")
    con.commit()
    print(f"  最终 {len(merged):,} 行（qfq {merged['qfq_factor'].notna().sum():,} / "
          f"hfq {merged['hfq_factor'].notna().sum():,}），股票 {merged['code'].nunique():,} 只")
    con.close()
    print(f"\n复权因子导入完成 → {db}")


def apply_qfq(db, table="daily_bar"):
    """用 adj_factor 把未复权价转成前复权价（pandas 向量化 + 按年分批，避免慢 JOIN）。

    兼容项目 load_panel（其过滤 WHERE adjust='qfq'）。
    前复权价 = 未复权价 × qfq_factor（通达信因子已以最新日为 1.0）。
    说明：涨跌额 change 同步复权；pct_chg 是比例、vol/amount/turn 不受复权影响，保持不变。
    """
    con = sqlite3.connect(str(db))
    has_af = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='adj_factor'").fetchone()
    if not has_af:
        print("⚠️ 未找到 adj_factor 表，请先导入复权因子（--kind factor）")
        con.close()
        return
    cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
    print(f"目标表 {table}，共 {len(cols)} 列")

    af = pd.read_sql(
        "SELECT code, date, qfq_factor FROM adj_factor "
        "WHERE qfq_factor IS NOT NULL AND qfq_factor > 0", con)
    print(f"复权因子可用 {len(af):,} 行")

    years = [r[0] for r in con.execute(
        f"SELECT DISTINCT substr(date,1,4) y FROM {table} WHERE adjust='unadj' ORDER BY y")]
    print(f"待复权年份：{len(years)} 个")
    total = 0
    for y in years:
        bar = pd.read_sql(f"SELECT * FROM {table} WHERE adjust='unadj' AND date LIKE ?",
                          con, params=[y + "%"])
        if not len(bar):
            continue
        m = bar.merge(af, on=["code", "date"], how="inner")
        if not len(m):
            print(f"  {y}: 无匹配复权因子，跳过")
            continue
        for c in ["open", "high", "low", "close", "preclose", "change"]:
            if c in m.columns:
                m[c] = m[c] * m["qfq_factor"]
        m["adjust"] = "qfq"
        m["source"] = "tdx"
        m = m[[c for c in cols if c in m.columns]]
        m.to_sql("_tmp_qfq", con, if_exists="replace", index=False)
        con.execute(f"DELETE FROM {table} WHERE adjust='qfq' AND date LIKE ?", (y + "%",))
        con.execute(f"INSERT OR REPLACE INTO {table} SELECT * FROM _tmp_qfq")
        con.commit()
        total += len(m)
        print(f"  {y}: +{len(m):,} 行（累计 {total:,}）", flush=True)

    con.execute("DROP TABLE IF EXISTS _tmp_qfq")
    con.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_code_date ON {table}(code, date)")
    con.commit()
    n_qfq = con.execute(f"SELECT COUNT(*) FROM {table} WHERE adjust='qfq'").fetchone()[0]
    n_un = con.execute(f"SELECT COUNT(*) FROM {table} WHERE adjust='unadj'").fetchone()[0]
    con.close()
    print(f"\n复权处理完成：qfq 行 {n_qfq:,}，unadj 行 {n_un:,}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=None)
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--kind", default="probe",
                    choices=["probe", "daily", "daily_zip", "factor", "apply_qfq"])
    ap.add_argument("--pattern", default=None, help="CSV glob（如 '**/*.csv'）")
    ap.add_argument("--table", default="daily_bar", help="目标表名（默认 daily_bar，兼容项目代码）")
    args = ap.parse_args()

    if args.kind == "probe":
        probe(args.src or ".")
        return
    if args.kind == "apply_qfq":
        apply_qfq(args.db, args.table)
        return
    if not args.src:
        probe(".")
        return
    if args.kind == "daily_zip":
        import_daily_zip(args.src, args.db, args.table)
    elif args.kind == "daily":
        import_daily(args.src, args.db, args.pattern)
    else:
        import_factor(args.src, args.db)


if __name__ == "__main__":
    main()
