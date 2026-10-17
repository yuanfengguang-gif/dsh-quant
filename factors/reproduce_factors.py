# -*- coding: utf-8 -*-
"""factors/reproduce_factors.py —— 复现主系统三个最强因子族（涨停族 + 资金族；价值族 bp 待估值历史就绪）

直接复现主系统已实证最强的因子，跑三层验证（combo_validate_sig 内部=第一层 ICIR + 第二层组合 + 第三层容量）。

因子：
  limup_ex_5     近5日涨停次数（bars.db pct_chg 重建涨停标记，主系统 ICIR 1.239）
  limup_ex_ret_20 近20日涨停次日超额（主系统 ICIR 1.099）
  lhb_jg_cnt_20  近20日龙虎榜机构买入次数（lhb.db 机构净买，主系统 ICIR 0.900）
  bp（价值族）   账面市值比=1/PB（valuation.db pbMRQ，估值历史就绪后再加）

用法：python factors/reproduce_factors.py [--topn 20 --rebalance 40]
"""
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

CACHE = BASE / "data" / "cache"


def _limup_flag(panel: pd.DataFrame) -> pd.Series:
    """非一字板涨停标记（主系统口径：ret≥9.5% 记涨停，high==low 记一字板 → 剔除一字板买不进）。"""
    code = panel.index.get_level_values("code").astype(str).str.split(".").str[0]
    c2 = code.str[:2].to_numpy()  # 前两位（判断板块）
    pct = panel["pct_chg"].to_numpy()
    is_st = panel["is_st"].to_numpy(dtype=bool)
    is_cyb_kcb = (c2 == "30") | (c2 == "68")
    thr = np.where(is_st, 0.045, np.where(is_cyb_kcb, 0.195, 0.095))
    limup = pct >= thr
    oneline = (panel["high"].to_numpy() == panel["low"].to_numpy())  # 一字板（买不进）
    return pd.Series((limup & ~oneline).astype(float), index=panel.index)


def limup_ex_5(panel: pd.DataFrame) -> pd.Series:
    """近 5 日涨停次数。"""
    flag = _limup_flag(panel)
    return flag.groupby(level="code").rolling(5, min_periods=1).sum().reset_index(level=0, drop=True)


def limup_ex_ret_20(panel: pd.DataFrame) -> pd.Series:
    """近 20 日涨停次日「超额」（涨停日次日收益 - 当日市场均值收益）累积。
    区别于已证伪的「涨停次日高开诱多」：这里是相对市场的超额，不是绝对次日收益。"""
    flag = _limup_flag(panel)
    pct = panel["pct_chg"]
    next_ret = pct.groupby(level="code").shift(-1)
    mkt = pct.groupby(level="date").transform("mean")
    next_mkt = mkt.groupby(level="code").shift(-1)
    excess = (next_ret - next_mkt) * flag
    return excess.groupby(level="code").rolling(20, min_periods=1).sum().reset_index(level=0, drop=True)


def lhb_jg_cnt_20(panel: pd.DataFrame) -> pd.Series:
    """近 20 日龙虎榜机构净买次数（从 lhb_detail.jiedu 解析「N家机构买入/卖出」的 N，净买=买-卖）。"""
    dbp = CACHE / "lhb.db"
    if not dbp.exists():
        raise FileNotFoundError(f"缺 {dbp}，先跑 data/fetcher_advanced.py lhb")
    con = sqlite3.connect(dbp)
    lhb = pd.read_sql("SELECT code, date, jiedu FROM lhb_detail", con)
    con.close()
    j = lhb["jiedu"].astype(str)
    lhb["n_buy"] = j.str.extract(r"(\d+)家机构买入").astype(float).fillna(0)
    lhb["n_sell"] = j.str.extract(r"(\d+)家机构卖出").astype(float).fillna(0)
    lhb["jg_net"] = lhb["n_buy"] - lhb["n_sell"]  # 机构净买次数
    code_map = {c.split(".")[0]: c for c in panel.index.get_level_values("code").unique()}
    lhb["full_code"] = lhb["code"].astype(str).str.zfill(6).map(code_map)
    lhb = lhb.dropna(subset=["full_code"])
    lhb["date"] = pd.to_datetime(lhb["date"])
    m = lhb.pivot_table(index="date", columns="full_code", values="jg_net", aggfunc="sum")
    m = m.reindex(panel.index.get_level_values(0).unique()).fillna(0)
    m20 = m.rolling(20, min_periods=1).sum()
    return m20.stack().reindex(panel.index).fillna(0)


def bp_value(panel: pd.DataFrame) -> pd.Series:
    """价值族 bp = 每股净资产/股价 = (eps/roe)/close（finance.db eps+roe，季度频率，60日披露延迟防前视）。
    pbMRQ 版覆盖率低且无披露延迟，回测反而不如本版（60日lag 更保守）。"""
    dbp = CACHE / "finance.db"
    if not dbp.exists():
        raise FileNotFoundError(f"缺 {dbp}")
    con = sqlite3.connect(dbp)
    fin = pd.read_sql("SELECT code, period, eps, roe FROM finance_report", con)
    con.close()
    fin["roe"] = pd.to_numeric(fin["roe"], errors="coerce")
    fin["eps"] = pd.to_numeric(fin["eps"], errors="coerce")
    fin["bps"] = np.where(fin["roe"] > 0, fin["eps"] / fin["roe"], np.nan)  # 每股净资产
    code_map = {c.split(".")[0]: c for c in panel.index.get_level_values("code").unique()}
    fin["full_code"] = fin["code"].astype(str).str.zfill(6).map(code_map)
    fin = fin.dropna(subset=["full_code", "bps"])
    fin["eff_date"] = pd.to_datetime(fin["period"]) + pd.Timedelta(days=60)
    m = fin.pivot_table(index="eff_date", columns="full_code", values="bps", aggfunc="last")
    dates = panel.index.get_level_values(0).unique().sort_values()
    m = m.reindex(m.index.union(dates)).sort_index().ffill().reindex(dates)
    bps = m.stack().reindex(panel.index)
    return bps / panel["close"]


def _finance_field(panel: pd.DataFrame, field: str) -> pd.Series:
    """读 finance.db 某字段，60 日披露延迟 + 前向填充，对齐 panel 索引。"""
    con = sqlite3.connect(CACHE / "finance.db")
    fin = pd.read_sql(f"SELECT code, period, {field} FROM finance_report", con)
    con.close()
    fin[field] = pd.to_numeric(fin[field], errors="coerce")
    code_map = {c.split(".")[0]: c for c in panel.index.get_level_values("code").unique()}
    fin["code"] = fin["code"].astype(str).str.zfill(6).map(code_map)
    fin = fin.dropna(subset=["code", field])
    fin["eff_date"] = pd.to_datetime(fin["period"]) + pd.Timedelta(days=60)
    m = fin.pivot_table(index="eff_date", columns="code", values=field, aggfunc="last")
    dates = panel.index.get_level_values(0).unique().sort_values()
    m = m.reindex(m.index.union(dates)).sort_index().ffill().reindex(dates)
    return m.stack().reindex(panel.index)


def open_prem_20(panel: pd.DataFrame) -> pd.Series:
    """20 日开盘溢价累积（open/prev_close - 1）。"""
    prev_close = panel["close"].groupby(level="code").shift(1)
    prem = panel["open"] / prev_close - 1
    return prem.groupby(level="code").rolling(20, min_periods=1).sum().reset_index(level=0, drop=True)


def turn_mid_prox(panel: pd.DataFrame) -> pd.Series:
    """换手中枢（主系统口径 backtest_pv_consensus）：-(20日均换手 - 全市场中位数)，接近中位=值大。"""
    t = panel["turn"]
    t20 = t.groupby(level="code").transform(lambda s: s.rolling(20, min_periods=5).mean())
    med = t20.groupby(level="date").transform("median")
    return -(t20 - med)


def sue(panel: pd.DataFrame) -> pd.Series:
    """SUE（主系统口径 fundamental.py）：(当期单季净利 - 上年同期) / |上年同期|，绝对值分母防负基数爆炸。"""
    con = sqlite3.connect(CACHE / "finance.db")
    fin = pd.read_sql("SELECT code, period, sq_net_profit FROM finance_report", con)
    con.close()
    fin["sq_net_profit"] = pd.to_numeric(fin["sq_net_profit"], errors="coerce")
    fin = fin.dropna(subset=["sq_net_profit"])
    fin["period"] = pd.to_datetime(fin["period"])
    fin["code6"] = fin["code"].astype(str).str.zfill(6)
    # 上年同期（同月、年份-1）
    fin["prev_period"] = fin["period"] - pd.DateOffset(years=1)
    prev = fin[["code6", "period", "sq_net_profit"]].rename(
        columns={"period": "prev_period", "sq_net_profit": "prev_sq"})
    fin = fin.merge(prev, on=["code6", "prev_period"], how="left")
    fin["sue"] = np.where(fin["prev_sq"].abs() > 1e-9,
                          (fin["sq_net_profit"] - fin["prev_sq"]) / fin["prev_sq"].abs(), np.nan)
    code_map = {c.split(".")[0]: c for c in panel.index.get_level_values("code").unique()}
    fin["full_code"] = fin["code6"].map(code_map)
    fin = fin.dropna(subset=["full_code", "sue"])
    fin["eff_date"] = fin["period"] + pd.Timedelta(days=60)  # PIT 披露延迟近似
    m = fin.pivot_table(index="eff_date", columns="full_code", values="sue", aggfunc="last")
    dates = panel.index.get_level_values(0).unique().sort_values()
    m = m.reindex(m.index.union(dates)).sort_index().ffill().reindex(dates)
    return m.stack().reindex(panel.index)


def f_score(panel: pd.DataFrame) -> pd.Series:
    """质量因子（主系统口径 FACTOR_ALIAS：roe → f_score，净资产收益率连续值）。"""
    return _finance_field(panel, "roe")


# 因子注册：名称 / 计算函数 / 方向（None=自动判向）
FACTORS = [
    ("limup_ex_5", limup_ex_5, None),
    ("limup_ex_ret_20", limup_ex_ret_20, -1),   # 涨停次日超额，方向-1（涨停反转族）
    ("lhb_jg_cnt_20", lhb_jg_cnt_20, None),
    ("bp_value", bp_value, None),
    ("open_prem_20", open_prem_20, -1),   # 跳空高开→回落（反转方向）
    ("turn_mid_prox", turn_mid_prox, None),
    ("sue", sue, None),
    ("f_score", f_score, None),
]


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-pool", action="store_true", help="把裁决「有效」的因子写三件套入池")
    ap.add_argument("--topn", type=int, default=DEFAULT_TOPN)
    ap.add_argument("--rebalance", default=DEFAULT_REBALANCE)
    args = ap.parse_args()
    topn, rebalance = args.topn, args.rebalance
    print("加载面板（bars.db 全量）...", flush=True)
    panel = load_panel("data/cache/bars.db", start="2019-01-01")
    print(f"面板 {panel.shape}", flush=True)

    CATEGORY = {"limup_ex_5": "情绪", "limup_ex_ret_20": "情绪",
                "lhb_jg_cnt_20": "资金", "bp_value": "价值",
                "open_prem_20": "情绪", "turn_mid_prox": "量价",
                "sue": "成长", "f_score": "质量"}

    rows, passed = [], []
    for name, fn, direction in FACTORS:
        try:
            sig = fn(panel)
            cov = float(sig.notna().mean())
            r = combo_validate_sig(name, sig, panel, topn=topn, rebalance=rebalance,
                                   start=DEFAULT_START, end=DEFAULT_END, direction=direction)
            m = r["metrics"]
            rows.append({"因子": name, "方向": f"{r['direction']:+d}", "结论": r["verdict"],
                         "icir20": r["health"]["icir_20"], "icir120": r["health"]["icir_120"],
                         "覆盖率": f"{cov:.2%}",
                         "年化": f"{m['annual_return']:+.1%}", "净超额": f"{r['excess_annual']:+.2%}",
                         "夏普": f"{m['sharpe']:.2f}", "回撤": f"{m['max_drawdown']:.1%}",
                         "换手": f"{r['capacity']['turnover']:.0%}"})
            print(f"  {name:<16s} 结论={r['verdict']} icir20={r['health']['icir_20']} "
                  f"icir120={r['health']['icir_120']} 净超额={r['excess_annual']:+.2%} "
                  f"夏普={m['sharpe']:.2f}", flush=True)
            if r["verdict"] == "有效":
                passed.append({
                    "code": name, "name_cn": name, "category": CATEGORY.get(name, "其他"),
                    "direction": r["direction"], "status": "有效",
                    "usage": "复现主系统最强因子族",
                    "icir_20": r["health"]["icir_20"], "icir_60": r["health"]["icir_60"],
                    "icir_120": r["health"]["icir_120"], "rank": r["score_latest"],
                })
        except Exception as e:
            print(f"  {name:<16s} 失败: {str(e)[:100]}", flush=True)

    print("\n=== 复现因子三层验证汇总 ===")
    print(pd.DataFrame(rows).to_string(index=False))

    if args.write_pool and passed:
        from factors.factor_pool_writer import write_pool
        data_date = str(panel.index.get_level_values(0).max())[:10]
        paths = write_pool(passed, data_date=data_date)
        print(f"\n=== {len(passed)} 个因子已写池 ===")
        for k, v in paths.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
