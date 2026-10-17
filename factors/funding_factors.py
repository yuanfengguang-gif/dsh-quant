# -*- coding: utf-8 -*-
"""factors/funding_factors.py —— 资金族因子（B 路线靶子 1：补齐最弱的族）

背景（docs/因子挖掘双路线方案.md）：
  T4 首轮 36 因子里，**资金族只有 1 个**（`lhb_jg_cnt_20`），且 `lhb.db` 仅 2019+ →
  2010-2018 恒为 0（"假覆盖"），等于该族在 2010-2018 完全空缺。
  而 `rzrq.db` 覆盖 **2010-03-31 ~ 2026-10-12（619 万行 / 3,854 只）** → 可补上这 16 年。

三个候选因子：
  margin_ratio_20 : 融资余额 20 日均 / 流通市值        （杠杆水平）
  margin_chg_20   : 融资余额 20 日变化率              （资金流入速度）
  short_ratio     : 融券余额 / 流通市值               （做空压力）

关键实现细节（不引入额外数据加载）：
  流通市值 = close × 流通股本，而 `turn = volume / 流通股本`
  → **流通股本 = volume / turn** → 流通市值 = close × volume / turn
  （turn 与 volume 都在 panel 里，单位：turn 为小数比率、volume 为股）

用法：
    from factors.funding_factors import margin_ratio_20, margin_chg_20, short_ratio
    sig = margin_ratio_20(panel)     # 返回与 panel.index 对齐的 Series
自检：python factors/funding_factors.py
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

CACHE = Path(__file__).resolve().parent.parent / "data" / "cache"
RZRQ = CACHE / "rzrq.db"

_WIN = 20
_cache: dict | None = None


def _load_rzrq() -> dict:
    """{(date, code6): (rzye, rqye)}；只读一次，模块级缓存"""
    global _cache
    if _cache is not None:
        return _cache
    con = sqlite3.connect(f"file:{RZRQ.as_posix()}?mode=ro", uri=True, timeout=60)
    d = {}
    for code, date, rzye, rqye in con.execute(
            "SELECT code, date, rzye, rqye FROM rzrq"):
        d[(str(date)[:10], str(code)[:6])] = (rzye, rqye)
    con.close()
    _cache = d
    return d


def _align(panel: pd.DataFrame, series: pd.Series) -> pd.Series:
    return series.reindex(panel.index)


def _rz_frame(panel: pd.DataFrame) -> pd.DataFrame:
    """把 rzrq 对齐到 panel，返回 rzye / rqye 两列（单位：元）"""
    rz = _load_rzrq()
    dates = panel.index.get_level_values(0)
    codes = panel.index.get_level_values("code")
    keys = list(zip(map(lambda x: str(x)[:10], dates), map(lambda x: str(x)[:6], codes)))
    rzye = np.array([rz.get(k, (np.nan, np.nan))[0] for k in keys], dtype=float)
    rqye = np.array([rz.get(k, (np.nan, np.nan))[1] for k in keys], dtype=float)
    return pd.DataFrame({"rzye": rzye, "rqye": rqye}, index=panel.index)


def _circ_mv(panel: pd.DataFrame) -> pd.Series:
    """流通市值（元）= close × volume / turn；turn<=0 或缺失时为 NaN"""
    close = panel["close"].astype(float)
    vol = panel["volume"].astype(float)
    turn = panel["turn"].astype(float)
    turn = turn.where(turn > 0)
    return (close * vol / turn)


def margin_ratio_20(panel: pd.DataFrame) -> pd.Series:
    """融资余额 20 日均 / 流通市值（越高=杠杆越重；方向预期为负）"""
    rz = _rz_frame(panel)
    mv = _circ_mv(panel)
    # 按 code 分组滚动
    rzye_ma = (rz["rzye"].groupby(level="code", group_keys=False)
               .apply(lambda s: s.rolling(_WIN, min_periods=5).mean()))
    sig = rzye_ma / mv.replace(0, np.nan)
    return _align(panel, sig)


def margin_chg_20(panel: pd.DataFrame) -> pd.Series:
    """融资余额 20 日变化率（资金流入速度；方向预期为正）"""
    rz = _rz_frame(panel)
    chg = rz["rzye"].groupby(level="code", group_keys=False).apply(
        lambda s: s / s.shift(_WIN) - 1.0)
    return _align(panel, chg)


def short_ratio(panel: pd.DataFrame) -> pd.Series:
    """融券余额 / 流通市值（做空压力；方向预期为负）"""
    rz = _rz_frame(panel)
    mv = _circ_mv(panel)
    sig = rz["rqye"] / mv.replace(0, np.nan)
    return _align(panel, sig)


# ---- 自检：不起全量面板，只用一小段验证数值合理 ----
if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("rzrq 记录数:", len(_load_rzrq()))
    con = sqlite3.connect(f"file:{(CACHE / 'bars.db').as_posix()}?mode=ro", uri=True, timeout=30)
    rows = con.execute(
        "SELECT date, code, close, volume, turn FROM daily_bar "
        "WHERE code='600519.SH' AND date BETWEEN '2026-09-20' AND '2026-10-16' ORDER BY date").fetchall()
    con.close()
    df = pd.DataFrame(rows, columns=["date", "code", "close", "volume", "turn"])
    df["date"] = pd.to_datetime(df["date"])
    panel = df.set_index(["date", "code"])
    print("样例面板:", panel.shape)
    for fn in (margin_ratio_20, margin_chg_20, short_ratio):
        s = fn(panel)
        print(f"  {fn.__name__:18s} 非空 {s.notna().sum()}/{len(s)}  末值={s.dropna().iloc[-1] if s.notna().any() else None}")
    print("\n流通市值自检（应≈1.6 万亿）:")
    print("  ", _circ_mv(panel).dropna().iloc[-1] / 1e12, "万亿")
