# -*- coding: utf-8 -*-
"""scripts/export_kb.py —— 从 research_kb.db 导出「结论层」并可版本化的文件 + 生成文档

为什么不导出行情层：
  AGENTS.md 规定「行情数据来自第三方，禁止再分发」。所以：
    - 行情层（idx_daily / div_yield / macro）→ 留在本地 research_kb.db
    - 结论层（round / finding / signal / strategy / error / defect / open）→ 导出到 data/kb/

输出：
  data/kb/conclusions.sql      结论层完整 SQL 转储（别人可重建）
  data/kb/conclusions.json     结论层 JSON（便于阅读/二次使用）
  docs/研究结论总表.md          按类别分组的全部结论（自动生成）
  docs/信号台账.md              13 个信号的完整台账（自动生成）

用法：
  python scripts/export_kb.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parents[1]
DB = BASE / "data" / "cache" / "research_kb.db"
OUTDIR = BASE / "data" / "kb"
DOCS = BASE / "docs"

CONCLUSION_TABLES = ["meta", "round", "finding", "signal", "strategy",
                     "data_source", "error_log", "defect_log", "open_item"]

VERDICT_ZH = {
    "CONFIRMED": "✅ 已验证",
    "FALSIFIED": "❌ 已证伪",
    "PARTIAL": "🟡 部分成立",
    "REFERENCE": "📌 仅参考",
    "USABLE": "✅ 可用",
    "LIGHT": "🟡 可轻用",
    "TEMPERATURE": "🌡️ 仅温度计",
}

CATEGORY_ORDER = ["认知", "收益", "风险", "估值", "信号", "建仓", "风控", "数据"]


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    return con


def export_sql(con: sqlite3.Connection) -> Path:
    out = OUTDIR / "conclusions.sql"
    lines = [
        "-- 红利低波养老方案 · 研究结论层（不含第三方行情数据）",
        f"-- 导出时间：{datetime.now():%Y-%m-%d %H:%M:%S}",
        "-- 来源：research_kb.db（本地全量库）",
        "-- 重建行情层：python scripts/build_research_kb.py",
        "",
    ]
    for t in CONCLUSION_TABLES:
        row = con.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone()
        if not row:
            continue
        lines.append(f"-- ── {t} ──")
        lines.append(f"DROP TABLE IF EXISTS [{t}];")
        lines.append(row["sql"] + ";")
        cols = [d[0] for d in con.execute(f"SELECT * FROM [{t}] LIMIT 1").description]
        # 找出主键（用于 INSERT OR REPLACE 重建）
        for r in con.execute(f"SELECT * FROM [{t}]"):
            vals = []
            for v in r:
                if v is None:
                    vals.append("NULL")
                elif isinstance(v, (int, float)):
                    vals.append(str(v))
                else:
                    vals.append("'" + str(v).replace("'", "''") + "'")
            lines.append(f"INSERT OR REPLACE INTO [{t}] ({','.join(cols)}) VALUES({','.join(vals)});")
        lines.append("")

    OUTDIR.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def export_json(con: sqlite3.Connection) -> Path:
    data = {"exported_at": datetime.now().isoformat(timespec="seconds"),
            "source": "research_kb.db", "tables": {}}
    for t in CONCLUSION_TABLES:
        try:
            data["tables"][t] = [dict(r) for r in con.execute(f"SELECT * FROM [{t}]")]
        except Exception:
            data["tables"][t] = []
    out = OUTDIR / "conclusions.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def gen_findings_doc(con: sqlite3.Connection) -> Path:
    rows = [dict(r) for r in con.execute("SELECT * FROM finding")]
    by_cat: dict[str, list] = {}
    for r in rows:
        by_cat.setdefault(r["category"] or "其他", []).append(r)

    L = ["# 研究结论总表", "",
         f"> 自动生成：{datetime.now():%Y-%m-%d %H:%M}　|　来源：`research_kb.db` 的 `finding` 表",
         "> 重建：`python scripts/export_kb.py`", "",
         f"**共 {len(rows)} 条结论**："
         + "　".join(f"{VERDICT_ZH.get(v, v)} {n} 条"
                    for v, n in con.execute(
                        "SELECT verdict, COUNT(*) FROM finding GROUP BY verdict "
                        "ORDER BY 2 DESC").fetchall()),
         "", "---", ""]

    order = [c for c in CATEGORY_ORDER if c in by_cat] + \
            [c for c in by_cat if c not in CATEGORY_ORDER]
    for cat in order:
        L.append(f"## {cat}（{len(by_cat[cat])} 条）")
        L.append("")
        L.append("| # | 结论 | 证据 | 判定 | 轮次 |")
        L.append("|---|---|---|---|---|")
        for r in sorted(by_cat[cat], key=lambda x: x["fid"]):
            st = (r["statement"] or "").replace("|", "\\|")
            ev = (r["evidence"] or "").replace("|", "\\|")
            L.append(f"| {r['fid']} | {st} | {ev} | {VERDICT_ZH.get(r['verdict'], r['verdict'])} | {r['rid'] or ''} |")
        L.append("")

    L.append("---")
    L.append("")
    L.append("## 说明")
    L.append("")
    L.append("| 判定 | 含义 |")
    L.append("|---|---|")
    L.append("| ✅ 已验证 | 有数据支撑，可写入策略 |")
    L.append("| ❌ 已证伪 | 数据否定，禁止使用 |")
    L.append("| 🟡 部分成立 | 有条件成立（如某段时期失效），只能轻用 |")
    L.append("| 📌 仅参考 | 有信息但不产生交易信号 |")

    out = DOCS / "研究结论总表.md"
    DOCS.mkdir(exist_ok=True)
    out.write_text("\n".join(L), encoding="utf-8")
    return out


def gen_signals_doc(con: sqlite3.Connection) -> Path:
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM signal ORDER BY CASE verdict "
        "WHEN 'USABLE' THEN 0 WHEN 'LIGHT' THEN 1 WHEN 'TEMPERATURE' THEN 2 ELSE 3 END, sid")]

    L = ["# 择时信号台账", "",
         f"> 自动生成：{datetime.now():%Y-%m-%d %H:%M}　|　来源：`research_kb.db` 的 `signal` 表",
         "> 重建：`python scripts/export_kb.py`", "",
         f"**共 {len(rows)} 个信号**："
         + "　".join(f"{VERDICT_ZH.get(v, v)} {n} 个"
                    for v, n in con.execute(
                        "SELECT verdict, COUNT(*) FROM signal GROUP BY verdict "
                        "ORDER BY 2 DESC").fetchall()),
         "", "---", "",
         "## 一、总表", "",
         "| # | 信号 | 类型 | 规则 | 样本 | 策略年化 | 策略回撤 | Calmar | 满仓年化 | 满仓回撤 | 判定 |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]

    def fmt_pct(x):
        return f"{x*100:.2f}%" if isinstance(x, (int, float)) else "—"

    def fmt_num(x):
        return f"{x:.3f}" if isinstance(x, (int, float)) else "—"

    for r in rows:
        L.append("| {sid} | {name} | {stype} | {rule} | {a}~{b} | {ann} | {mdd} | {cal} | "
                 "{annb} | {mddb} | {v} |".format(
                     sid=r["sid"], name=r["name"] or "", stype=r["stype"] or "",
                     rule=(r["rule"] or "").replace("|", "\\|"),
                     a=r["sample_start"] or "", b=r["sample_end"] or "",
                     ann=fmt_pct(r["ann"]), mdd=fmt_pct(r["mdd"]), cal=fmt_num(r["calmar"]),
                     annb=fmt_pct(r["ann_base"]), mddb=fmt_pct(r["mdd_base"]),
                     v=VERDICT_ZH.get(r["verdict"], r["verdict"])))

    L += ["", "---", "", "## 二、逐条说明", ""]
    for r in rows:
        L.append(f"### {r['sid']} · {r['name']}")
        L.append("")
        L.append(f"- **类型**：{r['stype'] or '—'}")
        L.append(f"- **规则**：{r['rule'] or '—'}")
        L.append(f"- **样本**：{r['sample_start'] or '—'} ~ {r['sample_end'] or '—'}")
        if isinstance(r["corr_fwd1y"], (int, float)):
            L.append(f"- **与未来 1 年收益相关系数**：{r['corr_fwd1y']:+.3f}")
        L.append(f"- **判定**：{VERDICT_ZH.get(r['verdict'], r['verdict'])}")
        if r["note"]:
            L.append(f"- **备注**：{r['note']}")
        L.append("")

    L += ["---", "",
          "## 三、汇总（这是本项目的核心教训）", "",
          "**13 个信号里：1 个可用、1 个可轻用、2 个仅作温度计、9 个证伪。**", "",
          "| 教训 | 说明 |",
          "|---|---|",
          "| 预测力 ≠ 可交易性 | ERP 相关系数 0.439（最强）但策略 Calmar 最差 |",
          "| 绝对阈值会漂移 | 股息率≥5% 在 2006-2014 从未达到，2020-2026 达 81% |",
          "| 部分降仓不如全卖 | 全卖 16.33% > 降到30% 16.20% > 降到半仓 16.11% |",
          "| 加过滤器常是负优化 | 连续N月过滤把年化从 16.61% 压到 14.21% |",
          "| 多重比较陷阱 | 测 13 个信号，1-2 个「显著」是随机期望 |"]

    out = DOCS / "信号台账.md"
    out.write_text("\n".join(L), encoding="utf-8")
    return out


def main() -> int:
    if not DB.exists():
        print(f"❌ 知识库不存在：{DB}\n   请先运行 python scripts/build_research_kb.py")
        return 1
    con = connect()

    print("=" * 70)
    print("【导出结论层】")
    print("=" * 70)

    p1 = export_sql(con)
    print(f"  ✅ {p1.relative_to(BASE)}  {p1.stat().st_size/1024:.1f} KB")
    p2 = export_json(con)
    print(f"  ✅ {p2.relative_to(BASE)}  {p2.stat().st_size/1024:.1f} KB")
    p3 = gen_findings_doc(con)
    print(f"  ✅ {p3.relative_to(BASE)}  {p3.stat().st_size/1024:.1f} KB")
    p4 = gen_signals_doc(con)
    print(f"  ✅ {p4.relative_to(BASE)}  {p4.stat().st_size/1024:.1f} KB")

    # 汇总
    print("\n" + "=" * 70)
    print("【知识库内容概览】")
    print("=" * 70)
    for t in ("round", "finding", "signal", "strategy", "data_source",
              "error_log", "defect_log", "open_item"):
        n = con.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
        print(f"  {t:<14s}{n:>4d} 行")

    print("\n【结论分布】")
    for r in con.execute("SELECT category, verdict, COUNT(*) n FROM finding "
                         "GROUP BY category, verdict ORDER BY category, verdict"):
        print(f"  {r['category']:<6s} {VERDICT_ZH.get(r['verdict'], r['verdict']):<12s} {r['n']:>3d}")

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
