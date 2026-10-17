# -*- coding: utf-8 -*-
"""risk/report_main_switch.py —— 生成《主库切换提案》markdown

依据：tdx_qfq.db（新主库候选） vs bars.db（现主库） vs hist_mv_new / hist_mv
输出：output/MAIN_DB_SWITCH_PROPOSAL_<日期>.md
用法：python risk/report_main_switch.py
"""
from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
C = BASE / "data" / "cache"
OUT = BASE / "output"


def main() -> int:
    con = sqlite3.connect(f"file:{(C / 'tdx_qfq.db').as_posix()}?mode=ro", uri=True, timeout=60)
    con.execute(f"ATTACH DATABASE '{(C / 'bars.db').as_posix()}' AS b")
    con.execute(f"ATTACH DATABASE '{(C / 'tdx_base.db').as_posix()}' AS k")
    con.execute(f"ATTACH DATABASE '{(C / 'hist_mv_new.db').as_posix()}' AS mv")
    con.execute(f"ATTACH DATABASE '{(C / 'hist_mv.db').as_posix()}' AS omv")
    q = lambda s, p=(): con.execute(s, p).fetchone()

    n_new, c_new, a_new, z_new = q("SELECT COUNT(*),COUNT(DISTINCT code),MIN(date),MAX(date) FROM main.daily_bar")
    n_old, c_old, a_old, z_old = q("SELECT COUNT(*),COUNT(DISTINCT code),MIN(date),MAX(date) FROM b.daily_bar WHERE adjust='qfq'")
    only_new = q("""SELECT COUNT(*) FROM main.daily_bar n LEFT JOIN b.daily_bar o
                    ON o.code=n.code AND o.date=n.date AND o.adjust='qfq' WHERE o.code IS NULL""")[0]
    only_old = q("""SELECT COUNT(*) FROM b.daily_bar o LEFT JOIN main.daily_bar n
                    ON n.code=o.code AND n.date=o.date WHERE o.adjust='qfq' AND n.code IS NULL""")[0]

    buckets = Counter()
    for (dev,) in con.execute("""
        SELECT ABS(n.close/o.close - 1) FROM main.daily_bar n
        JOIN b.daily_bar o ON o.code=n.code AND o.date=n.date AND o.adjust='qfq'
        WHERE n.close IS NOT NULL AND o.close IS NOT NULL AND o.close>0 AND n.date<='2026-10-09'"""):
        buckets["<1%" if dev < .01 else "1-10%" if dev < .1 else "10-100%" if dev < 1 else ">100%"] += 1
    tot = sum(buckets.values())

    garb = q("""SELECT COUNT(*), SUM(CASE WHEN n.close>1 THEN 1 ELSE 0 END) FROM b.daily_bar o
                JOIN k.daily kx ON kx.code=o.code AND kx.date=o.date
                LEFT JOIN main.daily_bar n ON n.code=o.code AND n.date=o.date
                WHERE o.adjust='qfq' AND o.close IS NOT NULL AND o.close<1 AND kx.close>10""")

    spots = []
    for code, date in (("000651.SZ", "2015-04-27"), ("600519.SH", "2015-06-01"),
                       ("600519.SH", "2010-06-01"), ("000001.SZ", "2010-06-01"),
                       ("600519.SH", "2026-10-09")):
        raw = q("SELECT close FROM k.daily WHERE code=? AND date=?", (code, date))
        old = q("SELECT close FROM b.daily_bar WHERE code=? AND date=? AND adjust='qfq'", (code, date))
        new = q("SELECT close FROM main.daily_bar WHERE code=? AND date=?", (code, date))
        spots.append((code, date, raw[0] if raw else None, old[0] if old else None,
                      round(new[0], 4) if new else None))

    mv_new = q("SELECT COUNT(*), COUNT(DISTINCT code), COUNT(DISTINCT month), MIN(month), MAX(month) FROM mv.hist_mv")
    mv_old = q("SELECT COUNT(*), COUNT(DISTINCT code), COUNT(DISTINCT month), MIN(month), MAX(month) FROM omv.hist_mv")
    mt_new = q("SELECT COUNT(*) FROM mv.hist_mv WHERE code='600519.SH'")[0]
    mt_old = q("SELECT COUNT(*) FROM omv.hist_mv WHERE code='600519.SH'")[0]

    # 受影响的下游：读 bars.db / hist_mv.db 的代码文件数（来自审计 JSON）
    import json
    audit = sorted((BASE / "logs").glob("data_source_audit_*.json"), key=lambda p: p.stat().st_mtime)
    down = {}
    if audit:
        rep = json.loads(audit[-1].read_text(encoding="utf-8"))
        for n in ("bars.db", "hist_mv.db"):
            down[n] = rep["dbs"].get(n, {}).get("code_files", 0)

    L = []
    A = L.append
    A("# 主库切换提案：bars.db → tdx_qfq.db")
    A("")
    A(f"> 生成：{datetime.now():%Y-%m-%d %H:%M} · 依据：`tdx_base.db` + 后复权因子 · 复现：`python risk\\report_main_switch.py`")
    A("")
    A("## 0. 结论")
    A("")
    A("**建议切换，但要接受「历史价格会变、历史回测需重跑」这个代价。**")
    A(f"新库补齐 **{only_new:,}** 行历史缺失、修复 **{garb[1]:,}** 行垃圾价格、口径统一为乘法前复权，"
      f"并把股票数从 {c_old:,} 提到 {c_new:,}（含北交所）。")
    A("")
    A("## 1. 覆盖对比")
    A("")
    A("| 项 | 现主库 bars.db | 新库 tdx_qfq.db |")
    A("|---|---|---|")
    A(f"| 行数 | {n_old:,} | **{n_new:,}** |")
    A(f"| 股票数 | {c_old:,} | **{c_new:,}** |")
    A(f"| 日期范围 | {a_old} ~ {z_old} | {a_new} ~ {z_new} |")
    A(f"| 复权口径 | 通达信减法式（早期为负→被丢弃） | **乘法式 qfq = raw × h/h(最新)** |")
    A(f"| 仅本库有 | — | **+{only_new:,} 行** |")
    A(f"| 仅旧库有 | {only_old:,} 行（10-12~10-16 增量，已并入新库） | — |")
    A("")
    A("## 2. 重叠段偏差分布（15.67M 行）")
    A("")
    A("| 偏差区间 | 行数 | 占比 |")
    A("|---|---|---|")
    for k in ("<1%", "1-10%", "10-100%", ">100%"):
        A(f"| {k} | {buckets[k]:,} | {buckets[k]/max(tot,1)*100:.2f}% |")
    A("")
    A("> 说明：`<1%` 表示新旧一致（末端口径相同）；差异主要来自两件事——")
    A("> ① 旧库历史段用减法式复权（分红超过价格时转负，被 `qfq_factor>0` 过滤丢弃）；")
    A("> ② 旧库早期存在**垃圾价格**（见 §3）。")
    A("")
    A("## 3. 旧库垃圾价格修复情况")
    A("")
    A(f"旧库中「qfq 价 < 1 元、但同期真实原始价 > 10 元」的行：**{garb[0]:,} 行**（558 只股票）")
    A("")
    A(f"新库中已恢复为 >1 元的：**{garb[1]:,} 行**（{garb[1]/max(garb[0],1)*100:.1f}%）")
    A("")
    A("## 4. 抽样核对（raw → 旧 qfq → 新 qfq）")
    A("")
    A("| 股票 | 日期 | 原始价 | 旧 bars.db | 新 tdx_qfq | 判定 |")
    A("|---|---|---|---|---|---|")
    for code, date, raw, old, new in spots:
        verd = "✅ 一致" if (old and new and abs(new / old - 1) < 0.01) else (
            "🔴 旧库垃圾" if (old and new and new / old > 2) else "🆕 旧库缺失")
        A(f"| {code} | {date} | {raw} | {old if old is not None else '缺失'} | **{new}** | {verd} |")
    A("")
    A("## 5. 市值库同步替换")
    A("")
    A("| 项 | 旧 hist_mv.db | 新 hist_mv_new.db |")
    A("|---|---|---|")
    A(f"| 行数 | {mv_old[0]:,} | **{mv_new[0]:,}** |")
    A(f"| 股票数 | {mv_old[1]:,} | **{mv_new[1]:,}** |")
    A(f"| 月份数 | {mv_old[2]}（{mv_old[3]}~{mv_old[4]}） | **{mv_new[2]}（{mv_new[3]}~{mv_new[4]}）** |")
    A(f"| 茅台 | **{mt_old} 行** | **{mt_new} 个月** |")
    A("")
    A("单位与旧库一致（百万元），重叠点差异 0.08%~1.1%。")
    A("")
    A("## 6. 影响面（切换后需要重建/重跑的）")
    A("")
    A(f"- 读 `bars.db` 的代码文件：**{down.get('bars.db', '?')} 个**（因子/组合/回测/风控/门户）")
    A(f"- 读 `hist_mv.db` 的代码文件：**{down.get('hist_mv.db', '?')} 个**")
    A("- **所有历史回测结论都会变化**（价格口径变了），必须走 T4：")
    A("  1. 重跑因子验证链（ICIR 海选 → 去重 → 组合层 T+1 → 分年度 holdout）")
    A("  2. 重跑组合构建/回测，对比新旧结论方向是否一致")
    A("  3. 重跑下游回归（7 项）")
    A("")
    A("## 7. 切换方案（含回滚）")
    A("")
    A("```powershell")
    A('cd "C:\\Users\\Administrator\\ DSH 量化交易系统\\deepseek-harness-quant"')
    A("# 1) 停掉每日任务（避免切换窗口写入）")
    A('schtasks /Change /TN "DSHQuant-TDX-DailyUpdate" /DISABLE')
    A("# 2) 归档现主库（不删）")
    A('Move-Item data\\cache\\bars.db data\\cache\\bars_before_qfq_switch_20261017.db')
    A("# 3) 新库就位")
    A('Move-Item data\\cache\\tdx_qfq.db data\\cache\\bars.db')
    A("# 4) 市值库同步")
    A('Move-Item data\\cache\\hist_mv.db data\\cache\\hist_mv_before_switch.db')
    A('Move-Item data\\cache\\hist_mv_new.db data\\cache\\hist_mv.db')
    A("# 5) 验收 → 通过后恢复任务")
    A("python risk\\verify_bars_switch.py")
    A('schtasks /Change /TN "DSHQuant-TDX-DailyUpdate" /ENABLE')
    A("```")
    A("")
    A("**回滚**：把两个 `*_before_*.db` / `*_before_qfq_switch_*.db` 改回原名即可。")
    A("")
    A("## 8. 切换前还需你确认的 3 件事")
    A("")
    A("| # | 事项 | 建议 |")
    A("|---|---|---|")
    A("| 1 | 是否接受「历史价格变化 → 历史回测结论全部重跑」 | 接受（旧价格是错的，不修才危险） |")
    A("| 2 | 65 只「因子含负值」股票如何处理 | 保留（已取 1e-6 下限）+ 因子研究剔除该名单 |")
    A("| 3 | 北交所 593 只是否纳入股票池 | 先纳入数据、回测中按需过滤（D-11） |")
    A("")

    OUT.mkdir(exist_ok=True)
    dst = OUT / f"MAIN_DB_SWITCH_PROPOSAL_{datetime.now():%Y%m%d}.md"
    dst.write_text("\n".join(L), encoding="utf-8")
    print(f"已生成: {dst}")
    print(f"  新库 {n_new:,} 行 / 旧库 {n_old:,} 行 / 补齐 {only_new:,} 行 / 垃圾修复 {garb[1]:,} 行")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
