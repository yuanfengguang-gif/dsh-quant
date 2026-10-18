# -*- coding: utf-8 -*-
"""scripts/r5_5_layer_sizing.py —— R5-5 三层方案测算 + 主案例（150 万 / 6 万/年）

产出：reports/r5_5_layer_sizing.json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, r"C:\Users\Lenovo\.dsh\skills\tdx-aidata")
sys.path.insert(0, r"C:\Users\Lenovo\.dsh\skills\tdx-aidata\lib")

from tdxaidata import tqs  # noqa: E402

START, END = "2005-01-01", "2026-10-17"
COST = 0.00036
RATES = [0.03, 0.035, 0.04, 0.05]
BUFFERS = [6, 12, 24]
BUF_YIELD = 0.015
INFL = 0.0208
CAP = 1_500_000
ANCHORS = {"C1": {"515180.SH": 1.0}, "C2": {"515080.SH": 1.0},
           "C3": {"515180.SH": 0.5, "515080.SH": 0.5}}
ENGINE = ["512890.SH", "515450.SH", "515100.SH"]


def fetch(code, adj="back"):
    r = tqs.get_market_data(field_list=["Close"], stock_list=[code], period="1d",
                            start_time=START, end_time=END, dividend_type=adj)
    c = r.get("Close")
    if c is None or len(c) == 0:
        return None
    s = c.iloc[:, 0].dropna(); s.index = pd.to_datetime(s.index)
    return s.sort_index()


def corrected(code):
    raw, back = fetch(code, "none"), fetch(code, "back")
    if raw is None or back is None:
        return None, None
    common = raw.index.intersection(back.index); raw, back = raw[common], back[common]
    try:
        d = tqs.get_divid_factors(stock_code=code)
        d = d[d.index <= raw.index[-1]] if d is not None and len(d) else d
    except Exception:
        d = None
    f = (back / raw); f = f / f.iloc[0]
    ret = raw.pct_change(); hfq = raw.copy(); price_adj = raw.copy()
    for i in range(1, len(raw)):
        r = float(ret.iloc[i]) if not np.isnan(ret.iloc[i]) else 0.0
        j = float(f.iloc[i] / f.iloc[i - 1])
        if abs(r) > 0.15 and j > 1.5 and r < -0.40:
            fac = 1.0 / float(raw.iloc[i] / raw.iloc[i - 1])
            hfq.iloc[i:] = hfq.iloc[i:] * fac
            price_adj.iloc[i:] = price_adj.iloc[i:] * fac
    if d is not None and len(d):
        for dt, row in d.iterrows():
            pos = int(raw.index.searchsorted(dt));  prev = float(raw.iloc[pos - 1]) if pos > 0 else 0
            D = float(row.get("Bonus", 0) or 0) / 10.0
            if 0 < pos < len(raw) and 0 < D < prev:
                hfq.iloc[pos:] = hfq.iloc[pos:] * (prev / (prev - D))
    return hfq, d, price_adj


def div_yield(code, price_adj, d, years):
    if d is None or len(d) == 0:
        return 0.0
    end = price_adj.index[-1]
    start = end - pd.Timedelta(days=365 * years)
    amt = sum(float(r.get("Bonus", 0) or 0) / 10.0 for dt, r in d.iterrows() if start <= pd.Timestamp(dt) <= end)
    return float(amt / years / float(price_adj.iloc[-1]))


def monthly_div(code, d, idx):
    s = pd.Series(0.0, index=idx)
    if d is not None and len(d):
        for dt, row in d.iterrows():
            key = pd.Timestamp(dt).to_period("M").to_timestamp("M")
            if key in s.index:
                s.loc[key] += float(row.get("Bonus", 0) or 0) / 10.0
    return s


def portfolio_sim(anchor_w, engine_w, rate, buffer_months, start=None, ret_engine=None, ret_anchor=None,
                  months_limit=240, anchor_yield=0.056):
    """三层组合月度模拟（真实提款）。返回生存与期末。"""
    codes = list(anchor_w) + ENGINE
    series = {}
    for c in codes:
        h, d, pa = corrected(c)
        if h is None:
            return None
        series[c] = (pa, d)
    # 月度净值
    m_idx = pd.date_range("2020-07-31", "2026-10-31", freq="ME")
    navs = {}
    for c in codes:
        h = series[c][0]
        navs[c] = h.reindex(h.index.union(m_idx)).ffill().reindex(m_idx)
    rA = None
    for c, w in anchor_w.items():
        r = navs[c].pct_change().fillna(0)
        rA = r * w if rA is None else rA + r * w
    rE = None
    for c in ENGINE:
        r = navs[c].pct_change().fillna(0)
        rE = r / len(ENGINE) if rE is None else rE + r / len(ENGINE)
    divs = {}
    for c in codes:
        divs[c] = monthly_div(c, series[c][1], m_idx)
    divA = sum(divs[c] * w for c, w in anchor_w.items())
    divE = sum(divs[c] / len(ENGINE) for c in ENGINE)

    cash_ratio = rate / max(0.001, anchor_yield)
    buf_ratio = (buffer_months / 12.0) * rate
    if cash_ratio + buf_ratio > 1:
        cash_ratio = max(0.0, 1 - buf_ratio)
    eng_ratio = max(0.0, 1 - cash_ratio - buf_ratio)
    cash_ratio = min(cash_ratio, 1.0)
    if cash_ratio + buf_ratio > 1:
        cash_ratio, buf_ratio = 1 - buf_ratio, buf_ratio

    V = 1.0
    A, B, E = V * cash_ratio, V * buf_ratio, V * eng_ratio
    start_i = 0
    if start is not None:
        start_i = int(m_idx.searchsorted(pd.Timestamp(start)))
    wd_nom = wd_real = 0.0
    for i in range(start_i + 1, len(m_idx)):
        A *= (1 + float(rA.iloc[i])); E *= (1 + float(rE.iloc[i])); B *= (1 + BUF_YIELD / 12)
        # 分红入现金
        cash = float(divA.iloc[i]) * A + float(divE.iloc[i]) * E
        w = rate / 12 * (1 + INFL) ** ((i - start_i) / 12.0)
        need = max(0.0, w - cash)
        if need > 0:
            take = min(need, B); B -= take; need -= take
            if need > 0:
                sell = min(need, E); E -= sell * (1 + COST); need -= sell
            if need > 0:
                sell = min(need, A); A -= sell * (1 + COST); need -= sell
        wd_nom += w; wd_real += w / (1 + INFL) ** ((i - start_i) / 12.0)
        V = A + B + E
        # 季度再平衡
        if i % 3 == 0 and V > 0:
            tA, tB, tE = V * cash_ratio, V * buf_ratio, V * eng_ratio
            trade = abs(A - tA) + abs(B - tB) + abs(E - tE)
            V -= trade * COST
            A, B, E = tA, tB, tE
        if V <= 0:
            break
    return {"survive_months": i - start_i, "ending_real_pct": round(V / (1 + INFL) ** ((i - start_i) / 12.0) * 100, 2),
            "ending_nominal_pct": round(V * 100, 2), "withdraw_nominal": round(wd_nom * 100, 2)}


def project(anchor_yield, engine_ret, rate, buffer_months, years=20, capital=CAP, fixed_w=None):
    """anchor_yield/engine_ret 为总回报；价格增长 = 总回报 − 股息率。"""
    a_price = max(0.0, anchor_yield - anchor_yield)  # 锚的股息率即 anchor_yield，价格增长≈0

    """常数收益 20 年投影（购买力固定）。"""
    cash_ratio = rate / max(0.001, anchor_yield)
    buf_ratio = (buffer_months / 12.0) * rate
    if cash_ratio + buf_ratio > 1:
        cash_ratio = max(0.0, 1 - buf_ratio)
    eng_ratio = max(0.0, 1 - cash_ratio - buf_ratio)
    V = capital
    A, B, E = V * cash_ratio, V * buf_ratio, V * eng_ratio
    w0 = fixed_w if fixed_w is not None else capital * rate
    months = 0
    for m in range(1, years * 12 + 1):
        A *= (1 + 0.0) ** (1 / 12)
        E *= (1 + max(0.0, engine_ret - 0.03)) ** (1 / 12)
        B *= (1 + BUF_YIELD) ** (1 / 12)
        w = w0 / 12 * (1 + INFL) ** (m / 12.0)
        cash = A * (anchor_yield / 12) + E * (0.03 / 12)
        need = max(0.0, w - cash)
        if need > 0:
            take = min(need, B); B -= take; need -= take
            if need > 0:
                sell = min(need, E); E -= sell; need -= sell
            if need > 0:
                sell = min(need, A); A -= sell; need -= sell
        V = A + B + E
        if V <= 0:
            break
        months = m
    real = V / (1 + INFL) ** (years)
    return {"months": months, "ending_real_pct": round(real / capital * 100, 2),
            "ending_nominal_pct": round(V / capital * 100, 2)}


def min_capital(anchor_yield, engine_ret, rate, buffer_months, years=20):
    lo, hi = 100000, 10000000
    for _ in range(40):
        mid = (lo + hi) / 2
        r = project(anchor_yield, engine_ret, rate, buffer_months, years, mid, fixed_w=60000.0)
        if r["months"] >= years * 12 and r["ending_real_pct"] > 0:
            hi = mid
        else:
            lo = mid
    return hi


def max_rate(anchor_yield, engine_ret, capital=CAP, buffer_months=12, years=20):
    best = 0.0
    for r in [x / 1000 for x in range(10, 81)]:
        res = project(anchor_yield, engine_ret, r, buffer_months, years, capital, fixed_w=None)
        if res["months"] >= years * 12 and res["ending_real_pct"] > 0:
            best = r
    return best


def main() -> int:
    out = {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "meta": {"task": "R5-5 三层比例 + 主案例", "capital": CAP, "infl": INFL}}

    # 股息率
    dy = {}
    for c in ("515180.SH", "515080.SH"):
        h, d, pa = corrected(c)
        dy[c] = {"y3": round(div_yield(c, h, d, 3), 4), "y5": round(div_yield(c, h, d, 5), 4)}
    out["div_yield"] = dy
    out["anchor_yield"] = {"C1": dy["515180.SH"]["y3"], "C2": dy["515080.SH"]["y3"],
                           "C3": round((dy["515180.SH"]["y3"] + dy["515080.SH"]["y3"]) / 2, 4)}

    # 表 1-B / 1-C
    tb, tc = [], []
    for ar, ay in out["anchor_yield"].items():
        for rt in RATES:
            cr = rt / ay
            tb.append({"anchor": ar, "rate": rt, "cash_ratio": round(cr, 4)})
    for rt in RATES:
        for bm in BUFFERS:
            ay = out["anchor_yield"]["C3"]
            cr = rt / ay
            br = (bm / 12) * rt
            er = 1 - cr - br
            tc.append({"rate": rt, "buffer_months": bm, "cash_ratio": round(cr, 4), "buffer_ratio": round(br, 4),
                       "engine_ratio": round(er, 4), "warning": er < 0.10,
                       "annual_withdraw_1m": round(1_000_000 * rt, 0)})
    out["sizing_anchor"] = tb
    out["sizing_matrix"] = tc

    # 缓冲工具（尝试 akshare；取不到则 GC001 近似/假设）
    buf = {"money_fund_511990": {"yield": BUF_YIELD, "note": "价格≈100，按 1.5%/年假设（未用价格序列）"}}
    try:
        import akshare as ak
        rep = ak.repo_rate_hist() if hasattr(ak, "repo_rate_hist") else None
        if rep is not None and len(rep):
            buf["repo"] = {"rows": int(len(rep)), "note": "akshare repo_rate_hist"}
        else:
            buf["repo"] = {"yield": "无", "note": "akshare 无 repo_rate_hist，未取到分期限收益率"}
    except Exception as e:
        buf["repo"] = {"yield": "无", "error": str(e)[:100]}
    out["buffer"] = buf

    # 费率敏感性
    fees = {"current": 0.006, "mid": 0.003, "best": 0.002}
    base = 0.1154  # 组合历史年化（R5-4 P4，低波等权）
    out["fee_sens"] = {}
    for k, f in fees.items():
        out["fee_sens"][k] = {"fee": f, "annual": round(base - (f - 0.002), 4)}
    out["fee_sens"]["gain_best_pp"] = round(out["fee_sens"]["best"]["annual"] - out["fee_sens"]["current"]["annual"], 4)
    out["fee_sens"]["cum20"] = round((1 + out["fee_sens"]["gain_best_pp"]) ** 20 - 1, 4)

    # 估值数据（尝试 akshare）
    try:
        import akshare as ak
        val = {}
        for code in ("H30269", "930955", "000922"):
            try:
                df = ak.index_value_hist_funddb(symbol=code, indicator="市盈率")
                val[code] = {"rows": int(len(df)), "start": str(df.iloc[0, 0])[:10]}
            except Exception as e:
                val[code] = {"error": str(e)[:80]}
        out["valuation"] = val
    except Exception as e:
        out["valuation"] = {"error": str(e)[:80]}

    # 12 组回测（共同窗口 2020-07 起）
    t5 = []
    for rt in RATES:
        for bm in BUFFERS:
            res = portfolio_sim(ANCHORS["C3"], None, rt, bm, anchor_yield=out["anchor_yield"]["C3"])
            t5.append({"rate": rt, "buffer_months": bm, **(res or {"error": "无数据"})})
    out["matrix_backtest"] = t5

    # 主案例 C1/C2/C3（12 月缓冲、4%）
    main_cases = {}
    for name, w in ANCHORS.items():
        hist = portfolio_sim(w, None, 0.04, 12, anchor_yield=out["anchor_yield"][name])
        hist_s1 = portfolio_sim(w, None, 0.04, 12, start="2021-02-18", anchor_yield=out["anchor_yield"][name])
        proj = {
            "base_11": project(out["anchor_yield"][name], 0.1141, 0.04, 12),
            "s3_6": project(out["anchor_yield"][name], 0.06, 0.04, 12),
            "s4_5": project(out["anchor_yield"][name], 0.05, 0.04, 12),
        }
        main_cases[name] = {"hist": hist, "hist_2021": hist_s1, "proj": proj,
                            "cash_ratio": round(0.04 / out["anchor_yield"][name], 4),
                            "engine_ratio": round(1 - 0.04 / out["anchor_yield"][name] - 0.04, 4)}
    out["main_case"] = main_cases
    out["main_answers"] = {
        "min_capital_6pct": round(min_capital(out["anchor_yield"]["C2"], 0.06, 0.04, 12) / 10000, 1),
        "max_rate_6pct": max_rate(out["anchor_yield"]["C2"], 0.06),
        "capital_1_5m_20y_6pct_survive": project(out["anchor_yield"]["C2"], 0.06, 0.04, 12)["months"] >= 240,
        "capital_1_5m_20y_5pct_survive": project(out["anchor_yield"]["C2"], 0.05, 0.04, 12)["months"] >= 240,
    }

    rp = BASE / "reports" / "r5_5_layer_sizing.json"
    rp.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("saved", rp)
    print("yields", out["anchor_yield"])
    print("main", out["main_answers"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
