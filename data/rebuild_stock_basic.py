# -*- coding: utf-8 -*-
"""data/rebuild_stock_basic.py —— 用通达信+通联重建 stock_basic（内容换源，文件名/表结构不变）

背景（CORE_ISSUE_TRACKER DS-08）：
  38 个代码文件读 `stock_basic.db`（code,name,industry,ipo_date,out_date,status）。
  按用户原则「保留的且新源能提供 → 换数据源」，本脚本把内容换成：
    上市股票：tdx_meta.stock_info_tdx（Name / rs_hyname 行业 / J_start 上市日 / IsQuitGP）
    退市股票：datayes_basic.sec_delisted（secShortName / listDate / delistDate）
  → 调用点零改动。

字段映射与已知差异（务必在文档披露）：
  code      ← 同旧库格式（600000.SH / 000001.SZ / 830xxx.BJ）
  name      ← stock_info_tdx.Name / datayes.secShortName
  industry  ← stock_info_tdx.rs_hyname（**通达信行业，如「酿酒」**）
              ⚠️ 旧库是证监会门类（如「J66货币金融服务」）→ **分类体系变了**（影响行业中性化，需披露）
  ipo_date  ← stock_info_tdx.J_start（YYYYMMDD→YYYY-MM-DD）/ datayes.listDate
  out_date  ← 退市股取 datayes.delistDate；在市股票为 ''（与旧库一致）
  status    ← '1' 在市 / '0' 退市（与旧库一致）

输出：data/cache/stock_basic_new.db → 表 stock_basic（schema 与旧库完全一致）
用法：python data/rebuild_stock_basic.py
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CACHE = Path(__file__).resolve().parent.parent / "data" / "cache"
META = CACHE / "tdx_meta.db"
DAY = CACHE / "datayes_basic.db"
OLD = CACHE / "stock_basic.db"
OUT = CACHE / "stock_basic_new.db"


def fmt_date(s: str) -> str:
    s = (s or "").strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s


def norm_code(ticker: str, exch: str = "") -> str:
    t = str(ticker or "").strip().zfill(6)
    e = str(exch or "").upper()
    if e in ("XSHG", "XSHE", "XBSE"):
        return t + ("." + {"XSHG": "SH", "XSHE": "SZ", "XBSE": "BJ"}[e])
    if t.startswith(("6", "9")):
        return t + ".SH"
    if t.startswith(("4", "8")):
        return t + ".BJ"
    return t + ".SZ"


def main() -> int:
    if OUT.exists():
        OUT.unlink()
    out = sqlite3.connect(str(OUT))
    out.execute("""CREATE TABLE stock_basic (
                     code TEXT PRIMARY KEY, name TEXT, industry TEXT,
                     ipo_date TEXT, out_date TEXT, status TEXT)""")

    meta = sqlite3.connect(f"file:{META.as_posix()}?mode=ro", uri=True, timeout=30)
    day = sqlite3.connect(f"file:{DAY.as_posix()}?mode=ro", uri=True, timeout=30)

    rows: dict[str, tuple] = {}
    # ① 在市（通达信元数据）
    n_tdx = 0
    for code, name, hy, j_start, is_quit in meta.execute(
            "SELECT code, Name, rs_hyname, J_start, IsQuitGP FROM stock_info_tdx"):
        rows[code] = (code, name or "", hy or "", fmt_date(j_start), "",
                      "1" if str(is_quit).strip() != "1" else "0")
        n_tdx += 1
    print(f"通达信在册: {n_tdx:,} 只")

    # ② 退市（通联清单，补精确退市日）
    n_del = 0
    for ticker, exch, name, ld, dd in day.execute(
            "SELECT ticker, exchangeCD, secShortName, listDate, delistDate FROM sec_delisted"):
        t = str(ticker or "").strip()
        if not (len(t) == 6 and t.isdigit()) or t.startswith(("200", "900")):
            continue
        if str(exch or "").upper() not in ("XSHG", "XSHE", "XBSE", "NEEQ"):
            continue
        code = norm_code(t, exch)
        n_del += 1
        if code in rows:
            c, nm, hy, ipo, _, _ = rows[code]
            rows[code] = (c, nm, hy, ipo or (ld or ""), (dd or "")[:10], "0")
        else:
            rows[code] = (code, name or "", "", (ld or "")[:10], (dd or "")[:10], "0")
    print(f"通联退市: {n_del:,} 只（其中已在通达信在册的做合并）")

    out.executemany("INSERT OR REPLACE INTO stock_basic VALUES (?,?,?,?,?,?)", list(rows.values()))
    out.commit()

    n = out.execute("SELECT COUNT(*) FROM stock_basic").fetchone()[0]
    st = dict(out.execute("SELECT status, COUNT(*) FROM stock_basic GROUP BY status").fetchall())
    print(f"\n完成: {n:,} 只（在市 {st.get('1',0):,} / 退市 {st.get('0',0):,}）")

    # 与旧库对比
    old = sqlite3.connect(f"file:{OLD.as_posix()}?mode=ro", uri=True, timeout=30)
    o = old.execute("SELECT COUNT(*), SUM(status='1'), SUM(status='0') FROM stock_basic").fetchone()
    print(f"旧库: {o[0]:,} 只（在市 {o[1]:,} / 退市 {o[2]:,}）")
    old_codes = {r[0] for r in old.execute("SELECT code FROM stock_basic")}
    new_codes = set(rows)
    print(f"  新增 {len(new_codes-old_codes):,} 只 | 缺失 {len(old_codes-new_codes):,} 只")
    print(f"  新增样例: {sorted(new_codes-old_codes)[:8]}")
    print(f"  缺失样例: {sorted(old_codes-new_codes)[:8]}")
    print("\n  industry 口径对比（取样）:")
    for code in ("600519.SH", "000001.SZ"):
        print(f"    {code}: 旧={old.execute('SELECT industry FROM stock_basic WHERE code=?',(code,)).fetchone()} "
              f"新={out.execute('SELECT industry FROM stock_basic WHERE code=?',(code,)).fetchone()}")
    print("\n  退市股抽样（应在市=j=0 & out_date 有值）:")
    for r in out.execute("SELECT * FROM stock_basic WHERE status='0' LIMIT 4"):
        print("   ", r)
    out.close(); meta.close(); day.close(); old.close()
    print(f"\n库: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
