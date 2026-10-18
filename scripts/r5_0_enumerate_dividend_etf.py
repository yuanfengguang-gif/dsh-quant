# -*- coding: utf-8 -*-
"""scripts/r5_0_enumerate_dividend_etf.py —— R5-0 红利 ETF 全清单枚举 + 指数股息率数据验证

只枚举与数据验证，不做收益比较。
  - 从通达信基金全表（market=31/33）枚举，按名称关键词 + 红利指数跟踪关系筛选
  - 采集 17 个字段 + 第十节 4 个股息率字段
  - 输出 config/etf_pool_dividend.yaml + reports/r5_0_dividend_etf_inventory.json
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, r"C:\Users\Lenovo\.dsh\skills\tdx-aidata")
sys.path.insert(0, r"C:\Users\Lenovo\.dsh\skills\tdx-aidata\lib")

from tdxaidata import tqs  # noqa: E402

KW = ("红利", "股息", "高股息", "分红", "现金流", "价值")
DIV_INDICES = ["000922.CSI", "000015.SH", "399324.SZ", "930955.CSI", "H30269.CSI", "931468.CSI"]
TR_MAP = {"000922.CSI": "H00922.CSI"}  # 仅此指数有全收益序列
START = "2005-01-01"
END = "2026-10-17"
TODAY = pd.Timestamp("2026-10-16")
RECENT_YEARS = [2023, 2024, 2025]


def fetch_daily(code: str):
    r = tqs.get_market_data(field_list=["Close", "Amount"], stock_list=[code], period="1d",
                            start_time=START, end_time=END, dividend_type="none")
    c = r.get("Close")
    if c is None or len(c) == 0:
        return None
    df = pd.DataFrame({"close": c.iloc[:, 0]})
    a = r.get("Amount")
    if a is not None:
        df["amount"] = a.iloc[:, 0]
    df.index = pd.to_datetime(df.index)
    return df.dropna(subset=["close"]).sort_index()


def fetch_div(code: str):
    try:
        d = tqs.get_divid_factors(stock_code=code)
        if d is None or len(d) == 0:
            return pd.DataFrame(columns=["Bonus"])
        d = d.copy()
        d.index = pd.to_datetime(d.index)
        return d.sort_index()
    except Exception:
        return pd.DataFrame(columns=["Bonus"])


def pctl(series: pd.Series, w: int = 1250) -> pd.Series:
    """滚动分位（O(n log w)，bisect 维护有序窗口）"""
    from bisect import bisect_right, bisect_left, insort
    vals = series.to_numpy(float)
    out = np.full(len(vals), np.nan)
    win = []
    for i, v in enumerate(vals):
        if np.isnan(v):
            continue
        insort(win, v)
        if len(win) > w:
            old = vals[i - w]
            if not np.isnan(old):
                j = bisect_left(win, old)
                if j < len(win) and win[j] == old:
                    win.pop(j)
        if len(win) == w:
            out[i] = bisect_right(win, v) / w * 100.0
    return pd.Series(out, index=series.index)


def tr_yield(pr_code: str, tr_code: str):
    pr = fetch_daily(pr_code)
    tr = fetch_daily(tr_code)
    if pr is None or tr is None:
        return None
    common = pr.index.intersection(tr.index)
    if len(common) < 300:
        return None
    ratio = (tr.loc[common, "close"] / pr.loc[common, "close"])
    y = ratio.pct_change(250)
    return y.dropna()


_IDX_CLOSE = None


def _index_close():
    global _IDX_CLOSE
    if _IDX_CLOSE is None:
        _IDX_CLOSE = fetch_daily("000300.SH")
    return _IDX_CLOSE


def infer_unit(df: pd.DataFrame, div: pd.DataFrame) -> int | None:
    """用除息日价格跳空反推 Bonus 的单位（10=每10份，100=每100份）。"""
    ic = _index_close()
    ratios = []
    for dt, row in div.iterrows():
        pos = int(df.index.searchsorted(dt))
        if pos <= 0 or pos >= len(df):
            continue
        prev, cur = float(df["close"].iloc[pos - 1]), float(df["close"].iloc[pos])
        ri = 0.0
        if ic is not None:
            ip = int(ic.index.searchsorted(dt))
            if 0 < ip < len(ic):
                ri = float(ic["close"].iloc[ip] / ic["close"].iloc[ip - 1] - 1)
        b = float(row.get("Bonus", 0) or 0)
        if b > 0:
            ratios.append((prev * (1 + ri) - cur) / b)
    if not ratios:
        return None
    med = float(np.median(ratios))
    if 0.05 <= med <= 0.2:
        return 10
    if 0.005 <= med <= 0.02:
        return 100
    return None


def etf_div_yield(df: pd.DataFrame, div: pd.DataFrame, unit: int = 10) -> pd.Series:
    """C 口径：ETF 自身 TTM 分红 / 价格（每份=Bonus/unit）。系统性低估。"""
    d = pd.Series(0.0, index=df.index)
    if div is not None and len(div):
        for dt, row in div.iterrows():
            if dt in d.index:
                d.loc[dt] = float(row.get("Bonus", 0) or 0) / float(unit)
    ttm = d.rolling(250, min_periods=1).sum()
    y = ttm / df["close"]
    return y[y > 0]


def cat_of(code: str, name: str) -> str:
    if code[:3] in ("160", "161", "162", "163", "164", "165", "166", "167", "168", "169", "501", "502", "506", "519") or "LOF" in name or "联接" in name:
        return "D"
    if any(k in name for k in ("港股", "恒生", "沪港深", "香港", "H股")):
        return "B"
    if any(k in name for k in ("低波", "质量", "潜力", "价值", "央企", "国企", "现金流", "100", "800", "A500", "300", "500", "1000", "科创", "大盘", "中盘", "小盘")):
        return "C"
    return "A"


def company_of(name: str) -> str:
    m = re.search(r"ETF(.+)$", name)
    if m and len(m.group(1)) >= 2:
        return m.group(1)
    return "无"


def main() -> int:
    print("枚举：基金全表 ...", flush=True)
    universe = list(dict.fromkeys(tqs.get_stock_list(market="31") + tqs.get_stock_list(market="33")))
    names = {}
    for c in universe:
        try:
            names[c] = tqs.get_stock_info(c).get("Name", "") or ""
        except Exception:
            names[c] = ""
    print(f"  基金代码 {len(universe)} 个", flush=True)

    # 指数名称 + 跟踪关系
    idx_name = {}
    for zs in DIV_INDICES:
        try:
            idx_name[zs] = tqs.get_stock_info(zs).get("Name", "")
        except Exception:
            idx_name[zs] = ""
    track = {}
    for zs in DIV_INDICES:
        try:
            r = tqs.get_trackzs_etf_info(zs) or []
        except Exception:
            r = []
        for item in r:
            cd = item.get("Code")
            if cd:
                track[cd] = {"index": zs, "index_name": idx_name.get(zs, ""), "aum": item.get("Sz")}
    print(f"  红利指数跟踪关系 {len(track)} 条（{len(DIV_INDICES)} 个指数）", flush=True)

    cands = [c for c in universe if (any(k in names.get(c, "") for k in KW) or c in track)]
    print(f"  候选 {len(cands)} 只", flush=True)

    # 指数级股息率（仅 000922 有全收益）
    idx_yield = {}
    for zs, tr in TR_MAP.items():
        y = tr_yield(zs.split(".")[0] + "." + zs.split(".")[1], tr)
        if y is not None and len(y) > 300:
            idx_yield[zs] = y
            print(f"  指数股息率(TR/PR) {zs}: {len(y)} 日，{str(y.index[0])[:10]} 起", flush=True)

    etfs = {}
    ymeta = {}
    for i, c in enumerate(cands, 1):
        nm = names.get(c, "")
        try:
            df = fetch_daily(c)
        except Exception as e:
            etfs[c] = {"code": c, "name": nm, "error": str(e)[:120]}
            continue
        if df is None or df.empty:
            etfs[c] = {"code": c, "name": nm, "data_rows": 0, "data_start": None, "usable": "历史不足"}
            continue
        div = fetch_div(c)
        div_dates = list(div.index)
        months = [int(d.month) for d in div_dates]
        unit = infer_unit(df, div) or 10
        amounts = [round(float(b) / float(unit), 4) for b in div.get("Bonus", [])]
        # 近 3 年频率：用滚动 3 年平均次数 + 中位间隔（对次新 ETF 也用可用区间）
        recent = [d for d in div_dates if d >= TODAY - pd.Timedelta(days=1095)]
        span = ((recent[-1] - recent[0]).days / 365.25) if len(recent) >= 2 else 0.0
        avg_per_year = (len(recent) / span) if span > 0.5 else 0.0
        med_gap = float(np.median(np.diff([d.value for d in recent]) / 86400e9)) if len(recent) >= 3 else None
        if span < 0.75:
            freq = "样本不足（<9个月）"
        elif avg_per_year >= 10 and (med_gap is not None and med_gap <= 45):
            freq = "月度"
        elif avg_per_year >= 3.3:
            freq = "季度"
        elif avg_per_year >= 1.7:
            freq = "半年"
        elif avg_per_year >= 0.7:
            freq = "年度"
        else:
            freq = "无/不规律"
        # 分红记录完整性：首次分红距上市 >2 年 → 疑似缺失
        first_div = div_dates[0] if div_dates else None
        if not div_dates:
            has_rec = "否（通达信无记录）"
        elif first_div is not None and (first_div - df.index[0]).days > 730:
            has_rec = "部分（疑似缺失）"
        else:
            has_rec = "是"
        # 规模/费率
        try:
            mi = tqs.get_more_info(c)
            aum = float(mi.get("Ltsz") or 0)
        except Exception:
            aum = None
        turnover = round(float(df["amount"].tail(20).mean()), 2) if "amount" in df else None
        start = str(df.index[0])[:10]
        usable = "是" if df.index[0] <= pd.Timestamp("2023-10-18") else "历史不足"
        tinfo = track.get(c, {})
        # 股息率序列
        y = None
        method = None
        if tinfo.get("index") in idx_yield:
            y = idx_yield[tinfo["index"]]
            method = "TR/PR（指数全收益/价格）"
        else:
            try:
                y = etf_div_yield(df, div, unit)
                method = "ETF分红TTM/价格(C口径)"
            except Exception:
                y = None
        reliable = True
        if y is not None and len(y) > 300:
            if method.startswith("ETF") and float(y.max()) > 0.15:
                reliable = False
            p = pctl(y, 1250)
            pv = p.dropna()
            ymeta[c] = {
                "method": method,
                "reliable": reliable,
                "unit": unit,
                "start": str(y.index[0])[:10],
                "n_days": int(len(y)),
                "yield_min": round(float(y.min()), 4),
                "yield_median": round(float(y.median()), 4),
                "yield_max": round(float(y.max()), 4),
                "pct_gt70_share": round(float((pv > 70).mean()), 4) if len(pv) else None,
                "pct_lt30_share": round(float((pv < 30).mean()), 4) if len(pv) else None,
                "pct_mid_share": round(float(((pv >= 30) & (pv <= 70)).mean()), 4) if len(pv) else None,
                "pct_first_date": str(pv.index[0])[:10] if len(pv) else None,
                "monthly": [{"month": str(d)[:7], "yield": round(float(v), 4), "pct": (round(float(p.loc[d]), 1) if d in p.index and not np.isnan(p.loc[d]) else None)}
                            for d, v in y.resample("ME").last().dropna().items()],
            }
        etfs[c] = {
            "code": c, "name": nm, "fund_company": company_of(nm),
            "track_index": (f"{tinfo['index']} {tinfo.get('index_name','')}".strip() if tinfo else "无（通达信无映射）"),
            "category": cat_of(c, nm),
            "list_date": start, "data_start": start, "data_rows": int(len(df)),
            "div_count": int(len(div_dates)), "div_months": months, "div_amounts": amounts,
            "div_unit": unit, "_div_dates": [str(d)[:10] for d in div_dates],
            "div_freq_recent": freq, "div_policy": "无公开信息",
            "fee_mgmt": "无", "fee_custody": "无",
            "latest_aum": (round(aum, 2) if aum else "无"),
            "avg_turnover_20d": turnover,
            "has_div_record": has_rec,
            "usable": usable,
            "div_yield_method": method,
            "div_yield_reliable": (ymeta[c]["reliable"] if c in ymeta else None),
            "div_yield_start": (ymeta[c]["start"] if c in ymeta else "无"),
        }
        if i % 25 == 0:
            print(f"  ... {i}/{len(cands)}", flush=True)

    # 月份覆盖矩阵（A 类 / 全部）
    def coverage(codes):
        mat = {c: {m: 0 for m in range(1, 13)} for c in codes}
        for c in codes:
            for m in etfs.get(c, {}).get("div_months", []):
                mat[c][m] += 1
        covered = [m for m in range(1, 13) if any(mat[c][m] > 0 for c in codes)]
        return mat, covered

    a_codes = [c for c, v in etfs.items() if v.get("category") == "A"]
    abc_codes = [c for c, v in etfs.items() if v.get("category") in ("A", "B", "C")]
    mat_a, cov_a = coverage(a_codes)
    mat_all, cov_all = coverage(abc_codes)

    def months_capable(freq):
        return [c for c, v in etfs.items() if v.get("div_freq_recent") == freq]

    monthly = months_capable("月度")
    out = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "meta": {
            "task": "R5-0 红利 ETF 枚举 + 指数股息率数据验证",
            "universe_source": "通达信 get_stock_list(market='31'/'33')",
            "n_universe": len(universe),
            "n_candidates": len(cands),
            "keywords": list(KW),
            "div_indices": {zs: idx_name.get(zs, "") for zs in DIV_INDICES},
            "tr_indices": TR_MAP,
            "note": "C 口径（ETF 分红 TTM/价格）系统性低估真实股息率：ETF 不强制全额分配；单位用除息日价格跳空反推（10 或 100）",
        },
        "summary": {
            "n_total": len(etfs),
            "n_by_category": {k: sum(1 for v in etfs.values() if v.get("category") == k) for k in ("A", "B", "C", "D")},
            "monthly_capable": monthly,
            "monthly_detail": {c: {"name": etfs[c]["name"], "aum": etfs[c]["latest_aum"],
                                   "div_dates": etfs[c]["_div_dates"]} for c in monthly},
            "quarterly_capable": months_capable("季度"),
            "semiannual_capable": months_capable("半年"),
            "annual_only": months_capable("年度"),
            "coverage_months_A": cov_a,
            "coverage_count_A": len(cov_a),
            "gap_months_A": [m for m in range(1, 13) if m not in cov_a],
            "coverage_months_all": cov_all,
            "coverage_count_all": len(cov_all),
            "gap_months_all": [m for m in range(1, 13) if m not in cov_all],
            "coverage_by_month_A": {str(m): [c for c in a_codes if mat_a[c][m] > 0] for m in range(1, 13)},
        },
        "etfs": etfs,
        "coverage_matrix_A": {c: {str(m): v for m, v in mat_a[c].items()} for c in a_codes},
        "coverage_matrix_all": {c: {str(m): v for m, v in mat_all[c].items()} for c in abc_codes},
        "div_yield": ymeta,
    }

    rp = BASE / "reports" / "r5_0_dividend_etf_inventory.json"
    rp.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    # 独立研究池 YAML
    import yaml as _yaml
    pool = [{"code": c, "name": v["name"], "track_index": v["track_index"],
             "category": v["category"], "usable": v["usable"]}
            for c, v in sorted(etfs.items(), key=lambda x: (x[1].get("category", ""), x[0]))
            if v.get("category") in ("A", "B", "C", "D")]
    header = ("# 红利/股息类 ETF 独立研究池（R5-0 枚举，勿与 config/etf_pool.yaml 混用）\n"
              "# 生成：scripts/r5_0_enumerate_dividend_etf.py\n"
              "# 字段：code / name / track_index / category(A/B/C/D) / usable\n")
    body = _yaml.safe_dump({"pool": pool}, allow_unicode=True, sort_keys=False)
    (BASE / "config" / "etf_pool_dividend.yaml").write_text(header + body, encoding="utf-8")
    (BASE / "config" / "etf_pool_dividend.yaml.example").write_text(header + body, encoding="utf-8")

    print(f"\n结果已存：{rp}")
    print("分类:", out["summary"]["n_by_category"])
    print("覆盖月份(A):", cov_a, "缺口:", out["summary"]["gap_months_A"])
    print("月度型:", monthly, "| 季度:", months_capable("季度"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
