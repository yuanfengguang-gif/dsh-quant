# -*- coding: utf-8 -*-
"""scripts/r5_1_data_foundation.py —— R5-1 数据地基补齐 + 三口径基础测算

研究池 v1.0（25 只，冻结）；不做收益排名。
  1) 自由现金流指数历史验证（≥750 日才可回测）
  2) 10 年期国债收益率（AkShare 公开源 → data/cache/macro.db）
  3) 分红记录抽查（通达信 vs 新浪累计分红）
  4) 三口径（不复权/前复权/后复权）指标 + 分红档案 + 费率/流动性
产出：reports/r5_1_data_foundation.json
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
FCF_INDICES = ["932365.CSI", "932366.CSI", "932367.CSI", "932368.CSI", "932369.CSI", "980092.CNI"]
SPOT = ["510880.SH", "515080.SH", "513530.SH", "561580.SH"]


def fetch_close(code: str) -> pd.Series | None:
    try:
        r = tqs.get_market_data(field_list=["Close"], stock_list=[code], period="1d",
                                start_time=START, end_time=END, dividend_type="none")
        c = r.get("Close")
        if c is None or len(c) == 0:
            return None
        s = c.iloc[:, 0].dropna()
        s.index = pd.to_datetime(s.index)
        return s.sort_index()
    except Exception:
        return None


def fetch_div(code: str) -> pd.DataFrame:
    try:
        d = tqs.get_divid_factors(stock_code=code)
        if d is None or len(d) == 0:
            return pd.DataFrame({"Bonus": pd.Series(dtype=float)}, index=pd.DatetimeIndex([]))
        d = d.copy()
        d.index = pd.to_datetime(d.index)
        return d.sort_index()
    except Exception:
        return pd.DataFrame(columns=["Bonus"])


def infer_unit(close: pd.Series, div: pd.DataFrame) -> int:
    if len(div) == 0:
        return 10
    idx = fetch_close("000300.SH")
    ratios = []
    for dt, row in div.iterrows():
        pos = int(close.index.searchsorted(dt))
        if pos <= 0 or pos >= len(close):
            continue
        ri = 0.0
        if idx is not None:
            ip = int(idx.index.searchsorted(dt))
            if 0 < ip < len(idx):
                ri = float(idx.iloc[ip] / idx.iloc[ip - 1] - 1)
        b = float(row.get("Bonus", 0) or 0)
        if b > 0:
            ratios.append((float(close.iloc[pos - 1]) * (1 + ri) - float(close.iloc[pos])) / b)
    if not ratios:
        return 10
    med = float(np.median(ratios))
    if 0.005 <= med <= 0.02:
        return 100
    return 10


def adjust(close: pd.Series, div: pd.DataFrame, unit: int) -> tuple[pd.Series, pd.Series]:
    qfq = close.copy()
    hfq = close.copy()
    for dt, row in div.iterrows():
        pos = int(close.index.searchsorted(dt))
        if pos <= 0 or pos >= len(close):
            continue
        d = float(row.get("Bonus", 0) or 0) / unit
        prev = float(close.iloc[pos - 1])
        if not (0 < d < prev):
            continue
        phi = prev / (prev - d)
        qfq.iloc[:pos] = qfq.iloc[:pos] / phi
        hfq.iloc[pos:] = hfq.iloc[pos:] * phi
    return qfq, hfq


def metrics(px: pd.Series) -> dict:
    r = px.pct_change().dropna()
    if len(r) < 2:
        return {}
    nav = px / px.iloc[0]
    yrs = len(r) / 252.0
    ann = float(nav.iloc[-1] ** (1 / yrs) - 1)
    vol = float(r.std() * np.sqrt(252))
    sharpe = float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else None
    dd = nav / nav.cummax() - 1
    maxdd = float(dd.min())
    return {
        "cum_return": round(float(nav.iloc[-1] - 1), 4),
        "annual": round(ann, 4), "vol": round(vol, 4),
        "sharpe": (round(sharpe, 3) if sharpe is not None else None),
        "max_drawdown": round(maxdd, 4),
        "calmar": (round(ann / abs(maxdd), 3) if maxdd else None),
        "start": str(px.index[0])[:10], "end": str(px.index[-1])[:10], "n_days": int(len(px)),
    }


def main() -> int:
    pool_cfg = yaml.safe_load((BASE / "config" / "r5_pool_v1.yaml").read_text(encoding="utf-8"))
    pool = pool_cfg["pool"]
    r5 = json.loads((BASE / "reports" / "r5_0_dividend_etf_inventory.json").read_text(encoding="utf-8"))
    inv = r5["etfs"]

    out = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "meta": {
            "task": "R5-1 数据地基补齐 + 三口径基础测算",
            "pool_version": "v1.0（冻结，25 只）",
            "pool_n": len(pool),
            "adjust_note": "前/后复权为自建事件法（除息日价格跳空反推单位，φ=P_prev/(P_prev−D)）；不用通达信 front（R3-0 已证其非除息日有噪声）",
        },
        "pool": {},
        "fcf_indices": {},
        "bond": {},
        "spot_check": {},
    }

    for item in pool:
        code, style, name = item["code"], item["style"], item["name"]
        close = fetch_close(code)
        if close is None or len(close) < 2:
            out["pool"][code] = {"code": code, "name": name, "style": style, "error": "无数据"}
            continue
        div = fetch_div(code)
        div = div[div.index <= close.index[-1]]  # 剔除未来除息日（通达信含已公告未除息）
        unit = infer_unit(close, div)
        qfq, hfq = adjust(close, div, unit)
        m = {"none": metrics(close), "qfq": metrics(qfq), "hfq": metrics(hfq)}
        # 分红档案
        amounts = [round(float(b) / unit, 4) for b in div.get("Bonus", [])]
        dates = list(div.index)
        months = [0] * 12
        for d in dates:
            months[d.month - 1] += 1
        ttm = sum(a for d, a in zip(dates, amounts) if d >= close.index[-1] - pd.Timedelta(days=365))
        cv = (round(float(np.std(amounts) / np.mean(amounts)), 4) if amounts and np.mean(amounts) > 0 else None)
        # 近 5 年连续性：相邻分红间隔 > 400 天视为中断
        recent = [d for d in dates if d >= close.index[-1] - pd.Timedelta(days=1825)]
        gap_break = False
        for a, b in zip(recent[:-1], recent[1:]):
            if (b - a).days > 400:
                gap_break = True
        out["pool"][code] = {
            "code": code, "name": name, "style": style,
            "data_start": str(close.index[0])[:10], "data_end": str(close.index[-1])[:10], "data_rows": int(len(close)),
            "usable": ("是" if len(close) >= 750 else "历史不足"),
            "aum": inv.get(code, {}).get("latest_aum", "无"),
            "avg_turnover_20d": inv.get(code, {}).get("avg_turnover_20d"),
            "fee_mgmt": "无", "fee_custody": "无",
            "unit": unit,
            "modes": m,
            "div_contrib": round(m["hfq"]["annual"] - m["none"]["annual"], 4),
            "div": {
                "count": len(dates), "first": (str(dates[0])[:10] if dates else "无"),
                "last": (str(dates[-1])[:10] if dates else "无"),
                "months": months, "amounts": amounts,
                "ttm_amount": round(float(ttm), 4),
                "ttm_yield": (round(float(ttm / float(close.iloc[-1])), 4) if float(close.iloc[-1]) else None),
                "continuity_5y": ("否（存在>400天中断）" if gap_break else "是"),
                "cv": cv,
            },
        }
        print(f"{code} {name}: rows={len(close)} none={m['none']['annual']:+.2%} hfq={m['hfq']['annual']:+.2%} unit={unit} div={len(dates)}", flush=True)

    # 自由现金流指数
    print("\n自由现金流指数 ...", flush=True)
    for c in FCF_INDICES:
        try:
            nm = tqs.get_stock_info(c).get("Name", "")
        except Exception:
            nm = ""
        s = fetch_close(c)
        if s is None:
            out["fcf_indices"][c] = {"name": nm, "rows": 0, "start": "无", "usable": "否（取不到）"}
        else:
            out["fcf_indices"][c] = {"name": nm, "rows": int(len(s)), "start": str(s.index[0])[:10],
                                     "end": str(s.index[-1])[:10],
                                     "usable": ("是" if len(s) >= 750 else "否（<750日）")}
        print(c, out["fcf_indices"][c], flush=True)

    # 10Y 国债收益率
    import sqlite3
    con = sqlite3.connect(str(BASE / "data" / "cache" / "macro.db"))
    by = pd.read_sql("SELECT date, y10 FROM bond_yield ORDER BY date", con)
    con.close()
    by["date"] = pd.to_datetime(by["date"])
    by = by.dropna()
    out["bond"] = {
        "source": "AkShare bond_zh_us_rate → data/cache/macro.db（公开数据，非通达信）",
        "start": str(by["date"].iloc[0])[:10], "end": str(by["date"].iloc[-1])[:10],
        "rows": int(len(by)), "missing": int(by["y10"].isna().sum()),
        "freq": "日频（交易日）",
        "last_y10": round(float(by["y10"].iloc[-1]), 4),
        "min": round(float(by["y10"].min()), 4), "max": round(float(by["y10"].max()), 4),
    }
    print("\n10Y 国债:", out["bond"], flush=True)

    # 分红记录抽查（vs 新浪累计分红）
    print("\n分红抽查 ...", flush=True)
    try:
        import akshare as ak
    except Exception as e:
        ak = None
        print("akshare 不可用", e)
    for code in SPOT:
        item = {"tdx_last3": [], "sina_last3": [], "events": [], "verdict": "无"}
        if code not in out["pool"]:
            out["spot_check"][code] = item
            continue
        p = out["pool"][code]
        _d = fetch_div(code)
        if len(_d):
            _d = _d[_d.index <= pd.Timestamp(p["data_end"])]
        dates = list(_d.index)
        unit = p["unit"]
        amounts = [round(float(b) / unit, 5) for b in _d.get("Bonus", [])]
        item["tdx_last3"] = [{"date": str(d)[:10], "amount": a} for d, a in list(zip(dates, amounts))[-3:]]
        if ak is not None:
            try:
                sym = ("sh" if code.endswith(".SH") else "sz") + code[:6]
                sdf = ak.fund_etf_dividend_sina(symbol=sym)
                sdf = sdf.dropna()
                cum = [(pd.Timestamp(r[0]), float(r[1])) for r in sdf.itertuples(index=False)]
                per = [(cum[i][0], round(cum[i][1] - (cum[i - 1][1] if i else 0.0), 5)) for i in range(len(cum))]
                item["sina_last3"] = [{"date": str(d)[:10], "amount": a} for d, a in per[-3:]]
                # 对齐比较最近 3 个 TDX 事件
                sina_map = {str(d)[:10]: a for d, a in per}
                for ev in item["tdx_last3"]:
                    sa = sina_map.get(ev["date"])
                    item["events"].append({"date": ev["date"], "tdx": ev["amount"], "sina": sa,
                                           "match": (sa is not None and abs(sa - ev["amount"]) <= 0.002)})
                n_match = sum(1 for e in item["events"] if e["match"])
                item["n_match"] = int(n_match)
                item["verdict"] = f"{n_match}/3 一致"
            except Exception as e:
                item["verdict"] = f"新浪取数失败：{str(e)[:80]}"
        out["spot_check"][code] = item
        print(code, item["verdict"], item["events"], flush=True)

    rp = BASE / "reports" / "r5_1_data_foundation.json"
    rp.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n结果已存：{rp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
