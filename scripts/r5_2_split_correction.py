# -*- coding: utf-8 -*-
"""scripts/r5_2_split_correction.py —— R5-2 份额折算修正（复权因子法）+ 养老提款测试

1) 复权因子法：factor = TDX back / none；跳变>5% 记为事件；
   折算判定：factor 跳变>1.5 且当日 raw 跌幅>40%（含非整数比例，如 3.076）
   分红判定：1.05 < 跳变 < 1.5
2) 修正后净值 = TDX back（已含折算与分红再投）
3) 提款测试：共同窗口（25 只最短）+ 每只全历史（补充）
产出：reports/r5_2_split_correction.json
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
import yaml

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, r"C:\Users\Lenovo\.dsh\skills\tdx-aidata")
sys.path.insert(0, r"C:\Users\Lenovo\.dsh\skills\tdx-aidata\lib")

from tdxaidata import tqs  # noqa: E402

START = "2005-01-01"
END = "2026-10-17"
COST = 0.00036
RATES = [0.03, 0.04, 0.05]
BENCH = {"510300.SH": "沪深300ETF", }


def fetch(code: str, adj: str = "none"):
    r = tqs.get_market_data(field_list=["Close"], stock_list=[code], period="1d",
                            start_time=START, end_time=END, dividend_type=adj)
    c = r.get("Close")
    if c is None or len(c) == 0:
        return None
    s = c.iloc[:, 0].dropna()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def metrics(px: pd.Series) -> dict:
    r = px.pct_change().dropna()
    if len(r) < 2:
        return {}
    nav = px / px.iloc[0]
    ann = float(nav.iloc[-1] ** (252 / len(r)) - 1)
    vol = float(r.std() * np.sqrt(252))
    dd = float((nav / nav.cummax() - 1).min())
    return {"annual": round(ann, 4), "vol": round(vol, 4),
            "sharpe": (round(float(r.mean() / r.std() * np.sqrt(252)), 3) if r.std() > 0 else None),
            "max_drawdown": round(dd, 4), "n_days": int(len(px)),
            "start": str(px.index[0])[:10], "end": str(px.index[-1])[:10]}


def month_end(px: pd.Series) -> pd.Series:
    return px.resample("ME").last().dropna()


def withdraw(nav_m: pd.Series, rate: float) -> dict:
    """月末提款，金额=初始本金的 rate/12，卖出成本 0.036%。"""
    v = 1.0
    w = rate / 12.0
    months = 0
    for i in range(1, len(nav_m)):
        v *= float(nav_m.iloc[i] / nav_m.iloc[i - 1])
        if v <= 0:
            break
        sell = min(w, v)
        v -= sell * (1 + COST)
        months += 1
        if v <= 0:
            break
    return {"months": months, "ending_pct": round(max(v, 0.0) * 100, 2)}


def main() -> int:
    pool = yaml.safe_load((BASE / "config" / "r5_pool_v1.yaml").read_text(encoding="utf-8"))["pool"]
    r51 = json.loads((BASE / "reports" / "r5_1_data_foundation.json").read_text(encoding="utf-8"))
    out = {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "meta": {"task": "R5-2 份额折算修正 + 养老提款测试",
                    "method": "复权因子法：factor=back/none；折算=跳变>1.5 且 raw 跌幅>40%；分红=1.05<跳变<1.5",
                    "cost": COST, "rates": RATES, "cash_return": "0%"},
           "pool": {}, "retire": {}, "bench": {}}

    back_map = {}
    tdx_back_map = {}
    def build_corrected(raw, div, splits):
        hfq = raw.copy()
        split_dates = {s["date"] for s in splits}
        for s in splits:
            pos = int(raw.index.searchsorted(pd.Timestamp(s["date"])))
            if 0 < pos < len(raw):
                hfq.iloc[pos:] = hfq.iloc[pos:] * (1.0 / s["ratio_price"])
        if div is not None and len(div):
            for dt, row in div.iterrows():
                ds = str(dt)[:10]
                if ds in split_dates:
                    continue
                pos = int(raw.index.searchsorted(dt))
                if pos <= 0 or pos >= len(raw):
                    continue
                D = float(row.get("Bonus", 0) or 0) / 10.0
                prev = float(raw.iloc[pos - 1])
                if 0 < D < prev:
                    hfq.iloc[pos:] = hfq.iloc[pos:] * (prev / (prev - D))
        return hfq

    for item in pool:
        code = item["code"]
        raw = fetch(code, "none")
        back = fetch(code, "back")
        if raw is None or back is None:
            out["pool"][code] = {"code": code, "name": item["name"], "error": "无数据"}
            continue
        common = raw.index.intersection(back.index)
        raw, back = raw[common], back[common]
        try:
            d = tqs.get_divid_factors(stock_code=code)
            d = d[d.index <= raw.index[-1]] if d is not None and len(d) else d
        except Exception:
            d = None
        factor = back / raw
        factor = factor / factor.iloc[0]
        ret = raw.pct_change()
        jumps, splits = [], []
        for i in range(1, len(raw)):
            r = float(ret.iloc[i]) if not np.isnan(ret.iloc[i]) else 0.0
            j = float(factor.iloc[i] / factor.iloc[i - 1])
            if abs(r) <= 0.15 and abs(j - 1) <= 0.05:
                continue
            ratio = float(raw.iloc[i] / raw.iloc[i - 1])
            near = min((abs(ratio - 1.0 / n) / (1.0 / n) for n in (2, 3, 4, 5, 8, 10)), default=9)
            kind = "其他"
            if abs(r) > 0.15 and (near < 0.05 or ratio < 0.6) and j > 1.5:
                kind = "折算"
                splits.append({"date": str(raw.index[i])[:10], "ratio_price": round(ratio, 6),
                               "factor_jump": round(j, 4)})
            elif abs(r) > 0.15:
                kind = "分红/其他"
            jumps.append({"date": str(raw.index[i])[:10], "raw_ret": round(r, 4),
                          "factor_jump": round(j, 4), "kind": kind})
        corrected = build_corrected(raw, d, splits)
        m = metrics(corrected)
        mb = metrics(back)
        before = r51["pool"].get(code, {})
        out["pool"][code] = {
            "code": code, "name": item["name"], "style": item["style"],
            "jumps": jumps, "n_jumps": len(jumps), "n_splits": len(splits),
            "splits": splits,
            "annual_before": before.get("modes", {}).get("hfq", {}).get("annual"),
            "maxdd_before": before.get("modes", {}).get("hfq", {}).get("max_drawdown"),
            "annual_after": m["annual"], "maxdd_after": m["max_drawdown"],
            "vol_after": m["vol"], "sharpe_after": m["sharpe"],
            "annual_tdx_back": mb["annual"], "maxdd_tdx_back": mb["max_drawdown"],
            "data_start": m["start"], "data_end": m["end"], "n_days": m["n_days"],
        }
        back_map[code] = corrected
        tdx_back_map[code] = back
        print(f'{code} {item["name"]}: splits={len(splits)} jumps={len(jumps)} '
              f'before={before.get("modes",{}).get("hfq",{}).get("annual")} after={m["annual"]} tdxback={mb["annual"]}', flush=True)

    # 共同窗口
    starts = {c: s.index[0] for c, s in back_map.items()}
    common_start = max(starts.values())
    common_end = min(s.index[-1] for s in back_map.values())
    out["retire"] = {"common_window": {"start": str(common_start)[:10], "end": str(common_end)[:10]},
                     "by_etf": {}, "worst": {}, "coverage": {}}

    for code, back in back_map.items():
        b = back[back.index >= common_start]
        if len(b) < 30:
            continue
        nav_m = month_end(b)
        rec = {}
        for rate in RATES:
            key = f"r{int(rate*100)}"
            w = withdraw(nav_m, rate)
            m = metrics(b)
            rec[key] = {"months": w["months"], "ending_pct": w["ending_pct"],
                        "annual": m["annual"], "maxdd": m["max_drawdown"]}
        out["retire"]["by_etf"][code] = rec
        # 全历史补充
        nav_full = month_end(back)
        rec_full = {}
        for rate in RATES:
            rec_full[f"r{int(rate*100)}"] = withdraw(nav_full, rate)
        out["retire"].setdefault("full_history", {})[code] = {
            "start": str(back.index[0])[:10],
            **{k: v for k, v in rec_full.items()},
        }
        # 最差/最好起点（滚动 36 个月）
        vals = []
        for i in range(len(nav_full) - 36):
            seg = nav_full.iloc[i:i + 37].reset_index(drop=True)
            v = 1.0
            w = 0.04 / 12
            ok = True
            for j in range(1, len(seg)):
                v *= seg.iloc[j] / seg.iloc[j - 1]
                if v <= 0:
                    ok = False
                    break
                v -= min(w, v) * (1 + COST)
            if ok and v > 0:
                vals.append((str(nav_full.index[i])[:10], v))
        if vals:
            w0 = min(vals, key=lambda x: x[1])
            b0 = max(vals, key=lambda x: x[1])
            out["retire"]["worst"][code] = {"worst_start": w0[0], "worst_end_pct": round(w0[1] * 100, 2),
                                            "best_start": b0[0], "best_end_pct": round(b0[1] * 100, 2)}
        # 分红覆盖度（按年，r4）
        divs = pd.DataFrame()  # placeholder
        try:
            d = tqs.get_divid_factors(stock_code=code)
            d = d[d.index <= back.index[-1]] if d is not None and len(d) else d
        except Exception:
            d = None
        price0 = float(b.iloc[0])
        cov = {}
        if d is not None and len(d):
            for y in range(b.index[0].year, b.index[-1].year + 1):
                amt = sum(float(r.get("Bonus", 0) or 0) / 10.0 for dt, r in d.iterrows() if dt.year == y)
                div_yield = amt / price0
                cov[str(y)] = {"div_per_share": round(amt, 4),
                               "coverage_r4": round(div_yield / 0.04, 4)}
        out["retire"]["coverage"][code] = cov

    # 基准
    for bcode, bname in BENCH.items():
        b = fetch(bcode, "back")
        if b is None:
            continue
        b = b[b.index >= common_start]
        nm = month_end(b)
        out["bench"][bcode] = {"name": bname, "start": str(b.index[0])[:10],
                               **{f"r{int(r*100)}": withdraw(nm, r) for r in RATES}}

    rp = BASE / "reports" / "r5_2_split_correction.json"
    rp.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n结果已存：{rp}")
    print("共同窗口:", out["retire"]["common_window"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
