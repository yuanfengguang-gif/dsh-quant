# -*- coding: utf-8 -*-
"""factors/import_qf_pool.py — QF-LLM 因子池导入 + 验证器（v2）

定位（生产者/消费者分工中的「消费者」侧，属于 deepseek-harness-quant）：
  读 qf-llm 的 pool.json（因子代码 + 元数据）→ 用本系统 bars.db 面板重算信号 →
  计算验证指标（RankIC/ICIR/覆盖率/分年度/holdout/逐日截面Spearman去重/T+1严格标签/容量代理）
  → 输出验证报告。

⚠️ 验证分层（重要，与 factor-mining-workflow / backtest-acceptance 对齐）：
  - 本脚本（v2）=「海选 + 分年度 + holdout + 去重 + T+1 label + 容量代理」验证：
    截面 ICIR 只是门票，不是实盘有效性。
  - 「组合层 T+1 回测」= 唯一裁决（因子能不能交易），成本/滑点/完整冲击容量在此层，
    将在 v3 接入 backtest 引擎。
  - 期望值校准：海选 → 组合层通过率约 8%，一轮 0 通过是常态（非流程错误）。

相对 qf-llm（生产者）补齐/纠正的 5 项（消费端补齐，不改生产者）：
  ① 去重口径：长表 Pearson → 逐日截面 Spearman（cross_corr）
  ② OOS 样本外：holdout_icir（HOLDOUT_START 之后不参与挖掘的留出段）
  ③ 分年度一致性：yearly_icir + 方向同向占比闸门
  ④ T+1 执行口径：标签改为 open-to-open（t+1 开盘买 → t+2 开盘卖）+ 一字板过滤
  ⑤ 容量代理：涨停暴露 + 流动性分位（诊断字段；完整冲击容量在组合层）

用法：
  python factors/import_qf_pool.py --pool <pool.json> --out logs/qf_pool_validation.json
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

# Windows 控制台 GBK 编码下打印 ✅/❌ 等 emoji 会 UnicodeEncodeError 崩溃 → 强制 UTF-8 + 替换
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ---- 海选门槛（对齐 factor-mining-workflow P4 + qf-llm scoring.py）----
MIN_ICIR = 0.3            # |ICIR| 下限（截面排序能力 + 稳定性）
MIN_COVERAGE = 0.3        # 覆盖率下限
MAX_POOL_CORR = 0.5       # 与池内因子最大截面相关（超过=同构淘汰）
HOLDOUT_START = "2025-01-01"   # 样本外起点（不参与挖掘的留出段）
YEAR_AGREE_RATIO = 0.75   # 分年度 ICIR 与总方向同向占比下限

# ---- 防守类因子分流规则（2026-10-13 实测校准）----
# turn_low 实测：日频 icir120=0.12（远低于 0.3）但组合层净超额 +3.03%/夏普 1.15 → 判「有效」。
# 结论：防守类（低换手/低波）因子的 alpha 在组合层、不在日频截面 IC，|ICIR|≥0.3 门槛对其偏严。
# 规则：防守类因子放宽第一层 icir 门槛（0.1），不强求 0.3，交给第二层组合裁决定生死。
DEFENSIVE_KEYWORDS = ("turn_low", "lowvol", "low_vol", "turn_20d", "turn_mid", "defensive", "amihud", "low_turn")
DEFENSIVE_MIN_ICIR = 0.1  # 防守类放宽门槛（只做粗筛，最终由组合层裁决）


def load_panel(db: str = "data/cache/bars.db", start: str = "2019-01-01") -> pd.DataFrame:
    """从 bars.db 读面板（MultiIndex date,code），与 qf-llm export_panel 同口径。"""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    df = pd.read_sql(
        "SELECT date, code, open, high, low, close, volume, amount, turn, pct_chg, is_st "
        "FROM daily_bar WHERE adjust='qfq' AND date>=? "
        "AND code GLOB '[0-9][0-9][0-9][0-9][0-9][0-9].*'",
        con, params=(start,),
    )
    con.close()
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["date", "code"]).set_index(["date", "code"])


def load_panel_extended(db: str = "data/cache/bars.db", start: str = "2019-01-01") -> pd.DataFrame:
    """bars.db + finance.db(roe/eps/sq_net_yoy/sq_rev_yoy, 60日披露延迟) + hist_mv.db(circ_mv) → 14 列面板。
    与 qf-llm 的 panel_v2.parquet 同口径，用于验证 qf-llm 挖出的基本面类因子（用 circ_mv/roe 等列）。"""
    panel = load_panel(db, start)
    dates = panel.index.get_level_values(0).unique().sort_values()
    code_map = {c.split(".")[0]: c for c in panel.index.get_level_values("code").unique()}
    cache = Path(db).parent

    fin_db = cache / "finance.db"
    if fin_db.exists():
        con = sqlite3.connect(f"file:{fin_db}?mode=ro", uri=True)
        fin = pd.read_sql("SELECT code, period, roe, eps, sq_net_yoy, sq_rev_yoy FROM finance_report", con)
        con.close()
        fin["code"] = fin["code"].astype(str).str.zfill(6).map(code_map)
        fin = fin.dropna(subset=["code"])
        fin["period"] = pd.to_datetime(fin["period"])
        fin["eff_date"] = fin["period"] + pd.Timedelta(days=60)
        for f in ["roe", "eps", "sq_net_yoy", "sq_rev_yoy"]:
            m = fin.pivot_table(index="eff_date", columns="code", values=f, aggfunc="last")
            m = m.reindex(dates).ffill()
            panel[f] = m.stack().reindex(panel.index)

    mv_db = cache / "hist_mv.db"
    if mv_db.exists():
        con = sqlite3.connect(f"file:{mv_db}?mode=ro", uri=True)
        mv = pd.read_sql("SELECT month, code, circ_mv FROM hist_mv", con)
        con.close()
        mv["date"] = pd.to_datetime(mv["month"] + "-01") + pd.offsets.MonthEnd(0)
        m = mv.pivot_table(index="date", columns="code", values="circ_mv", aggfunc="last")
        m = m.reindex(dates).ffill()
        panel["circ_mv"] = m.stack().reindex(panel.index)
    return panel


def forward_returns(panel: pd.DataFrame) -> pd.Series:
    """T+1 严格口径（对齐 backtest-acceptance 铁律）：
    t 日收盘出信号 → t+1 日开盘买入 → t+2 日开盘卖出（open-to-open），
    并剔除 t+1 日一字板涨停（high==low 且 pct_chg>0，开盘即封死买不进）的样本。
    避免 qf-llm 占位口径（close[t+1]/close[t]）的收盘价前视问题。"""
    op = panel["open"]
    fwd = op.groupby(level=1, sort=False).shift(-2) / op.groupby(level=1, sort=False).shift(-1) - 1.0
    # t+1 日一字板（全天无波动且上涨，买不进）→ 该样本标签置 NaN
    oneline = ((panel["high"] == panel["low"]) & (panel["pct_chg"] > 0)).astype(bool)
    oneline_next = oneline.groupby(level=1, sort=False).shift(-1).fillna(False).astype(bool)
    return fwd.where(~oneline_next)


def cross_sectional_ics(factor: pd.Series, fwd: pd.Series) -> pd.Series:
    """逐日截面 RankIC（rank 后 Pearson = Spearman），向量化（避免逐日循环）。"""
    df = pd.DataFrame({"f": factor, "r": fwd}).dropna()
    if df.empty:
        return pd.Series(dtype=float)
    df = df[~df.index.duplicated(keep="last")]
    fw, rw = df["f"].unstack(), df["r"].unstack()
    fr, rr = fw.rank(axis=1), rw.rank(axis=1)
    mask = fw.notna() & rw.notna()
    fr, rr = fr.where(mask), rr.where(mask)
    fz = fr.sub(fr.mean(axis=1), axis=0)
    rz = rr.sub(rr.mean(axis=1), axis=0)
    cov = fz.mul(rz).sum(axis=1)
    ic = cov / (fz.pow(2).sum(axis=1) * rz.pow(2).sum(axis=1)).pow(0.5)
    return ic.replace([np.inf, -np.inf], np.nan).dropna()


def cross_corr(a: pd.Series, b: pd.Series) -> float:
    """逐日截面 Spearman（rank 后 Pearson）相关取均值——Barra 风格去重口径。
    只测「截面上对股票排序是否相似」，不被时间趋势污染；替换原长表 Pearson。"""
    df = pd.DataFrame({"a": a, "b": b}).dropna()
    if df.empty:
        return 0.0
    df = df[~df.index.duplicated(keep="last")]
    aw, bw = df["a"].unstack(), df["b"].unstack()
    ar, br = aw.rank(axis=1), bw.rank(axis=1)
    mask = aw.notna() & bw.notna()
    ar, br = ar.where(mask), br.where(mask)
    az = ar.sub(ar.mean(axis=1), axis=0)
    bz = br.sub(br.mean(axis=1), axis=0)
    cov = az.mul(bz).sum(axis=1)
    corr = cov / (az.pow(2).sum(axis=1) * bz.pow(2).sum(axis=1)).pow(0.5)
    corr = corr.replace([np.inf, -np.inf], np.nan).dropna()
    return float(corr.mean()) if len(corr) >= 30 else 0.0


def capacity_proxy(sig: pd.Series, panel: pd.DataFrame) -> dict:
    """容量/可交易性代理（海选层粗略口径；完整冲击成本在组合层回测）。
    - limup_exposure: 多头 top10% 中「信号日已涨停(pct_chg>=0.095)」占比 → 越高越难成交
    - med_amount_pct: 多头篮子的日均成交额在全市场股票中的分位 → 越低容量越小
    仅作为诊断字段上报，不设硬闸门（避免用粗略代理误杀）。"""
    df = pd.DataFrame({"s": sig, "pct": panel["pct_chg"], "amt": panel["amount"]}).dropna()
    if df.empty:
        return {"limup_exposure": None, "med_amount_pct": None}
    # 多头 = 逐日截面 signal top10%（向量化 rank，避免 groupby-apply）
    top = df[df.groupby(level=0)["s"].rank(pct=True) >= 0.9]
    limup_exposure = float((top["pct"] >= 0.095).mean())
    top_amt = top.groupby(level=1)["amt"].mean()
    all_amt = df.groupby(level=1)["amt"].mean()
    basket_amt = float(top_amt.mean())
    med_amount_pct = float((all_amt < basket_amt).mean())
    return {"limup_exposure": round(limup_exposure, 4), "med_amount_pct": round(med_amount_pct, 4)}


def _run_factor(code: str, panel: pd.DataFrame):
    """exec 因子代码并返回 factor(panel) 的 Series（可能抛异常）。

    命名空间与 qf-llm sandbox 对齐：注入 np/pd/numpy/pandas（因子代码常用 np.xxx）。
    """
    ns = {"np": np, "pd": pd, "numpy": np, "pandas": pd}
    exec(code, ns)
    fn = ns.get("factor")
    if fn is None:
        raise ValueError("无 factor 函数")
    sig = fn(panel)
    if not isinstance(sig, pd.Series):
        raise TypeError("factor 未返回 Series")
    return sig.reindex(panel.index)


def validate_one(name, code, panel, fwd, pooled_signals):
    """执行一个因子代码，计算海选 + 分年度验证指标。"""
    try:
        sig = _run_factor(code, panel)
    except Exception as e:
        return {"name": name, "error": str(e)[:200]}
    ics = cross_sectional_ics(sig, fwd)
    if len(ics) < 30:
        return {"name": name, "error": f"有效 IC 样本 {len(ics)} < 30"}

    ic = float(ics.mean())
    ir = float(ic / ics.std()) if ics.std() > 1e-12 else 0.0
    cov = float(sig.notna().mean())
    direction = 1 if ic >= 0 else -1

    # 分年度 ICIR
    yearly = {str(y): round(float(g.mean() / (g.std() + 1e-9)), 3)
              for y, g in ics.groupby(ics.index.year)}
    agree = sum(1 for v in yearly.values() if v * direction > 0)
    n_year = len(yearly)
    # holdout 样本外 ICIR
    ho = ics[ics.index >= HOLDOUT_START]
    ho_icir = float(ho.mean() / (ho.std() + 1e-9)) if len(ho) >= 10 and ho.std() > 1e-12 else None

    # 去重（与已通过因子）
    max_corr = max((abs(cross_corr(sig, ps)) for ps in pooled_signals), default=0.0)

    # 容量/可交易性代理（诊断字段，不设硬闸门）
    cap = capacity_proxy(sig if direction == 1 else -sig, panel)

    # 防守类因子分流：放宽第一层 icir 门槛（alpha 在组合层，不在日频 IC）
    is_defensive = any(k in (name or "").lower() for k in DEFENSIVE_KEYWORDS)
    min_icir = DEFENSIVE_MIN_ICIR if is_defensive else MIN_ICIR

    pass_icir = abs(ir) >= min_icir
    pass_cov = cov >= MIN_COVERAGE
    pass_year = (agree / n_year >= YEAR_AGREE_RATIO) if n_year else False
    pass_corr = max_corr <= MAX_POOL_CORR
    pass_gate = bool(pass_icir and pass_cov and pass_year and pass_corr)

    return {
        "name": name, "rank_ic": round(ic, 5), "ic_ir": round(ir, 3),
        "direction": direction, "coverage": round(cov, 4),
        "defensive": is_defensive, "min_icir_used": min_icir,
        "yearly_icir": yearly, "holdout_icir": ho_icir,
        "max_corr": round(max_corr, 3),
        "limup_exposure": cap.get("limup_exposure"),
        "med_amount_pct": cap.get("med_amount_pct"),
        "pass": pass_gate, "pass_icir": pass_icir, "pass_cov": pass_cov,
        "pass_year": pass_year, "pass_corr": pass_corr,
        "code": code,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", required=True, help="qf-llm 的 pool.json 路径")
    ap.add_argument("--out", default="logs/qf_pool_validation.json")
    ap.add_argument("--panel-db", default="data/cache/bars.db")
    args = ap.parse_args()

    with open(args.pool, encoding="utf-8") as f:
        pool = json.load(f)
    print(f"读入 {len(pool)} 个入池因子", flush=True)

    panel = load_panel_extended(args.panel_db)
    fwd = forward_returns(panel)
    print(f"面板 {panel.shape}（含基本面/市值列），fwd 标签 {fwd.notna().sum():,} 个", flush=True)

    results = []
    pooled_signals = []
    for rec in pool:
        name = rec.get("name")
        code = rec.get("code")
        if not code:
            results.append({"name": name, "error": "pool 缺 code 字段（旧版 qf-llm 未落盘代码，需重挖）"})
            continue
        r = validate_one(name, code, panel, fwd, pooled_signals)
        results.append(r)
        if r.get("pass"):
            try:
                sig = _run_factor(code, panel)
                pooled_signals.append(sig if r["direction"] == 1 else -sig)
            except Exception:
                pass
        print(f"  {name}: icir={r.get('ic_ir')} cov={r.get('coverage')} "
              f"corr={r.get('max_corr')} 涨停暴露={r.get('limup_exposure')} "
              f"流动性分位={r.get('med_amount_pct')} {'✅通过' if r.get('pass') else '❌'} "
              f"{r.get('error', '')}", flush=True)

    passed = [r for r in results if r.get("pass")]
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    report = {
        "source_pool": args.pool,
        "n_total": len(pool), "n_pass": len(passed),
        "thresholds": {"min_icir": MIN_ICIR, "min_coverage": MIN_COVERAGE,
                       "max_pool_corr": MAX_POOL_CORR, "holdout_start": HOLDOUT_START,
                       "year_agree_ratio": YEAR_AGREE_RATIO},
        "note": "v2 海选+分年度+holdout+逐日截面Spearman去重+T+1严格标签+容量代理；成本/滑点与完整冲击容量在组合层回测",
        "results": results,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n=== 验证完成：{len(passed)}/{len(pool)} 通过海选+分年度+去重 ===")
    print(f"报告: {args.out}")


if __name__ == "__main__":
    main()
