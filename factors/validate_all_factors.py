# -*- coding: utf-8 -*-
"""factors/validate_all_factors.py —— 统一验证全量可得因子（8 强 + 技术面 + 基本面 + 经典指标 + 量价）

口径：与 reproduce_factors.py 完全一致——combo_validate_sig（内部=第一层 ICIR + 第二层组合 + 第三层容量）。
因子来源（见 FACTOR_FORMULA_CATALOG.md）：
  - 8 强（reproduce_factors.py，已反推）
  - 14 技术面（backtest_all_factors.py）
  - 5 五强量价（backtest_pv_consensus.py）
  - 6 基本面（fundamental.py）
  - 6 动量/低波/新高（factor_engine.py）
  - 10 经典技术指标（classic_indicators.py）

用法：python factors/validate_all_factors.py [--topn 20 --rebalance 40] [--out logs/all_factors_validation.json]
"""
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from factors.import_qf_pool import load_panel
from factors.combo_validate import combo_validate_sig, DEFAULT_TOPN, DEFAULT_REBALANCE, DEFAULT_START, DEFAULT_END
from factors.funding_factors import margin_ratio_20, margin_chg_20, short_ratio
from factors.reproduce_factors import (
    limup_ex_5, limup_ex_ret_20, lhb_jg_cnt_20, bp_value,
    open_prem_20, turn_mid_prox, sue, f_score, _finance_field,
)

CACHE = BASE / "data" / "cache"


# ============================ 技术面（backtest_all_factors.py → panel 化） ============================

def o2c_sum_20(panel):
    """日内收益反转：(-(close/open-1)) 20 日滚动和。"""
    x = -(panel["close"] / panel["open"] - 1)
    return x.groupby(level="code").rolling(20, min_periods=5).sum().reset_index(level=0, drop=True)


def turn_std20(panel):
    """低换手波动：-20 日换手 std。"""
    return (-panel["turn"].groupby(level="code").rolling(20, min_periods=5).std()
            .reset_index(level=0, drop=True))


def amihud(panel):
    """非流动性：|ret|/amount 20 日均值。"""
    ret = panel["close"].groupby(level="code").pct_change()
    return ((ret.abs() / (panel["amount"] + 1e-8))
            .groupby(level="code").rolling(20, min_periods=5).mean().reset_index(level=0, drop=True))


def chip_concentration(panel):
    """筹码集中（换手波动比取负）：-(20日换手 std / 20日换手中位数)，逐股时序。"""
    t = panel["turn"]
    std = t.groupby(level="code").rolling(20, min_periods=5).std().reset_index(level=0, drop=True)
    med = t.groupby(level="code").rolling(20, min_periods=5).median().reset_index(level=0, drop=True)
    return -(std / med.replace(0, np.nan))


def beta_60(panel):
    """60 日 beta vs 等权市场（宽表向量化）。"""
    r = panel["close"].unstack("code").pct_change()
    mkt = r.mean(axis=1)
    rm = r.rolling(60).mean()
    mm = mkt.rolling(60).mean()
    cov = (r.sub(rm, axis=0).mul((mkt - mm), axis=0)).rolling(60).mean()
    var = (mkt - mm).pow(2).rolling(60).mean()
    return cov.div(var.replace(0, np.nan), axis=0).stack().reindex(panel.index)


def mom_120(panel):
    return panel["close"].groupby(level="code").pct_change(120)


def reversal_20(panel):
    return -(panel["close"].groupby(level="code").pct_change(20))


def lowvol_60(panel):
    ret = panel["close"].groupby(level="code").pct_change()
    return -(ret.groupby(level="code").rolling(60, min_periods=40).std()
             .reset_index(level=0, drop=True))


def near_high_250(panel):
    c = panel["close"].groupby(level="code")
    hi = c.rolling(250, min_periods=125).max().reset_index(level=0, drop=True)
    return (panel["close"] / hi).clip(upper=1.0)


def vol_contract(panel):
    """波动收缩：-(20 日波动率 - 其 20 日前值)。"""
    ret = panel["close"].groupby(level="code").pct_change()
    v20 = ret.groupby(level="code").rolling(20, min_periods=5).std().reset_index(level=0, drop=True)
    return -(v20 - v20.groupby(level="code").shift(20))


def rsi_14(panel):
    c = panel["close"]
    d = c.groupby(level="code").diff()
    up = d.clip(lower=0).groupby(level="code").rolling(14).mean().reset_index(level=0, drop=True)
    dn = (-d.clip(upper=0)).groupby(level="code").rolling(14).mean().reset_index(level=0, drop=True)
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def vol_ratio(panel):
    v = panel["volume"]
    return v / v.groupby(level="code").rolling(20, min_periods=5).mean().reset_index(level=0, drop=True)


def ma_trend_20(panel):
    c = panel["close"]
    return c / c.groupby(level="code").rolling(20, min_periods=5).mean().reset_index(level=0, drop=True) - 1


def mom_20(panel):
    return panel["close"].groupby(level="code").pct_change(20)


# ============================ 五强量价（backtest_pv_consensus.py） ============================

def turnover_low(panel):
    """低换手：-20 日均换手。"""
    t20 = panel["turn"].groupby(level="code").transform(lambda s: s.rolling(20, min_periods=5).mean())
    return -t20


def sentiment(panel):
    """换手异动：20 日均换手 / 60 日均换手。"""
    t20 = panel["turn"].groupby(level="code").transform(lambda s: s.rolling(20, min_periods=5).mean())
    t60 = panel["turn"].groupby(level="code").transform(lambda s: s.rolling(60, min_periods=20).mean())
    return t20 / t60.replace(0, np.nan)


# ============================ 基本面（fundamental.py → finance.db 直读） ============================

def _panel_codes_dates(panel):
    """从 panel 派生 codes/dates（不再依赖 validate_all_factors.main 设置的全局变量）。"""
    codes = panel.index.get_level_values("code").unique()
    dates = panel.index.get_level_values(0).unique().sort_values()
    return codes, dates


def _fin_hist(field, panel):
    """finance.db 字段 → 60 日披露 lag + ffill → panel 对齐。"""
    return _finance_field_any(field, panel)


def _finance_field_any(field, panel):
    con = sqlite3.connect(CACHE / "finance.db")
    fin = pd.read_sql(f"SELECT code, period, {field} FROM finance_report", con)
    con.close()
    fin[field] = pd.to_numeric(fin[field], errors="coerce")
    codes, dates = _panel_codes_dates(panel)
    code_map = {c.split(".")[0]: c for c in codes}
    fin["code"] = fin["code"].astype(str).str.zfill(6).map(code_map)
    fin = fin.dropna(subset=["code", field])
    fin["eff_date"] = pd.to_datetime(fin["period"]) + pd.Timedelta(days=60)
    m = fin.pivot_table(index="eff_date", columns="code", values=field, aggfunc="last")
    m = m.reindex(m.index.union(dates)).sort_index().ffill().reindex(dates)
    return m.stack().reindex(panel.index)


def c_factor(panel):
    """C 因子：最新单季净利同比。"""
    return _finance_field_any("sq_net_yoy", panel).reindex(panel.index)


def accel_factor(panel):
    """同比加速度：当期 sq_net_yoy - 上期 sq_net_yoy（需按 period 排序取相邻报告期）。"""
    con = sqlite3.connect(CACHE / "finance.db")
    fin = pd.read_sql("SELECT code, period, sq_net_yoy FROM finance_report", con)
    con.close()
    fin["sq_net_yoy"] = pd.to_numeric(fin["sq_net_yoy"], errors="coerce")
    fin = fin.dropna(subset=["sq_net_yoy"]).sort_values(["code", "period"])
    fin["prev"] = fin.groupby("code")["sq_net_yoy"].shift(1)
    fin["accel"] = fin["sq_net_yoy"] - fin["prev"]
    codes, dates = _panel_codes_dates(panel)
    code_map = {c.split(".")[0]: c for c in codes}
    fin["code"] = fin["code"].astype(str).str.zfill(6).map(code_map)
    fin = fin.dropna(subset=["code", "accel"])
    fin["eff_date"] = pd.to_datetime(fin["period"]) + pd.Timedelta(days=60)
    m = fin.pivot_table(index="eff_date", columns="code", values="accel", aggfunc="last")
    m = m.reindex(m.index.union(dates)).sort_index().ffill().reindex(dates)
    return m.stack().reindex(panel.index)


def a_factor(panel):
    """3 年年度净利 CAGR。"""
    con = sqlite3.connect(CACHE / "finance.db")
    fin = pd.read_sql("SELECT code, period, net_profit FROM finance_report", con)
    con.close()
    fin["net_profit"] = pd.to_numeric(fin["net_profit"], errors="coerce")
    fin = fin.dropna(subset=["net_profit"])
    fin["period"] = pd.to_datetime(fin["period"])
    fin = fin[fin["period"].dt.month == 12].sort_values(["code", "period"])
    fin["prev_np"] = fin.groupby("code")["net_profit"].shift(1)
    fin["years"] = fin.groupby("code")["period"].diff().dt.days / 365.0
    fin["cagr"] = (fin["net_profit"] / fin["prev_np"]) ** (1 / fin["years"].clip(lower=1)) - 1
    codes, dates = _panel_codes_dates(panel)
    code_map = {c.split(".")[0]: c for c in codes}
    fin["code"] = fin["code"].astype(str).str.zfill(6).map(code_map)
    fin = fin.dropna(subset=["code", "cagr"])
    fin = fin[~np.isinf(fin["cagr"].astype(float))]
    fin["eff_date"] = pd.to_datetime(fin["period"]) + pd.Timedelta(days=60)
    m = fin.pivot_table(index="eff_date", columns="code", values="cagr", aggfunc="last")
    m = m.reindex(m.index.union(dates)).sort_index().ffill().reindex(dates)
    return m.stack().reindex(panel.index)


def pead_factor(panel):
    """PEAD 代理：本季同比 > 上季同比取全值，否则 ×0.5。"""
    con = sqlite3.connect(CACHE / "finance.db")
    fin = pd.read_sql("SELECT code, period, sq_net_yoy FROM finance_report", con)
    con.close()
    fin["sq_net_yoy"] = pd.to_numeric(fin["sq_net_yoy"], errors="coerce")
    fin = fin.dropna(subset=["sq_net_yoy"]).sort_values(["code", "period"])
    fin["prev"] = fin.groupby("code")["sq_net_yoy"].shift(1)
    fin["pead"] = np.where(fin["sq_net_yoy"] > fin["prev"], fin["sq_net_yoy"], fin["sq_net_yoy"] * 0.5)
    codes, dates = _panel_codes_dates(panel)
    code_map = {c.split(".")[0]: c for c in codes}
    fin["code"] = fin["code"].astype(str).str.zfill(6).map(code_map)
    fin = fin.dropna(subset=["code", "pead"])
    fin["eff_date"] = pd.to_datetime(fin["period"]) + pd.Timedelta(days=60)
    m = fin.pivot_table(index="eff_date", columns="code", values="pead", aggfunc="last")
    m = m.reindex(m.index.union(dates)).sort_index().ffill().reindex(dates)
    return m.stack().reindex(panel.index)


# ============================ 经典技术指标（classic_indicators.py → panel 化） ============================

def _ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def macd_hist(panel):
    c = panel["close"]
    dif = c.groupby(level="code").transform(lambda s: _ema(s, 12) - _ema(s, 26))
    dea = dif.groupby(level="code").transform(lambda s: _ema(s, 9))
    return dif - dea


def kdj_j(panel):
    h = panel["high"].groupby(level="code").rolling(9).max().reset_index(level=0, drop=True)
    l = panel["low"].groupby(level="code").rolling(9).min().reset_index(level=0, drop=True)
    rsv = (panel["close"] - l) / (h - l).replace(0, np.nan) * 100
    k = rsv.groupby(level="code").transform(lambda s: s.ewm(com=2, adjust=False).mean())
    d = k.groupby(level="code").transform(lambda s: s.ewm(com=2, adjust=False).mean())
    return 3 * k - 2 * d


def boll_lower(panel):
    c = panel["close"]
    mid = c.groupby(level="code").rolling(20).mean().reset_index(level=0, drop=True)
    std = c.groupby(level="code").rolling(20).std().reset_index(level=0, drop=True)
    return c / (mid - 2 * std) - 1


def ma_bull(panel):
    c = panel["close"]
    return c.groupby(level="code").rolling(20).mean().reset_index(level=0, drop=True) / \
        c.groupby(level="code").rolling(60).mean().reset_index(level=0, drop=True) - 1


def roc12(panel):
    return panel["close"].groupby(level="code").pct_change(12)


def wr14(panel):
    h = panel["high"].groupby(level="code").rolling(14).max().reset_index(level=0, drop=True)
    l = panel["low"].groupby(level="code").rolling(14).min().reset_index(level=0, drop=True)
    return (h - panel["close"]) / (h - l).replace(0, np.nan) * -100


def cci14(panel):
    h = panel["high"].groupby(level="code").rolling(14).max().reset_index(level=0, drop=True)
    l = panel["low"].groupby(level="code").rolling(14).min().reset_index(level=0, drop=True)
    tp = (h + l + panel["close"]) / 3
    ma = tp.groupby(level="code").rolling(14).mean().reset_index(level=0, drop=True)
    md = (tp - ma).abs().groupby(level="code").rolling(14).mean().reset_index(level=0, drop=True)
    return (tp - ma) / (0.015 * md).replace(0, np.nan)


def ma200_trend(panel):
    c = panel["close"]
    return c / c.groupby(level="code").rolling(200).mean().reset_index(level=0, drop=True) - 1


# ============================ 因子注册 ============================

_PANEL_CODES = []
_PANEL_DATES = []

FACTORS = [
    # 8 强（reproduce_factors.py）
    ("limup_ex_5", limup_ex_5, None),
    ("limup_ex_ret_20", limup_ex_ret_20, -1),
    ("lhb_jg_cnt_20", lhb_jg_cnt_20, None),
    ("bp_value", bp_value, None),
    ("open_prem_20", open_prem_20, -1),
    ("turn_mid_prox", turn_mid_prox, None),
    ("sue", sue, None),
    ("f_score", f_score, None),
    # 技术面
    ("o2c_sum_20", o2c_sum_20, None),
    ("turn_std20", turn_std20, None),
    ("amihud", amihud, None),
    ("chip_concentration", chip_concentration, None),
    ("beta_60", beta_60, None),
    ("mom_120", mom_120, -1),
    ("reversal_20", reversal_20, None),
    ("lowvol_60", lowvol_60, None),
    ("near_high_250", near_high_250, None),
    ("vol_contract", vol_contract, None),
    ("rsi_14", rsi_14, -1),
    ("vol_ratio", vol_ratio, None),
    ("ma_trend_20", ma_trend_20, None),
    ("mom_20", mom_20, -1),
    # 五强量价
    ("turnover_low", turnover_low, None),
    ("sentiment", sentiment, None),
    # 基本面
    ("c_factor", c_factor, None),
    ("accel_factor", accel_factor, None),
    ("a_factor", a_factor, None),
    ("pead_factor", pead_factor, None),
    # 经典技术指标
    ("macd_hist", macd_hist, None),
    ("kdj_j", kdj_j, -1),
    ("boll_lower", boll_lower, -1),
    ("ma_bull", ma_bull, None),
    ("roc12", roc12, -1),
    ("wr14", wr14, -1),
    ("cci14", cci14, -1),
    ("ma200_trend", ma200_trend, None),
    # ★2026-10-17 资金族（B 路线靶子 1）：rzrq.db 覆盖 2010-03 起，补上 lhb 只有 2019+ 的空白
    ("margin_ratio_20", margin_ratio_20, None),
    ("margin_chg_20", margin_chg_20, None),
    ("short_ratio", short_ratio, None),
]

CATEGORY = {
    "limup_ex_5": "情绪", "limup_ex_ret_20": "情绪", "lhb_jg_cnt_20": "资金", "bp_value": "价值",
    "open_prem_20": "情绪", "turn_mid_prox": "量价", "sue": "成长", "f_score": "质量",
    "o2c_sum_20": "反转动量", "turn_std20": "量价", "amihud": "量价", "chip_concentration": "筹码",
    "beta_60": "量价", "mom_120": "反转动量", "reversal_20": "反转动量", "lowvol_60": "反转动量",
    "near_high_250": "量价", "vol_contract": "量价", "rsi_14": "反转动量", "vol_ratio": "量价",
    "ma_trend_20": "量价", "mom_20": "反转动量", "turnover_low": "量价", "sentiment": "情绪",
    "c_factor": "成长", "accel_factor": "成长", "a_factor": "成长", "pead_factor": "成长",
    "macd_hist": "量价", "kdj_j": "反转动量", "boll_lower": "反转动量", "ma_bull": "量价",
    "roc12": "反转动量", "wr14": "反转动量", "cci14": "反转动量", "ma200_trend": "量价", "margin_ratio_20": "资金", "margin_chg_20": "资金", "short_ratio": "资金",
}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--topn", type=int, default=DEFAULT_TOPN)
    ap.add_argument("--rebalance", default=DEFAULT_REBALANCE)
    ap.add_argument("--out", default=str(BASE / "logs" / "all_factors_validation.json"))
    ap.add_argument("--only", default="", help="逗号分隔因子名，只跑这些（默认全部）")
    args = ap.parse_args()

    global _PANEL_CODES, _PANEL_DATES
    # ★2026-10-17 配置驱动：面板加载起点来自 config/backtest_window.yaml
    try:
        from factors.window_config import get_window as _gw
        _pstart = _gw()["panel_load_start"]
    except Exception:
        _pstart = "2019-01-01"
    print(f"加载面板（bars.db，start={_pstart}）...", flush=True)
    panel = load_panel("data/cache/bars.db", start=_pstart)
    _PANEL_CODES = panel.index.get_level_values("code").unique()
    _PANEL_DATES = panel.index.get_level_values(0).unique().sort_values()
    print(f"面板 {panel.shape}", flush=True)

    rows, passed = [], []
    _only = {x.strip() for x in args.only.split(",") if x.strip()}
    _todo = [t for t in FACTORS if (not _only or t[0] in _only)]
    print(f"待验证 {len(_todo)} / {len(FACTORS)} 个因子；窗口 {DEFAULT_START} ~ {DEFAULT_END}", flush=True)
    for name, fn, direction in _todo:
        try:
            sig = fn(panel)
            if not isinstance(sig, pd.Series):
                sig = pd.Series(sig)
            sig = sig.reindex(panel.index)
            cov = float(sig.notna().mean())
            # ★2026-10-17 覆盖率告警：因子只有部分历史却当全期结论是最容易犯的错
            #   （例：lhb_jg_cnt_20 依赖 lhb.db，而该库仅 2019+ → 2010-2018 覆盖率为 0）
            warn = ""
            if cov < 0.50:
                warn = f"⚠️覆盖率仅{cov:.0%}（结论不代表全窗口）"
            elif cov < 0.80:
                warn = f"🟡覆盖率{cov:.0%}"
            # ★2026-10-17 截面退化检查（防「假覆盖」）：
            #   lhb_jg_cnt_20 名义覆盖 100%，但 2012/2015/2018 截面 std=0、nunique=1（恒为 0），
            #   真实信号只有 2019+。这类因子必须标出来，否则会把 7 年结论当 17 年用。
            try:
                _yb = sig.groupby(sig.index.get_level_values(0).year).agg(["std", "nunique"])
                _dead = [str(int(y)) for y, row in _yb.iterrows()
                         if (row["std"] or 0) == 0 or (row["nunique"] or 0) <= 1]
                if _dead:
                    warn = (warn + f" ⚠️截面退化年份:{','.join(_dead[:6])}"
                            + ("…" if len(_dead) > 6 else ""))
            except Exception:
                pass
            if warn:
                print(f"  {name:<18s} {warn}", flush=True)
            r = combo_validate_sig(name, sig, panel, topn=args.topn, rebalance=args.rebalance,
                                   start=DEFAULT_START, end=DEFAULT_END, direction=direction)
            m = r["metrics"]
            rows.append({"因子": name, "族": CATEGORY.get(name, "其他"), "方向": f"{r['direction']:+d}",
                         "结论": r["verdict"], "icir20": round(r["health"]["icir_20"], 3),
                         "icir120": round(r["health"]["icir_120"], 3), "覆盖率": round(cov, 4),
                         "覆盖告警": warn,
                         "年化": round(m["annual_return"], 4), "净超额": round(r["excess_annual"], 4),
                         "夏普": round(m["sharpe"], 3), "回撤": round(m["max_drawdown"], 4),
                         "换手": round(r["capacity"]["turnover"], 3)})
            print(f"  {name:<18s} {r['verdict']} icir20={r['health']['icir_20']:+.3f} "
                  f"icir120={r['health']['icir_120']:+.3f} 净超额={r['excess_annual']:+.2%} "
                  f"夏普={m['sharpe']:.2f}", flush=True)
            if r["verdict"] == "有效":
                passed.append(name)
        except Exception as e:
            print(f"  {name:<18s} 失败: {str(e)[:120]}", flush=True)
            rows.append({"因子": name, "族": CATEGORY.get(name, "其他"), "结论": f"失败:{str(e)[:60]}"})

    df = pd.DataFrame(rows)
    print("\n=== 全量因子统一验证汇总 ===")
    print(df.to_string(index=False))
    out = {"validated_at": str(pd.Timestamp.now())[:19], "factors": rows, "有效": passed}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n有效 {len(passed)} 个：{passed}")
    print(f"结果已存：{args.out}")


if __name__ == "__main__":
    main()

