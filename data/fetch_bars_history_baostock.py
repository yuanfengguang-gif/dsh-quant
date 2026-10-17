# -*- coding: utf-8 -*-
"""data/fetch_bars_history_baostock.py —— baostock 全量重拉 2010-2018 历史日线（安全版）

★设计依据（研究 baostock 规则后的针对性改造，避免复现 IP 被封）：
1. 【根因】上次 finance_quality 抓取被封 = multiprocessing 4 进程 + 每股 login/logout（千万次登录）
   → 登录接口比查询接口限频严格得多，反复登录触发 IP 封禁（login 报 10001011）。
2. 【正例】valuation 抓取成功（5.2M 行）= 单进程 + 单次 bs.login() + query_history_k_data_plus 每股 1 次。
3. 【限频】社区实测 baostock QPS ≈ 20（分钟线口径）；日线每股 1 次、串行 + 0.3s 间隔 ≈ 3 QPS，远低于上限。

★本脚本铁律：
  - 单进程、单次 bs.login()（启动时登录一次，全程复用，绝不在循环里重复登录）
  - 串行逐股查询，每股 1 次 query_history_k_data_plus（一次拉满 2010-2018）
  - 每股间隔 RATE 秒（默认 0.3s ≈ 3 QPS）
  - 连续失败 ≥ MAX_CONSEC_FAIL 次 → 暂停 FAIL_BACKOFF 秒（防把「偶发错误」打成「IP 封禁」）
  - 登录失败（10001011 被封）→ 立即退出，绝不重试硬刚
  - 断点续传：logs/bars_history_baostock_progress.txt

★单位口径（与 bars.db 现有 akshare 2019+ 对齐，待 baostock 恢复后逐项实测核对）：
  - code: baostock "sh.600519" → "600519.SH"
  - volume: baostock 股（与 akshare 股一致）
  - amount: baostock 元（与 akshare 元一致）
  - pctChg: baostock 返回「百分数」（1.09=1.09%）→ ÷100 存小数（0.0109，与 akshare 一致）
  - turn: baostock 百分数 → ÷100（与 akshare 小数一致，待核对）
  - adjustflag=2 = 前复权（比例口径，与 akshare qfq 一致）

用法：python data/fetch_bars_history_baostock.py [--start 2010-01-01 --end 2018-12-31] [--limit N]
"""
import os
import sqlite3
import sys
import time
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

for k in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]:
    os.environ.pop(k, None)

PROGRESS = BASE / "logs" / "bars_history_baostock_progress.txt"
RATE = 0.3                 # 每股间隔秒（≈3 QPS）
MAX_CONSEC_FAIL = 20       # 连续失败阈值
FAIL_BACKOFF = 120         # 连续失败后的暂停秒
BARS_DB = BASE / "data" / "cache" / "bars.db"

# baostock query_history_k_data_plus 返回字段顺序（与 fields 参数一致）
FIELDS = "date,code,open,high,low,close,preclose,volume,amount,turn,pctChg,isST"
COLS = FIELDS.split(",")


def _bs_code(code):
    """'600519.SH' → 'sh.600519'"""
    c, suf = code.split(".")
    p = "sh" if suf == "SH" else ("sz" if suf == "SZ" else "bj")
    return f"{p}.{c}"


def _full_code(bs_code):
    """'sh.600519' → '600519.SH'"""
    p, c = bs_code.split(".")
    return f"{c}.{'SH' if p == 'sh' else ('SZ' if p == 'sz' else 'BJ')}"


def load_codes():
    con = sqlite3.connect(str(BASE / "data" / "cache" / "stock_basic.db"))
    codes = [r[0] for r in con.execute(
        "SELECT code FROM stock_basic WHERE code LIKE '%.SH' OR code LIKE '%.SZ'").fetchall()]
    con.close()
    return codes


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2010-01-01")
    ap.add_argument("--end", default="2018-12-31")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    import baostock as bs
    lg = bs.login()
    if lg.error_code != "0":
        print(f"✗ baostock 登录失败: {lg.error_code} {lg.error_msg}", flush=True)
        print("  → 大概率 IP 仍被封（10001011），请等待冷却后再跑，不要反复重试。", flush=True)
        return
    print("✓ baostock 登录成功（单次登录，全程复用）", flush=True)

    codes = load_codes()
    if args.limit:
        codes = codes[:args.limit]
    done = set()
    if PROGRESS.exists():
        done = {l.strip() for l in PROGRESS.read_text(encoding="utf-8").splitlines() if l.strip()}
    todo = [c for c in codes if c not in done]
    print(f"待拉 {len(todo)} 只（已完成 {len(done)}），区间 {args.start}~{args.end}", flush=True)

    con = sqlite3.connect(str(BARS_DB))
    # 先删旧的 baostock 源（若有残档），避免主键冲突
    con.execute("DELETE FROM daily_bar WHERE source='baostock' AND date<=?", (args.end,))
    con.commit()
    n_ok = n_rows = consecutive_fail = 0
    t0 = time.time()
    for i, code in enumerate(todo):
        try:
            rs = bs.query_history_k_data_plus(
                _bs_code(code), FIELDS, start_date=args.start, end_date=args.end,
                frequency="d", adjustflag="2")
            rows = []
            while rs.error_code == "0" and rs.next():
                rows.append(rs.get_row_data())
            if rows:
                df = pd.DataFrame(rows, columns=COLS)
                df["code"] = _full_code(df["code"].iloc[0])
                df["adjust"] = "qfq"
                df["source"] = "baostock"
                # 单位换算（baostock 百分数 → 小数，与 akshare 对齐）
                df["pct_chg"] = pd.to_numeric(df["pctChg"], errors="coerce") / 100.0
                df["turn"] = pd.to_numeric(df["turn"], errors="coerce") / 100.0
                df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
                df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
                df["is_st"] = pd.to_numeric(df["isST"], errors="coerce").fillna(0).astype(int)
                out = df[["code", "date", "open", "high", "low", "close", "preclose",
                          "volume", "amount", "turn", "pct_chg", "is_st", "adjust", "source"]]
                for col in ["open", "high", "low", "close", "preclose", "volume", "amount"]:
                    out[col] = pd.to_numeric(out[col], errors="coerce")
                out.to_sql("daily_bar", con, if_exists="append", index=False)
                con.commit()
                n_rows += len(out)
            n_ok += 1
            consecutive_fail = 0
            with open(PROGRESS, "a", encoding="utf-8") as f:
                f.write(code + "\n")
        except Exception as e:
            consecutive_fail += 1
            if consecutive_fail >= MAX_CONSEC_FAIL:
                print(f"  连续失败 {consecutive_fail} → 暂停 {FAIL_BACKOFF}s（防触发封禁）", flush=True)
                time.sleep(FAIL_BACKOFF)
                consecutive_fail = 0
        time.sleep(RATE)
        if (i + 1) % 100 == 0:
            el = (time.time() - t0) / 60
            print(f"  进度 {i+1}/{len(todo)}，成功 {n_ok}，{n_rows} 行，{el:.1f} 分钟，"
                  f"{n_ok/el:.1f} 只/分", flush=True)
    con.close()
    bs.logout()
    print(f"完成: 成功 {n_ok}/{len(todo)}，{n_rows} 行", flush=True)


if __name__ == "__main__":
    main()
