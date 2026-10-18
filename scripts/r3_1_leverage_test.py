# -*- coding: utf-8 -*-
"""scripts/r3_1_leverage_test.py —— R3-1 降仓激进度 + 等价固定仓位对照

规格：reports/R3-1_任务书.md
  T3 / T5 / T35(=T3 OR T5)；档位 D50/D30/D20/D0；现金 0%（主）/1.5%（敏感性）
  每个（触发器,档位）算等效固定仓位 = 1 − (1−档位)×触发天数占比，并做恒定权重对照（G3）
产出：reports/r3_1_leverage_test.json
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
LEVELS = {"D50": 0.50, "D30": 0.30, "D20": 0.20, "D0": 0.0}
CASH = {"c0": 0.0, "c15": 0.015}
EVENTS = [("2007-10", "2007-10-16"), ("2015-06", "2015-06-08"), ("2018-01", "2018-01-24"),
          ("2021-02", "2021-02-18"), ("2024-09", "2024-05-20")]
BULL = [2007, 2009, 2019, 2024]


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
    return {
        "annual": round(ann, 4), "vol": round(vol, 4),
        "sharpe": (round(sharpe, 3) if sharpe is not None else None),
        "max_drawdown": round(maxdd, 4),
        "calmar": (round(ann / abs(maxdd), 3) if maxdd else None),
        "dd_days_max": int(longest), "n_days": int(len(ret)),
        "yearly": {str(y): round(float((1 + g).prod() - 1), 4) for y, g in ret.groupby(ret.index.year)},
    }


def simulate(idx: pd.DataFrame, flag: pd.Series, level: float, cash_annual: float) -> pd.Series:
    opens = idx["open"].to_numpy(float)
    n = len(idx)
    target = np.where(flag.fillna(False).to_numpy(bool), level, 1.0)
    rc = cash_annual / 252.0
    rets = np.zeros(n - 1)
    w = 1.0
    pending = 0.0
    for i in range(n - 1):
        r = opens[i + 1] / opens[i] - 1.0
        rets[i] = w * r + (1 - w) * rc - pending
        new_w = target[i]
        pending = COST * abs(new_w - w) if abs(new_w - w) > 1e-12 else 0.0
        w = new_w
    return pd.Series(rets, index=idx.index[1:])


def fixed_weight(idx: pd.DataFrame, w: float, cash_annual: float) -> pd.Series:
    op = idx["open"].to_numpy(float)
    r = pd.Series(op[1:] / op[:-1] - 1.0, index=idx.index[1:])
    return w * r + (1 - w) * (cash_annual / 252.0)


def main() -> int:
    idx = fetch("000300.SH")
    idx905 = fetch("000905.SH")
    idx852 = fetch("000852.SH")
    idxcyb = fetch("399006.SZ")
    close = idx["close"]
    ret = close.pct_change()

    ma250 = close.rolling(250).mean()
    max250 = close.rolling(250).max()
    t3 = (close < ma250) & (close / max250 - 1 < -0.20)

    px = pd.concat([idx["close"], idx905["close"], idx852["close"], idxcyb["close"]], axis=1, join="inner")
    px.columns = ["HS300", "ZZ500", "ZZ1000", "CYB"]
    r4 = px.pct_change()
    pairs = [(a, b) for i, a in enumerate(r4.columns) for b in list(r4.columns)[i + 1:]]
    cors = pd.concat([r4[a].rolling(60).corr(r4[b]) for a, b in pairs], axis=1).mean(axis=1)
    lift = cors - cors.rolling(250).median()
    t5 = (lift > 0.05).reindex(idx.index).fillna(False)
    t35 = (t3.fillna(False) | t5.fillna(False))

    valid = {
        "T3": str(ma250.dropna().index[0])[:10],
        "T5": str(lift.dropna().index[0])[:10],
        "T35": str(min(ma250.dropna().index[0], lift.dropna().index[0]))[:10],
    }
    flags = {"T3": t3.fillna(False), "T5": t5, "T35": t35}

    bh = metrics(pd.Series(idx["open"].to_numpy(float)[1:] / idx["open"].to_numpy(float)[:-1] - 1.0,
                           index=idx.index[1:]))
    bh_yearly_close, prev = {}, None
    for y, g in close.groupby(close.index.year):
        bh_yearly_close[str(y)] = (round(float(g.iloc[-1] / prev - 1), 4) if prev else None)
        prev = g.iloc[-1]
    bh_yearly_open = bh["yearly"]  # open-to-open，与组合收益同口径，用于算超额
    bh16_ret = pd.Series(idx["open"].to_numpy(float)[1:] / idx["open"].to_numpy(float)[:-1] - 1.0,
                         index=idx.index[1:])
    bh16 = metrics(bh16_ret[bh16_ret.index >= pd.Timestamp("2016-01-01")])

    out = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "meta": {
            "task": "R3-1 降仓激进度 + 等价固定仓位对照",
            "window": {"start": str(idx.index[0])[:10], "end": str(idx.index[-1])[:10]},
            "triggers": "T3 / T5 / T35=T3 OR T5（定义同 R3-0）",
            "levels": {k: v for k, v in LEVELS.items()},
            "cash": {"c0": "0%（主口径）", "c15": "1.5%（敏感性）"},
            "cost": "ETF 0.036%/边",
            "exec": "触发次日开盘调仓",
            "equiv_note": "等效固定仓位 = 1 − (1−档位)×触发天数占比；恒定权重每日再平衡、不计成本",
        },
        "first_valid": valid,
        "bh": {k: v for k, v in bh.items() if k != "yearly"},
        "bh_yearly_close": bh_yearly_close,
        "bh_yearly_open": bh_yearly_open,
        "bh_2016": bh16,
        "triggers": {},
    }

    for t in ("T3", "T5", "T35"):
        flag = flags[t]
        first = pd.Timestamp(valid[t])
        avail = int((idx.index >= first).sum())
        trig = int(flag[flag.index >= first].sum())
        share = trig / avail if avail else 0.0
        out["triggers"][t] = {"first_valid": valid[t], "days_share": round(share, 4), "levels": {}}
        for lname, lv in LEVELS.items():
            s0 = simulate(idx, flag, lv, CASH["c0"])
            s15 = simulate(idx, flag, lv, CASH["c15"])
            ew = 1.0 - (1.0 - lv) * share
            e0 = fixed_weight(idx, ew, CASH["c0"])
            e15 = fixed_weight(idx, ew, CASH["c15"])
            m0, m15, me0, me15 = metrics(s0), metrics(s15), metrics(e0), metrics(e15)
            extra = (m0["calmar"] / me0["calmar"] - 1.0) if (m0["calmar"] and me0["calmar"]) else None
            out["triggers"][t]["levels"][lname] = {
                "level": lv, "equiv_weight": round(ew, 4),
                "sim0": m0, "sim15": m15, "equiv0": me0, "equiv15": me15,
                "dd_improvement": round(abs(bh["max_drawdown"]) - abs(m0["max_drawdown"]), 4),
                "extra_value_pct": (round(extra, 4) if extra is not None else None),
                "g3_pass": bool(extra is not None and extra > 0.10),
                "y2016": metrics(s0[s0.index >= pd.Timestamp("2016-01-01")]),
            }

    # 表 1
    t1 = [{"trigger": "买入持有", "level": "—", **{k: bh[k] for k in ("annual", "sharpe", "max_drawdown", "calmar")},
           "dd_improvement": 0.0, "equiv_weight": 1.0}]
    for t in ("T3", "T5", "T35"):
        for lname in LEVELS:
            v = out["triggers"][t]["levels"][lname]
            t1.append({"trigger": t, "level": lname,
                       "annual": v["sim0"]["annual"], "sharpe": v["sim0"]["sharpe"],
                       "max_drawdown": v["sim0"]["max_drawdown"], "calmar": v["sim0"]["calmar"],
                       "dd_improvement": v["dd_improvement"], "equiv_weight": v["equiv_weight"]})
    out["table1"] = t1

    # 表 2：G3 对照
    t2 = []
    for t in ("T3", "T5", "T35"):
        for lname in LEVELS:
            v = out["triggers"][t]["levels"][lname]
            t2.append({"trigger": t, "level": lname,
                       "trigger_calmar": v["sim0"]["calmar"], "equiv_weight": v["equiv_weight"],
                       "equiv_calmar": v["equiv0"]["calmar"],
                       "trigger_dd": v["sim0"]["max_drawdown"],
                       "equiv_dd": v["equiv0"]["max_drawdown"],
                       "extra_value_pct": v["extra_value_pct"], "g3_pass": v["g3_pass"]})
    out["table2"] = t2

    # 表 3：牛市代价（超额 = 组合年内收益 − 买入持有**同口径** open-to-open 年内收益）
    combos = [("T3", "D20"), ("T5", "D20"), ("T35", "D20"), ("T3", "D0"), ("T35", "D0")]
    all_combos = [(t, l) for t in ("T3", "T5", "T35") for l in LEVELS]
    excess = {f"{t}-{l}": {} for t, l in all_combos}
    t3rows = []
    for y in BULL:
        row = {"year": str(y), "base_return_close": bh_yearly_close.get(str(y))}
        for t, l in all_combos:
            yv = out["triggers"][t]["levels"][l]["sim0"]["yearly"].get(str(y))
            ex = round(yv - bh_yearly_open[str(y)], 4) if (yv is not None and bh_yearly_open.get(str(y)) is not None) else None
            excess[f"{t}-{l}"][str(y)] = ex
            if (t, l) in combos:
                row[f"{t}-{l}"] = ex
        t3rows.append(row)
    totals = {f"{t}-{l}": round(sum(v for v in excess[f"{t}-{l}"].values() if v is not None), 4)
              for t, l in all_combos}
    t3rows.append({"year": "合计", **{k: v for k, v in totals.items() if any(k == f"{t}-{l}" for t, l in combos)}})
    out["table3"] = t3rows
    out["table3_by_year"] = {r["year"]: r for r in t3rows}
    out["bull_2y"] = {"2007+2009": {
        f"{t}-{l}": round((excess[f"{t}-{l}"].get("2007") or 0) + (excess[f"{t}-{l}"].get("2009") or 0), 4)
        for t, l in all_combos}}

    # 表 4：2016+
    t4 = [{"trigger": "买入持有", "level": "—", **{k: bh16[k] for k in ("annual", "sharpe", "max_drawdown", "calmar")},
           "excess_vs_bh": 0.0}]
    for t in ("T3", "T5", "T35"):
        for lname in LEVELS:
            m = out["triggers"][t]["levels"][lname]["y2016"]
            t4.append({"trigger": t, "level": lname, "annual": m["annual"], "sharpe": m["sharpe"],
                       "max_drawdown": m["max_drawdown"], "calmar": m["calmar"],
                       "excess_vs_bh": round(m["annual"] - bh16["annual"], 4)})
    out["table4"] = t4

    # 表 5：关键节点
    t5rows = []
    close_v = close.to_numpy(float)
    for key, peak_date in EVENTS:
        pos = int(idx.index.searchsorted(pd.Timestamp(peak_date)))
        window_end = min(pos + 750, len(close_v) - 1)
        trough = pos + int(np.argmin(close_v[pos:window_end + 1]))
        row = {"event": key, "peak": str(idx.index[pos])[:10],
               "dd": round(float(1 - close_v[trough] / close_v[pos]), 4)}
        for t in ("T3", "T5", "T35"):
            sub = flags[t].iloc[pos:trough + 1]
            idxs = np.where(sub.fillna(False).to_numpy(bool))[0]
            if len(idxs) == 0:
                row[t] = {"status": "未触发"}
            else:
                k = int(idxs[0])
                row[t] = {"status": "触发", "first": str(idx.index[pos + k])[:10],
                          "dd_at_trigger": round(float(1 - close_v[pos + k] / close_v[pos]), 4)}
        t5rows.append(row)
    out["table5"] = t5rows

    # 门禁：每个（触发器,档位）逐条
    gates = {}
    for t in ("T3", "T5", "T35"):
        gates[t] = {}
        for lname in LEVELS:
            v = out["triggers"][t]["levels"][lname]
            g1 = bool(v["dd_improvement"] >= 0.15)
            two = out["bull_2y"]["2007+2009"].get(f"{t}-{lname}")
            two = -9.0 if two is None else two
            g2 = bool(two >= -0.25)
            g3 = bool(v["g3_pass"])
            g4 = bool((v["y2016"]["sharpe"] or -9) >= bh16["sharpe"])
            # G5：0% 与 1.5% 的相对结论方向一致（触发式超额符号相同）
            ex0 = v["sim0"]["annual"] - bh["annual"]
            ex15 = v["sim15"]["annual"] - bh["annual"]
            g5 = bool((ex0 >= 0) == (ex15 >= 0))
            gates[t][lname] = {"G1": g1, "G2": g2, "G3": g3, "G4": g4, "G5": g5,
                               "all_pass": all([g1, g2, g3, g4, g5]),
                               "g2_2y_excess": two,
                               "excess_0": round(ex0, 4), "excess_15": round(ex15, 4)}
    out["gates"] = gates
    out["gates_by_key"] = {f"{t}-{l}": gates[t][l] for t in gates for l in gates[t]}
    out["table1_by_key"] = {("BH" if r["level"] == "—" else f'{r["trigger"]}-{r["level"]}'): r for r in t1}
    out["table2_by_key"] = {f'{r["trigger"]}-{r["level"]}': r for r in t2}
    out["table4_by_key"] = {("BH" if r["level"] == "—" else f'{r["trigger"]}-{r["level"]}'): r for r in t4}
    out["table5_by_event"] = {r["event"]: r for r in t5rows}
    out["summary"] = {
        "best_by_trigger": {t: max(LEVELS, key=lambda l: out["triggers"][t]["levels"][l]["sim0"]["calmar"] or -9)
                            for t in ("T3", "T5", "T35")},
        "any_all_pass": any(gates[t][l]["all_pass"] for t in gates for l in gates[t]),
        "g3_pass_count": sum(1 for t in gates for l in gates[t] if gates[t][l]["G3"]),
        "g1_pass_count": sum(1 for t in gates for l in gates[t] if gates[t][l]["G1"]),
    }

    rp = BASE / "reports" / "r3_1_leverage_test.json"
    rp.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"结果已存：{rp}")
    for t in ("T3", "T5", "T35"):
        print(f"\n{t}: first_valid={valid[t]} share={out['triggers'][t]['days_share']}")
        for l in LEVELS:
            v = out["triggers"][t]["levels"][l]
            print(f"  {l}: 年化 {v['sim0']['annual']:+.2%} 夏普 {v['sim0']['sharpe']} DD {v['sim0']['max_drawdown']:.2%} "
                  f"Calmar {v['sim0']['calmar']} | eq {v['equiv_weight']:.1%} Calmar {v['equiv0']['calmar']} "
                  f"extra {v['extra_value_pct']} G3={v['g3_pass']}")
    print("\nG3 pass count:", out["summary"]["g3_pass_count"], "| all-pass combos:", out["summary"]["any_all_pass"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
