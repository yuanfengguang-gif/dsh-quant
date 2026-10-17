# -*- coding: utf-8 -*-
"""factors/validate_deep.py —— 深验证（验收链后三步 ③④⑤）

③ 暴露审计：市值暴露 + 行业×市值双中性后 ICIR（剔除 size/行业 beta，看 alpha 是否幸存）
④ Brinson 归因：行业配置贡献 vs 行业内选股贡献（年化）
⑤ 容量 + 失效监控：换手/容量 + 分年度净超额（衰减检测）

口径：
  - 行业 = stock_basic.industry（证监会一级，83 类，覆盖率 93.9%）
  - 市值 = hist_mv.circ_mv（月频 2020 起，前向填充）
  - 中性化 = 行业内 demean → 对 log(circ_mv) 正交化，逐日截面
  - Brinson = 因子 top-N 等权组合 vs 等权基准，逐日行业配置/选股分解后年化

用法：python factors/validate_deep.py
"""
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
except Exception:
    pass

from factors.import_qf_pool import load_panel, forward_returns, cross_sectional_ics, cross_corr
from factors.combo_validate import combo_validate_sig, DEFAULT_START, DEFAULT_END
from factors.reproduce_factors import bp_value, sue, f_score, turn_mid_prox
from factors.validate_all_factors import amihud, mom_120, near_high_250, ma200_trend

CACHE = BASE / "data" / "cache"

DEEP_FACTORS = [
    ("amihud", amihud, None),
    ("ma200_trend", ma200_trend, None),
    ("f_score", f_score, None),
    ("mom_120", mom_120, -1),
    ("bp_value", bp_value, None),
    ("near_high_250", near_high_250, None),
    ("sue", sue, None),
    ("turn_mid_prox", turn_mid_prox, None),
]


def load_industry_map():
    con = sqlite3.connect(str(CACHE / "stock_basic.db"))
    m = {r[0].split(".")[0]: r[1] for r in con.execute(
        "SELECT code, industry FROM stock_basic WHERE industry != '' AND industry IS NOT NULL").fetchall()}
    con.close()
    return m


def load_mv_wide(dates, codes):
    con = sqlite3.connect(str(CACHE / "hist_mv.db"))
    mv = pd.read_sql("SELECT month, code, circ_mv FROM hist_mv", con)
    con.close()
    mv["date"] = pd.to_datetime(mv["month"] + "-01") + pd.offsets.MonthEnd(0)
    m = mv.pivot_table(index="date", columns="code", values="circ_mv", aggfunc="last")
    m = m.reindex(dates).ffill()
    return m.reindex(columns=codes)


def industry_demean(fw, ind_map):
    out = fw.copy()
    ind_cols = defaultdict(list)
    for code in fw.columns:
        ind = ind_map.get(str(code).split(".")[0])
        if ind:
            ind_cols[ind].append(code)
    for ind, cols in ind_cols.items():
        if len(cols) > 1:
            out[cols] = fw[cols].sub(fw[cols].mean(axis=1), axis=0)
    return out


def size_orthogonalize(fw, mv_wide):
    lm = np.log(mv_wide.reindex(index=fw.index, columns=fw.columns))
    fz = fw.sub(fw.mean(axis=1), axis=0)
    lz = lm.sub(lm.mean(axis=1), axis=0)
    beta = (fz * lz).sum(axis=1) / ((lz ** 2).sum(axis=1) + 1e-12)
    return fz - lz.mul(beta, axis=0)


def icir_of_long(sig, fwd):
    ics = cross_sectional_ics(sig, fwd)
    if len(ics) < 30:
        return None
    return float(ics.mean() / (ics.std() + 1e-12))


def brinson_daily(close_wide, sig, ind_map, topn=20):
    """逐日 Brinson 归因：因子 top-N 等权组合 vs 等权基准。
    用 close 收益（不是因子值变化）；返回 (年化配置贡献, 年化选股贡献, 年化交互贡献)。"""
    ret = close_wide.pct_change()
    rank = sig.unstack().rank(axis=1, pct=True)
    n = rank.shape[1]
    thr = 1 - topn / n
    is_top = rank >= thr
    ind_series = pd.Series({c: ind_map.get(str(c).split(".")[0], "NA") for c in close_wide.columns})
    R_b = ret.mean(axis=1)  # 基准日收益（等权全市场）
    alloc = pd.Series(0.0, index=ret.index)
    sel = pd.Series(0.0, index=ret.index)
    inter = pd.Series(0.0, index=ret.index)
    for ind_name in ind_series.unique():
        cols = ind_series[ind_series == ind_name].index
        if len(cols) == 0:
            continue
        wb = len(cols) / n
        rb = ret[cols].mean(axis=1)
        top_mask = is_top[cols]
        wp = top_mask.sum(axis=1) / topn
        rp = ret[cols].where(top_mask).mean(axis=1)
        alloc += (wp - wb) * (rb - R_b)
        sel += wb * (rp.sub(rb).fillna(0))
        inter += (wp - wb) * (rp.sub(rb).fillna(0))
    a = alloc.mean() * 252
    s = sel.mean() * 252
    i = inter.mean() * 252
    return a, s, i


def main():
    print("加载面板 + 行业 + 市值...", flush=True)
    panel = load_panel("data/cache/bars.db", start="2019-01-01")
    fwd = forward_returns(panel)
    dates = panel.index.get_level_values(0).unique().sort_values()
    codes = panel.index.get_level_values("code").unique()
    ind_map = load_industry_map()
    mv_wide = load_mv_wide(dates, codes)
    print(f"行业映射 {len(ind_map)} 只 / 市值覆盖 {mv_wide.notna().sum().sum():,} 单元格", flush=True)
    close_wide = panel["close"].unstack()

    rows = []
    for name, fn, direction in DEEP_FACTORS:
        try:
            sig = fn(panel).reindex(panel.index)
            fw = sig.unstack()
            # ③ 暴露审计
            raw_ir = icir_of_long(sig, fwd)
            lm = np.log(mv_wide.reindex(index=fw.index, columns=fw.columns))
            size_sig = lm.stack().reindex(sig.index)
            size_exp = cross_corr(sig, size_sig)
            fw_dn = size_orthogonalize(industry_demean(fw, ind_map), mv_wide)
            dn_ir = icir_of_long(fw_dn.stack().reindex(panel.index), fwd)
            # ④ Brinson
            a, s, i = brinson_daily(close_wide, sig, ind_map, topn=20)
            # 组合层裁决 + ⑤ 容量/失效
            r = combo_validate_sig(name, sig, panel, topn=20, rebalance=40,
                                   start=DEFAULT_START, end=DEFAULT_END, direction=direction)
            m = r["metrics"]
            rows.append({
                "因子": name, "方向": f"{r['direction']:+d}",
                "原始ICIR": round(raw_ir, 3), "双中性ICIR": round(dn_ir, 3),
                "市值暴露": round(size_exp, 3),
                "配置贡献": round(a, 4), "选股贡献": round(s, 4), "交互": round(i, 4),
                "净超额": round(r["excess_annual"], 4), "夏普": round(m["sharpe"], 3),
                "换手": round(r["capacity"]["turnover"], 3), "回撤": round(m["max_drawdown"], 3),
            })
            print(f"  {name:<14} 原始ICIR={raw_ir:+.3f} 双中性={dn_ir:+.3f} 市值暴露={size_exp:+.3f} "
                  f"配置={a:+.2%} 选股={s:+.2%} 净超额={r['excess_annual']:+.2%} 夏普={m['sharpe']:.2f}",
                  flush=True)
        except Exception as e:
            print(f"  {name:<14} 失败: {str(e)[:120]}", flush=True)
            rows.append({"因子": name, "失败": str(e)[:80]})

    df = pd.DataFrame(rows)
    print("\n=== 深验证汇总（③暴露审计 + ④Brinson + ⑤容量/失效） ===")
    print(df.to_string(index=False))
    out = BASE / "logs" / "deep_validation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(df.to_json(orient="records", force_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已存：{out}")


if __name__ == "__main__":
    main()
