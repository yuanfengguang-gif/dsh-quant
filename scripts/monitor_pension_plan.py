# -*- coding: utf-8 -*-
"""scripts/monitor_pension_plan.py —— 养老方案月度监控（v2.3）

一次运行给出：
  1. 建仓进度（10万已投 / 140万待投 / 剩余月数 / 兜底日）
  2. 股息率 5 年分位 → 卫星仓买卖信号
  3. 6 月季节性提醒
  4. ERP 估值温度计（仅参考）
  5. 行业集中度快照
  6. 本月结论（可执行）

用法：
  python scripts/monitor_pension_plan.py                 # 今天
  python scripts/monitor_pension_plan.py --date 2026-10-16
  python scripts/monitor_pension_plan.py --history 12    # 附过去 12 个月信号
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parents[1]
DB = BASE / "data" / "cache" / "dividend_research.db"
CFG = BASE / "config" / "pension_plan.yaml"
OUTDIR = BASE / "reports"


def load_cfg() -> dict:
    with open(CFG, encoding="utf-8") as f:
        return yaml.safe_load(f)


def conn() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)


def rolling_pct(v: np.ndarray, win: int) -> np.ndarray:
    out = np.full(len(v), np.nan)
    for i in range(len(v)):
        seg = v[max(0, i - win + 1):i + 1]
        seg = seg[~np.isnan(seg)]
        if len(seg) > 60 and not np.isnan(v[i]):
            out[i] = (seg < v[i]).mean()
    return out


def load_index(code: str) -> pd.DataFrame:
    with conn() as c:
        d = pd.read_sql_query(
            "SELECT date,close,pe_ttm FROM idx_daily WHERE code=? ORDER BY date", c, params=(code,))
        dy = pd.read_sql_query(
            "SELECT date,dy_ttm FROM div_yield WHERE code=? ORDER BY date", c, params=(code,))
    d = d.merge(dy, on="date", how="left")
    d["date"] = pd.to_datetime(d["date"])
    return d.sort_values("date").reset_index(drop=True)


def load_bond() -> pd.DataFrame:
    with conn() as c:
        b = pd.read_sql_query("SELECT date,value FROM macro WHERE key='cn10y' ORDER BY date", c)
    b["date"] = pd.to_datetime(b["date"])
    return b.rename(columns={"value": "bond10y"})


def get_etf_prices(codes: list[str], asof: str) -> tuple[dict, str]:
    """取 ETF 价格。优先东财历史（可取任意日），失败退化到新浪现价快照。
    返回 (价格字典, 数据来源说明)"""
    out, src = {}, ""
    try:
        import akshare as ak
    except Exception:
        return out, "akshare 不可用"

    # 路径 1：东财历史（可取 asof 当日）
    for c in codes:
        try:
            df = ak.fund_etf_hist_em(symbol=c, period="daily", adjust="")
            df.columns = [str(x) for x in df.columns]
            df["日期"] = pd.to_datetime(df["日期"])
            df = df[df["日期"] <= pd.Timestamp(asof)]
            if len(df):
                out[c] = float(df["收盘"].iloc[-1])
        except Exception:
            pass
    if out:
        return out, "东财历史（asof 当日收盘）"

    # 路径 2：新浪现价快照（只能取最新）
    try:
        snap = ak.fund_etf_category_sina(symbol="ETF基金")
        snap.columns = [str(x) for x in snap.columns]
        snap["code6"] = snap["代码"].astype(str).str.extract(r"(\d{6})")[0]
        px = dict(zip(snap["code6"], pd.to_numeric(snap["最新价"], errors="coerce")))
        for c in codes:
            if c in px and not pd.isna(px[c]):
                out[c] = float(px[c])
        if out:
            return out, "新浪现价快照（非 asof 当日）"
    except Exception:
        pass

    return out, "取数失败（东财+新浪均不可用）"


def bank_strength(cfg: dict) -> dict | None:
    """银行强弱监测（只追踪，不自动调仓）

    计算：中证银行 过去 N 年 vs 红利低波 过去 N 年的年化收益差
    返回：银行年化、红利年化、差值、判定（强/中/弱）
    """
    bm = cfg.get("bank_monitor", {})
    if not bm.get("enabled"):
        return None
    win = float(bm.get("window_years", 3))
    try:
        import akshare as ak
        d = ak.stock_zh_index_daily(symbol=bm.get("index_code", "sz399986"))
        d.columns = [str(x) for x in d.columns]
        d["date"] = pd.to_datetime(d["date"])
        bank = d[["date", "close"]].rename(columns={"close": "bank"})
    except Exception:
        return None

    with conn() as c:
        ref = pd.read_sql_query(
            "SELECT date,close FROM idx_daily WHERE code=? ORDER BY date",
            c, params=(bm.get("benchmark", "H30269"),))
    if len(ref) < 300:
        return None
    ref["date"] = pd.to_datetime(ref["date"])
    ref = ref.rename(columns={"close": "div"})

    m = bank.merge(ref, on="date").sort_values("date").reset_index(drop=True)
    start = m["date"].iloc[-1] - pd.Timedelta(days=int(365.25 * win))
    m = m[m["date"] >= start].reset_index(drop=True)
    if len(m) < 100:
        return None

    yrs = (m["date"].iloc[-1] - m["date"].iloc[0]).days / 365.25
    a_bank = (m["bank"].iloc[-1] / m["bank"].iloc[0]) ** (1 / yrs) - 1
    a_div = (m["div"].iloc[-1] / m["div"].iloc[0]) ** (1 / yrs) - 1
    diff = a_bank - a_div

    strong = float(bm.get("strong_threshold", 0.05))
    weak = float(bm.get("weak_threshold", -0.10))
    if diff > strong:
        level, hint = "强", "银行明显领先，512890 集中度暂不构成拖累"
    elif diff < weak:
        level, hint = "弱", "银行明显落后，考虑降低 512890 权重（用户决定）"
    else:
        level, hint = "中", "银行与红利基本同步，维持 25%"

    # 近年趋势（每年一组，看方向）
    m["yr"] = m["date"].dt.year
    trend = []
    for yr, g in m.groupby("yr"):
        if len(g) < 100:
            continue
        rb = g["bank"].iloc[-1] / g["bank"].iloc[0] - 1
        rd = g["div"].iloc[-1] / g["div"].iloc[0] - 1
        trend.append({"year": int(yr), "bank": float(rb), "div": float(rd),
                      "diff": float(rb - rd)})

    return {"window_years": win, "start": str(m["date"].iloc[0])[:10],
            "bank_ann": float(a_bank), "div_ann": float(a_div), "diff": float(diff),
            "level": level, "hint": hint, "trend": trend,
            "action": bm.get("action", "display_only")}


def entry_breakeven_stats(cfg: dict) -> dict | None:
    """计算「按本计划建仓，账户浮亏转正所需月数」的历史分布。

    模拟：第 1-3 月各投 immediate_amount/3，第 wait_deadline_months 月末投完 wait_amount。
    对每个历史月起点跑一遍，统计转正所需月数。
    """
    ent = cfg.get("entry", {})
    imm = float(ent.get("immediate_amount", 100000))
    wait = float(ent.get("wait_amount", 1400000))
    total = imm + wait
    imm_months = int(ent.get("immediate_months", 3))
    wait_m = int(ent.get("wait_deadline_months", 12))

    with conn() as c:
        d = pd.read_sql_query(
            "SELECT date,close FROM idx_daily WHERE code='H20269' ORDER BY date", c)
    if len(d) < 500:
        return None
    d["date"] = pd.to_datetime(d["date"])
    d = d.sort_values("date").reset_index(drop=True)
    d["ym"] = d["date"].dt.to_period("M")
    m = d.groupby("ym").last().reset_index()
    m["date"] = m["ym"].dt.to_timestamp(how="end")
    px = m["close"].to_numpy(float)
    dates = m["date"].to_numpy()

    bes, worsts = [], []
    horizon = wait_m + 24
    for si in range(0, len(px) - horizon - 2):
        shares = invested = 0.0
        be = None
        worst = 0.0
        for k in range(horizon):
            i = si + k
            if i >= len(px):
                break
            if k < imm_months:
                amt = imm / imm_months
                shares += amt / px[i]; invested += amt
            if k == wait_m - 1:
                shares += wait / px[i]; invested += wait
            val = shares * px[i]
            if invested > 0:
                worst = min(worst, val / invested - 1)
            if be is None and invested >= total - 1 and val >= invested:
                be = k + 1
        if be is not None:
            bes.append(be); worsts.append(worst)
    if not bes:
        return None
    a = np.array(bes)
    return {
        "n": len(a),
        "median": float(np.median(a)),
        "p90": float(np.percentile(a, 90)),
        "worst": int(a.max()),
        "best": int(a.min()),
        "pct_immediate": float((a <= wait_m).mean()),
        "worst_dd_median": float(np.median(worsts)),
        "worst_dd_p10": float(np.percentile(worsts, 10)),
        "span": f"{str(dates[0])[:7]} ~ {str(dates[len(px)-horizon-2])[:7]}",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="评估日期 YYYY-MM-DD，默认今天")
    ap.add_argument("--history", type=int, default=0, help="附过去 N 个月信号")
    args = ap.parse_args()

    cfg = load_cfg()
    asof = args.date or date.today().isoformat()
    asof_ts = pd.Timestamp(asof)

    sig = cfg["signals"]
    plan = cfg["plan"]

    # ── 1. 股息率分位
    idx_code = sig["dividend_pct"]["index_code"]
    d = load_index(idx_code)
    d = d[d["date"] <= asof_ts].reset_index(drop=True)
    if len(d) == 0:
        print(f"❌ 没有 {asof} 之前的数据")
        return 1
    win = int(sig["dividend_pct"]["window"])
    d["dy_pct"] = rolling_pct(d["dy_ttm"].to_numpy(float), win)
    cur_dy = float(d["dy_ttm"].iloc[-1])
    cur_pct = float(d["dy_pct"].iloc[-1]) if not np.isnan(d["dy_pct"].iloc[-1]) else np.nan
    last_date = d["date"].iloc[-1].date()
    exp_th = sig["dividend_pct"]["expensive"]
    cheap_th = sig["dividend_pct"]["cheap"]

    # ── 2. ERP 温度计
    erp_val = erp_pct = np.nan
    if sig["erp_thermometer"]["enabled"]:
        dz = load_index(sig["erp_thermometer"]["index_code"])
        bond = load_bond()
        dz = dz.merge(bond, on="date", how="left")
        dz = dz[(dz["date"] <= asof_ts) & dz["bond10y"].notna()].reset_index(drop=True)
        if len(dz) > 300:
            dz["erp"] = np.where(dz["pe_ttm"] > 0,
                                 1.0 / dz["pe_ttm"] - dz["bond10y"] / 100.0, np.nan)
            dz["erp_pct"] = rolling_pct(dz["erp"].to_numpy(float),
                                        int(sig["erp_thermometer"]["window"]))
            if not np.isnan(dz["erp"].iloc[-1]):
                erp_val = float(dz["erp"].iloc[-1])
                erp_pct = float(dz["erp_pct"].iloc[-1])

    # ── 3. ETF 价格
    codes = [a["code"] for a in cfg["assets"]]
    prices, price_src = get_etf_prices(codes, asof)

    # ── 4. 建仓进度
    ent = cfg.get("entry", {})
    start = ent.get("start_date")
    progress = None
    if start:
        st = pd.Timestamp(start)
        months_passed = (asof_ts.year - st.year) * 12 + (asof_ts.month - st.month)
        deadline = st + pd.DateOffset(months=int(ent["wait_deadline_months"]))
        remain = max(0, int(ent["wait_deadline_months"]) - months_passed)
        progress = {"start": str(st.date()), "months_passed": months_passed,
                    "months_remaining": remain, "deadline": str(deadline.date()),
                    "due": asof_ts >= deadline}

    # ── 5. 判定
    actions = []
    month = asof_ts.month

    if not np.isnan(cur_pct):
        if cur_pct <= exp_th:
            actions.append(("🔴 卫星仓：卖出", f"股息率分位 {cur_pct:.0%} ≤ {exp_th:.0%}（偏贵）"))
        elif cur_pct >= cheap_th:
            actions.append(("🟢 卫星仓：买回", f"股息率分位 {cur_pct:.0%} ≥ {cheap_th:.0%}（便宜）"))
        else:
            actions.append(("⚪ 卫星仓：不动", f"股息率分位 {cur_pct:.0%}（{exp_th:.0%}~{cheap_th:.0%} 中性区）"))

    if sig["june_effect"]["enabled"] and month == int(sig["june_effect"]["month"]):
        rp = sig["june_effect"]["reduced_position"]
        actions.append(("🟡 6 月降仓", f"本月仓位降到 {rp:.0%}（历史 6 月均值 -3.57%）"))

    if progress:
        if progress["due"]:
            actions.append(("🔵 建仓兜底：投完 140 万", f"已到 {progress['deadline']} 截止日，无条件投完"))
        elif progress["months_remaining"] <= 1:
            actions.append(("🟡 建仓临近兜底", f"还剩 {progress['months_remaining']} 个月"))
        else:
            actions.append(("⚪ 建仓等待中", f"还剩 {progress['months_remaining']} 个月（截止 {progress['deadline']}）"))
    else:
        actions.append(("⚪ 建仓未启动", "config 里 entry.start_date 还是 null"))

    actions.append(("📋 生活费", f"本月从货币ETF取 {plan['initial_annual']/12:,.0f} 元"))

    # ── 6. 输出 Markdown
    L = []
    L.append(f"# 养老方案月度监控 · {asof}")
    L.append("")
    L.append(f"> 数据截止：**{last_date}**　|　方案：{plan['name']}")
    L.append(f"> 生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}")
    L.append("")

    L.append("## 一、本月结论")
    L.append("")
    L.append("| 项目 | 动作 | 依据 |")
    L.append("|---|---|---|")
    for a, b in actions:
        L.append(f"| {a.split('：')[0]} | **{a.split('：')[-1]}** | {b} |" if "：" in a
                 else f"| {a} | — | {b} |")
    L.append("")

    L.append("## 二、核心信号")
    L.append("")
    L.append(f"### ① 股息率 5 年分位（管卫星仓）")
    L.append("")
    L.append("| 项目 | 数值 |")
    L.append("|---|---|")
    L.append(f"| 指数 | {sig['dividend_pct']['index_code']} {sig['dividend_pct']['index_name']} |")
    L.append(f"| 股息率(TTM) | **{cur_dy:.2%}** |")
    L.append(f"| 5 年分位 | **{cur_pct:.0%}** |" if not np.isnan(cur_pct) else "| 5 年分位 | — |")
    L.append(f"| 卖出阈值 | ≤ {exp_th:.0%} |")
    L.append(f"| 买回阈值 | ≥ {cheap_th:.0%} |")
    if not np.isnan(cur_pct):
        if cur_pct <= exp_th:
            dist = "**已触发卖出**"
        elif cur_pct >= cheap_th:
            dist = "**已触发买回**"
        else:
            dist = f"距卖出还需分位降 {(cur_pct-exp_th)*100:.0f}pp"
        L.append(f"| 状态 | {dist} |")
    L.append("")
    L.append("> **实测（R43/R44）**：该信号 20 年只调仓 **11 次**（平均 2 年 1 次），不算频繁。"
             "**不要加「连续 N 个月同向」过滤** —— 实测过滤会降低年化 0.6~2.4pp。")
    L.append(">")
    L.append("> **卫星仓要「全卖全买」，不要「部分降仓」**："
             "全卖 16.33%/−52.2%（Calmar 0.313）优于降到 30% 的 16.20%/−56.9%（0.285）。")

    L.append("### ② ERP 估值温度计（仅参考，不调仓）")
    L.append("")
    if not np.isnan(erp_val):
        L.append("| 项目 | 数值 |")
        L.append("|---|---|")
        L.append(f"| ERP = 1/PE − 10Y国债 | **{erp_val:.2%}** |")
        L.append(f"| 3 年分位 | **{erp_pct:.0%}** |")
        if erp_pct >= 0.7:
            judge = "偏便宜（历史上高 ERP 后收益较好）"
        elif erp_pct <= 0.3:
            judge = "偏贵"
        else:
            judge = "中性"
        L.append(f"| 判定 | {judge} |")
        L.append("")
        L.append("> ⚠️ R41/R42 实测：ERP 有最强预测力（相关系数 0.439）但**做成策略反而降低年化**，"
                 "因为 ERP 低点与回撤发生点不重合。**只看不用。**")
    else:
        L.append("_无国债数据（2018 前）_")
    L.append("")

    L.append("## 三、持仓行业集中度（2026Q2 实测，季度复核）")
    L.append("")
    L.append("| 代码 | 名称 | 权重 | 前三大行业 | 银行占比 | 判定 |")
    L.append("|---|---|---|---|---|---|")
    for a in cfg["assets"]:
        t3 = a.get("top3_industry", np.nan)
        bk = a.get("bank_share", np.nan)
        ok = "✅" if (not np.isnan(t3) and t3 < 0.5) else "⚠️"
        L.append(f"| {a['code']} | {a['name']} | {a['weight']:.0%} | {t3:.1%} | {bk:.1%} | {ok} |")
    wt3 = sum(a["weight"] * a.get("top3_industry", 0) for a in cfg["assets"])
    wbk = sum(a["weight"] * a.get("bank_share", 0) for a in cfg["assets"])
    L.append(f"| **加权** | — | 100% | **{wt3:.1%}** | **{wbk:.1%}** | {'✅' if wt3 < 0.5 else '⚠️'} |")
    L.append("")

    L.append("## 四、ETF 最新价")
    L.append("")
    L.append(f"数据来源：{price_src}")
    L.append("")
    if prices:
        L.append("| 代码 | 名称 | 价格 |")
        L.append("|---|---|---|")
        for a in cfg["assets"]:
            p = prices.get(a["code"])
            L.append(f"| {a['code']} | {a['name']} | {p:.3f} |" if p else f"| {a['code']} | {a['name']} | — |")
    else:
        L.append("_行情取数失败（网络或接口问题），**不影响信号判断**_")
    L.append("")

    L.append("## 五、建仓进度")
    if not progress:
        L.append("")
        L.append("**未启动** —— `config/pension_plan.yaml` 的 `entry.start_date` 还是 null。")
        L.append("开始建仓时填写该日期，本工具会自动追踪进度与兜底倒计时。")
        L.append("")
    if progress:
        L.append("")
        L.append("| 项目 | 数值 |")
        L.append("|---|---|")
        L.append(f"| 建仓起始 | {progress['start']} |")
        L.append(f"| 已过月数 | {progress['months_passed']} |")
        L.append(f"| 剩余月数 | **{progress['months_remaining']}** |")
        L.append(f"| 兜底截止日 | **{progress['deadline']}** |")
        L.append(f"| 状态 | {'🔵 该投完了' if progress['due'] else '⚪ 继续等'} |")
        L.append("")
        L.append(f"| 阶段 | 金额 | 说明 |")
        L.append("|---|---|---|")
        L.append(f"| 立即投入 | {ent['immediate_amount']:,} 元 | 分 {ent['immediate_months']} 个月定投 |")
        L.append(f"| 等待中 | {ent['wait_amount']:,} 元 | 放 511990 货币ETF华宝添益 |")
        L.append(f"| 兜底 | 第 {ent['wait_deadline_months']} 个月末 | **无条件投完** |")
        L.append("")

    # ── 银行强弱监测（只追踪，不自动调仓）
    bst = bank_strength(cfg)
    if bst:
        L.append("## 六、银行强弱监测（只追踪，不自动调仓）")
        L.append("")
        L.append(f"> 中证银行 vs 红利低波，滚动 {bst['window_years']:.0f} 年"
                 f"（{bst['start']} 起算）")
        L.append("")
        L.append("| 项目 | 数值 |")
        L.append("|---|---|")
        L.append(f"| 中证银行 年化 | {bst['bank_ann']:.2%} |")
        L.append(f"| 红利低波 年化 | {bst['div_ann']:.2%} |")
        L.append(f"| **差值（银行 − 红利）** | **{bst['diff']*100:+.2f}pp** |")
        L.append(f"| **判定** | **{bst['level']}** |")
        L.append(f"| 提示 | {bst['hint']} |")
        L.append("")
        L.append("**逐年分解：**")
        L.append("")
        L.append("| 年份 | 银行 | 红利低波 | 差值 |")
        L.append("|---|---|---|---|")
        for t in bst["trend"]:
            L.append(f"| {t['year']} | {t['bank']:+.2%} | {t['div']:+.2%} | "
                     f"**{t['diff']*100:+.2f}pp** |")
        L.append("")
        L.append("> ⚠️ **这是顺势指标，不是预测指标。** 银行走强可能已接近末期"
                 "（2022-2024 曾连续 3 年落后 22-32pp 后反转）。"
                 "**只用于追踪理解，是否调整权重由你决定。**")

    # ── 建仓期回本参考
    bes = entry_breakeven_stats(cfg)
    if bes:
        L.append("## 七、建仓期回本参考（历史统计）")
        L.append("")
        L.append(f"> 模拟「{ent.get('immediate_amount', 0):,} 元分 {ent.get('immediate_months', 3)} 个月 + "
                 f"{ent.get('wait_amount', 0):,} 元第 {ent.get('wait_deadline_months', 12)} 个月投完」，"
                 f"遍历 {bes['n']} 个历史起点（{bes['span']}）。")
        L.append("")
        L.append("| 指标 | 数值 |")
        L.append("|---|---|")
        L.append(f"| **账户浮亏转正所需月数 · 中位** | **{bes['median']:.0f} 个月** |")
        L.append(f"| P90 | {bes['p90']:.0f} 个月 |")
        L.append(f"| **最坏** | **{bes['worst']} 个月（{bes['worst']/12:.1f} 年）** |")
        L.append(f"| 最好 | {bes['best']} 个月 |")
        L.append(f"| 投完即转正的起点占比 | **{bes['pct_immediate']:.1%}** |")
        L.append(f"| 建仓期最深浮亏 · 中位 | {bes['worst_dd_median']:.1%} |")
        L.append(f"| 建仓期最深浮亏 · P10 | {bes['worst_dd_p10']:.1%} |")
        L.append("")
        L.append("> 📌 来源：穷诸葛「红利之道三-节奏的账」提出的指标（一次投入 89 月 vs 分批 14 月）。"
                 "我们的计划因「等 12 个月」，中位 12 个月即转正。")

    if args.history > 0:
        L.append(f"## 八、过去 {args.history} 个月信号历史")
        L.append("")
        L.append("| 月份 | 股息率 | 分位 | 信号 |")
        L.append("|---|---|---|---|")
        d["ym"] = d["date"].dt.to_period("M")
        g = d.groupby("ym").last().tail(args.history)
        for ym, r in g.iterrows():
            pv = r["dy_pct"]
            if np.isnan(pv):
                s = "—"
            elif pv <= exp_th:
                s = "🔴 卖出"
            elif pv >= cheap_th:
                s = "🟢 买回"
            else:
                s = "⚪ 不动"
            L.append(f"| {ym} | {r['dy_ttm']:.2%} | {pv:.0%} | {s} |")
        L.append("")

    L.append("---")
    L.append("")
    L.append("## 附：本工具不做什么")
    L.append("")
    L.append("| 不做 | 原因 |")
    L.append("|---|---|")
    L.append("| 不预测涨跌 | 13 个信号测下来只有 1 个可用（R39） |")
    L.append("| 不给个股建议 | 只用指数/ETF 数据 |")
    L.append("| 不自动下单 | 只出信号，人工执行 |")
    L.append("| 不用 ERP 调仓 | R41/R42 实测它降年化 |")

    md = "\n".join(L)
    OUTDIR.mkdir(exist_ok=True)
    out = OUTDIR / f"月度监控_{asof}.md"
    out.write_text(md, encoding="utf-8")

    # 控制台摘要
    print("=" * 78)
    print(f"【养老方案月度监控】{asof}   数据截止 {last_date}")
    print("=" * 78)
    for a, b in actions:
        print(f"  {a:<22s} {b}")
    print("-" * 78)
    print(f"  股息率 {cur_dy:.2%}  5年分位 {cur_pct:.0%}" if not np.isnan(cur_pct)
          else f"  股息率 {cur_dy:.2%}  分位 —")
    if not np.isnan(erp_val):
        print(f"  ERP {erp_val:.2%}  3年分位 {erp_pct:.0%}（仅参考）")
    print(f"  加权前三大行业 {wt3:.1%}  加权银行 {wbk:.1%}")
    print(f"\n  报告已写入：{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
