# -*- coding: utf-8 -*-
"""scripts/b1_single_asset.py —— B1 单资产择时基线（HS300）

规格来源：docs/ETF择时策略设计.md §十（2026-10-18 PM 下发）

信号（只两个）：
  ma_state   = 1 if close > MA200 else 0
  vol_target = min(1.0, 0.15 / realized_vol_20d)   # 年化波动 15%
  position   = ma_state × vol_target

执行：月末收盘定信号 → 次交易日**开盘**执行；盘中偏离 >20pp 触发补调
成本：config/costs_etf.yaml（买/卖各 0.036%，无印花税）
现金：511990 无分红记录、价格收益≈0 → 用年化 2% 近似（设计稿允许）

三组对照：(a) 买入持有 HS300；(b) 固定 60/40；(c) 仅 ma_state（去掉 vol_target）

产物：reports/b1_single_asset.json
用法：python scripts/b1_single_asset.py
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

CASH_ANNUAL = 0.02
COST_CFG = yaml.safe_load((BASE / "config" / "costs_etf.yaml").read_text(encoding="utf-8"))
BUY = float(COST_CFG["commission"]) + float(COST_CFG["slippage"])
SELL = BUY
MA_WINDOW = 200
VOL_WINDOW = 20
TARGET_VOL = 0.15
TRIGGER = 0.20
WINDOWS = {"2010+": "2010-01-01", "2016+": "2016-01-01"}
BEAR_YEARS = [2015, 2018, 2022]


def fetch(code: str, dividend_type: str, start="2005-01-01", end="2026-10-17") -> pd.DataFrame:
    r = tqs.get_market_data(field_list=["Open", "High", "Low", "Close", "Volume"], stock_list=[code],
                            period="1d", start_time=start, end_time=end, dividend_type=dividend_type)
    c = r.get("Close")
    if c is None or len(c) == 0:
        raise RuntimeError(f"{code} 无数据")
    df = pd.DataFrame({"open": r["Open"].iloc[:, 0], "close": c.iloc[:, 0]}).dropna()
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def build_front(df: pd.DataFrame, div: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """自建前复权：qfq_t = P_t × Π_{除息日>t}(1 − D/P_prev)，D = Bonus/10（实测隐含分红≈Bonus/10）。

    不用 TDX dividend_type='front'：其序列在非除息日有噪声（如 2013-06-24 日收益与不复权差 3.5pp），
    同口径下前复权年化 6.70% 与后复权 ~4.9% 不自洽。
    """
    n = len(df)
    factor = np.ones(n)
    used = []
    for d, r in div.iterrows():
        d = pd.Timestamp(d)
        pos = int(df.index.searchsorted(d))
        if pos <= 0 or pos >= n:
            continue
        D = float(r["Bonus"]) / 10.0
        prev = float(df["close"].iloc[pos - 1])
        if prev > D > 0:
            phi = 1.0 - D / prev
            factor[:pos] *= phi
            used.append({"date": str(d)[:10], "bonus_per_10": float(r["Bonus"]),
                         "dividend_per_share": round(D, 4), "phi": round(phi, 6)})
    out = df.copy()
    out["open"] = out["open"] * factor
    out["close"] = out["close"] * factor
    return out, {"n_events": len(used), "events": used,
                 "first_close_adjusted": round(float(out["close"].iloc[0]), 4)}


def metrics(ret: pd.Series, pos: pd.Series | None = None, cost_ret: pd.Series | None = None) -> dict:
    ret = ret.dropna()
    if len(ret) < 30:
        return {"n": len(ret)}
    nav = (1 + ret).cumprod()
    yrs = len(ret) / 252.0
    ann = float(nav.iloc[-1] ** (1 / yrs) - 1)
    vol = float(ret.std() * np.sqrt(252))
    sharpe = float(ret.mean() / ret.std() * np.sqrt(252)) if ret.std() > 0 else None
    peak = nav.cummax()
    dd = nav / peak - 1
    maxdd = float(dd.min())
    under = (nav < peak).to_numpy()
    longest = cur = 0
    for u in under:
        cur = cur + 1 if u else 0
        longest = max(longest, cur)
    return {
        "n_days": int(len(ret)),
        "annual_return": round(ann, 4),
        "vol": round(vol, 4),
        "sharpe": (round(sharpe, 3) if sharpe is not None else None),
        "max_drawdown": round(maxdd, 4),
        "calmar": (round(ann / abs(maxdd), 3) if maxdd else None),
        "dd_days_max": int(longest),
        "total_return": round(float(nav.iloc[-1] - 1), 4),
        "avg_position": (round(float(pos.mean()), 3) if pos is not None else None),
        "turnover_per_year": (round(float(np.abs(np.diff(pos.values)).sum()) / yrs, 3) if pos is not None else None),
    }


def yearly(ret: pd.Series) -> dict:
    out = {}
    for y, g in ret.groupby(ret.index.year):
        out[str(y)] = round(float((1 + g).prod() - 1), 4)
    return out


def run_timing(df: pd.DataFrame, use_vol: bool = True) -> dict:
    """在给定价格序列上跑择时，返回逐日收益/仓位/成本（open-to-open）。"""
    dates = df.index
    opens = df["open"].to_numpy(float)
    closes = df["close"].to_numpy(float)
    n = len(df)
    close_s = pd.Series(closes, index=dates)
    ma = close_s.rolling(MA_WINDOW, min_periods=MA_WINDOW).mean().to_numpy()
    r_close = close_s.pct_change()
    vol = r_close.rolling(VOL_WINDOW, min_periods=VOL_WINDOW).std().to_numpy() * np.sqrt(252)

    # 收盘时点的目标仓位
    pos_star = np.zeros(n)
    for i in range(n):
        ms = 1.0 if (not np.isnan(ma[i]) and closes[i] > ma[i]) else 0.0
        if use_vol:
            v = vol[i]
            vt = min(1.0, TARGET_VOL / v) if (v is not None and not np.isnan(v) and v > 0) else 1.0
        else:
            vt = 1.0
        pos_star[i] = ms * vt

    month_end = np.zeros(n, dtype=bool)
    for i in range(n - 1):
        month_end[i] = dates[i].month != dates[i + 1].month
    month_end[n - 1] = True

    rc = CASH_ANNUAL / 252.0
    rets = np.zeros(n - 1)
    weights = np.zeros(n - 1)
    costs = np.zeros(n - 1)
    w = 0.0
    desired = 0.0
    pending_cost = 0.0
    for i in range(n - 1):
        r = opens[i + 1] / opens[i] - 1.0
        w = min(max(w, 0.0), 1.0)
        port = w * r + (1.0 - w) * rc - pending_cost
        rets[i] = port
        weights[i] = w
        costs[i] = pending_cost
        # 漂移后的实际权重
        denom = w * (1 + r) + (1 - w) * (1 + rc)
        w_drift = (w * (1 + r)) / denom if denom > 0 else w
        # 收盘决策（作用于下一交易日开盘）
        target = None
        if month_end[i]:
            desired = pos_star[i]
            target = desired
        elif abs(w_drift - desired) > TRIGGER:
            target = desired
        if target is not None and abs(target - w_drift) > 1e-9:
            delta = target - w_drift
            pending_cost = (BUY if delta > 0 else SELL) * abs(delta)
            w = target
        else:
            pending_cost = 0.0
            w = w_drift
    idx = dates[1:]
    return {
        "ret": pd.Series(rets, index=idx),
        "pos": pd.Series(weights, index=idx),
        "cost": pd.Series(costs, index=idx),
        "pos_star": pd.Series(pos_star[:-1], index=idx),
        "ma": pd.Series(ma[:-1], index=idx),
    }


def buy_hold(df: pd.DataFrame) -> pd.Series:
    op = df["open"].to_numpy(float)
    return pd.Series(op[1:] / op[:-1] - 1.0, index=df.index[1:])


def fixed_mix(df: pd.DataFrame, w_asset: float = 0.6) -> pd.Series:
    r = buy_hold(df)
    return w_asset * r + (1 - w_asset) * (CASH_ANNUAL / 252.0)


def slice_win(s: pd.Series, start: str) -> pd.Series:
    return s[s.index >= pd.Timestamp(start)]


def evaluate(df: pd.DataFrame, label: str) -> dict:
    strat = run_timing(df, use_vol=True)
    ma_only = run_timing(df, use_vol=False)
    bh = buy_hold(df)
    mix = fixed_mix(df)
    out = {"label": label, "data": {
        "rows": int(len(df)), "start": str(df.index[0])[:10], "end": str(df.index[-1])[:10]}}
    for wname, wstart in WINDOWS.items():
        st = slice_win(strat["ret"], wstart)
        if len(st) < 60:
            continue
        pos = slice_win(strat["pos"], wstart)
        bh_w = slice_win(bh, wstart)
        mix_w = slice_win(mix, wstart)
        ma_w = slice_win(ma_only["ret"], wstart)
        res = {
            "strategy": metrics(st, pos),
            "buy_hold": metrics(bh_w),
            "fixed_60_40": metrics(mix_w),
            "ma_only": metrics(ma_w),
            "yearly": {"strategy": yearly(st), "buy_hold": yearly(bh_w), "fixed_60_40": yearly(mix_w)},
            "bear_years": {
                str(y): {
                    "strategy": round(float((1 + st[st.index.year == y]).prod() - 1), 4) if (st.index.year == y).any() else None,
                    "buy_hold": round(float((1 + bh_w[bh_w.index.year == y]).prod() - 1), 4) if (bh_w.index.year == y).any() else None,
                    "fixed_60_40": round(float((1 + mix_w[mix_w.index.year == y]).prod() - 1), 4) if (mix_w[mix_w.index.year == y]).any() else None,
                } for y in BEAR_YEARS
            },
        }
        out[wname] = res
    # 净值与仓位（全样本）
    out["curves"] = {
        "dates": [str(d)[:10] for d in strat["ret"].index],
        "nav_strategy": [round(float(v), 6) for v in (1 + strat["ret"]).cumprod()],
        "nav_buy_hold": [round(float(v), 6) for v in (1 + bh).cumprod()],
        "nav_fixed_60_40": [round(float(v), 6) for v in (1 + mix).cumprod()],
        "position": [round(float(v), 4) for v in strat["pos"]],
        "pos_target": [round(float(v), 4) for v in strat["pos_star"]],
    }
    return out


def gates(res: dict) -> dict:
    s, a, b = res["strategy"], res["buy_hold"], res["fixed_60_40"]
    checks = {
        "1_dd_and_calmar_vs_bh": bool(s["max_drawdown"] > a["max_drawdown"] and (s["calmar"] or -9) > (a["calmar"] or -9)),
        "2_sharpe_vs_60_40": bool((s["sharpe"] or -9) > (b["sharpe"] or -9)),
        "3_sharpe_ge_05": bool((s["sharpe"] or -9) >= 0.5),
        "4_maxdd_le_30": bool(abs(s["max_drawdown"]) <= 0.30),
    }
    checks["all_pass"] = all(checks.values())
    return {
        "checks": checks,
        "deltas": {
            "maxdd_strategy_vs_bh": round(s["max_drawdown"] - a["max_drawdown"], 4),
            "calmar_strategy_vs_bh": round((s["calmar"] or 0) - (a["calmar"] or 0), 3),
            "sharpe_strategy_vs_60_40": round((s["sharpe"] or 0) - (b["sharpe"] or 0), 3),
        },
    }


def main() -> int:
    print("取数：HS300 指数（none）...", flush=True)
    idx = fetch("000300.SH", "none", start="2005-01-01")
    print(f"  指数 {len(idx)} 行 {idx.index[0].date()} ~ {idx.index[-1].date()}", flush=True)

    print("取数：510300 ETF（不复权 + 分红事件 → 自建前复权）...", flush=True)
    etf_raw = fetch("510300.SH", "none", start="2005-01-01")
    div = tqs.get_divid_factors(stock_code="510300.SH")
    etf, adj_meta = build_front(etf_raw, div)
    etf_tdx_front = fetch("510300.SH", "front", start="2005-01-01")
    print(f"  ETF {len(etf)} 行 {etf.index[0].date()} ~ {etf.index[-1].date()}；"
          f"分红 {adj_meta['n_events']} 次；自建前复权首价 {adj_meta['first_close_adjusted']}", flush=True)

    out = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "fingerprint": {
            "strategy": "b1_single_asset",
            "ma_window": MA_WINDOW,
            "vol_window": VOL_WINDOW,
            "vol_target": TARGET_VOL,
            "trigger_pp": TRIGGER,
            "rebalance": "monthly + 20pp deviation",
            "exec_price": "next trading day open (open-to-open returns)",
            "cost_model": "config/costs_etf.yaml",
            "cost_buy": BUY, "cost_sell": SELL,
            "cash_return": f"{CASH_ANNUAL:.2%}/yr（511990 无分红记录，价格收益≈0，按设计近似）",
            "window": list(WINDOWS.keys()),
            "data": {"index": "000300.SH none",
                     "etf": "510300.SH 自建前复权（none + 分红事件，Bonus 为每 10 份）"},
        },
        "adjustment": adj_meta,
        "index": evaluate(idx, "HS300 指数 000300.SH"),
        "etf": evaluate(etf, "510300.SH 自建前复权"),
    }

    # TDX front 与自建前复权的差异（数据质量披露）
    common_f = etf.index.intersection(etf_tdx_front.index)
    r_self = etf.loc[common_f, "close"].pct_change().dropna()
    r_tdx = etf_tdx_front.loc[common_f, "close"].pct_change().dropna()
    out["tdx_front_check"] = {
        "note": "TDX dividend_type='front' 在非除息日与自建序列不一致，故不采用；仅作数据质量披露",
        "corr_daily": round(float(np.corrcoef(r_self, r_tdx)[0, 1]), 4),
        "max_abs_daily_diff": round(float((r_self - r_tdx).abs().max()), 4),
        "n_days_diff_gt_1pct": int(((r_self - r_tdx).abs() > 0.01).sum()),
        "annual_self": round(float((1 + r_self).prod() ** (252 / len(r_self)) - 1), 4),
        "annual_tdx_front": round(float((1 + r_tdx).prod() ** (252 / len(r_tdx)) - 1), 4),
    }

    # 跟踪差异（共同日期）
    common = idx.index.intersection(etf.index)
    ri = idx.loc[common, "close"].pct_change().dropna()
    re = etf.loc[common, "close"].pct_change().dropna()
    out["tracking"] = {
        "common_days": int(len(ri)),
        "corr_daily_returns": round(float(np.corrcoef(ri, re)[0, 1]), 4),
        "annual_index": round(float(ri.mean() * 252), 4),
        "annual_etf_front": round(float(re.mean() * 252), 4),
        "tracking_error": round(float((ri - re).std() * np.sqrt(252)), 4),
    }

    # 门禁：主判定窗口 = 2016+（与 P0 一致）；同时报 2010+
    out["gates"] = {k: gates(v) for k, v in out["index"].items() if k in WINDOWS}
    out["gates_etf"] = {k: gates(v) for k, v in out["etf"].items() if k in WINDOWS}
    out["primary_window"] = "2016+"

    rp = BASE / "reports" / "b1_single_asset.json"
    rp.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print("\n=== 指数 000300.SH ===")
    for w in WINDOWS:
        if w not in out["index"]:
            continue
        r = out["index"][w]
        print(f"[{w}] 策略 年化 {r['strategy']['annual_return']:+.2%} 夏普 {r['strategy']['sharpe']} "
              f"回撤 {r['strategy']['max_drawdown']:.1%} Calmar {r['strategy']['calmar']} 仓位 {r['strategy']['avg_position']:.2f}")
        print(f"       买入持有 年化 {r['buy_hold']['annual_return']:+.2%} 夏普 {r['buy_hold']['sharpe']} "
              f"回撤 {r['buy_hold']['max_drawdown']:.1%} Calmar {r['buy_hold']['calmar']}")
        print(f"       固定60/40 年化 {r['fixed_60_40']['annual_return']:+.2%} 夏普 {r['fixed_60_40']['sharpe']} "
              f"回撤 {r['fixed_60_40']['max_drawdown']:.1%} Calmar {r['fixed_60_40']['calmar']}")
        print(f"       仅MA     年化 {r['ma_only']['annual_return']:+.2%} 夏普 {r['ma_only']['sharpe']}")
        print(f"       门禁: {out['gates'][w]['checks']}")
        print(f"       熊年: {r['bear_years']}")
    print("\n=== ETF 510300 front ===")
    for w in WINDOWS:
        if w not in out["etf"]:
            continue
        r = out["etf"][w]
        print(f"[{w}] 策略 年化 {r['strategy']['annual_return']:+.2%} 夏普 {r['strategy']['sharpe']} "
              f"回撤 {r['strategy']['max_drawdown']:.1%} Calmar {r['strategy']['calmar']}")
    print(f"\n跟踪: {out['tracking']}")
    print(f"结果已存：{rp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
