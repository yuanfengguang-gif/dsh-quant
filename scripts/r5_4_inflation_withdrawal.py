# -*- coding: utf-8 -*-
"""scripts/r5_4_inflation_withdrawal.py —— R5-4 通胀调整提款 + 滚动覆盖度 + 组合测试

1) 515300 2025 年数据核查（TDX back 序列异常）
2) CPI：akshare macro_china_cpi_yearly（年率），2007-01=100；末段外推并标注
3) 提款规则 A/B/C/D × 名义/实际
4) 滚动 3 年分红覆盖度
5) 组合 P1-P5 与月度分红覆盖
产出：reports/r5_4_inflation_withdrawal.json
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

START = "2005-01-01"
END = "2026-10-17"
COST = 0.00036
RATE = 0.04
COMBO = {"P1": {"512890.SH": 1.0}, "P2": {"515450.SH": 1.0}, "P3": {"515100.SH": 1.0},
         "P4": {"512890.SH": 1 / 3, "515450.SH": 1 / 3, "515100.SH": 1 / 3},
         "P5": {"512890.SH": 0.60, "515450.SH": 0.25, "515100.SH": 0.15}}


def fetch(code: str, adj: str):
    r = tqs.get_market_data(field_list=["Close"], stock_list=[code], period="1d",
                            start_time=START, end_time=END, dividend_type=adj)
    c = r.get("Close")
    if c is None or len(c) == 0:
        return None
    s = c.iloc[:, 0].dropna()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def corrected(code: str):
    raw = fetch(code, "none")
    back = fetch(code, "back")
    if raw is None or back is None:
        return None, None, []
    common = raw.index.intersection(back.index)
    raw, back = raw[common], back[common]
    try:
        d = tqs.get_divid_factors(stock_code=code)
        d = d[d.index <= raw.index[-1]] if d is not None and len(d) else d
    except Exception:
        d = None
    factor = (back / raw)
    factor = factor / factor.iloc[0]
    ret = raw.pct_change()
    splits = []
    for i in range(1, len(raw)):
        r = float(ret.iloc[i]) if not np.isnan(ret.iloc[i]) else 0.0
        j = float(factor.iloc[i] / factor.iloc[i - 1])
        if abs(r) > 0.15 and j > 1.5 and r < -0.40:
            splits.append({"date": str(raw.index[i])[:10], "ratio": float(raw.iloc[i] / raw.iloc[i - 1])})
    hfq = raw.copy()
    for s in splits:
        pos = int(raw.index.searchsorted(pd.Timestamp(s["date"])))
        if 0 < pos < len(raw):
            hfq.iloc[pos:] = hfq.iloc[pos:] * (1.0 / s["ratio"])
    if d is not None and len(d):
        for dt, row in d.iterrows():
            if any(str(dt)[:10] == s["date"] for s in splits):
                continue
            pos = int(raw.index.searchsorted(dt))
            if pos <= 0 or pos >= len(raw):
                continue
            D = float(row.get("Bonus", 0) or 0) / 10.0
            prev = float(raw.iloc[pos - 1])
            if 0 < D < prev:
                hfq.iloc[pos:] = hfq.iloc[pos:] * (prev / (prev - D))
    return hfq, d, splits


def cpi_series():
    import akshare as ak
    df = ak.macro_china_cpi_yearly().dropna(subset=["今值"])
    df["date"] = pd.to_datetime(df["日期"])
    df["month"] = (df["date"] - pd.offsets.MonthBegin(1)).dt.to_period("M").astype(str)
    yoy = df.set_index("month")["今值"].astype(float).sort_index()
    months = pd.period_range("2007-01", "2026-10", freq="M").astype(str)
    y = yoy.reindex(months)
    last_known = y.dropna().iloc[-1]
    extrapolated = y.isna()
    y = y.fillna(last_known)
    idx = [100.0]
    for v in y.values[1:]:
        idx.append(idx[-1] * (1 + v / 100.0) ** (1 / 12))
    s = pd.Series(idx, index=months)
    meta = {"source": "AkShare macro_china_cpi_yearly（国家统计局年率）",
            "n_months": int(len(s)), "last_known_month": str(yoy.dropna().index[-1]),
            "last_known_yoy": float(last_known), "n_extrapolated": int(extrapolated.sum()),
            "start": months[0], "end": months[-1]}
    return s, meta


def month_end(s: pd.Series) -> pd.Series:
    return s.resample("ME").last().dropna()


def sim_withdraw(nav_m: pd.Series, rule: str, cpi: pd.Series, div_m: pd.Series | None = None) -> dict:
    """nav_m 月末净值；cpi 月度指数（与 nav_m 同期）；div_m 月末分红（每份，规则 D）。"""
    v = 1.0
    peak = 1.0
    maxdd = 0.0
    months = 0
    wd_nom = 0.0
    wd_real = 0.0
    divs = div_m.reindex(nav_m.index).fillna(0.0) if div_m is not None else None
    base = float(cpi.iloc[0])
    def defl(t):
        return float(cpi.get(str(t.to_period("M")), cpi.iloc[-1])) / base
    for i in range(1, len(nav_m)):
        v *= float(nav_m.iloc[i] / nav_m.iloc[i - 1])
        peak = max(peak, v)
        maxdd = min(maxdd, v / peak - 1)
        m = nav_m.index[i]
        if rule == "A":
            w = RATE / 12
        elif rule == "B":
            w = RATE / 12 * defl(m)
        elif rule == "C":
            w = RATE / 12 * max(v, 0)
        else:  # D
            w = 0.0
        if rule == "D":
            if divs is not None:
                dv = float(divs.iloc[i])
                wd_nom += dv
                wd_real += dv / defl(m)
            months += 1
            continue
        sell = min(w, v)
        v -= sell * (1 + COST)
        wd_nom += sell
        wd_real += sell / defl(m)
        months += 1
        if v <= 0:
            break
    end_def = defl(nav_m.index[-1])
    return {"months": months, "ending_nominal_pct": round(max(v, 0) * 100, 2),
            "ending_real_pct": round(max(v, 0) / end_def * 100, 2),
            "withdraw_nominal": round(wd_nom * 100, 2), "withdraw_real": round(wd_real / end_def * 100, 2),
            "maxdd": round(maxdd, 4)}


def main() -> int:
    import akshare as ak
    r52 = json.loads((BASE / "reports" / "r5_2_split_correction.json").read_text(encoding="utf-8"))
    pool24 = sorted(r52["retire"]["by_etf"].keys())
    out = {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "meta": {"task": "R5-4 通胀调整提款", "pool_n": len(pool24), "rate": RATE,
                    "note": "净值=自建修正后复权（raw×折算×分红）；CPI 为年率月度指数，末段外推"}}

    # 515300 2025 核查
    raw = fetch("515300.SH", "none"); back = fetch("515300.SH", "back")
    r25 = raw[(raw.index >= "2025-01-01") & (raw.index <= "2025-12-31")]
    b25 = back[(back.index >= "2025-01-01") & (back.index <= "2025-12-31")]
    hfq515300, _, _ = corrected("515300.SH")
    c25 = hfq515300[(hfq515300.index >= "2025-01-01") & (hfq515300.index <= "2025-12-31")]
    out["check_515300"] = {"corrected_2025_ret": round(float(c25.iloc[-1] / c25.iloc[0] - 1), 4),
                           "raw_2025_ret": round(float(r25.iloc[-1] / r25.iloc[0] - 1), 4),
                           "back_2025_ret": round(float(b25.iloc[-1] / b25.iloc[0] - 1), 4),
                           "raw_first": round(float(r25.iloc[0]), 4), "raw_last": round(float(r25.iloc[-1]), 4),
                           "back_first": round(float(b25.iloc[0]), 4), "back_last": round(float(b25.iloc[-1]), 4),
                           "conclusion": "TDX 后复权序列异常（首尾同值），2025 真实收益需用自建修正序列"}

    cpi, cpi_meta = cpi_series()
    out["cpi"] = cpi_meta
    out["cpi_segments"] = {}
    for a, b in (("2007-01", "2015-12"), ("2016-01", "2026-10")):
        seg = cpi[(cpi.index >= a) & (cpi.index <= b)]
        cum = float(seg.iloc[-1] / seg.iloc[0] - 1)
        yrs = len(seg) / 12
        out["cpi_segments"][f"{a}~{b}"] = {"cum": round(cum, 4), "annual": round((1 + cum) ** (1 / yrs) - 1, 4),
                                           "n_months": int(len(seg))}

    cum_all = float(cpi.iloc[-1] / cpi.iloc[0] - 1)
    out["cpi_full"] = {"cum": round(cum_all, 4), "annual": round((1 + cum_all) ** (12 / len(cpi)) - 1, 4)}
    series, divs = {}, {}
    out["etf"] = {}
    for code in pool24:
        hfq, d, splits = corrected(code)
        if hfq is None or len(hfq) < 30:
            out["etf"][code] = {"error": "无数据"}
            continue
        series[code] = hfq
        nav_m = month_end(hfq)
        div_m = pd.Series(0.0, index=nav_m.index)
        if d is not None and len(d):
            for dt, row in d.iterrows():
                D = float(row.get("Bonus", 0) or 0) / 10.0
                key = pd.Timestamp(dt).to_period("M").to_timestamp("M")
                if key in div_m.index:
                    div_m.loc[key] += D
        divs[code] = div_m
        r = hfq.pct_change().dropna()
        ann = float((hfq.iloc[-1] / hfq.iloc[0]) ** (252 / len(r)) - 1)
        dd = float((hfq / hfq.cummax() - 1).min())
        out["etf"][code] = {"start": str(hfq.index[0])[:10], "n_splits": len(splits),
                            "annual": round(ann, 4), "maxdd": round(dd, 4),
                            "rules": {}, "div_months": [0] * 12}
        for rule in ("A", "B", "C", "D"):
            out["etf"][code]["rules"][rule] = sim_withdraw(nav_m, rule, cpi, div_m)
        for dt in (d.index if d is not None else []):
            out["etf"][code]["div_months"][pd.Timestamp(dt).month - 1] += 1
        out["etf"][code]["div_month_map"] = {str(i + 1): int(v) for i, v in enumerate(out["etf"][code]["div_months"])}
        print(code, out["etf"][code].get("annual"), {k: out["etf"][code]["rules"][k]["ending_real_pct"] for k in "ABCD"}, flush=True)

    # 滚动 3 年覆盖度
    out["rolling_cover"] = {}
    for code in pool24:
        if code not in series:
            continue
        nav_m = month_end(series[code])
        div_m = divs[code].reindex(nav_m.index).fillna(0.0)
        price0 = float(series[code].iloc[0])
        covs = []
        for i in range(len(nav_m) - 36):
            win = div_m.iloc[i:i + 36]
            div_sum = float(win.sum()) / price0
            covs.append(div_sum / (RATE * 3))
        out["rolling_cover"][code] = {
            "n_windows": len(covs),
            "min": round(min(covs), 4) if covs else None,
            "median": round(float(np.median(covs)), 4) if covs else None,
            "max": round(max(covs), 4) if covs else None,
            "share_ge_100": round(float(np.mean([c >= 1 for c in covs])), 4) if covs else None,
        }

    # 组合（515450 不在 24 只池内，仅组合使用）
    for code in ("515450.SH",):
        if code not in series:
            hfq, d, splits = corrected(code)
            if hfq is not None:
                series[code] = hfq
                div_m = pd.Series(0.0, index=month_end(hfq).index)
                if d is not None and len(d):
                    for dt, row in d.iterrows():
                        key = pd.Timestamp(dt).to_period("M").to_timestamp("M")
                        if key in div_m.index:
                            div_m.loc[key] += float(row.get("Bonus", 0) or 0) / 10.0
                divs[code] = div_m

    out["combo"] = {}
    combo_start = max(series[c].index[0] for c in ("512890.SH", "515450.SH", "515100.SH"))
    for name, w in COMBO.items():
        rets = pd.DataFrame({c: series[c].pct_change() for c in w}).dropna()
        rets = rets[rets.index >= combo_start]
        wser = pd.Series(w)
        port = (rets * wser).sum(axis=1)
        # 季度再平衡近似：按季度切分，段内买入持有
        q = port.index.to_period("Q")
        nav = (1 + port).groupby(q).prod()
        nav_series = nav.cumprod()
        ann = float(nav_series.iloc[-1] ** (4 / len(nav_series)) - 1)
        dd = float((nav_series / nav_series.cummax() - 1).min())
        sharpe = float(port.mean() / port.std() * np.sqrt(252)) if port.std() > 0 else None
        # 分红月份（加权，固定权重）
        div_pf = pd.Series(0.0, index=pd.period_range(str(pd.Timestamp(combo_start).to_period("M")), "2026-10", freq="M").astype(str))
        for c, wt in w.items():
            dm = divs[c].copy()
            dm.index = dm.index.to_period("M").astype(str)
            p0 = float(series[c].iloc[0])
            div_pf = div_pf.add((dm / p0 * wt).reindex(div_pf.index).fillna(0.0), fill_value=0.0)
        month_counts = [0] * 12
        for m in div_pf.index:
            mon = int(m[-2:])
            if div_pf[m] > 0:
                month_counts[mon - 1] += 1
        monthly_need = RATE / 12
        share = float((div_pf >= monthly_need).mean())
        out["combo"][name] = {"weights": w, "start": str(pd.Timestamp(combo_start).date()),
                              "annual": round(ann, 4), "maxdd": round(dd, 4),
                              "sharpe": round(sharpe, 3) if sharpe else None,
                              "months_covered": int(sum(1 for x in month_counts if x > 0)),
                              "month_counts": month_counts,
                              "monthly_coverage_share": round(share, 4)}
        print(name, out["combo"][name], flush=True)

    rp = BASE / "reports" / "r5_4_inflation_withdrawal.json"
    rp.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("saved", rp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
