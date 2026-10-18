# -*- coding: utf-8 -*-
"""scripts/r3_0_trigger_drill.py —— R3-0 危机触发器历史演习（只做数据统计，不做策略）

规格：reports/R3-0_任务书.md v1.1
  T1 vol20 的 750 日 trailing 分位 >90%
  T2 同 T1 >97%
  T3 close<MA250 且 close/rolling_max250-1 < -20%
  T4 (融资余额/流通市值) 20 日变化 < -5%（仅 2016+）
  T5 (4 指数 60 日平均两两相关) − (过去 250 日中位数) > +0.05
  T6 T1 AND T3

降仓模拟：非触发 100%，触发 50%，t0 次日开盘执行，ETF 成本 0.036%/边，现金 0%。
产出：reports/r3_0_trigger_drill.json
"""
from __future__ import annotations

import json
import sqlite3
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

CACHE = BASE / "data" / "cache"
COST_CFG = yaml.safe_load((BASE / "config" / "costs_etf.yaml").read_text(encoding="utf-8"))
COST_SIDE = float(COST_CFG["commission"]) + float(COST_CFG["slippage"])
CASH_DAILY = 0.0

EVENTS = [
    ("2007-10 金融海啸", "2007-10-16", -0.723),
    ("2015-06 股灾", "2015-06-08", -0.465),
    ("2018-01 贸易战", "2018-01-24", -0.325),
    ("2021-02 核心资产", "2021-02-18", -0.450),
    ("2024-09 急跌", "2024-05-20", -0.157),
]
BULL_YEARS = [2007, 2009, 2019, 2024]
TRIGGERS = ["T1", "T2", "T3", "T4", "T5", "T6"]


def fetch(code: str) -> pd.DataFrame:
    r = tqs.get_market_data(field_list=["Open", "Close"], stock_list=[code], period="1d",
                            start_time="2005-01-01", end_time="2026-10-17", dividend_type="none")
    c = r.get("Close")
    df = pd.DataFrame({"open": r["Open"].iloc[:, 0], "close": c.iloc[:, 0]}).dropna()
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def rolling_rank(s: pd.Series, w: int) -> pd.Series:
    vals = s.to_numpy(float)
    out = np.full(len(vals), np.nan)
    for i in range(w - 1, len(vals)):
        win = vals[i - w + 1:i + 1]
        if np.isnan(win).any():
            continue
        out[i] = float((win <= win[-1]).mean())
    return pd.Series(out, index=s.index)


def to_segments(flag: pd.Series) -> list[dict]:
    segs, start = [], None
    for i, d in enumerate(flag.index):
        v = bool(flag.iloc[i])
        if v and start is None:
            start = i
        elif not v and start is not None:
            segs.append({"start": start, "end": i - 1})
            start = None
    if start is not None:
        segs.append({"start": start, "end": len(flag) - 1})
    return segs


def seg_metrics(idx: pd.DataFrame, rolls: dict, seg: dict) -> dict:
    d = idx.index
    i0 = seg["start"]
    close = idx["close"].to_numpy(float)
    t0 = d[i0]
    dd0 = float(1.0 - close[i0] / rolls["max250"][i0]) if not np.isnan(rolls["max250"][i0]) else None
    out = {"t0": str(t0)[:10], "t_end": str(d[seg["end"]])[:10], "dd_at_t0": (round(dd0, 4) if dd0 is not None else None)}
    for k in (20, 60, 120):
        j = i0 + k
        out[f"ret_{k}"] = round(float(close[j] / close[i0] - 1), 4) if j < len(close) else None
    win = close[i0:i0 + 61]
    if len(win) > 1:
        peak = np.maximum.accumulate(win)
        out["fwd_max_dd_60"] = round(float(-np.min(win / peak - 1)), 4)
    else:
        out["fwd_max_dd_60"] = None
    out["hit"] = (1 if (out.get("ret_60") is not None and out["ret_60"] < 0) else 0) if out.get("ret_60") is not None else None
    return out


def simulate(idx: pd.DataFrame, flag: pd.Series, cost: float = COST_SIDE) -> dict:
    """触发→次日开盘降至 50%；非触发→100%。open-to-open，现金 0%，双边成本。"""
    d = idx.index
    opens = idx["open"].to_numpy(float)
    n = len(idx)
    target = np.where(flag.fillna(False).to_numpy(bool), 0.5, 1.0)
    rets = np.zeros(n - 1)
    w = 1.0
    pending = 0.0
    for i in range(n - 1):
        r = opens[i + 1] / opens[i] - 1.0
        rets[i] = w * r + (1 - w) * CASH_DAILY - pending
        # 收盘决策（作用于下一开盘）
        new_w = target[i]
        pending = cost * abs(new_w - w) if abs(new_w - w) > 1e-12 else 0.0
        w = new_w
    ret = pd.Series(rets, index=d[1:])
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
    yearly = {str(y): round(float((1 + g).prod() - 1), 4) for y, g in ret.groupby(ret.index.year)}
    return {
        "annual": round(ann, 4), "sharpe": (round(sharpe, 3) if sharpe is not None else None),
        "max_drawdown": round(maxdd, 4), "calmar": (round(ann / abs(maxdd), 3) if maxdd else None),
        "dd_days_max": int(longest), "vol": round(vol, 4), "yearly": yearly,
        "ret_series": ret,
    }


def buy_hold_metrics(ret: pd.Series) -> dict:
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
    return {"annual": round(ann, 4), "sharpe": (round(sharpe, 3) if sharpe is not None else None),
            "max_drawdown": round(maxdd, 4), "calmar": (round(ann / abs(maxdd), 3) if maxdd else None),
            "dd_days_max": int(longest), "vol": round(vol, 4),
            "yearly": {str(y): round(float((1 + g).prod() - 1), 4) for y, g in ret.groupby(ret.index.year)}}


def main() -> int:
    print("取数：指数 ...", flush=True)
    idx = fetch("000300.SH")
    idx905 = fetch("000905.SH")
    idx852 = fetch("000852.SH")
    idxcyb = fetch("399006.SZ")
    print(f"  HS300 {len(idx)} 行 {idx.index[0].date()}~{idx.index[-1].date()}", flush=True)

    close = idx["close"]
    ret = close.pct_change()
    vol20 = ret.rolling(20).std() * np.sqrt(252)
    rank = rolling_rank(vol20, 750)
    t1 = rank > 0.90
    t2 = rank > 0.97
    ma250 = close.rolling(250).mean()
    max250 = close.rolling(250).max()
    dd250 = close / max250 - 1
    t3 = (close < ma250) & (dd250 < -0.20)

    # T4：融资余额 / 流通市值
    con = sqlite3.connect(str(CACHE / "rzrq.db"))
    fin = pd.read_sql("SELECT date, SUM(rzye) AS fin FROM rzrq GROUP BY date ORDER BY date", con)
    con.close()
    fin["date"] = pd.to_datetime(fin["date"])
    fin = fin.set_index("date")["fin"]
    con = sqlite3.connect(str(CACHE / "hist_mv.db"))
    mv = pd.read_sql("SELECT month, SUM(circ_mv) AS cap FROM hist_mv GROUP BY month ORDER BY month", con)
    con.close()
    mv["date"] = pd.to_datetime(mv["month"] + "-01") + pd.offsets.MonthEnd(0)
    mv = mv.set_index("date")["cap"]
    fin_d = fin.reindex(idx.index).ffill()
    cap_d = mv.reindex(idx.index).ffill() * 1e6  # 百万 → 元
    ratio = fin_d / cap_d
    t4 = (ratio / ratio.shift(20) - 1) < -0.05
    t4 = t4 & (idx.index >= pd.Timestamp("2016-01-01"))

    # T5：4 指数 60 日平均两两相关 − 过去 250 日中位数 > 0.05
    px = pd.concat([idx["close"], idx905["close"], idx852["close"], idxcyb["close"]], axis=1, join="inner")
    px.columns = ["HS300", "ZZ500", "ZZ1000", "CYB"]
    r4 = px.pct_change()
    pairs = [(a, b) for i, a in enumerate(r4.columns) for b in list(r4.columns)[i + 1:]]
    cors = pd.concat([r4[a].rolling(60).corr(r4[b]) for a, b in pairs], axis=1).mean(axis=1)
    lift = cors - cors.rolling(250).median()
    t5 = (lift > 0.05).reindex(idx.index)
    lift_idx = lift.reindex(idx.index)

    t6 = t1 & t3

    flags = {"T1": t1, "T2": t2, "T3": t3, "T4": t4, "T5": t5, "T6": t6}
    valid_start = {
        "T1": str(rank.dropna().index[0])[:10] if rank.notna().any() else None,
        "T2": str(rank.dropna().index[0])[:10] if rank.notna().any() else None,
        "T3": str(ma250.dropna().index[0])[:10] if ma250.notna().any() else None,
        "T4": "2016-01-01",
        "T5": str(lift.dropna().index[0])[:10] if lift.notna().any() else None,
        "T6": str(rank.dropna().index[0])[:10] if rank.notna().any() else None,
    }

    rolls = {"max250": max250.to_numpy(float)}
    bh_ret = pd.Series(idx["open"].to_numpy(float)[1:] / idx["open"].to_numpy(float)[:-1] - 1.0,
                       index=idx.index[1:])
    bh = buy_hold_metrics(bh_ret)

    out = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "meta": {
            "task": "R3-0 危机触发器历史演习",
            "window": {"start": str(idx.index[0])[:10], "end": str(idx.index[-1])[:10]},
            "index": "000300.SH none（通达信直取）",
            "quantile": "trailing 750 交易日",
            "cost_model": "config/costs_etf.yaml 买/卖各 0.036%",
            "exec": "触发次日开盘降仓至 50%",
            "cash_return": "0%（任务书未规定；R7 标注）",
            "data_limits": {"T1/T2": f"滚动分位最早 {valid_start['T1']}（此前标数据不足）",
                            "T4": "仅 2016+（融资余额/流通市值）",
                            "T5": f"相关性最早 {valid_start['T5']}"},
        },
        "buy_hold": {k: v for k, v in bh.items() if k != "yearly"},
        "buy_hold_yearly": bh["yearly"],
        "triggers": {},
    }

    for t in TRIGGERS:
        flag = flags[t].fillna(False)
        segs = to_segments(flag)
        metrics = [seg_metrics(idx, rolls, s) for s in segs]
        hit_vals = [m["ret_60"] for m in metrics if m.get("ret_60") is not None]
        hits = [m["hit"] for m in metrics if m.get("hit") is not None]
        false_ret = [m["ret_60"] for m in metrics if m.get("ret_60") is not None and m["ret_60"] > 0]
        first = pd.Timestamp(valid_start[t]) if valid_start[t] else None
        avail_days = int((idx.index >= first).sum()) if first is not None else 0
        trig_days = int(flag[flag.index >= first].sum()) if first is not None else 0
        sim = simulate(idx, flag)
        ret_s = sim.pop("ret_series")
        sim["excess_vs_bh"] = round(sim["annual"] - bh["annual"], 4)
        sim["yearly_excess_vs_bh"] = {
            str(y): round(float((1 + ret_s[ret_s.index.year == y]).prod()
                                - (1 + bh_ret[bh_ret.index.year == y]).prod()), 4)
            for y in sorted(set(ret_s.index.year))}

        out["triggers"][t] = {
            "first_valid": valid_start[t],
            "segments": metrics,
            "stats": {
                "n_segments": len(metrics),
                "years_available": round(avail_days / 252.0, 2),
                "freq_per_year": round(len(metrics) / (avail_days / 252.0), 2) if avail_days else None,
                "days_share": round(trig_days / avail_days, 4) if avail_days else None,
                "hit_rate": round(float(np.mean(hits)), 4) if hits else None,
                "false_alarm_median_ret60": round(float(np.median(false_ret)), 4) if false_ret else None,
                "n_false_alarm": len(false_ret),
            },
            "sim": sim,
        }

    # 关键节点：trough 取 750 交易日（约 3 年）内的最低点，避免把 2021-2024 慢熊截断在 1 年内
    events = []
    close_v = close.to_numpy(float)
    for name, peak_date, stated in EVENTS:
        peak_ts = pd.Timestamp(peak_date)
        pos = int(idx.index.searchsorted(peak_ts))
        peak = close_v[pos]
        window_end = min(pos + 750, len(close_v) - 1)
        trough_pos = pos + int(np.argmin(close_v[pos:window_end + 1]))
        actual = round(float(close_v[trough_pos] / peak - 1), 4)
        row = {"event": name, "peak": str(idx.index[pos])[:10],
               "trough": str(idx.index[trough_pos])[:10],
               "stated_dd": stated, "actual_dd": actual, "triggers": {}}
        for t in TRIGGERS:
            f = flags[t]
            first_ts = pd.Timestamp(valid_start[t]) if valid_start[t] else None
            if first_ts is not None and first_ts > peak_ts:
                row["triggers"][t] = {"status": "数据不足", "first": None, "dd_at_trigger": None}
                continue
            sub = f.iloc[pos:trough_pos + 1]
            hit_idx = np.where(sub.fillna(False).to_numpy(bool))[0]
            if len(hit_idx) == 0:
                row["triggers"][t] = {"status": "未触发", "first": None, "dd_at_trigger": None}
            else:
                k = int(hit_idx[0])
                dd_at = round(float(1 - close_v[pos + k] / peak), 4)
                item = {"status": "触发", "first": str(idx.index[pos + k])[:10], "dd_at_trigger": dd_at}
                if t == "T5":
                    item["lift"] = round(float(lift_idx.iloc[pos + k]), 4) if not np.isnan(lift_idx.iloc[pos + k]) else None
                row["triggers"][t] = item
        events.append(row)
    out["events"] = events

    # 表 3 牛市误触发（基准用 close-to-close 日历年，与任务书口径一致）
    close_yearly, prev_close = {}, None
    for y, g in close.groupby(close.index.year):
        close_yearly[str(y)] = (round(float(g.iloc[-1] / prev_close - 1), 4) if prev_close else None)
        prev_close = g.iloc[-1]
    t3rows = []
    for y in BULL_YEARS:
        counts = {t: len([s for s in out["triggers"][t]["segments"] if s["t0"][:4] == str(y)]) for t in TRIGGERS}
        t3rows.append({"year": y, "base_return": close_yearly.get(str(y)),
                       "trigger_counts": counts,
                       "T1_sim_excess": out["triggers"]["T1"]["sim"]["yearly_excess_vs_bh"].get(str(y))})
    out["table3"] = t3rows
    # 供溯源引用：把数组转成带键对象（audit_citations 的 [src:] 正则不能容纳路径里的 [ ]）
    out["events_by_key"] = {e["event"].split(" ")[0]: e for e in events}
    out["table3_by_year"] = {str(r["year"]): r for r in t3rows}

    # 同一窗口（2016+）的公平对照：不同触发器有效起点不同（T4 2016 / T5 2011）
    bh_2016 = buy_hold_metrics(bh_ret[bh_ret.index >= pd.Timestamp("2016-01-01")])
    out["same_window_2016"] = {"buy_hold": bh_2016, "triggers": {}}
    for t in TRIGGERS:
        # 重算该触发器的收益序列（simulate 已 pop，故重建一次）
        flag = flags[t].fillna(False)
        sim_full = simulate(idx, flag)
        rs = sim_full.pop("ret_series")
        m16 = buy_hold_metrics(rs[rs.index >= pd.Timestamp("2016-01-01")])
        m16["excess_vs_bh"] = round(m16["annual"] - bh_2016["annual"], 4)
        out["same_window_2016"]["triggers"][t] = m16

    # 汇总表（table1/2/4 由报告方按 JSON 渲染，这里保留结构化）
    out["summary"] = {
        "buy_hold": {k: v for k, v in bh.items() if k != "yearly"},
        "triggers": {t: {"stats": out["triggers"][t]["stats"], "sim": {k: v for k, v in out["triggers"][t]["sim"].items()}} for t in TRIGGERS},
    }

    rp = BASE / "reports" / "r3_0_trigger_drill.json"
    rp.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"结果已存：{rp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
