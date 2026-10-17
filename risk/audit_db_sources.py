# -*- coding: utf-8 -*-
"""risk/audit_db_sources.py —— 「库 → 数据源 → 更新通道」审计（识别无数据源/无更新通道的库）

回答三个问题：
  1) 最终要用的每个 .db，数据来自哪个源？
  2) 每个库有没有「更新通道」（有脚本能写它）？
  3) 有没有「无数据源」或「有源但没人更新」的孤儿库？

判定方法（静态）：
  · 数据源：库内 `source` 列取值 + 库名特征 + 已知映射表（带证据）
  · 写入者：代码里同时出现该库名 + 写关键字（INSERT/CREATE TABLE/to_sql/REPLACE/UPDATE）
  · 读取者：代码里同时出现该库名 + 读关键字（SELECT/read_sql/connect）
  · 新鲜度：文件 mtime 距今天数

用法：python risk/audit_db_sources.py
输出：logs/db_source_map_<时间戳>.json + 控制台表
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent.parent
LOGS = BASE / "logs"
SKIP = {"node_modules", ".git", "__pycache__", "parquet", "dist", "build"}
CODE_EXT = {".py", ".ps1", ".cmd", ".bat", ".js", ".html"}

# 已知数据源映射（人工判定 + 证据）
SOURCE_MAP = {
    "bars.db":        ("通达信（本地文件导入 + API 增量）", "daily_bar.source = tdx / tdx_api / baostock(16 行残留)"),
    "bars_tdx.db":    ("通达信（本地文件 + API）", "adjust=qfq 由本地文件算、unadj 由 API 增量写；adj_factor 来自通达信复权因子文件"),
    "tdx_meta.db":    ("通达信（API：get_stock_info/index/sector）", "universe/stock_info_tdx/index_member/sector 均由 fetch_tdx_meta.py 拉取"),
    "finance_csmar.db": ("CSMAR 国泰安（本地 CSV 导入）", "D:\\BaiduNetdiskDownload\\A股上市公司财务数据（1990-2026.3.31）"),
    "datayes_basic.db": ("通联 DataYes（免费接口）", "sec_listed / sec_delisted（退市清单，listStatusCD=DE）"),
    "finance.db":     ("akshare/同花顺（旧）", "finance_report.source = akshare_ths"),
    "valuation.db":   ("baostock（旧）", "PE/PB/PS/PCF/turn/isST，2020-06 起"),
    "stock_basic.db": ("tushare/akshare（旧）", "code/name/industry/ipo_date"),
    "hist_mv.db":     ("未标注（旧，月频流通市值）", "只有 month/code/circ_mv，无 source 列"),
    "finance_quality.db": ("baostock + tushare 双源（旧）", "quality 表 roe_avg/gp_margin/..."),
    "lhb.db":         ("东方财富（akshare 封装，旧）", "lhb_detail / lhb_inst / lhb_jg_snap"),
    "limitup.db":     ("东方财富（akshare 封装，旧）", "zt_pool 等"),
    "rzrq.db":        ("东方财富（旧）", "rzrq 619 万行"),
    "consensus.db":   ("同花顺（旧）", "consensus 8,419 行快照"),
    "industry.db":    ("申万（akshare 封装，旧）", "sw_index 162 行"),
    "minute.db":      ("（文件不存在）", "已改走 parquet"),
    "bars_incr.db":   ("（历史写入路由库）", "0.02MB 空库"),
    "bars_legacy_backup_20261016.db": ("旧多源快照（回滚用）", "daily_bar: akshare 8.44M + tencent 4.97M + baostock 8,765"),
    "bars_tdx_test.db": ("通达信（导入测试）", "131,473 行 tdx"),
    "demo_bars.db":   ("合成演示数据", "source=demo"),
}
WRITE_RE = re.compile(r"INSERT|CREATE TABLE|to_sql|REPLACE INTO|UPDATE |executemany|ALTER TABLE", re.I)
READ_RE = re.compile(r"SELECT|read_sql|connect\(|PRAGMA|ATTACH", re.I)


def main() -> int:
    t0 = datetime.now()
    # 代码索引
    files = [p for p in BASE.glob("**/*") if p.is_file() and p.suffix.lower() in CODE_EXT
             and not any(x in SKIP for x in p.parts)]
    texts = {}
    for p in files:
        try:
            texts[str(p.relative_to(BASE)).replace("\\", "/")] = p.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

    dbs = []
    for p in sorted(BASE.glob("**/*.db")):
        if any(x in SKIP for x in p.parts):
            continue
        name = p.name
        rel = str(p.relative_to(BASE)).replace("\\", "/")
        is_demo = "demo" in rel
        writers, readers = set(), set()
        for f, txt in texts.items():
            # 只认该 db 的路径语境（区分 data/cache vs data/demo）
            if name not in txt:
                continue
            if is_demo != ("demo" in f):
                # demo 库只由 demo 目录脚本使用；cache 库忽略 demo 目录脚本
                if is_demo or ("demo" in f and f"demo/{name}" not in txt):
                    continue
            # 文件级判定：提到该库 + 全文出现写/读关键字（SQL 里库名与关键字常隔多行）
            if WRITE_RE.search(txt):
                writers.add(f)
            if READ_RE.search(txt):
                readers.add(f)
        size_mb = round(p.stat().st_size / 1024 / 1024, 2)
        age_days = round((datetime.now().timestamp() - p.stat().st_mtime) / 86400, 1)
        src, ev = SOURCE_MAP.get(name, ("未登记", ""))
        # 库内 source 列补充证据
        inner = ""
        try:
            con = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True, timeout=5)
            for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
                cols = [r[1] for r in con.execute(f"PRAGMA table_info(`{t}`)")]
                if "source" in cols:
                    dist = dict(con.execute(f"SELECT source, COUNT(*) FROM `{t}` GROUP BY source").fetchall())
                    inner += f"{t}.source={dist} "
            con.close()
        except Exception:  # noqa: BLE001
            pass
        status = "✅ 有源+有更新通道" if (writers and not name.startswith("bars_legacy")) else \
                 ("🟡 有源+无更新通道（孤儿）" if readers and not writers else \
                  ("⚪ 无人读" if not readers else "❓ 待查"))
        dbs.append({"db": rel, "name": name, "size_mb": size_mb, "age_days": age_days,
                    "source": src, "evidence": ev, "inner_source": inner.strip(),
                    "writers": sorted(writers)[:6], "n_writers": len(writers),
                    "readers": sorted(readers)[:6], "n_readers": len(readers), "status": status})

    print("=" * 108)
    print(f"库 → 数据源 → 更新通道 审计   {t0:%Y-%m-%d %H:%M}")
    print("=" * 108)
    print(f"  {'库':34s}{'MB':>8s}{'天':>5s}  {'写入者':>6s}{'读取者':>6s}  状态")
    for d in dbs:
        print(f"  {d['db']:34s}{d['size_mb']:>8.1f}{d['age_days']:>5.1f}  "
              f"{d['n_writers']:>6d}{d['n_readers']:>6d}  {d['status']}")

    print("\n【一】数据源明细")
    print(f"  {'库':30s} 数据源")
    for d in dbs:
        print(f"  {d['name']:30s} {d['source']}")
        if d["inner_source"]:
            print(f"  {'':30s}   库内标记: {d['inner_source']}")
        if d["evidence"]:
            print(f"  {'':30s}   证据: {d['evidence'][:100]}")

    print("\n【二】孤儿库（有源但没有任何更新脚本 → 数据会越来越旧）")
    for d in dbs:
        if d["status"].startswith("🟡"):
            print(f"  ● {d['name']:26s} 读取者 {d['n_readers']} 个，写入者 0 个，最后更新 {d['age_days']} 天前")
            print(f"      读它的: {', '.join(d['readers'])}")

    print("\n【三】无数据源登记")
    for d in dbs:
        if d["source"] == "未登记":
            print(f"  ● {d['name']}（{d['db']}）")

    out = LOGS / f"db_source_map_{t0.strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps({"ts": t0.strftime("%Y-%m-%d %H:%M:%S"), "dbs": dbs},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n完整结果: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
