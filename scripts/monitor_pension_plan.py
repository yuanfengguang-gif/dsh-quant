# -*- coding: utf-8 -*-
"""scripts/monitor_pension_plan.py —— 养老方案月度监控（v2.3）

一次运行给出：
  1. 建仓进度（10万已投 / 140万待投 / 剩余月数 / 兜底日）
  2. 股息率绝对阈值 → 卫星仓买卖信号
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


def load_state() -> dict:
    """读取持仓与提款记录（config/portfolio_state.yaml）"""
    f = BASE / "config" / "portfolio_state.yaml"
    if not f.exists():
        return {}
    try:
        with open(f, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        return {}


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


def portfolio_health(cfg: dict, asof: str) -> dict | None:
    """持仓健康：现金池水位、权重漂移、累计提款与购买力

    数据来源：config/portfolio_state.yaml（手工填写）。未填写时返回 None。
    """
    st = load_state()
    if not st:
        return None
    plan = cfg.get("plan", {})
    monthly = float(plan.get("initial_annual", 60000)) / 12.0
    cpi = float(plan.get("assume_cpi", 0.02))

    # 现金
    cash_amt = (st.get("cash") or {}).get("amount")
    cash_amt = float(cash_amt) if cash_amt is not None else None

    # 持仓市值
    prices, _src = get_etf_prices([a["code"] for a in cfg.get("assets", [])], asof)
    rows, total_hold = [], 0.0
    any_holding = False
    for a in cfg.get("assets", []):
        h = next((x for x in (st.get("holdings") or [])
                  if str(x.get("code")) == str(a["code"])), None)
        amt = None
        if h:
            if h.get("amount") is not None:
                amt = float(h["amount"])
            elif h.get("shares") is not None and a["code"] in prices:
                amt = float(h["shares"]) * prices[a["code"]]
        if amt is not None:
            any_holding = True
            total_hold += amt
        rows.append({"code": a["code"], "name": a["name"],
                     "target_weight": float(a.get("weight", 0)),
                     "amount": amt,
                     "drift": None})
    if not any_holding and cash_amt is None:
        return None

    total_asset = total_hold + (cash_amt or 0.0)
    for r in rows:
        if r["amount"] is not None and total_asset > 0:
            r["actual_weight"] = r["amount"] / total_asset
            r["drift"] = r["actual_weight"] - r["target_weight"]
        else:
            r["actual_weight"] = None

    # 提款与购买力
    wds = st.get("withdrawals") or []
    wd_total = 0.0
    wd_real = 0.0
    for w in wds:
        try:
            amt = float(w.get("amount") or 0)
        except Exception:
            continue
        wd_total += amt
        # 按 CPI 折算到最新时点的购买力（简化：用年数幂）
        try:
            dt = pd.Timestamp(w.get("date"))
            yrs = max(0.0, (pd.Timestamp(asof) - dt).days / 365.25)
            wd_real += amt * (1 + cpi) ** yrs
        except Exception:
            wd_real += amt

    deps = st.get("deposits") or []
    dep_total = sum(float(d.get("amount") or 0) for d in deps)

    return {
        "as_of": st.get("as_of"),
        "cash": cash_amt,
        "cash_months": (cash_amt / monthly) if (cash_amt is not None and monthly > 0) else None,
        "cash_min_months": float(cfg.get("risk", {}).get("cash_min_months", 3)),
        "monthly_cost": monthly,
        "holdings": rows,
        "total_hold": total_hold if any_holding else None,
        "total_asset": total_asset if (any_holding or cash_amt is not None) else None,
        "withdrawal_total": wd_total if wds else None,
        "withdrawal_real": wd_real if wds else None,
        "withdrawal_count": len(wds),
        "deposit_total": dep_total if deps else None,
        "deposit_count": len(deps),
    }


def dividend_level(cfg: dict) -> dict | None:
    """股息率绝对值的历史区间（交叉验证分位信号，因为分位会漂移）"""
    code = cfg["signals"]["dividend_abs"]["index_code"]
    d = load_index(code)
    v = d["dy_ttm"].dropna()
    if len(v) < 500:
        return None
    cur = float(v.iloc[-1])
    qs = {p: float(np.percentile(v, p)) for p in (5, 10, 25, 50, 75, 90, 95)}
    return {"cur": cur, "min": float(v.min()), "max": float(v.max()),
            "mean": float(v.mean()), "pct": qs,
            "pctile_now": float((v < cur).mean()), "n": int(len(v))}


def signal_track_record(cfg: dict, horizon_months: int = 12) -> dict | None:
    """信号历史战绩：每次触发后未来 N 个月的实际收益（用于监控信号是否失效）"""
    sig = cfg["signals"]["dividend_abs"]
    d = load_index(sig["index_code"])
    tr_code = {"H30269": "H20269", "000922": "H00922"}.get(sig["index_code"], "H20269")
    with conn() as c:
        t = pd.read_sql_query("SELECT date,close FROM idx_daily WHERE code=? ORDER BY date",
                              c, params=(tr_code,))
    t["date"] = pd.to_datetime(t["date"])
    d = d.merge(t.rename(columns={"close": "tr"}), on="date", how="left")
    d["date"] = pd.to_datetime(d["date"])
    d = d.sort_values("date").reset_index(drop=True)
    exp, cheap = float(sig["sell_below"]), float(sig["buy_above"])
    mo = d.set_index("date")[["dy_ttm", "tr"]].resample("ME").last().reset_index()
    mo["pct"] = mo["dy_ttm"]      # 这里不再是分位，而是绝对股息率本身
    mo["sig"] = np.where(mo["dy_ttm"] <= exp, "SELL",
                         np.where(mo["dy_ttm"] >= cheap, "BUY", ""))
    events, prev = [], ""
    for _, r in mo.iterrows():
        s = r["sig"]
        if s and s != prev:
            events.append((r["date"], s, r["pct"], r["tr"]))
            prev = s
    out = []
    for dt, s, p, tr0 in events:
        idx = mo.index[mo["date"] >= dt + pd.DateOffset(months=horizon_months)]
        if len(idx) == 0 or pd.isna(tr0) or pd.isna(mo.loc[idx[0], "tr"]):
            continue
        out.append({"date": str(dt)[:10], "signal": s, "pct": float(p),
                    "fwd": float(mo.loc[idx[0], "tr"] / tr0 - 1)})
    if not out:
        return None
    sells = [e for e in out if e["signal"] == "SELL"]
    buys = [e for e in out if e["signal"] == "BUY"]
    return {"horizon": horizon_months, "n_total": len(out),
            "n_sell": len(sells), "n_buy": len(buys),
            "sell_avg": float(np.mean([e["fwd"] for e in sells])) if sells else None,
            "buy_avg": float(np.mean([e["fwd"] for e in buys])) if buys else None,
            "recent": out[-6:]}


def price_alerts(cfg: dict, asof: str) -> list:
    """价格异常报警（只基于指数，不需要持仓数据）"""
    out = []
    code = cfg["signals"]["dividend_abs"]["index_code"]
    tr_code = {"H30269": "H20269", "000922": "H00922"}.get(code, "H20269")
    with conn() as c:
        t = pd.read_sql_query("SELECT date,close FROM idx_daily WHERE code=? ORDER BY date",
                              c, params=(tr_code,))
    t["date"] = pd.to_datetime(t["date"])
    t = t[t["date"] <= pd.Timestamp(asof)].reset_index(drop=True)
    if len(t) < 10:
        return out
    d1 = float(t["close"].pct_change().dropna().iloc[-1])
    d5 = float(t["close"].iloc[-1] / t["close"].iloc[-6] - 1) if len(t) > 6 else 0.0
    if d1 <= -0.05:
        out.append(("单日大跌", f"今日跌 {d1:.1%}（阈值 -5%）→ 不要看价格，看信号"))
    if d5 <= -0.08:
        out.append(("一周大跌", f"近 5 日跌 {d5:.1%}（阈值 -8%）→ 检查现金池是否够用"))
    if d5 >= 0.10:
        out.append(("一周大涨", f"近 5 日涨 {d5:.1%} → 检查是否该卖卫星仓（看分位）"))
    return out


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
    idx_code = sig["dividend_abs"]["index_code"]
    d = load_index(idx_code)
    d = d[d["date"] <= asof_ts].reset_index(drop=True)
    if len(d) == 0:
        print(f"❌ 没有 {asof} 之前的数据")
        return 1
    # 绝对阈值：直接用股息率本身，不再算分位
    cur_dy = float(d["dy_ttm"].iloc[-1])
    cur_pct = cur_dy            # 变量名保留以兼容下游
    dy_ok = not np.isnan(cur_dy)
    last_date = d["date"].iloc[-1].date()
    exp_th = float(sig["dividend_abs"]["sell_below"])
    cheap_th = float(sig["dividend_abs"]["buy_above"])

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

    if dy_ok:
        if cur_pct <= exp_th:
            actions.append(("🔴 卫星仓：应空仓", f"股息率 {cur_pct:.2%} ≤ {exp_th:.1%}（太贵）"))
        elif cur_pct >= cheap_th:
            actions.append(("🟢 卫星仓：买回", f"股息率 {cur_dy:.2%} ≥ {cheap_th:.1%}（便宜）"))
        else:
            actions.append(("⚪ 卫星仓：不动", f"股息率 {cur_dy:.2%}（{exp_th:.1%}~{cheap_th:.1%} 中性区）"))

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

    L.append("## 二、核心信号（绝对股息率阈值）")
    L.append("")
    L.append(f"### ① 股息率绝对阈值（管卫星仓）")
    L.append("")
    L.append("| 项目 | 数值 |")
    L.append("|---|---|")
    L.append(f"| 指数 | {sig['dividend_abs']['index_code']} {sig['dividend_abs']['index_name']} |")
    L.append(f"| **当前股息率** | **{cur_dy:.2%}** |")
    L.append(f"| 卖出阈值（太贵） | 股息率 ≤ {exp_th:.1%} |")
    L.append(f"| 买回阈值（便宜） | 股息率 ≥ {cheap_th:.1%} |")
    if dy_ok:
        if cur_dy <= exp_th:
            st = f"**应空仓**（股息率 {cur_dy:.2%} ≤ {exp_th:.1%}）"
        elif cur_dy >= cheap_th:
            st = f"**应满仓**（股息率 {cur_dy:.2%} ≥ {cheap_th:.1%}）"
        else:
            st = (f"**维持现状**（股息率 {cur_dy:.2%} 在 {exp_th:.1%}~{cheap_th:.1%} 之间）")
        L.append(f"| **状态** | {st} |")
        L.append(f"| 距卖出还需 | 股息率降 {(cur_dy-exp_th)*100:.2f}pp"
                 f"（股价约需涨 {(cur_dy/exp_th-1)*100:.0f}%） |")
    L.append(f"| 检查频率 | 每月 |")
    L.append("")
    L.append("> **实测（R89-R99）**：该信号 20 年只调仓 **2 次**（2007-10 卖 / 2014-09 买回）。"
             "Calmar 0.250（永不动 0.226），年化 13.06%（永不动 12.97%）。")
    L.append(">")
    L.append("> **⚠️ 重大局限**：本策略只在「高分红年代」有效。2007-2013 年股息率仅 1.5%~3.5%，"
             "永远够不到 4.0% 买回线 → 长期空仓；2008 年指数跌 66.2%，股息率也只从 1.56% 涨到 2.15%，"
             "仍不满足买回。**20 年回测实质是「13 年空仓 + 7 年满仓」。**")
    L.append(">")
    L.append("> **卫星仓要「全卖全买」，不要「部分降仓」**："
             "全卖 −52.2% 回撤优于降到 30% 的 −56.9%。")
    L.append(">")
    L.append("> **应急条款：不加**。R97 宽版仅 +0.004 Calmar 但多 8 次摩擦；"
             "R98 窄版从不触发；R99 回落版产生「买了又卖」冲突。")

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
        L.append("| 月份 | 股息率 | 卖出线 | 买回线 | 信号 |")
        L.append("|---|---|---|---|---|")
        d["ym"] = d["date"].dt.to_period("M")
        g = d.groupby("ym").last().tail(args.history)
        for ym, r in g.iterrows():
            pv = r["dy_ttm"]
            if np.isnan(pv):
                s = "—"
            elif pv <= exp_th:
                s = "🔴 卖出"
            elif pv >= cheap_th:
                s = "🟢 买回"
            else:
                s = "⚪ 不动"
            L.append(f"| {ym} | {pv:.2%} | {exp_th:.1%} | {cheap_th:.1%} | {s} |")
        L.append("")

    L.append("---")
    L.append("")
    # ── 股息率绝对值（交叉验证分位）
    dl = dividend_level(cfg)
    if dl:
        L.append("## 九、股息率历史位置（20 年分布）")
        L.append("")
        L.append(f"> 分位会随窗口漂移，绝对值不会。两者一起看更可靠。"
                 f"（样本 {dl['n']} 个交易日）")
        L.append("")
        L.append("| 项目 | 数值 |")
        L.append("|---|---|")
        L.append(f"| **当前股息率** | **{dl['cur']:.2%}** |")
        L.append(f"| 当前在历史中的位置 | **{dl['pctile_now']:.0%}**（0%=最低，100%=最高） |")
        L.append(f"| 历史区间 | {dl['min']:.2%} ~ {dl['max']:.2%} |")
        L.append(f"| 历史均值 | {dl['mean']:.2%} |")
        L.append("")
        L.append("| 历史分位点 | 5% | 10% | 25% | 50% | 75% | 90% | 95% |")
        L.append("|---|---|---|---|---|---|---|---|")
        L.append("| 对应股息率 | " + " | ".join(
            f"{dl['pct'][k]:.2%}" for k in (5, 10, 25, 50, 75, 90, 95)) + " |")
        L.append("")

    # ── 信号历史战绩（是否失效）
    strk = signal_track_record(cfg)
    if strk:
        L.append("## 十、信号历史战绩（防失效）")
        L.append("")
        L.append(f"> 每次信号触发后 {strk['horizon']} 个月，红利低波全收益的实际涨跌。"
                 f"共 {strk['n_total']} 次触发。")
        L.append("")
        L.append("| 信号 | 触发次数 | 之后 12 个月平均 |")
        L.append("|---|---|---|")
        if strk["sell_avg"] is not None:
            L.append(f"| 卖出信号（分位≤30%） | {strk['n_sell']} | **{strk['sell_avg']:+.2%}** |")
        if strk["buy_avg"] is not None:
            L.append(f"| 买回信号（分位≥70%） | {strk['n_buy']} | **{strk['buy_avg']:+.2%}** |")
        L.append("")
        L.append("**最近 6 次触发：**")
        L.append("")
        L.append("| 日期 | 信号 | 分位 | 之后 12 个月 |")
        L.append("|---|---|---|---|")
        for e in strk["recent"]:
            L.append(f"| {e['date']} | {'卖出' if e['signal']=='SELL' else '买回'} | "
                     f"{e['pct']:.0%} | {e['fwd']:+.2%} |")
        L.append("")
        L.append("> 📌 **判读方法**：卖出信号后如果平均是**负的**（说明卖对了），买回信号后如果"
                 "平均是**正的**（说明买对了），信号就还活着。如果两者反过来，信号可能已失效。")

    # ── 价格异常报警
    alerts = price_alerts(cfg, asof)
    L.append("## 十一、异常报警")
    L.append("")
    if alerts:
        for a, b in alerts:
            L.append(f"- **{a}**：{b}")
    else:
        L.append("_今日无异常（单日跌超 5% / 5 日跌超 8% / 5 日涨超 10% 才报）_")
    L.append("")
    L.append("> 报警只基于指数价格，**不需要持仓数据**。")
    L.append("> 现金池水位、权重漂移、提款进度这几项需要实际持仓金额，"
             "等开始建仓填写 `entry.start_date` 后再启用。")

    # ── 持仓健康（现金池 / 权重漂移 / 提款购买力）
    ph = portfolio_health(cfg, asof)
    L.append("## 十二、持仓健康（需填 config/portfolio_state.yaml）")
    L.append("")
    if not ph:
        L.append("**未填写持仓数据** —— `config/portfolio_state.yaml` 里的 `holdings` 和 `cash` 都是空的。")
        L.append("")
        L.append("填好之后，这里会自动显示：")
        L.append("")
        L.append("- 现金池还能撑几个月（低于 3 个月会报警）")
        L.append("- 三只 ETF 的实际权重与目标权重的偏离")
        L.append("- 累计提款了多少、按通胀折算的实际购买力")
        L.append("")
    else:
        if ph.get("cash_months") is not None:
            cm = ph["cash_months"]
            warn = cm < ph["cash_min_months"]
            L.append("| 项目 | 数值 |")
            L.append("|---|---|")
            L.append(f"| 现金池余额 | {ph['cash']:,.0f} 元 |")
            L.append(f"| 月生活费 | {ph['monthly_cost']:,.0f} 元 |")
            L.append(f"| **现金池还能撑** | **{cm:.1f} 个月**"
                     f"{' 🔴 **低于红线，必须补足**' if warn else ''} |")
            L.append(f"| 红线 | {ph['cash_min_months']:.0f} 个月 |")
            L.append("")
        if ph.get("holdings"):
            L.append("**权重漂移：**")
            L.append("")
            L.append("| 代码 | 名称 | 市值 | 实际权重 | 目标权重 | 偏离 |")
            L.append("|---|---|---|---|---|---|")
            for r in ph["holdings"]:
                amt = f"{r['amount']:,.0f}" if r["amount"] is not None else "—"
                aw = f"{r['actual_weight']:.1%}" if r["actual_weight"] is not None else "—"
                dr = f"{r['drift']*100:+.1f}pp" if r["drift"] is not None else "—"
                flag = " ⚠️" if (r["drift"] is not None and abs(r["drift"]) > 0.10) else ""
                L.append(f"| {r['code']} | {r['name']} | {amt} | {aw} | "
                         f"{r['target_weight']:.0%} | {dr}{flag} |")
            if ph.get("total_asset"):
                L.append(f"| **合计** | — | **{ph['total_asset']:,.0f}** | 100% | 100% | — |")
            L.append("")
            L.append("> 偏离超过 10pp 会标 ⚠️，提示再平衡。")
            L.append("")
        if ph.get("withdrawal_total") is not None:
            L.append("**提款与购买力：**")
            L.append("")
            L.append("| 项目 | 数值 |")
            L.append("|---|---|")
            L.append(f"| 累计提款笔数 | {ph['withdrawal_count']} |")
            L.append(f"| **累计提款（名义）** | **{ph['withdrawal_total']:,.0f} 元** |")
            L.append(f"| **按通胀折算的实际购买力** | **{ph['withdrawal_real']:,.0f} 元** |")
            if ph.get("deposit_total"):
                L.append(f"| 累计建仓投入 | {ph['deposit_total']:,.0f} 元（{ph['deposit_count']} 笔） |")
            L.append("")
            L.append("> 「实际购买力」= 把每笔提款按 CPI 折算到今天的价值，"
                     "用来判断同样的钱还能不能买到同样的东西。")
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
    print(f"  股息率 {cur_dy:.2%}  卖出线 {exp_th:.1%}  买回线 {cheap_th:.1%}" if dy_ok
          else f"  股息率 {cur_dy:.2%}  分位 —")
    if not np.isnan(erp_val):
        print(f"  ERP {erp_val:.2%}  3年分位 {erp_pct:.0%}（仅参考）")
    print(f"  加权前三大行业 {wt3:.1%}  加权银行 {wbk:.1%}")
    print(f"\n  报告已写入：{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
