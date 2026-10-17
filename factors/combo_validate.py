# -*- coding: utf-8 -*-
"""factors/combo_validate.py — 第二层：组合层 T+1 裁决（★唯一裁决） + 第三层容量审计

定位（factor-mining-workflow P6 + backtest-acceptance）：
  第一层（import_qf_pool.py）只给「截面 ICIR 门票」；因子能不能交易，只信这一层。
  本层把一个因子接进组合回测引擎（T+1 open 买入 + 一字板过滤 + 成本），
  用「净超额 + 夏普 + 分年度」裁决，并给出容量诊断（换手 + 流动性分位）。

对齐铁律：
  - 铁律① T+1 无前视：复用 backtest/bt_runner.py 的 _period_backtest（T+1 open + 一字板过滤）
  - 铁律⑩ 验收五步 + T+1 组合层：本层 = 组合层裁决（唯一裁决）
  - 结论分级（backtest-acceptance）：✅有效(年化>0 且 夏普>0.5) / 🟡观察(年化>0 夏普≤0.5) / ❌无效(年化≤0)

诚实披露（开源版简化点，报告里必须写）：
  开源仓库的 _period_backtest =「Top N 等权 + 全换仓成本近似」，缺私有主系统 combo_backtest
  验收 v1 的「单股≤50% 上限 / 现金兜底 / qfq 跳变修正」——本层是简化组合层，不是验收 v1 全实现。

用法：
  python factors/combo_validate.py --pool <pool.json> --name r4_f1
      [--topn 20 --rebalance 40 --start 2020-06-01 --end 2025-12-31]
"""
import argparse
import json
import sys
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

from factors.import_qf_pool import load_panel, _run_factor, cross_sectional_ics, forward_returns
from backtest.bt_runner import _period_backtest
from backtest.bt_report import archive, compute_metrics

# 成本模型（backtest-acceptance 默认）：佣金万2.6 + 卖出印花税0.05% + 滑点0.1%
COST = 0.00026 + 0.0005 + 0.001

DEFAULT_TOPN = 20
DEFAULT_REBALANCE = 40        # turn_low 已实证口径：40 交易日调仓
# ★2026-10-17 配置驱动：窗口收敛到 config/backtest_window.yaml
#   旧注释「hist_mv / turn 覆盖边界（铁律③）」所述前提已失效：
#   hist_mv 现 319 个月（2000-04 起）、turn 全历史 0% 缺失（见 CORE_ISSUE_TRACKER 9.19）
try:
    from factors.window_config import get_window as _get_window
    _W = _get_window()
    DEFAULT_START = _W["start"]
    DEFAULT_END = _W["end"]
except Exception:
    DEFAULT_START = "2010-01-01"
    DEFAULT_END = "2025-12-31"
VERDICT_SHARPE = 0.5          # 有效/观察 分界（backtest-acceptance）


def _build_score(sig: pd.Series, direction: int) -> pd.DataFrame:
    """因子信号 → 组合 score 矩阵（行=交易日，列=股票，逐日截面 rank 0-1，越大越好）。"""
    s = sig * direction
    return s.unstack().rank(axis=1, pct=True)


def _rebalance_dates(index, rebalance):
    """与 _period_backtest 同口径的调仓日列表。"""
    if isinstance(rebalance, int):
        positions = list(range(60, len(index), rebalance))
        return [index[p] for p in positions]
    ym = index.astype(str).str[:7]
    if rebalance == "Q":
        qm = pd.Series(index).dt.to_period("Q").astype(str)
        period_ends = pd.Series(index).groupby(qm.values).max().tolist()
    else:
        period_ends = pd.Series(index).groupby(ym).max().tolist()
    return period_ends


def _turnover(score: pd.DataFrame, topn: int, dates) -> float:
    """真实换手率：相邻调仓期 Top N 集合的重叠率补集（1 - 重叠/topn）的均值。"""
    prev = None
    ts = []
    for d in dates:
        if d not in score.index:
            continue
        sc = score.loc[d].dropna()
        if len(sc) < topn:
            continue
        picks = set(sc.nlargest(topn).index)
        if prev is not None:
            ts.append(1.0 - len(picks & prev) / topn)
        prev = picks
    return float(np.mean(ts)) if ts else 1.0


def _rolling_icir(ics: pd.Series, window: int) -> float:
    """滚动窗口 ICIR（最新值）：rolling mean/std 的比，用于 health/manifest 的 icir20/60/120。"""
    if len(ics) < max(window // 2, 10):
        return None
    r = ics.rolling(window, min_periods=window // 2)
    m, s = r.mean(), r.std()
    v = (m / s).dropna()
    return round(float(v.iloc[-1]), 4) if len(v) else None


def _adv_pct(score: pd.DataFrame, panel: pd.DataFrame, topn: int, dates) -> float:
    """多头篮子的 20 日均成交额（ADV）在全市场股票中的分位（0-1，越高流动性越好）。
    冲击成本代理：篮子 ADV 分位越低 → 容量越小（完整冲击预算需资金规模假设，见报告 note）。"""
    amount = panel["amount"].unstack()
    adv = amount.rolling(20, min_periods=20).mean()
    vals = []
    for d in dates:
        if d not in score.index or d not in adv.index:
            continue
        sc = score.loc[d].dropna()
        picks = sc.nlargest(topn).index
        row = adv.loc[d].reindex(picks).dropna()
        if len(row):
            vals.append(float(row.median()))
    if not vals:
        return None
    basket = float(np.median(vals))
    last = adv.dropna(how="all").iloc[-1].dropna()
    return float((last < basket).mean()) if len(last) else None


def combo_validate(name, code, panel, topn=DEFAULT_TOPN, rebalance=DEFAULT_REBALANCE,
                   start=DEFAULT_START, end=DEFAULT_END, direction=None):
    """对一个因子（exec code）跑组合层 T+1 裁决。薄封装 → combo_validate_sig。"""
    sig = _run_factor(code, panel)
    return combo_validate_sig(name, sig, panel, topn=topn, rebalance=rebalance,
                              start=start, end=end, direction=direction)


def combo_validate_sig(name, sig, panel, topn=DEFAULT_TOPN, rebalance=DEFAULT_REBALANCE,
                       start=DEFAULT_START, end=DEFAULT_END, direction=None):
    """对预计算的原始信号 (date, code) Series 跑组合层 T+1 裁决。
    返回 {verdict, metrics, excess, yearly, capacity, archive, health, score_latest}。"""
    # 1) 方向（默认按截面 RankIC 符号自动判向）+ 健康指标（滚动 ICIR，方向化后正=好）
    fwd = forward_returns(panel)
    ics_raw = cross_sectional_ics(sig, fwd)
    if direction is None:
        direction = 1 if ics_raw.mean() >= 0 else -1
    ics = ics_raw * direction
    health = {
        "icir_20": _rolling_icir(ics, 20),
        "icir_60": _rolling_icir(ics, 60),
        "icir_120": _rolling_icir(ics, 120),
    }

    # 2) 切片到回测窗口（因子在 2019 全量上算好 warmup，再截 [start, end]）
    win = ((panel.index.get_level_values(0) >= start)
           & (panel.index.get_level_values(0) <= end))
    p = panel[win]
    closes = p["close"].unstack()
    opens = p["open"].unstack()
    highs = p["high"].unstack()
    score = _build_score(sig[win], direction)
    # 对齐索引（unstack 后按日期，去空行）
    closes, opens, highs = closes.sort_index(), opens.sort_index(), highs.sort_index()
    score = score.sort_index().reindex(closes.index)

    # 3) 组合层 T+1 回测（复用引擎，含 T+1 open + 一字板过滤）
    ret = _period_backtest(closes, opens, highs, score, topn, rebalance=rebalance)

    # 4) 成本（按真实换手摊入，替代 run_backtest 的全换仓近似）
    rdates = _rebalance_dates(score.index, rebalance)
    turnover = _turnover(score, topn, rdates)
    n_periods = len(rdates) or 1
    cost_total = COST * 2 * turnover * n_periods
    net_ret = ret - cost_total / max(len(ret), 1)

    # 5) 指标 + 基准 + 超额
    bench = closes.pct_change().fillna(0).mean(axis=1).loc[net_ret.index]
    metrics = compute_metrics(net_ret)
    bench_metrics = compute_metrics(bench)
    excess_annual = metrics["annual_return"] - bench_metrics["annual_return"]

    # 6) 分年度超额
    yearly = {}
    for y, g in net_ret.groupby(net_ret.index.year):
        b = bench.loc[g.index]
        gy = (1 + g).prod() - 1
        by = (1 + b).prod() - 1
        yearly[str(y)] = {"excess": round(float(gy - by), 4)}

    # 7) 裁决（backtest-acceptance 三级）
    ann, sharpe = metrics["annual_return"], metrics["sharpe"]
    if ann > 0 and sharpe > VERDICT_SHARPE and excess_annual > 0:
        verdict = "有效"
    elif ann > 0:
        verdict = "观察"
    else:
        verdict = "无效"

    # 8) 容量诊断
    adv_pct = _adv_pct(score, p, topn, rdates)
    capacity = {"turnover": round(turnover, 4), "adv_pct": round(adv_pct, 4) if adv_pct is not None else None}

    # 9) 归档（category=因子，前端 /backtest 自动可见）
    slug = f"{name}_t{topn}"
    params = {"name": f"{name} 组合层T+1", "strategy": "combo_validate",
              "topn": topn, "rebalance": rebalance, "start": start, "end": end,
              "direction": direction,
              "note": "简化组合层：TopN等权+全换仓成本近似，缺单股≤50%/现金兜底/qfq跳变修正"}
    arch = archive(net_ret, params=params, benchmark=bench, name=slug,
                   category="因子", factors=[name], verdict=verdict, save_html=False)

    return {
        "name": name, "direction": direction, "verdict": verdict,
        "metrics": metrics, "bench_metrics": bench_metrics,
        "excess_annual": round(excess_annual, 4),
        "yearly_excess": yearly, "capacity": capacity,
        "health": health, "score_latest": score.iloc[-1],
        "archive": arch.get("json_path"),
    }


def main():
    ap = argparse.ArgumentParser(description="组合层 T+1 裁决（第二层）")
    ap.add_argument("--pool", required=True, help="qf-llm pool.json")
    ap.add_argument("--name", required=True, help="要裁决的因子名（如 r4_f1）")
    ap.add_argument("--topn", type=int, default=DEFAULT_TOPN)
    ap.add_argument("--rebalance", default=DEFAULT_REBALANCE,
                    help="调仓周期：整数=交易日数 / M=月频 / Q=季度")
    ap.add_argument("--start", default=DEFAULT_START)
    ap.add_argument("--end", default=DEFAULT_END)
    ap.add_argument("--panel-db", default="data/cache/bars.db")
    ap.add_argument("--direction", type=int, default=None, help="1/-1；缺省按 RankIC 符号自动判向")
    ap.add_argument("--write-pool", action="store_true", help="裁决为「有效」时写入三件套到 data/factorpool/output/")
    ap.add_argument("--category", default="量价", help="manifest category（走 category_to_family 归族）")
    ap.add_argument("--name-cn", default=None, help="manifest 中文名（缺省=因子名）")
    ap.add_argument("--data-date", default=None, help="三件套数据日（缺省=面板最新交易日）")
    args = ap.parse_args()

    if isinstance(args.rebalance, str) and args.rebalance.isdigit():
        args.rebalance = int(args.rebalance)

    with open(args.pool, encoding="utf-8") as f:
        pool = json.load(f)
    rec = next((x for x in pool if x.get("name") == args.name), None)
    if rec is None or not rec.get("code"):
        print(f"❌ 未找到因子 {args.name} 或其缺 code 字段")
        sys.exit(2)

    print(f"加载面板（bars.db 全量，供因子 warmup）...", flush=True)
    panel = load_panel(args.panel_db, start="2019-01-01")
    print(f"面板 {panel.shape}，裁决因子 {args.name}（top{args.topn} / 调仓{args.rebalance} / {args.start}~{args.end}）", flush=True)

    r = combo_validate(args.name, rec["code"], panel, topn=args.topn,
                       rebalance=args.rebalance, start=args.start, end=args.end,
                       direction=args.direction)

    m = r["metrics"]
    print("\n=== 组合层 T+1 裁决结果 ===")
    print(f"因子: {r['name']}  方向: {r['direction']:+d}  结论: {r['verdict']}")
    print(f"年化 {m['annual_return']:+.2%} | 基准 {r['bench_metrics']['annual_return']:+.2%} "
          f"| 净超额 {r['excess_annual']:+.2%}")
    print(f"夏普 {m['sharpe']:.2f} | 回撤 {m['max_drawdown']:.2%} | 样本 {m['n_days']} 天")
    print(f"容量: 换手 {r['capacity']['turnover']:.2%} | 篮子ADV分位 {r['capacity']['adv_pct']}")
    print(f"健康: icir20={r['health']['icir_20']} icir60={r['health']['icir_60']} icir120={r['health']['icir_120']}")
    print("分年度净超额:")
    for y, v in r["yearly_excess"].items():
        print(f"  {y}: {v['excess']:+.2%}")
    print(f"归档: {r['archive']}")

    # 第三层：三件套登记（仅裁决「有效」才入池，铁律⑩：组合层是唯一裁决）
    if args.write_pool:
        if r["verdict"] != "有效":
            print(f"\n⚠️ 结论「{r['verdict']}」≠ 有效，不写三件套（宁缺毋滥）")
            return
        from factors.factor_pool_writer import write_pool
        data_date = args.data_date or str(panel.index.get_level_values(0).max())[:10]
        factors = [{
            "code": args.name, "name_cn": args.name_cn or args.name,
            "category": args.category, "direction": r["direction"],
            "status": "有效", "usage": "qf-llm 组合层验证通过",
            "icir_20": r["health"]["icir_20"], "icir_60": r["health"]["icir_60"],
            "icir_120": r["health"]["icir_120"], "rank": r["score_latest"],
        }]
        paths = write_pool(factors, data_date=data_date)
        print(f"\n=== 三件套已写入 data/factorpool/output/ ===")
        for k, v in paths.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
