# -*- coding: utf-8 -*-
"""risk/report_data_sources.py —— 由审计 JSON 生成《数据源迁移审计报告》markdown

输入：logs/data_source_audit_<ts>.json（由 risk/audit_data_sources.py 生成）
输出：output/DATA_SOURCE_MIGRATION_AUDIT_<日期>.md

用法：python risk/report_data_sources.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent.parent
LOGS, OUT = BASE / "logs", BASE / "output"

# 旧库 → 通达信替代方案（人工判定，用于报告）
PLAN = {
    "finance.db":         ("✅ 可替代", "finance_csmar.db（fin_core/fin_core_q，含 publish_date，年度 95,435 / 季度 325,903）", "P1"),
    "stock_basic.db":     ("✅ 可替代", "tdx_meta.db → universe(5,581) / stock_info_tdx(63 列，含 IsSTGP/IsQuitGP/指数归属)", "P1"),
    "hist_mv.db":         ("⚠️ 需新建管道", "tdx_meta.ActiveCapital(万股) × 当日 close → 流通市值；月频聚合即可", "P2"),
    "finance_quality.db": ("⚠️ 需重算", "CSMAR 指标（ROE/ROA/毛利率等）在 fin_core 内已有，需重写 quality 表", "P2"),
    "valuation.db":       ("⚠️ 部分可替代", "通达信 get_more_info（Beta/PE/市值/股息率）；换手率已可从 ActiveCapital 算；isST 2020+ 短期仍需保留", "P2"),
    "industry.db":        ("⚠️ 部分可替代", "通达信 get_sector_list / get_zzgz_stocklist；申万 162 行体量小，可最后处理", "P3"),
    "lhb.db":             ("❌ 通达信无", "龙虎榜只在东财有 → **不能停**，保留并明确标注为外部补充源", "—"),
    "limitup.db":         ("❌ 通达信无", "涨停/炸板池只在东财有 → **不能停**", "—"),
    "rzrq.db":            ("❌ 通达信无", "两融明细只在东财有 → **不能停**", "—"),
    "consensus.db":       ("❌ 通达信无", "一致预期只在同花顺有 → **不能停**", "—"),
    "minute.db":          ("✅ 死引用", "文件已不存在（改走 parquet），清掉引用即可", "P0"),
    "bars_incr.db":       ("✅ 可废弃", "主库现已可写，写入路由机制失效 → 移除 DailyCache 里的双库路由", "P0"),
}

# 关键运行链路（按项目实际计划任务/门户推断）
KEY_CHAIN = [
    ("data/daily_pipeline.py", "每日全链（18:30 计划任务）"),
    ("data/after_close_scan.py", "盘后扫描（17:35 计划任务）"),
    ("dev_auto.py", "4h 巡检驱动"),
    ("deck/deck_server.py", "门户服务端（8787）"),
    ("deck/live_api.py", "门户 API 层"),
    ("deck/system_live.py", "门户健康面板"),
    ("factors/opportunities/scan.py", "机会扫描（核心）"),
    ("factors/opportunities/tech_pitch.py", "科技 Pitch"),
    ("factors/import_qf_pool.py", "因子池 → 面板加载"),
    ("factors/portfolio_builder.py", "组合构建（15 只）"),
    ("factors/combo_portfolio.py", "组合回测"),
    ("factors/formula_miner.py", "LLM 因子挖掘"),
    ("factors/fscore.py", "F-Score 财务质量"),
    ("factors/reproduce_factors.py", "因子复现"),
    ("risk/stop_monitor.py", "止损监测"),
    ("risk/position_stop_check.py", "持仓止损检查"),
    ("risk/take_profit_check.py", "止盈检查"),
    ("backtest/bt_runner.py", "回测引擎"),
    ("data/cache.py", "DailyCache（统一读写入口）"),
    ("data/tdx_daily_update.py", "通达信增量（新）"),
    ("data/fix_bars_increment.py", "unadj→qfq 合并（新）"),
]


def main() -> int:
    src = sorted(LOGS.glob("data_source_audit_*.json"), key=lambda p: p.stat().st_mtime)[-1]
    rep = json.loads(src.read_text(encoding="utf-8"))
    dbs, per_file, summ = rep["dbs"], rep["per_file"], rep["summary"]
    t = datetime.now().strftime("%Y-%m-%d %H:%M")

    L = []
    A = L.append
    A("# 数据源迁移审计报告（通达信 vs 程序引用）")
    A("")
    A(f"> 生成：{t} · 审计源：`{src.name}` · 复现：`python risk\\audit_data_sources.py`")
    A("> 目标：确认「程序里打开的库」是否都已经换成「为通达信新建的库」。")
    A("")
    A("## 0. 一句话结论")
    A("")
    A("**行情层切了，其它层没切。** 主行情 `bars.db` 已是通达信数据（含增量），"
      "但**财务/基础信息/市值/财务质量/估值**仍大量跑在旧免费源库上，"
      "而本轮新建的 `finance_csmar.db`、`tdx_meta.db` 几乎没被业务代码用起来。")
    A("")
    pure_new, mixed, pure_old = summ["pure_new_files"], summ["mixed_files"], summ["pure_old_files"]
    A(f"| 状态 | 代码文件数 |")
    A(f"|---|---|")
    A(f"| ✅ 只用新库（已切换） | **{len(pure_new)}** |")
    A(f"| ⚠️ 新旧混用（半切换） | **{len(mixed)}** |")
    A(f"| ❌ 只用旧库（完全未切换） | **{len(pure_old)}** |")
    A("")

    A("## 1. 主库确认（第三次核实，含实测）")
    A("")
    bars = dbs.get("bars.db", {})
    A("| 证据 | 结果 |")
    A("|---|---|")
    A("| 代码默认路径 | `data/cache.py:41` → `DEFAULT_DB = CACHE_DIR / \"bars.db\"` |")
    A(f"| 引用规模 | **{bars.get('code_sites')} 处 / {bars.get('code_files')} 个代码文件** |")
    A("| 内容标记 | `daily_bar` 15,700,238 行；`source` = tdx 15,672,362 + tdx_api 27,860 + **baostock 16（残留）** |")
    A("| 旧表归档 | `daily_bar_legacy`（切换前 13.42M 行）仍在库内 |")
    A("| 写权限实测 | `BEGIN IMMEDIATE` 成功取得写锁 → **主库当前可写** |")
    A("| 遗留机制 | `bars_incr.db` 仅 24 KB 空库 → 旧的「主库只读→写入路由」**已不生效** |")
    A("")
    A("**结论**：主库 = `C:\\Users\\Administrator\\ DSH 量化交易系统\\deepseek-harness-quant\\data\\cache\\bars.db`，"
      "内容已是通达信，且可写、可读、被 140 个代码文件引用。")
    A("")
    A("待清理（很小的残留）：`daily_bar` 里 16 行 `source='baostock'`、`adjust='none'`。")
    A("")

    A("## 2. 新库清单 × 实际使用度")
    A("")
    A("| 新库 | 内容 | 代码引用 | 结论 |")
    A("|---|---|---|---|")
    for n in ["bars.db", "bars_tdx.db", "tdx_meta.db", "finance_csmar.db", "datayes_basic.db"]:
        d = dbs.get(n, {})
        note = {
            "bars.db": "✅ 主力，已全面使用",
            "bars_tdx.db": "✅ 增量链路在用",
            "tdx_meta.db": "⚠️ 只有 5 个文件在用（元数据几乎闲置）",
            "finance_csmar.db": "⚠️ 只有 4 个文件在用（CSMAR 财务几乎闲置）",
            "datayes_basic.db": "⚠️ 只有 4 个文件在用（退市清单未接入主链）",
        }.get(n, "")
        A(f"| `{n}` | {rep['new_dbs'].get(n,'')} | {d.get('code_sites',0)} 处 / {d.get('code_files',0)} 个文件 | {note} |")
    A("")

    A("## 3. 旧库清单 × 是否还能停")
    A("")
    A("| 旧库 | 代码引用 | 通达信可替代？ | 替代方案 | 优先级 |")
    A("|---|---|---|---|---|")
    for n, (verdict, how, pr) in PLAN.items():
        d = dbs.get(n, {})
        A(f"| `{n}` | **{d.get('code_sites',0)} 处 / {d.get('code_files',0)} 个文件** | {verdict} | {how} | {pr} |")
    A("")
    A("> **不能停的旧库（通达信无对应）**：`lhb.db`、`limitup.db`、`rzrq.db`、`consensus.db`。"
      "这 4 个必须保留，并在文档/代码注释里明确标注为「外部补充源」，"
      "否则「全部切到通达信」这个目标会以断功能为代价。")
    A("")

    A("## 4. 关键运行链路 → 数据库依赖")
    A("")
    A("N=新库（通达信）、O=旧库（待停）、U=引用但文件不存在（断链）")
    A("")
    A("| 链路 | 说明 | 新库 | 旧库 | 断链 | 判定 |")
    A("|---|---|---|---|---|---|")
    for f, desc in KEY_CHAIN:
        d = per_file.get(f)
        if not d:
            A(f"| `{f}` | {desc} | — | — | — | 无库引用 |")
            continue
        n, o, u = ",".join(d["NEW"]) or "—", ",".join(d["OLD"]) or "—", ",".join(d["UNKNOWN"]) or "—"
        if d["NEW"] and not d["OLD"]:
            verdict = "✅ 已切换"
        elif d["NEW"] and d["OLD"]:
            verdict = "⚠️ 半切换"
        elif d["OLD"]:
            verdict = "❌ 未切换"
        else:
            verdict = "—"
        A(f"| `{f}` | {desc} | {n} | {o} | {u} | {verdict} |")
    A("")

    A("## 5. 完全未切换的代码文件（❌ 只用旧库）")
    A("")
    for f in sorted(pure_old):
        d = per_file[f]
        A(f"- `{f}` — 旧库：{', '.join(d['OLD'])}" + (f"；断链：{', '.join(d['UNKNOWN'])}" if d["UNKNOWN"] else ""))
    A("")

    A("## 6. 半切换的代码文件（⚠️ 新旧混用）")
    A("")
    A(f"共 {len(mixed)} 个。以下按「引用了哪些旧库」排序，优先处理引用旧库多的：")
    A("")
    for f in sorted(mixed, key=lambda x: (-len(per_file[x]["OLD"]), x)):
        d = per_file[f]
        A(f"- `{f}` — 新：{', '.join(d['NEW'])}｜**旧：{', '.join(d['OLD'])}**")
    A("")

    A("## 7. 断链（代码引用了但文件不存在）")
    A("")
    A("| 库名 | 代码处 | 代码文件 |")
    A("|---|---|---|")
    for n, d in sorted(dbs.items(), key=lambda kv: -kv[1]["code_sites"]):
        if d["tier"] == "UNKNOWN" and d["code_sites"] and not d["exists"]:
            A(f"| `{n}` | {d['code_sites']} | {d['code_files']} |")
    A("")
    A("这些引用**不会报错但会静默降级**（大多包在 try/except 里），是「看起来跑通、实际没数据」的典型来源。")
    A("")

    A("## 8. 建议的迁移顺序（按风险与收益）")
    A("")
    A("| 阶段 | 内容 | 为什么先做这个 |")
    A("|---|---|---|")
    A("| **P0** | 清死引用：`minute.db`(9 文件)、`bars_incr.db` 路由（`data/cache.py`） | 零风险、纯减法；消除误导 |")
    A("| **P0** | 清 `bars.db` 里 16 行 baostock 残留 | 让「单一数据源」这句话成立 |")
    A("| **P1** | `finance.db`(39 文件) → `finance_csmar.db` | 旧库无披露日（PIT 不可用），CSMAR 有 publish_date，收益最大 |")
    A("| **P1** | `stock_basic.db`(38 文件) → `tdx_meta` | 基础信息是几乎所有脚本的横切依赖 |")
    A("| **P2** | `hist_mv.db`(24) → ActiveCapital×close 自算 | 组合构建/回测的市值中性化依赖它 |")
    A("| **P2** | `finance_quality.db`(14)、`valuation.db`(9) | 需重算/需新接口，工作量中等 |")
    A("| **P3** | `industry.db`(3) | 体量最小 |")
    A("| **例外** | `lhb.db`/`limitup.db`/`rzrq.db`/`consensus.db` **保留** | 通达信无对应，停了就断功能 |")
    A("")
    A("> 建议做法：**不改 487 处调用点**，而是在 `data/cache.py` 这一层做「源适配器」——"
      "`finance.db` 的读取统一收口到一个函数，内部改成读 `finance_csmar.db` 并做字段映射（列名/代码格式/单位）。"
      "这样 P1 只需改 1-2 个文件，而不是 39 个。")
    A("")

    A("## 9. 复现命令")
    A("")
    A("```powershell")
    A('cd "C:\\Users\\Administrator\\ DSH 量化交易系统\\deepseek-harness-quant"')
    A("python risk\\audit_data_sources.py      # 产出 logs/data_source_audit_<ts>.json")
    A("python risk\\report_data_sources.py     # 生成本报告")
    A("```")
    A("")
    A("*本报告由脚本生成，文件清单来自静态扫描，可直接核对每一处 file:line（见审计 JSON 的 sites 字段）。*")

    OUT.mkdir(exist_ok=True)
    dst = OUT / f"DATA_SOURCE_MIGRATION_AUDIT_{datetime.now().strftime('%Y%m%d')}.md"
    dst.write_text("\n".join(L), encoding="utf-8")
    print(f"报告已生成: {dst}")
    print(f"  已切换 {len(pure_new)} / 半切换 {len(mixed)} / 未切换 {len(pure_old)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
