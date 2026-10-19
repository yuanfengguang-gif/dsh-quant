# -*- coding: utf-8 -*-
"""scripts/monitor_sell_signal.py —— 每月「该不该卖 ETF」信号检查

用法：
  python scripts/monitor_sell_signal.py                  # 检查最新交易日
  python scripts/monitor_sell_signal.py --date 2026-06-30  # 检查指定日期（复盘用）
  python scripts/monitor_sell_signal.py --history 12      # 看过去 12 个月的信号历史

输出：
  终端打印 + reports/月度卖出信号_YYYY-MM-DD.md

规则（来自 config/pension_plan.yaml）：
  rule=ma_premium（默认）：收盘价 > MA250 × 1.05 触发
  rule=dividend_pct      ：红利低波股息率 5 年滚动分位 <= 30% 触发
  无论是否触发：12 月末强制兜底卖出（每年必卖一次）
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent.parent
CONFIG = BASE / "config" / "pension_plan.yaml"
STATE = BASE / "config" / "pension_state.json"
REPORT_DIR = BASE / "reports"
CACHE = BASE / "data" / "cache" / "etf_cache"


def load_config():
    import yaml
    with open(CONFIG, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"last_sell_date": None, "last_sell_year": None, "last_check": None}


def save_state(s):
    STATE.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")


def fetch_etf(code: str, market: str) -> pd.DataFrame | None:
    """优先本地缓存，其次新浪，最后 akshare 其他源"""
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{market}{code}.csv"
    df = None
    try:
        import akshare as ak
        df = ak.fund_etf_hist_sina(symbol=f"{market}{code}")
        if df is not None and len(df) > 100:
            df.to_csv(f, index=False, encoding="utf-8-sig")
    except Exception:
        df = None
    if df is None and f.exists():
        df = pd.read_csv(f)
        print(f"    ⚠️ {code} 联网失败，用本地缓存（可能是旧数据）")
    if df is None or len(df) == 0:
        return None
    df.columns = [str(c) for c in df.columns]
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def compute_signal(df: pd.DataFrame, window: int, premium: float) -> dict:
    close = df["close"].astype(float)
    ma = close.rolling(window).mean()
    last = df.iloc[-1]
    ma_last = float(ma.iloc[-1])
    px = float(last["close"])
    ratio = px / ma_last if ma_last else float("nan")
    return {
        "date": str(last["date"].date()),
        "close": px,
        "ma": ma_last,
        "ratio": ratio,
        "trigger": bool(ma_last and px > ma_last * (1 + premium)),
        "ma_series": ma,
    }


def annual_need(cfg: dict, year_offset: int) -> float:
    """按假设通胀推算某年的年提款额"""
    p = cfg["plan"]
    return p["initial_annual"] * (1 + p["assume_cpi"]) ** year_offset


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="检查指定日期 YYYY-MM-DD（默认最新）")
    ap.add_argument("--history", type=int, default=0, help="打印过去 N 个月的触发历史")
    args = ap.parse_args()

    cfg = load_config()
    state = load_state()
    sig = cfg["signal"]
    window = sig["ma_window"]
    premium = sig["premium"]
    target_px = None

    print("=" * 96)
    print(f"【{cfg['plan']['name']}】卖出信号检查")
    print("=" * 96)
    print(f"  规则：收盘价 > MA{window} × {1+premium:.2f}  → 触发卖出")
    print(f"  兜底：每年 {sig['fallback_month']} 月末无条件卖出一次")
    print()

    rows = []
    all_dates = None
    for a in cfg["assets"]:
        df = fetch_etf(a["code"], a["market"])
        if df is None:
            print(f"  ❌ {a['code']} {a['name']}：取数失败")
            continue
        if args.date:
            df = df[df["date"] <= args.date].reset_index(drop=True)
        if len(df) < window:
            print(f"  ⚠️ {a['code']} {a['name']}：数据不足 {window} 日")
            continue
        s = compute_signal(df, window, premium)
        rows.append({"asset": a, "sig": s, "df": df})
        all_dates = s["date"]

    if not rows:
        print("  没有可用数据，退出")
        return

    print(f"  检查日期：{all_dates}")
    print()
    print(f"  {'代码':>8s}  {'名称':<22s}{'收盘':>8s}{'MA250':>9s}{'比值':>7s}  {'状态':<12s}{'距离触发':>10s}")
    print("  " + "-" * 88)
    n_trigger = 0
    total_weight_trig = 0.0
    for r in rows:
        a, s = r["asset"], r["sig"]
        gap = (s["ratio"] - (1 + premium)) * 100
        status = "🔴 触发" if s["trigger"] else "⚪ 未触发"
        if s["trigger"]:
            n_trigger += 1
            total_weight_trig += a["weight"]
        print(f"  {a['code']:>8s}  {a['name']:<22s}{s['close']:>8.3f}{s['ma']:>9.3f}"
              f"{s['ratio']:>7.3f}  {status:<12s}{gap:>+9.2f}%")

    # ── 判断今年是否已卖
    cur_year = int(all_dates[:4])
    already = (state.get("last_sell_year") == cur_year)
    month = int(all_dates[5:7])
    fallback = (month == sig["fallback_month"])

    print()
    print("=" * 96)
    print("【本月结论】")
    print("=" * 96)
    if n_trigger > 0 and not already:
        print(f"  🔴 有 {n_trigger} 只触发（合计权重 {total_weight_trig:.0%}）→ 本月应执行卖出")
        print(f"     操作：每只触发 ETF 各卖出「全年所需 ÷ 3」；所得转货币ETF")
    elif n_trigger > 0 and already:
        print(f"  ⚪ 触发但今年已卖过（{state.get('last_sell_date')}）→ 本月不操作")
    elif fallback and not already:
        print(f"  🟡 本月是 {sig['fallback_month']} 月且今年未卖 → **兜底卖出（必做）**")
    else:
        print(f"  ⚪ 未触发 → 本月不操作（继续从货币ETF取生活费）")

    # ── 提款额
    p = cfg["plan"]
    cpi_years = max(0, cur_year - p["cpi_base_year"])
    need = annual_need(cfg, cpi_years)
    print()
    print(f"  本年生活费（按 {p['assume_cpi']:.1%} 通胀推算）：{need:,.0f} 元 / 年"
          f" = {need/12:,.0f} 元 / 月")
    print(f"  货币ETF 目标水位：{need:,.0f} 元（{cfg['cash']['target_months']} 个月）")

    # ── 历史信号
    if args.history:
        print()
        print("=" * 96)
        print(f"【过去 {args.history} 个月的信号历史】")
        print("=" * 96)
        df0 = rows[0]["df"].set_index("date")
        close = df0["close"].astype(float)
        ma = close.rolling(window).mean()
        ratio = close / ma
        me = ratio.resample("ME").last().dropna()
        recent = me.tail(args.history)
        print(f"  {'月份':>10s}{'比值':>8s}  {'状态':<10s}")
        for d, v in recent.items():
            st = "🔴触发" if v > 1 + premium else "⚪"
            print(f"  {str(d.date())[:7]:>10s}{v:>8.3f}  {st}")

    # ── 写报告
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / f"月度卖出信号_{all_dates}.md"
    lines = [f"# 月度卖出信号 · {all_dates}", "",
             f"> 方案：{cfg['plan']['name']}　规则：收盘 > MA{window} × {1+premium:.2f}",
             "", "| 代码 | 名称 | 收盘 | MA250 | 比值 | 状态 | 距离触发 |",
             "|---|---|---|---|---|---|---|"]
    for r in rows:
        a, s = r["asset"], r["sig"]
        lines.append(f"| {a['code']} | {a['name']} | {s['close']:.3f} | {s['ma']:.3f} | "
                     f"{s['ratio']:.3f} | {'🔴 触发' if s['trigger'] else '⚪ 未触发'} | "
                     f"{(s['ratio']-(1+premium))*100:+.2f}% |")
    lines += ["", f"**结论**：{'本月应卖出（' + str(n_trigger) + ' 只触发）' if (n_trigger and not already) else ('兜底卖出' if (fallback and not already) else '本月不操作')}",
              "", f"本年生活费 {need:,.0f} 元（月 {need/12:,.0f} 元）"]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n  报告已存：{out}")

    state["last_check"] = all_dates
    save_state(state)


if __name__ == "__main__":
    main()
