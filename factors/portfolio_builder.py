# -*- coding: utf-8 -*-
"""factors/portfolio_builder.py —— 组合构建（6 环节，对齐用户确认的组合构建方案）

六环节（执行顺序按「先过滤→再中性→后选股」的合理顺序，与方案逐条对应）：
  L1 因子合成信号：选中因子（factor_subset 结果）方向化 + robust 归一化 → 等权(首选)/风险平价 合成 score
  L5 硬过滤：ST(is_st) / 退市(out_date) / 次新上市(ipo_date+60d) / 流动性(20日均额截面后 5%)
  L4 行业×市值中性：行业内 demean → 对 log(circ_mv) 正交化（剔除行业/市值 beta）
  L2 Top 10~20 选股：中性化 score 截面取 Top N
  L3 等权(首选)/风险平价：仓位权重（等权 或 逆波动率）
  L6 Regime 择时仓位：等权全市场指数 vs MA200 → 多/空两态，多头满仓、空头减半

口径（对齐 backtest-acceptance + combo_validate）：
  - T+1 open 买入 + 一字板涨停过滤（open≈high 买不进）
  - 成本：佣金万2.6 + 卖出印花税0.05% + 滑点0.1%（按真实换手摊入）
  - 回测窗默认 2020-06-01 ~ 2025-12-31（hist_mv/turn 覆盖边界），等权全市场为基准

用法：python factors/portfolio_builder.py [--topn 15 --factor-weighting eq|rp --pos-weighting eq|rp]
"""
import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from factors.import_qf_pool import load_panel, forward_returns, cross_sectional_ics
from factors.reproduce_factors import bp_value, sue, f_score, turn_mid_prox
from factors.validate_all_factors import (amihud, mom_120, near_high_250, ma200_trend,
                                          c_factor, accel_factor, a_factor, pead_factor,
                                          kdj_j, ma_bull, turn_std20, lowvol_60)
from backtest.bt_report import compute_metrics

CACHE = BASE / "data" / "cache"
COST = 0.00026 + 0.0005 + 0.001   # 佣金+印花税+滑点（backtest-acceptance 默认）

DEFAULT_TOPN = 15                 # 决策 #1：持仓 15 只
DEFAULT_REBALANCE = 40            # 40 交易日调仓（turn_low 实证口径）
# ★2026-10-17 配置驱动：窗口收敛到 config/backtest_window.yaml（缺文件/缺字段时回落原写死值）
try:
    from factors.window_config import get_window as _get_window
    _W = _get_window()
    DEFAULT_START = _W["start"]
    DEFAULT_END = _W["end"]
    PANEL_LOAD_START = _W["panel_load_start"]
except Exception:
    DEFAULT_START = "2010-01-01"
    DEFAULT_END = "2025-12-31"
    PANEL_LOAD_START = "2019-01-01"

# 因子注册（与 factor_subset.CANDIDATE_FACTORS 对齐）
FACTOR_FNS = {
    "amihud": amihud, "ma200_trend": ma200_trend, "f_score": f_score, "mom_120": mom_120,
    "bp_value": bp_value, "near_high_250": near_high_250, "pead_factor": pead_factor,
    "sue": sue, "c_factor": c_factor, "turn_mid_prox": turn_mid_prox,
    "accel_factor": accel_factor, "a_factor": a_factor, "kdj_j": kdj_j, "ma_bull": ma_bull, "turn_std20": turn_std20, "lowvol_60": lowvol_60,
}
FAMILY = {
    "amihud": "量价", "ma200_trend": "量价", "f_score": "质量", "mom_120": "反转",
    "bp_value": "价值", "near_high_250": "量价", "pead_factor": "成长", "sue": "成长",
    "c_factor": "成长", "turn_mid_prox": "量价", "accel_factor": "成长", "a_factor": "成长",
    "kdj_j": "反转", "ma_bull": "量价",
}


def _robust_wide(sig: pd.Series) -> pd.DataFrame:
    """截面 robust 归一化（逐日 median/MAD clip ±5）→ wide。"""
    med = sig.groupby(level=0).transform("median")
    mad = (sig - med).abs().groupby(level=0).transform("median")
    z = ((sig - med) / (mad + 1e-6)).clip(-5, 5)
    return z.unstack()


# ============================ L1 因子合成信号 ============================

def composite_signal(panel, selected, factor_weighting="eq", directions=None):
    """L1：方向化 + robust 归一化 + 合成（等权/风险平价）。返回 (composite_wide, factor_info)。
    directions: 可选 {name: ±1} 冻结方向（前向模拟盘/holdout 用，防用未来数据判向）；缺省按 RankIC 自动判向。"""
    fwd = forward_returns(panel)
    info = {}
    normed = {}
    for name in selected:
        sig = FACTOR_FNS[name](panel).reindex(panel.index)
        if directions and name in directions:
            d = directions[name]
        else:
            ics = cross_sectional_ics(sig, fwd)
            d = 1 if (len(ics) and ics.mean() >= 0) else -1
        nz = _robust_wide(sig * d)
        normed[name] = nz
        info[name] = {"direction": d, "family": FAMILY.get(name, "其他")}

    if factor_weighting == "rp":
        # 风险平价（因子级）：权重 ∝ 1/信号时序标准差（代理波动率）
        vols = {n: float(normed[n].stack().std() + 1e-12) for n in selected}
        inv = {n: 1.0 / vols[n] for n in selected}
        tot = sum(inv.values())
        w = {n: inv[n] / tot for n in selected}
    else:
        w = {n: 1.0 / len(selected) for n in selected}

    comp = sum(normed[n] * w[n] for n in selected)
    for n in selected:
        info[n]["weight"] = round(w[n], 4)
    return comp, info


# ============================ L5 硬过滤 ============================

def hard_filter_mask(panel, illiquid_pct=0.05):
    """L5：ST / 退市 / 次新上市 / 流动性。返回 tradeable 布尔 wide（True=可交易）。"""
    dates = panel.index.get_level_values(0).unique().sort_values()
    codes = panel.index.get_level_values("code").unique()
    wide_index = dates

    # ST（bars.db is_st 字段）
    st_wide = (panel["is_st"].fillna(0) > 0).unstack().reindex(index=wide_index, columns=codes).fillna(True)

    # 退市 / 上市（stock_basic）
    con = sqlite3.connect(f"file:{CACHE / 'stock_basic.db'}?mode=ro", uri=True)
    sb = pd.read_sql("SELECT code, name, ipo_date, out_date, status FROM stock_basic", con)
    con.close()
    # stock_basic.code 是「600000.SH」全码格式，先拆出 6 位数字再 zfill（否则 map 全落空）
    sb["code6"] = sb["code"].astype(str).str.split(".").str[0].str.zfill(6)
    code_map = {c.split(".")[0]: c for c in codes}
    sb["full_code"] = sb["code6"].map(code_map)
    sb = sb.dropna(subset=["full_code"])
    sb["ipo"] = pd.to_datetime(sb["ipo_date"], errors="coerce")
    sb["out"] = pd.to_datetime(sb["out_date"], errors="coerce")
    delist_codes = set(sb.loc[sb["name"].astype(str).str.contains("退"), "full_code"])
    # ST 兜底：bars.db is_st 字段可能陈旧（如 ST西王 is_st=0），用 stock_basic.name 当前名含 "ST" 再兜一层。
    # 注：name 是当前快照，对历史回测略保守（把"后来才戴帽"的股也剔了），但宁错杀不漏（避免 ST 混进持仓）。
    st_name_codes = set(sb.loc[sb["name"].astype(str).str.contains("ST"), "full_code"])
    exclude_codes = delist_codes | st_name_codes
    ipo_map = sb.set_index("full_code")["ipo"].to_dict()
    out_map = sb.set_index("full_code")["out"].to_dict()

    tradeable = pd.DataFrame(True, index=wide_index, columns=codes)
    for c in codes:
        if c in exclude_codes:
            tradeable[c] = False
        ipo = ipo_map.get(c)
        if pd.notna(ipo):
            tradeable[c] &= (tradeable.index >= ipo + pd.Timedelta(days=60))
        out = out_map.get(c)
        if pd.notna(out):
            tradeable[c] &= (tradeable.index <= out)
    tradeable &= ~st_wide

    # 流动性：20 日均成交额截面后 5% 剔除
    amt = panel["amount"].unstack().reindex(index=wide_index, columns=codes)
    adv = amt.rolling(20, min_periods=5).mean()
    adv_rank = adv.rank(axis=1, pct=True)
    tradeable &= (adv_rank > illiquid_pct).fillna(False)
    return tradeable


# ============================ L4 行业×市值中性 ============================

def load_industry_map():
    con = sqlite3.connect(f"file:{CACHE / 'stock_basic.db'}?mode=ro", uri=True)
    m = {r[0].split(".")[0]: r[1] for r in con.execute(
        "SELECT code, industry FROM stock_basic WHERE industry != '' AND industry IS NOT NULL").fetchall()}
    con.close()
    return m


def load_mv_wide(dates, codes):
    con = sqlite3.connect(f"file:{CACHE / 'hist_mv.db'}?mode=ro", uri=True)
    mv = pd.read_sql("SELECT month, code, circ_mv FROM hist_mv", con)
    con.close()
    mv["date"] = pd.to_datetime(mv["month"] + "-01") + pd.offsets.MonthEnd(0)
    m = mv.pivot_table(index="date", columns="code", values="circ_mv", aggfunc="last")
    m = m.reindex(dates).ffill()
    return m.reindex(columns=codes)


def neutralize(score_wide, ind_map, mv_wide):
    """L4：行业内 demean → 对 log(circ_mv) 正交化（NaN=已过滤股票，保持 NaN）。"""
    out = score_wide.copy()
    ind_cols = defaultdict(list)
    for code in out.columns:
        ind = ind_map.get(str(code).split(".")[0])
        if ind:
            ind_cols[ind].append(code)
    for ind, cols in ind_cols.items():
        if len(cols) > 1:
            out[cols] = out[cols].sub(out[cols].mean(axis=1), axis=0)
    lm = np.log(mv_wide.reindex(index=out.index, columns=out.columns))
    fz = out.sub(out.mean(axis=1), axis=0)
    lz = lm.sub(lm.mean(axis=1), axis=0)
    beta = (fz * lz).sum(axis=1) / ((lz ** 2).sum(axis=1) + 1e-12)
    return fz - lz.mul(beta, axis=0)


# ============================ L6 Regime 择时 ============================

def regime_position(close_wide, ma_window=200, bear_exposure=0.5):
    """L6：等权全市场指数 vs MA200。多头满仓 / 空头减半。返回逐日仓位乘数 Series。"""
    mkt = close_wide.mean(axis=1)
    ma = mkt.rolling(ma_window, min_periods=ma_window // 2).mean()
    pos = pd.Series(1.0, index=close_wide.index)
    pos[mkt < ma] = bear_exposure
    return pos


# ============================ 组合回测（T+1 + 权重 + 择时） ============================

def _pos_weights(returns_hist, picks, weighting):
    """L3：仓位权重。eq=等权；rp=逆波动率（60 日收益波动）。"""
    if weighting == "rp":
        vol = returns_hist[picks].rolling(60, min_periods=20).std().iloc[-1].fillna(
            returns_hist[picks].std().fillna(returns_hist[picks].std().median()))
        inv = 1.0 / (vol + 1e-9)
        return inv / inv.sum()
    return pd.Series(1.0 / len(picks), index=picks)


# 个股级止损配置（复用 risk/stop_rules.py 的 7 条规则，第15课/欧奈尔口径）
STOP_LOSS_CFG = {
    "stop_loss_pct": 0.07,           # 硬止损 7%
    "stop_loss_below_pivot": 0.08,   # 支撑止损（Top-N 无突破点，实际不触发）
    "time_stop_weeks": 3,            # 时间止损 3 周
    "time_stop_min_gain": 0.03,      # 3 周涨幅 < 3%
    "profit_take_low": 0.20,         # 止盈下沿 20%
    "profit_take_high": 0.25,        # 止盈上沿 25%
    "trailing_stop_ma": 50,          # 移动止损 50 日均线
    "high_drawdown_exit": 0.08,      # 高点回撤 8%
    "atr_stop_mult": 2.0,            # ATR 止损倍数
}


def _period_stop_loss(closes, opens, picks, buy_pos, nxt_pos, w, atr_wide, ma50_wide, sr):
    """个股级止损：逐日检查持仓，触发止损则次日转现金。返回该周期每日组合收益 Series。

    简化（诚实披露）：止损触发按当日收盘价卖出（T+0 近似，非 T+1 开盘）；止盈的"分批卖 50%"简化为全卖。
    """
    dates = closes.index[buy_pos: nxt_pos + 1]
    entry = opens.iloc[buy_pos].reindex(picks)          # T+1 开盘买入价
    held = [s for s in picks if pd.notna(entry.get(s)) and entry[s] > 0]
    if not held:
        return pd.Series(0.0, index=dates)
    entry = entry.reindex(held)
    peak = entry.copy()                                  # 持仓期最高收盘价
    # 原始权重固定（等权 1/N 或风险平价），止损卖出后现金留现金、不重新分配给剩余股
    wmap = {s: (w[s] if s in w.index else 1.0 / len(held)) for s in held}
    daily = pd.Series(0.0, index=dates)
    prev_close = None
    for k, d in enumerate(dates):
        cd = closes.loc[d]
        # 当日个股收益（首日 close/entry-1，其余 close/prev_close-1）
        r = {}
        for s in held:
            base = entry[s] if k == 0 else (
                prev_close.get(s) if (prev_close is not None and pd.notna(prev_close.get(s))) else entry[s])
            r[s] = (cd[s] / base - 1.0) if (pd.notna(cd.get(s)) and base and base > 0) else 0.0
        # 更新持仓期最高价
        for s in held:
            if pd.notna(cd.get(s)) and cd[s] > peak[s]:
                peak[s] = cd[s]
        # 当日组合收益 = 原始权重加权（止损股现金部分自然为 0，不再归一化）
        daily.loc[d] = sum(r[s] * wmap[s] for s in held)
        # 止损检查
        to_sell = []
        for s in held:
            if not pd.notna(cd.get(s)) or entry[s] <= 0:
                continue
            atr = atr_wide.loc[d, s] if (atr_wide is not None and s in atr_wide.columns
                                         and pd.notna(atr_wide.loc[d, s])) else None
            ma50 = ma50_wide.loc[d, s] if (ma50_wide is not None and s in ma50_wide.columns
                                           and pd.notna(ma50_wide.loc[d, s])) else None
            dec = sr.check(entry_price=entry[s], current_price=cd[s], atr=atr,
                           ma_50=ma50, peak_price=peak[s], hold_weeks=k / 5.0)
            if dec.should_sell:
                to_sell.append(s)
        for s in to_sell:
            held.remove(s)
            wmap.pop(s, None)
        prev_close = cd
        if not held:
            break
    return daily


def build_and_backtest(panel, selected, topn=DEFAULT_TOPN, rebalance=DEFAULT_REBALANCE,
                       start=DEFAULT_START, end=DEFAULT_END,
                       factor_weighting="eq", pos_weighting="eq",
                       neutral=True, regime_on=True, hard_filter_on=True, directions=None,
                       stop_loss=True):
    """六环节流水线 → 日收益序列 + 诊断。directions 冻结方向（前向/holdout 用）。stop_loss=个股级止损(7条规则)。"""
    dates = panel.index.get_level_values(0).unique().sort_values()
    codes = panel.index.get_level_values("code").unique()

    # L1 合成信号
    comp, factor_info = composite_signal(panel, selected, factor_weighting, directions=directions)
    comp = comp.sort_index()

    # L5 硬过滤
    if hard_filter_on:
        tradeable = hard_filter_mask(panel)
        comp = comp.where(tradeable.reindex(index=comp.index, columns=comp.columns))
    n_tradeable = int(comp.notna().sum(axis=1).mean())

    # L4 中性
    if neutral:
        ind_map = load_industry_map()
        mv_wide = load_mv_wide(dates, codes)
        comp = neutralize(comp, ind_map, mv_wide)

    # 回测窗切片
    win = (comp.index >= start) & (comp.index <= end)
    score = comp[win]
    closes = panel["close"].unstack().sort_index().reindex(score.index)
    opens = panel["open"].unstack().sort_index().reindex(score.index)
    highs = panel["high"].unstack().sort_index().reindex(score.index)

    # L6 Regime
    regime = regime_position(closes) if regime_on else pd.Series(1.0, index=closes.index)

    # 个股级止损所需的 ATR/MA50（用全面板算保证 warmup，回测窗索引访问）
    if stop_loss:
        atr_wide = (panel["high"].unstack().sort_index() - panel["low"].unstack().sort_index()).rolling(20, min_periods=5).mean()
        ma50_wide = panel["close"].unstack().sort_index().rolling(50, min_periods=20).mean()
    else:
        atr_wide = ma50_wide = None

    # 调仓日
    if isinstance(rebalance, int):
        positions = list(range(60, len(score.index), rebalance))
        if positions and positions[-1] < len(score.index) - 1:
            positions.append(len(score.index) - 1)
    else:
        qm = pd.Series(score.index).dt.to_period("Q").astype(str)
        positions = [score.index.get_loc(d) for d in
                     pd.Series(score.index).groupby(qm.values).max().tolist()]

    # 三级回撤控制（主系统 config/params.yaml risk.drawdown_levels，第15课《风险控制与资金管理》）
    #   - 阈值 5%/10%/15% + 熔断减至 30% = 主系统明确
    #   - 警戒×0.7 / 控制×0.5 = 对主系统「降低新开仓规模 / 停止新开仓·开始减仓」的定量映射（主系统只给定性，未给具体数）
    DD_WARN, DD_STOP, DD_CIRCUIT = 0.05, 0.10, 0.15
    CIRCUIT_POS = 0.30
    COOLDOWN_DAYS = 5    # 主系统冷静期 5 天

    ret = pd.Series(0.0, index=score.index)
    daily_ret = closes.pct_change()
    prev_picks = None
    n_rebal = 0
    nav = 1.0            # 组合累计净值（含择时+回撤降仓，不含成本）
    peak = 1.0           # 历史最高净值
    circuit_left = 0     # 熔断冷静期剩余天数
    dd_log = []          # 回撤仓位切换记录
    for i, pos in enumerate(positions[:-1]):
        nxt_pos = positions[i + 1]
        sc = score.iloc[pos].dropna()
        if len(sc) < topn:
            continue
        picks = sc.nlargest(topn).index.tolist()
        buy_pos = pos + 1
        if buy_pos > nxt_pos:
            continue
        bo = opens.iloc[buy_pos].reindex(picks)
        bh = highs.iloc[buy_pos].reindex(picks)
        buyable = bo[(bo < bh - 1e-9)].index.tolist()
        if len(buyable) < 1:
            continue
        w = _pos_weights(daily_ret.iloc[:buy_pos], buyable, pos_weighting)
        # 止损与择时联动：只在择时空头（熊市）启用个股止损，多头（牛市）不误杀（压力测试发现的 regime 依赖）
        bear_now = regime_on and float(regime.iloc[pos]) < 0.999
        if stop_loss and bear_now:
            from risk.stop_rules import StopRules
            sr = StopRules(STOP_LOSS_CFG)
            port = _period_stop_loss(closes, opens, buyable, buy_pos, nxt_pos, w, atr_wide, ma50_wide, sr)
        else:
            seg = closes[buyable].iloc[buy_pos: nxt_pos + 1].pct_change().fillna(0)
            seg.iloc[0] = (closes.iloc[buy_pos][buyable] / opens.iloc[buy_pos][buyable] - 1).values
            port = (seg * w.reindex(seg.columns).fillna(0).values).sum(axis=1)
        port = port * regime.loc[port.index]   # L6 择时仓位
        # ★三级回撤控制（逐日，对齐主系统 check_drawdown 每日检查）：
        #   当日仓位乘数由「截至昨日净值」的回撤决定 → 无未来函数
        scaled = pd.Series(0.0, index=port.index)
        prev_mult = None
        for j, d in enumerate(port.index):
            dd = nav / peak - 1.0
            if circuit_left > 0:
                mult = CIRCUIT_POS
                circuit_left -= 1
            elif dd <= -DD_CIRCUIT:
                mult = CIRCUIT_POS
                circuit_left = COOLDOWN_DAYS
            elif dd <= -DD_STOP:
                mult = 0.5
            elif dd <= -DD_WARN:
                mult = 0.7
            else:
                mult = 1.0
            if mult != prev_mult:
                dd_log.append({"date": str(d)[:10], "dd": round(dd, 4), "仓位": mult})
                prev_mult = mult
            r = float(port.iloc[j]) * mult
            scaled.iloc[j] = r
            nav = nav * (1.0 + r)
            peak = max(peak, nav)
        ret.loc[port.index] = scaled
        prev_picks = set(picks)
        n_rebal += 1

    # 成本（按真实换手摊入）
    turnover = _turnover_from(score, topn, positions)
    cost_total = COST * 2 * turnover * max(n_rebal, 1)
    net = ret - cost_total / max(len(ret), 1)

    bench = closes.pct_change().fillna(0).mean(axis=1).loc[net.index]
    metrics = compute_metrics(net)
    bench_metrics = compute_metrics(bench)
    excess_annual = metrics["annual_return"] - bench_metrics["annual_return"]

    return {
        "net_ret": net, "bench": bench, "metrics": metrics, "bench_metrics": bench_metrics,
        "excess_annual": excess_annual, "turnover": turnover, "n_rebal": n_rebal,
        "n_tradeable": n_tradeable, "factor_info": factor_info,
        "regime_mean": float(regime.mean()), "score": score, "dd_log": dd_log,
    }


def _turnover_from(score, topn, positions):
    prev = None
    ts = []
    for pos in positions:
        if pos >= len(score.index):
            continue
        sc = score.iloc[pos].dropna()
        if len(sc) < topn:
            continue
        picks = set(sc.nlargest(topn).index)
        if prev is not None:
            ts.append(1.0 - len(picks & prev) / topn)
        prev = picks
    return float(np.mean(ts)) if ts else 1.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--factors", default="amihud,ma200_trend,f_score,mom_120,bp_value,sue,turn_mid_prox",
                    help="逗号分隔的选中因子（缺省=八因子候选）")
    ap.add_argument("--topn", type=int, default=DEFAULT_TOPN)
    ap.add_argument("--rebalance", default=DEFAULT_REBALANCE)
    ap.add_argument("--start", default=DEFAULT_START)
    ap.add_argument("--end", default=DEFAULT_END)
    ap.add_argument("--factor-weighting", default="eq", choices=["eq", "rp"])
    ap.add_argument("--pos-weighting", default="eq", choices=["eq", "rp"])
    ap.add_argument("--no-neutral", action="store_true")
    ap.add_argument("--no-regime", action="store_true")
    ap.add_argument("--no-filter", action="store_true")
    ap.add_argument("--out", default=str(BASE / "logs" / "portfolio_builder.json"))
    args = ap.parse_args()

    selected = [f.strip() for f in args.factors.split(",") if f.strip()]
    unknown = [f for f in selected if f not in FACTOR_FNS]
    if unknown:
        print(f"未知因子 {unknown}，可用：{list(FACTOR_FNS)}")
        sys.exit(2)

    print("加载面板（bars.db 全量 2019+）...", flush=True)
    panel = load_panel("data/cache/bars.db", start=PANEL_LOAD_START)
    print(f"面板 {panel.shape}", flush=True)

    print(f"组合构建：{len(selected)} 因子 / Top{args.topn} / 调仓{args.rebalance} / "
          f"因子权重{args.factor_weighting} / 仓位{args.pos_weighting} / "
          f"中性{not args.no_neutral} / 择时{not args.no_regime} / 过滤{not args.no_filter}", flush=True)

    r = build_and_backtest(
        panel, selected, topn=args.topn, rebalance=args.rebalance,
        start=args.start, end=args.end,
        factor_weighting=args.factor_weighting, pos_weighting=args.pos_weighting,
        neutral=not args.no_neutral, regime_on=not args.no_regime,
        hard_filter_on=not args.no_filter)

    m, bm = r["metrics"], r["bench_metrics"]
    print("\n=== 组合构建结果（6 环节）===", flush=True)
    print(f"选中因子: {selected}", flush=True)
    for n, info in r["factor_info"].items():
        print(f"  {n:<14} 族={info['family']:<4} 方向{info['direction']:+d} 权重={info['weight']}", flush=True)
    print(f"年化 {m['annual_return']:+.2%} | 基准 {bm['annual_return']:+.2%} | 净超额 {r['excess_annual']:+.2%}", flush=True)
    print(f"夏普 {m['sharpe']:.2f} | 回撤 {m['max_drawdown']:.2%} | 样本 {m['n_days']} 天", flush=True)
    print(f"换手 {r['turnover']:.2%} | 调仓 {r['n_rebal']} 次 | 可交易股均 {r['n_tradeable']} 只 | 择时均仓 {r['regime_mean']:.2f}", flush=True)

    yearly = {}
    for y, g in r["net_ret"].groupby(r["net_ret"].index.year):
        b = r["bench"].loc[g.index]
        yearly[str(y)] = {"excess": round(float((1 + g).prod() - (1 + b).prod()), 4)}
    print("分年度净超额:", flush=True)
    for y, v in yearly.items():
        print(f"  {y}: {v['excess']:+.2%}", flush=True)

    out = {
        "validated_at": str(pd.Timestamp.now())[:19],
        "factors": selected,
        "factor_info": r["factor_info"],
        "params": {"topn": args.topn, "rebalance": str(args.rebalance), "start": args.start, "end": args.end,
                   "factor_weighting": args.factor_weighting, "pos_weighting": args.pos_weighting,
                   "neutral": not args.no_neutral, "regime": not args.no_regime, "filter": not args.no_filter},
        "metrics": {k: round(v, 6) if isinstance(v, (int, float)) else v for k, v in m.items()},
        "bench_annual": round(bm["annual_return"], 6),
        "excess_annual": round(r["excess_annual"], 4),
        "turnover": round(r["turnover"], 4),
        "n_rebal": r["n_rebal"],
        "n_tradeable": r["n_tradeable"],
        "regime_mean": round(r["regime_mean"], 4),
        "yearly_excess": yearly,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已存：{args.out}")


if __name__ == "__main__":
    main()

