# -*- coding: utf-8 -*-
"""data/infer_hist_st.py —— 用涨跌停制度反推历史 ST（PIT 安全，不改主库 is_st）

背景（HANDOFF.md P0-3）：
  valuation.db 的 isST 只覆盖 2020-06 起；2020-06 前用的是「通达信当前名称含 ST」近似，
  等于把「今天 ST」回溯到 2000 年，双向错误：
    · 假阳性：当前 ST 的 191 只股票，其 2000-2020 全部历史被标 ST（当时多数并非 ST）
    · 假阴性：历史戴帽、现已摘帽的股票，2020 前完全没标记（主要错误，实测近似段仅 191 只）
  本机无 PIT 历史 ST 源：tushare token 为占位符（config/params.yaml）、通达信只有当前状态、
  CSMAR 无 ST 字段、valuation.isST 仅 2020-06 起。

方法（纯本地、只用价格数据，PIT 安全）：
  ST/*ST 主板股票涨跌幅限制为 ±5%（普通股 ±10%），故「经常贴着 ±5% 封板」是 ST 的价格签名。
    · 适用：主板 600/601/603/605/000/001/002/003 全程；
            创业板 300 仅至 2020H1（2020-08-24 起 ST 亦为 20%）
    · 排除：科创板 688（20%）、北交所 4/8（30%）
    · 签名日：|pct_chg| ∈ [0.047, 0.053]（注意 pct_chg 是**小数**口径）且 close≈high/low
    · 判定：某 code 在某半年签名日占比 ≥ THRESH → 判为 ST
  规则先用 2020-07 起（valuation.isST 精确段，主板）做 precision/recall 验证再外推历史。
  实测（THRESH=0.05）：P=0.821 R=0.699；THRESH=0.02：P=0.751 R=0.863。

输出（全部新增，**不修改** daily_bar.is_st）：
  · data/cache/tdx_meta.db → 表 is_st_inferred(code, period, board, n_days, sig_days, sig_ratio, inferred)
  · logs/infer_hist_st_<时间戳>.json —— 验证指标 + 阈值敏感性 + 分年覆盖 + 与旧近似对比
  · 控制台摘要

用法：python data/infer_hist_st.py [--thresh 0.05]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent.parent
CACHE = BASE / "data" / "cache"
BARS = CACHE / "bars.db"
META = CACHE / "tdx_meta.db"
VAL = CACHE / "valuation.db"
LOGS = BASE / "logs"

SIG_LO, SIG_HI = 0.047, 0.053      # ±5% 容差（**小数**口径：0.05 = 5%）
EXACT_FROM = "2020-07-01"          # valuation.isST 精确覆盖起点（避开 6 月首月）
MAIN_PREFIX = ("600", "601", "603", "605", "000", "001", "002", "003")


def to_code(c6: str) -> str:
    c = str(c6).zfill(6)
    if c.startswith(("6", "9")):
        return f"{c}.SH"
    if c.startswith(("0", "2", "3")):
        return f"{c}.SZ"
    if c.startswith(("4", "8")):
        return f"{c}.BJ"
    return f"{c}.SZ"


def board_of(code: str) -> str:
    c = code.split(".")[0]
    if c.startswith(MAIN_PREFIX):
        return "main"
    if c.startswith("300"):
        return "gem"
    if c.startswith("688"):
        return "star"
    if c.startswith(("4", "8")):
        return "bse"
    return "other"


def rule_applies(board: str, period: str) -> bool:
    if board == "main":
        return True
    if board == "gem":
        return period <= "2020H1"
    return False


def scan_signatures(con: sqlite3.Connection) -> dict[tuple[str, str], list[int]]:
    """一次全表扫描 → {(code, period): [n_days, sig_days]}"""
    out: dict[tuple[str, str], list[int]] = {}
    sql = ("SELECT code, date, pct_chg, high, low, close FROM daily_bar "
           "WHERE adjust='qfq' AND pct_chg IS NOT NULL")
    for code, d, p, h, l, cl in con.execute(sql):
        period = f"{d[:4]}H{1 if int(d[5:7]) <= 6 else 2}"
        if not rule_applies(board_of(code), period):
            continue
        cell = out.setdefault((code, period), [0, 0])
        cell[0] += 1
        a = abs(p)
        if SIG_LO <= a <= SIG_HI and (cl >= h * 0.999 or cl <= l * 1.001):
            cell[1] += 1
    return out


def exact_labels(from_date: str) -> dict[tuple[str, str], float]:
    """2020-07 起每 (code, 半年) 的真实 ST 占比。注意 valuation.isST 是 text '0'/'1'"""
    con = sqlite3.connect(f"file:{VAL.as_posix()}?mode=ro", uri=True, timeout=20)
    agg: dict[tuple[str, str], list[int]] = {}
    for c6, d, isst in con.execute("SELECT code, date, isST FROM valuation WHERE date >= ?", (from_date,)):
        code = to_code(c6)
        if board_of(code) != "main":
            continue
        period = f"{d[:4]}H{1 if int(d[5:7]) <= 6 else 2}"
        cell = agg.setdefault((code, period), [0, 0])
        cell[0] += 1
        cell[1] += int(isst)        # '0'/'1' 文本 → int（勿用 1 if isst else 0）
    con.close()
    return {k: v[1] / v[0] for k, v in agg.items() if v[0] >= 60}


def evaluate(sig: dict, lab: dict, thresh: float) -> dict:
    tp = fp = fn = 0
    for key, (n, s) in sig.items():
        if key not in lab:
            continue
        truth = lab[key] >= 0.5
        pred = (s / n) >= thresh
        if pred and truth:
            tp += 1
        elif pred:
            fp += 1
        elif truth:
            fn += 1
    P = tp / (tp + fp) if tp + fp else None
    R = tp / (tp + fn) if tp + fn else None
    F = (2 * P * R / (P + R)) if (P and R) else None
    return {"tp": tp, "fp": fp, "fn": fn,
            "precision": round(P, 4) if P else None,
            "recall": round(R, 4) if R else None,
            "f1": round(F, 4) if F else None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--thresh", type=float, default=0.05, help="签名占比阈值（默认 0.05）")
    args = ap.parse_args()
    thresh = args.thresh
    t0 = datetime.now()

    con = sqlite3.connect(f"file:{BARS.as_posix()}?mode=ro", uri=True, timeout=30)
    print("扫描 ±5% 封板签名（全表一次）...")
    sig = scan_signatures(con)
    print(f"  覆盖 {len({k[0] for k in sig}):,} 只股票 × {len({k[1] for k in sig})} 个半年")
    old_pre = dict(con.execute(
        "SELECT substr(date,1,4), COUNT(DISTINCT CASE WHEN is_st=1 THEN code END) "
        "FROM daily_bar WHERE date < '2020-06-01' GROUP BY 1"))
    con.close()

    print("读取 valuation.isST 精确标签（2020-07 起，主板）...")
    lab = exact_labels(EXACT_FROM)
    n_st_truth = sum(1 for v in lab.values() if v >= 0.5)
    print(f"  精确标签组 {len(lab):,}，其中 ST 组 {n_st_truth:,} "
          f"({n_st_truth/max(len(lab),1)*100:.2f}%)")

    print("\n=== 规则验证（对 2020H2 起精确标签）===")
    sensitivity = {}
    for th in (0.02, 0.03, 0.05, 0.08, 0.10, 0.15):
        m = evaluate(sig, lab, th)
        sensitivity[f"{th:.2f}"] = m
        star = "  ← 采用" if abs(th - thresh) < 1e-9 else ""
        print(f"  阈值 {th:.2f}: P={m['precision']} R={m['recall']} F1={m['f1']} "
              f"(TP={m['tp']} FP={m['fp']} FN={m['fn']}){star}")
    adopted = sensitivity.get(f"{thresh:.2f}", {})

    # ---- 生成推断表 ----
    inferred_rows = []
    by_period: dict[str, list[int]] = {}
    for (code, period), (n, s) in sig.items():
        ratio = s / n if n else 0.0
        inf = 1 if ratio >= thresh else 0
        inferred_rows.append((code, period, board_of(code), n, s, round(ratio, 5), inf))
        cell = by_period.setdefault(period, [0, 0])
        cell[0] += 1
        cell[1] += inf

    print("\n=== 推断的历史 ST 覆盖（半年: 判 ST 只数 / 该半年有数据只数）===")
    for period in sorted(by_period):
        n_st, n_all = by_period[period][1], by_period[period][0]
        mark = "  ← 精确标签段(仅供对照)" if period >= "2020H2" else ""
        print(f"   {period}: {n_st:>5} / {n_all:>5}  ({n_st/max(n_all,1)*100:5.2f}%){mark}")

    print("\n=== 与旧「当前名称近似」对比（每年判为 ST 的股票数）===")
    print("   年份   旧近似(仅当前ST股)   新推断")
    for year in sorted({p[:4] for p in by_period}):
        halves = [p for p in by_period if p.startswith(year)]
        new_n = max(by_period[p][1] for p in halves) if halves else 0
        old_n = old_pre.get(year, 0)
        print(f"   {year}   {old_n:>10}      {new_n:>8}")

    con = sqlite3.connect(str(META))
    con.execute("DROP TABLE IF EXISTS is_st_inferred")
    con.execute("""CREATE TABLE is_st_inferred (
                     code TEXT, period TEXT, board TEXT, n_days INTEGER,
                     sig_days INTEGER, sig_ratio REAL, inferred INTEGER)""")
    con.executemany("INSERT INTO is_st_inferred VALUES (?,?,?,?,?,?,?)", inferred_rows)
    con.execute("CREATE INDEX IF NOT EXISTS idx_is_st_inf ON is_st_inferred(code, period)")
    con.commit()
    con.close()

    rep = {
        "ts": t0.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_s": round((datetime.now() - t0).total_seconds(), 1),
        "method": (f"±5% 封板签名（|pct_chg|∈[{SIG_LO},{SIG_HI}] 且 close≈high/low）；"
                   f"主板全程 + 创业板≤2020H1；阈值 {thresh}"),
        "caveat": ("同一 5% 涨跌幅制度亦可能出现在其他情形（如未股改 S 股、重大资产重组复牌首日等），"
                   "推断结果是**近似**，非交易所 PIT 标记；precision/recall 已在 2020H2+ 精确段实测。"),
        "validation_on_exact_labels": {
            "window": f"{EXACT_FROM} 起（valuation.isST，主板，≥60 交易日）",
            "groups": len(lab), "st_groups": n_st_truth,
            "adopted_thresh": thresh, "adopted": adopted, "sensitivity": sensitivity,
        },
        "old_approx_stocks_by_year": old_pre,
        "inferred_by_period": {p: {"n_st": v[1], "n_all": v[0]} for p, v in sorted(by_period.items())},
        "rows_written": len(inferred_rows),
        "note": "本脚本不修改 daily_bar.is_st；推断表供质量报告与后续可选切换使用。",
    }
    LOGS.mkdir(exist_ok=True)
    out = LOGS / f"infer_hist_st_{t0.strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告: {out}")
    print(f"推断表: {META} → is_st_inferred（{len(inferred_rows):,} 行，阈值 {thresh}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
