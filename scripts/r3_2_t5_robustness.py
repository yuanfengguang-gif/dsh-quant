# -*- coding: utf-8 -*-
"""scripts/r3_2_t5_robustness.py —— R3-2 T5 稳健性压测

规格：reports/R3-2_任务书.md
  主窗口 2011-09-06~2026-10-16（共同窗口）；2016+ 副窗口
  测试：逐年分解 / 阈值邻域(0.03,0.05,0.07) / 成本 1x2x3x / 无未来函数 / 简单策略对比
  修正 G3：回撤匹配法 w=触发回撤/BH回撤，固定年化=w×BH年化，增益=触发年化−固定年化
产出：reports/r3_2_t5_robustness.json
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

COST_CFG = yaml.safe_load((BASE / "config" / "costs_etf.yaml").read_text(encoding="utf-8"))
COST = float(COST_CFG["commission"]) + float(COST_CFG["slippage"])
MAIN_START = "2011-09-06"
SUB_START = "2016-01-01"
LEVELS = {"T5-D0": ("T5", 0.0), "T5-D20": ("T5", 0.20), "T35-D0": ("T35", 0.0), "T3-D50": ("T3", 0.50)}
THRESHOLDS = [0.03, 0.05, 0.07]
COSTS = [COST, COST * 2, COST * 3]
BULL_MAIN = [2014, 2019, 2020, 2025]


def fetch(code: str) -> pd.DataFrame:
    r = tqs.get_market_data(field_list=["Open", "Close"], stock_list=[code], period="1d",
                            start_time="2005-01-01", end_time="2026-10-17", dividend_type="none")
    c = r.get("Close")
    df = pd.DataFrame({"open": r["Open"].iloc[:, 0], "close": c.iloc[:, 0]}).dropna()
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def metrics(ret: pd.Series) -> dict:
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
    return {"annual": round(ann, 4), "vol": round(vol, 4),
            "sharpe": (round(sharpe, 3) if sharpe is not None else None),
            "max_drawdown": round(maxdd, 4), "calmar": (round(ann / abs(maxdd), 3) if maxdd else None),
            "dd_days_max": int(longest), "n_days": int(len(ret)),
            "yearly": {str(y): round(float((1 + g).prod() - 1), 4) for y, g in ret.groupby(ret.index.year)}}


def simulate(idx: pd.DataFrame, flag: pd.Series, level: float, cost: float, off_level: float = 1.0) -> tuple[pd.Series, dict]:
    opens = idx["open"].to_numpy(float)
    n = len(idx)
    target = np.where(flag.fillna(False).to_numpy(bool), level, off_level)
    rets = np.zeros(n - 1)
    costs = np.zeros(n - 1)
    w = 1.0
    pending = 0.0
    switches = 0
    for i in range(n - 1):
        r = opens[i + 1] / opens[i] - 1.0
        rets[i] = w * r - pending
        costs[i] = pending
        new_w = target[i]
        if abs(new_w - w) > 1e-12:
            switches += 1
            pending = cost * abs(new_w - w)
        else:
            pending = 0.0
        w = new_w
    return pd.Series(rets, index=idx.index[1:]), {"switches": switches, "costs": pd.Series(costs, index=idx.index[1:])}


def fixed(idx: pd.DataFrame, w: float) -> pd.Series:
    op = idx["open"].to_numpy(float)
    r = pd.Series(op[1:] / op[:-1] - 1.0, index=idx.index[1:])
    return w * r


def main() -> int:
    idx = fetch("000300.SH")
    idx905 = fetch("000905.SH")
    idx852 = fetch("000852.SH")
    idxcyb = fetch("399006.SZ")
    close = idx["close"]

    px = pd.concat([idx["close"], idx905["close"], idx852["close"], idxcyb["close"]], axis=1, join="inner")
    px.columns = ["HS300", "ZZ500", "ZZ1000", "CYB"]
    r4 = px.pct_change()
    pairs = [(a, b) for i, a in enumerate(r4.columns) for b in list(r4.columns)[i + 1:]]
    corr60 = pd.concat([r4[a].rolling(60).corr(r4[b]) for a, b in pairs], axis=1).mean(axis=1)
    med250 = corr60.rolling(250).median()
    lift = corr60 - med250
    lift_idx = lift.reindex(idx.index)
    corr_idx = corr60.reindex(idx.index)
    med_idx = med250.reindex(idx.index)

    def t5_flag(thr: float) -> pd.Series:
        return (lift_idx > thr).fillna(False)

    ma250 = close.rolling(250).mean()
    max250 = close.rolling(250).max()
    t3 = ((close < ma250) & (close / max250 - 1 < -0.20)).fillna(False)

    main_start = pd.Timestamp(MAIN_START)
    bh_full = pd.Series(idx["open"].to_numpy(float)[1:] / idx["open"].to_numpy(float)[:-1] - 1.0,
                        index=idx.index[1:])
    bh = bh_full[bh_full.index >= main_start]
    bh_m = metrics(bh)

    def build(t5_thr=0.05):
        t5 = t5_flag(t5_thr)
        return {"T5": t5, "T3": t3, "T35": (t5 | t3)}

    flags = build(0.05)

    def run(trigger: str, level: float, cost: float = COST, t5_thr: float = 0.05):
        fl = flags[trigger] if t5_thr == 0.05 else build(t5_thr)[trigger]
        ret, extra = simulate(idx, fl, level, cost)
        r = ret[ret.index >= main_start]
        m = metrics(r)
        w_dd = abs(m["max_drawdown"]) / abs(bh_m["max_drawdown"]) if bh_m["max_drawdown"] else None
        fixed_ann = w_dd * bh_m["annual"] if w_dd is not None else None
        m["equiv_weight_dd"] = (round(w_dd, 4) if w_dd is not None else None)
        m["fixed_annual"] = (round(fixed_ann, 4) if fixed_ann is not None else None)
        m["g3_gain"] = (round(m["annual"] - fixed_ann, 4) if fixed_ann is not None else None)
        m["dd_improvement"] = round(abs(bh_m["max_drawdown"]) - abs(m["max_drawdown"]), 4)
        m["switches"] = extra["switches"]
        m["years"] = round(len(r) / 252.0, 2)
        m["switches_per_year"] = round(extra["switches"] / (len(r) / 252.0), 2) if len(r) else None
        m["total_cost"] = round(float(extra["costs"][extra["costs"].index >= main_start].sum()), 6)
        m["cost_per_year"] = round(m["total_cost"] / (len(r) / 252.0), 6) if len(r) else None
        m["excess_vs_bh"] = round(m["annual"] - bh_m["annual"], 4)
        r16 = r[r.index >= pd.Timestamp(SUB_START)]
        m["y2016"] = metrics(r16)
        m["y2016"]["excess_vs_bh"] = round(m["y2016"]["annual"] - metrics(bh_full[bh_full.index >= pd.Timestamp(SUB_START)])["annual"], 4)
        return m

    out = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "meta": {
            "task": "R3-2 T5 稳健性压测",
            "main_window": {"start": MAIN_START, "end": str(idx.index[-1])[:10]},
            "sub_window": {"start": SUB_START, "end": str(idx.index[-1])[:10]},
            "index": "000300.SH none（通达信）",
            "cost_base": COST, "cash_return": "0%",
            "exec": "信号 t 收盘 → t+1 开盘调仓",
            "g3_method": "回撤匹配 w=触发回撤/BH回撤，固定年化=w×BH年化，增益=触发年化−固定年化",
        },
        "bh": {k: v for k, v in bh_m.items() if k != "yearly"},
        "bh_yearly": bh_m["yearly"],
        "configs": {},
    }

    for key, (trig, level) in LEVELS.items():
        out["configs"][key] = run(trig, level)
        print(f"{key}: 年化 {out['configs'][key]['annual']:+.2%} 夏普 {out['configs'][key]['sharpe']} "
              f"DD {out['configs'][key]['max_drawdown']:.2%} 增益 {out['configs'][key]['g3_gain']:+.2%}", flush=True)

    # 阈值邻域（T5-D0）
    out["thresholds"] = {}
    for thr in THRESHOLDS:
        m = run("T5", 0.0, t5_thr=thr)
        out["thresholds"][f"{thr:.2f}"] = m
        print(f"阈值 {thr}: 年化 {m['annual']:+.2%} 夏普 {m['sharpe']} DD {m['max_drawdown']:.2%} 增益 {m['g3_gain']:+.2%}", flush=True)

    # 成本敏感性（T5-D0, thr=0.05）
    out["costs"] = {}
    for c in COSTS:
        m = run("T5", 0.0, cost=c)
        out["costs"][f"{c*100:.3f}%"] = m
        print(f"成本 {c*100:.3f}%: 年化 {m['annual']:+.2%} 超额 {m['excess_vs_bh']:+.2%} 累计成本 {m['total_cost']:.4%}", flush=True)

    # 简单策略
    simple = {"BH": {k: v for k, v in bh_m.items() if k != "yearly"}}
    for w in (0.8, 0.6):
        r = fixed(idx, w)
        r = r[r.index >= main_start]
        simple[f"const{int(w*100)}"] = metrics(r)
    ma_flag = (close > ma250).fillna(False)
    ma_ret, ma_extra = simulate(idx, ma_flag, 1.0, COST, off_level=0.0)
    ma_m = metrics(ma_ret[ma_ret.index >= main_start])
    ma_m["switches"] = ma_extra["switches"]
    simple["MA250"] = ma_m
    out["simple"] = simple
    out["configs"]["T5-D0"]["vs_ma250_sharpe"] = round((out["configs"]["T5-D0"]["sharpe"] or 0) - (ma_m["sharpe"] or 0), 4)
    out["configs"]["T5-D0"]["vs_const80_sharpe"] = round((out["configs"]["T5-D0"]["sharpe"] or 0) - (simple["const80"]["sharpe"] or 0), 4)
    out["configs"]["T5-D20"]["vs_ma250_sharpe"] = round((out["configs"]["T5-D20"]["sharpe"] or 0) - (ma_m["sharpe"] or 0), 4)
    out["configs"]["T5-D20"]["vs_const80_sharpe"] = round((out["configs"]["T5-D20"]["sharpe"] or 0) - (simple["const80"]["sharpe"] or 0), 4)

    # 逐年分解（T5-D0 / T5-D20 / T35-D0）
    years = [str(y) for y in range(2011, 2027)]
    yearly = {}
    for y in years:
        row = {"year": y, "base": bh_m["yearly"].get(y)}
        for k in ("T5-D0", "T5-D20", "T35-D0"):
            yv = out["configs"][k]["yearly"].get(y)
            row[k] = yv
            row[f"{k}_excess"] = (round(yv - bh_m["yearly"][y], 4) if (yv is not None and bh_m["yearly"].get(y) is not None) else None)
        yearly[y] = row
    out["yearly"] = yearly
    ex = [yearly[y]["T5-D0_excess"] for y in years if yearly[y]["T5-D0_excess"] is not None]
    pos = [e for e in ex if e > 0]
    out["yearly_stats"] = {
        "n_years": len(ex),
        "positive_years": len(pos),
        "positive_share": round(len(pos) / len(ex), 4) if ex else None,
        "sum_positive": round(float(sum(pos)), 4) if pos else 0.0,
        "concentration_top2": (round(float(sum(sorted(pos, reverse=True)[:2]) / sum(pos)), 4) if pos and sum(pos) > 0 else None),
        "max_single_excess": (round(float(max(ex)), 4) if ex else None),
        "max_single_share": (round(float(max(ex) / sum(ex)), 4) if ex and sum(ex) > 0 else None),
        "cumulative_excess": round(float(sum(ex)), 4) if ex else None,
    }

    # 无未来函数：信号序列 + 抽样触发点
    t5 = flags["T5"]
    first_1 = str(t5[t5].index[0])[:10] if t5.any() else None
    # 触发段
    segs, start = [], None
    vals = t5.to_numpy(bool)
    for i, v in enumerate(vals):
        if v and start is None:
            start = i
        elif not v and start is not None:
            segs.append((start, i - 1)); start = None
    if start is not None:
        segs.append((start, len(vals) - 1))
    samples = []
    picks = segs[:2] + segs[len(segs) // 2:len(segs) // 2 + 1] + segs[-2:] if len(segs) >= 5 else segs
    for (a, b) in picks[:5]:
        d = idx.index[a]
        c60 = corr_idx.iloc[a] if a < len(corr_idx) else np.nan
        md = med_idx.iloc[a] if a < len(med_idx) else np.nan
        lf = lift_idx.iloc[a] if a < len(lift_idx) else np.nan
        fwd = close.iloc[min(a + 60, len(close) - 1)] / close.iloc[a] - 1
        samples.append({"date": str(d)[:10], "corr60": (round(float(c60), 4) if not np.isnan(c60) else None),
                        "median250": (round(float(md), 4) if not np.isnan(md) else None),
                        "lift": (round(float(lf), 4) if not np.isnan(lf) else None),
                        "duration_days": int(b - a + 1),
                        "fwd60_market": round(float(fwd), 4)})
    out["no_lookahead"] = {
        "first_signal_1": first_1,
        "n_segments": len(segs),
        "samples": samples,
        "samples_by_date": {s["date"]: s for s in samples},
        "signal_series": {
            "dates": [str(d)[:10] for d in idx.index],
            "values": [int(v) for v in vals],
        },
    }

    # 修正 G3 与门禁
    cfg = out["configs"]

    def gate(k):
        m = cfg[k]
        g1 = bool(m["dd_improvement"] >= 0.10)
        bull = sum((m["yearly"].get(str(y)) or 0) - (bh_m["yearly"].get(str(y)) or 0) for y in BULL_MAIN)
        g2 = bool(bull >= -0.15)
        g3 = bool((m["g3_gain"] or -9) >= 0.02)
        return {"G1": g1, "G2": g2, "G3": g3, "bull_sum": round(bull, 4)}

    gates = {k: gate(k) for k in cfg}
    thr_gains = [out["thresholds"][f"{t:.2f}"]["g3_gain"] for t in THRESHOLDS]
    g4 = bool(all((x or -9) > 0 for x in thr_gains) and len(set(1 if (x or 0) > 0 else -1 for x in thr_gains)) == 1)
    ys = out["yearly_stats"]
    g5 = bool(ys["concentration_top2"] is not None and ys["concentration_top2"] < 0.60)
    c3 = out["costs"][f"{COSTS[2]*100:.3f}%"]
    g6 = bool(c3["excess_vs_bh"] > 0)
    t5d0 = cfg["T5-D0"]
    g7 = bool((t5d0["sharpe"] or -9) > (simple["MA250"]["sharpe"] or 9) and (t5d0["sharpe"] or -9) > (simple["const80"]["sharpe"] or 9))
    out["gates"] = {"per_config": gates,
                    "G4": g4, "G5": g5, "G6": g6, "G7": g7,
                    "threshold_gains": [round(x, 4) if x is not None else None for x in thr_gains],
                    "concentration_top2": ys["concentration_top2"],
                    "cost3_excess": c3["excess_vs_bh"]}

    out["summary"] = {
        "main_window": {"start": MAIN_START, "end": str(idx.index[-1])[:10]},
        "t5_d0": {k: t5d0[k] for k in ("annual", "sharpe", "max_drawdown", "calmar", "g3_gain", "equiv_weight_dd", "dd_improvement")},
        "verdict": ("T5 成立" if (gates["T5-D0"]["G1"] and gates["T5-D0"]["G2"] and gates["T5-D0"]["G3"] and g4 and g5 and g6 and g7) else "未通过全部门禁"),
    }

    rp = BASE / "reports" / "r3_2_t5_robustness.json"
    rp.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n结果已存：{rp}")
    print("门禁:", json.dumps({k: v for k, v in out["gates"].items() if k != "per_config"}, ensure_ascii=False))
    print("逐年统计:", ys)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
