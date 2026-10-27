# -*- coding: utf-8 -*-
"""scripts/build_crisis_indicators.py —— 生成危机信号指标库（25 个）+ 领先性排序

数据缓存：data/cache/crisis/indicators25.csv（月频）
用法：
    python scripts/build_crisis_indicators.py            # 增量（已有缓存则只补最新）
    python scripts/build_crisis_indicators.py --full     # 全量重算

说明：25 个指标全部统一方向为「数值越大＝压力越大」。
A股本土的 PE/PB 直接使用 akshare 自带的历史分位（比自算更准）。
"""
from __future__ import annotations
import sys, argparse, sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parents[1]
CACHE = BASE / "data" / "cache" / "crisis"
DB = BASE / "data" / "cache" / "dividend_research.db"
CACHE.mkdir(parents=True, exist_ok=True)
OUT = CACHE / "indicators25.csv"

US_TICKERS = ["SPY", "IWM", "RSP", "EEM", "HYG", "LQD", "IEF", "JNK", "GLD",
              "UUP", "VXX", "XLF", "XLY", "XLP", "CPER", "USO", "SPHB", "SPLV"]


def usc(sym: str) -> pd.Series:
    f = CACHE / f"us_{sym}.csv"
    if f.exists():
        return pd.read_csv(f, parse_dates=["date"]).set_index("date")["close"].astype(float)
    import akshare as ak
    df = ak.stock_us_daily(symbol=sym)
    df.columns = [str(c) for c in df.columns]
    df["date"] = pd.to_datetime(df["date"])
    s = df.set_index("date")["close"].astype(float)
    s.to_frame("close").to_csv(f)
    return s


def cnc(sym: str) -> pd.Series:
    f = CACHE / f"cn_{sym}.csv"
    if f.exists():
        return pd.read_csv(f, parse_dates=["date"]).set_index("date")["close"].astype(float)
    import akshare as ak
    df = ak.stock_zh_index_daily(symbol=sym)
    df.columns = [str(c) for c in df.columns]
    df["date"] = pd.to_datetime(df["date"])
    s = df.set_index("date")["close"].astype(float)
    s.to_frame("close").to_csv(f)
    return s


def mm(s: pd.Series) -> pd.Series:
    x = s.resample("ME").last().dropna()
    x.index = x.index.to_period("M").to_timestamp("M")
    return x


def pct5(s: pd.Series, win: int = 60, minp: int = 24) -> pd.Series:
    return s.rolling(win, min_periods=minp).apply(lambda x: (x < x.iloc[-1]).mean(), raw=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    a = ap.parse_args()

    import akshare as ak
    print("  [1/4] 加载美股序列…")
    U = {s: usc(s) for s in US_TICKERS}
    print(f"        {len(U)} 个标的")

    print("  [2/4] 加载 A 股序列…")
    HS = cnc("sh000300")
    tips = pd.read_csv(BASE / "data" / "cache" / "tips10y.csv",
                       parse_dates=["date"]).set_index("date")["tips10y"]
    try:
        b = ak.bond_zh_us_rate(start_date="20050101")
        b.columns = [str(c) for c in b.columns]
        b["日期"] = pd.to_datetime(b["日期"])
        b = b.set_index("日期")
        curve102 = b["美国国债收益率10年-2年"].astype(float)
    except Exception:
        curve102 = None

    def a_margin():
        df = ak.macro_china_market_margin_sh()
        df.columns = [str(c) for c in df.columns]
        df["日期"] = pd.to_datetime(df["日期"])
        col = "融资融券余额" if "融资融券余额" in df.columns else "融资余额"
        return df.set_index("日期")[col].astype(float).sort_index()

    def a_pe():
        df = ak.stock_a_ttm_lyr(); df.columns = [str(c) for c in df.columns]
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        return df["middlePETTM"].astype(float), df["quantileInAllHistoryMiddlePeTtm"].astype(float)

    def a_pb():
        df = ak.stock_a_all_pb(); df.columns = [str(c) for c in df.columns]
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        return df["middlePB"].astype(float), df["quantileInAllHistoryMiddlePB"].astype(float)

    MARGIN = a_margin(); APE, APE_Q = a_pe(); APB, APB_Q = a_pb()

    c = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    amt = pd.read_sql_query(
        "SELECT date,amount FROM idx_daily WHERE code='000300' AND amount IS NOT NULL ORDER BY date", c)
    c.close()
    amt["date"] = pd.to_datetime(amt["date"])
    HS_AMT = amt.set_index("date")["amount"].astype(float)

    print("  [3/4] 合成月频矩阵…")
    M = pd.DataFrame({"spy": mm(U["SPY"]), "iwm": mm(U["IWM"]), "rsp": mm(U["RSP"]),
                      "eem": mm(U["EEM"]), "hyg": mm(U["HYG"]), "lqd": mm(U["LQD"]),
                      "ief": mm(U["IEF"]), "jnk": mm(U["JNK"]), "gld": mm(U["GLD"]),
                      "uup": mm(U["UUP"]), "vxx": mm(U["VXX"]), "xlf": mm(U["XLF"]),
                      "xly": mm(U["XLY"]), "xlp": mm(U["XLP"]), "cper": mm(U["CPER"]),
                      "uso": mm(U["USO"]), "sphb": mm(U["SPHB"]), "splv": mm(U["SPLV"]),
                      "hs": mm(HS)})
    M["margin"] = mm(MARGIN).reindex(M.index).ffill()
    M["ape"] = APE.reindex(M.index, method="ffill")
    M["apb"] = APB.reindex(M.index, method="ffill")
    M["amt"] = mm(HS_AMT).reindex(M.index).ffill()
    M["tips"] = tips.reindex(M.index, method="ffill")
    if curve102 is not None:
        M["c102"] = curve102.reindex(M.index, method="ffill")

    print("  [4/4] 构建 25 个指标…")
    F = pd.DataFrame(index=M.index)

    def safe(name, series, higher_stress=True):
        if series is None:
            return
        F[name] = pct5(series) * 100 if higher_stress else (1 - pct5(series)) * 100

    F["1_回撤"] = (1 - M["spy"] / M["spy"].cummax()) * 100
    F["2_波动率分位"] = pct5(M["spy"].pct_change().rolling(3).std() * np.sqrt(12)) * 100
    F["3_低于MA10M"] = (1 - M["spy"] / M["spy"].rolling(10, min_periods=6).mean()).clip(lower=0) * 100
    safe("4_信用利差(HYG/LQD)", M["hyg"] / M["lqd"], higher_stress=False)
    F["5_垃圾债动能"] = (-M["hyg"].pct_change(3) * 100).clip(lower=0)
    safe("6_垃圾债vs国债(HYG/IEF)", M["hyg"] / M["ief"], higher_stress=False)
    if "c102" in M:
        F["7_曲线10Y2Y"] = -M["c102"]
    F["8_TIPS实际利率"] = M["tips"]
    safe("9_美元动量", M["uup"].pct_change(3), higher_stress=True)
    safe("10_小盘vs大盘(IWM/SPY)", M["iwm"] / M["spy"], higher_stress=False)
    safe("11_等权vs市值权(RSP/SPY)", M["rsp"] / M["spy"], higher_stress=False)
    safe("12_高beta vs低波(SPHB/SPLV)", M["sphb"] / M["splv"], higher_stress=False)
    safe("13_金融股相对(XLF/SPY)", M["xlf"] / M["spy"], higher_stress=False)
    safe("14_周期vs防御(XLY/XLP)", M["xly"] / M["xlp"], higher_stress=False)
    safe("15_新兴vs美股(EEM/SPY)", M["eem"] / M["spy"], higher_stress=False)
    rets = pd.DataFrame({"spy": M["spy"].pct_change(), "iwm": M["iwm"].pct_change(),
                         "eem": M["eem"].pct_change(), "hyg": M["hyg"].pct_change(),
                         "gld": M["gld"].pct_change(), "lqd": M["lqd"].pct_change()})
    F["16_资产相关性"] = rets.rolling(3).corr().groupby(level=0).apply(
        lambda x: x.values[np.triu_indices(len(x), 1)].mean()).reindex(M.index) * 100
    safe("17_VIX代理(VXX)", M["vxx"], higher_stress=True)
    safe("18_铜金比(CPER/GLD)", M["cper"] / M["gld"], higher_stress=False)
    F["19_原油动能"] = (-M["uso"].pct_change(3) * 100).clip(lower=0)
    safe("20_两融余额分位", M["margin"], higher_stress=True)
    F["21_两融3月变化"] = (M["margin"].pct_change(3) * 100).clip(lower=0)
    # 注意：akshare 的 quantileInAllHistory* 列只有最后一行有值（历史全 NaN），
    # 不能用它做时间序列，必须自己算滚动分位（E28）
    F["22_全A市盈率分位"] = pct5(M["ape"]) * 100
    F["23_全A市净率分位"] = pct5(M["apb"]) * 100
    F["24_沪深300成交额分位"] = pct5(M["amt"]) * 100
    F["25_沪深300回撤"] = (1 - M["hs"] / M["hs"].cummax()) * 100

    F.to_csv(OUT)
    print(f"\n  ✅ 已保存 {F.shape[1]} 个指标 × {F.shape[0]} 月 → {OUT}")
    print(f"     最新月：{F.index[-1].date()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
