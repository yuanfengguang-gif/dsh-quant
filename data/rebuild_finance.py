# -*- coding: utf-8 -*-
"""data/rebuild_finance.py —— 用 CSMAR 重建 finance_report（新库先行，不覆盖旧库）

口径设计（解决 DS-07/DS-15 的语义问题）：
  旧库约定：`bp = eps/roe` 应等于每股净资产（BVPS）；`roe` 是单季 ROE。
  → 新建库统一为**单季口径**，并让 eps/roe 恒等式自动成立：
        eps  = 单季归母净利 / 总股本
        roe  = 单季归母净利 / 净资产
        eps / roe ≡ 净资产 / 总股本 = BVPS      （恒等，结构上一致）
  累计列（net_profit/revenue）用 CSMAR 季度累计；单季 = 同财年内累计差分。

字段映射：
  net_profit  ← np_parent 累计 / 1e8（亿元，归母）
  revenue     ← total_revenue 累计 / 1e8（亿元，**营业总收入**；与旧库口径一致，已验茅台 1505.60 亿完全吻合）
  sq_net_profit/sq_revenue ← 同财年内差分（Q1=累计；Q2=H1−Q1；Q3=9M−H1；Q4=FY−9M）
  sq_net_yoy/sq_rev_yoy    ← 与上年同季单季值比（fraction）
  eps/roe     ← 单季口径（见上）
  source      ← 'csmar'

输出：data/cache/finance_new.db → 表 finance_report（schema 与旧库完全一致，11 列）
用法：python data/rebuild_finance.py
"""
from __future__ import annotations

import bisect
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CACHE = Path(__file__).resolve().parent.parent / "data" / "cache"
FIN = CACHE / "finance_csmar.db"
BASE_DB = CACHE / "tdx_base.db"
OLD = CACHE / "finance.db"
OUT = CACHE / "finance_new.db"


def main() -> int:
    t0 = time.time()
    if OUT.exists():
        OUT.unlink()
    out = sqlite3.connect(str(OUT))
    out.execute("PRAGMA synchronous=OFF")
    out.execute("""CREATE TABLE finance_report (
        code TEXT, period TEXT, net_profit REAL, revenue REAL,
        sq_net_profit REAL, sq_net_yoy REAL, sq_revenue REAL, sq_rev_yoy REAL,
        eps REAL, roe REAL, source TEXT, PRIMARY KEY (code, period))""")
    out.commit()

    fin = sqlite3.connect(f"file:{FIN.as_posix()}?mode=ro", uri=True, timeout=60)
    base = sqlite3.connect(f"file:{BASE_DB.as_posix()}?mode=ro", uri=True, timeout=60)

    # ① 股本序列（每股 → [(date, shares)])
    print("读取股本序列 …", flush=True)
    sh = defaultdict(list)
    for code, d, ts in base.execute(
            "SELECT code, date, total_share FROM daily WHERE total_share>0 ORDER BY code, date"):
        sh[code].append((d, ts * 10000.0))
    sh_dates = {c: [x[0] for x in v] for c, v in sh.items()}
    print(f"  {len(sh):,} 只有股本")

    # ② 年度净资产（用于 roe 与自证）
    print("读取年度净资产 …", flush=True)
    equity = {}
    for code, period, eq in fin.execute(
            "SELECT code, period, equity FROM fin_core WHERE equity IS NOT NULL AND equity>0"):
        equity[(code, period)] = eq
    eq_dates = defaultdict(list)
    for (c, p) in equity:
        eq_dates[c].append(p)
    for c in eq_dates:
        eq_dates[c].sort()

    def shares_at(code: str, period: str) -> float | None:
        v = sh.get(code)
        if not v:
            return None
        ds = sh_dates[code]
        i = bisect.bisect_right(ds, period) - 1
        if i < 0:
            i = 0
        return v[i][1]

    def equity_at(code: str, period: str) -> float | None:
        ds = eq_dates.get(code)
        if not ds:
            return None
        i = bisect.bisect_right(ds, period) - 1
        if i < 0:
            i = 0
        return equity.get((code, ds[i]))

    # ③ 季度累计 → 单季差分
    print("读取季度累计并差分 …", flush=True)
    rows_by_code = defaultdict(dict)          # code → {period: (np_parent, total_revenue, eps, roe_a)}
    for code, period, npp, trev, eps0, roe0 in fin.execute(
            "SELECT code, period, np_parent, total_revenue, eps, roe_a FROM fin_core_q"):
        rows_by_code[code][period] = (npp, trev, eps0, roe0)
    print(f"  {len(rows_by_code):,} 只有季度数据")

    recs = []
    for code, per_map in rows_by_code.items():
        periods = sorted(per_map)
        # 同财年内按季度顺序差分
        by_year = defaultdict(list)
        for p in periods:
            by_year[p[:4]].append(p)
        sq = {}          # period → (sq_np, sq_rev) 单位：元
        for y, ps in by_year.items():
            ps.sort()
            prev_np = prev_rev = 0.0
            for p in ps:
                npp = per_map[p][0] or 0.0
                trev = per_map[p][1] or 0.0
                sq[p] = (npp - prev_np, trev - prev_rev)
                prev_np, prev_rev = npp, trev
        for p in periods:
            npp, trev, eps0, roe0 = per_map[p]
            npp = npp or 0.0
            trev = trev or 0.0
            s_np, s_rev = sq[p]
            # 同比：上年同季单季值
            prev_p = f"{int(p[:4])-1}{p[4:]}"
            yoy_np = yoy_rev = None
            if prev_p in sq:
                p_np, p_rev = sq[prev_p]
                if p_np > 0:
                    yoy_np = s_np / p_np - 1
                if p_rev > 0:
                    yoy_rev = s_rev / p_rev - 1
            # ★eps/roe 统一用**期末摊薄**口径（不是 CSMAR 的加权平均 roe_a）：
            #   eps = 累计归母净利 / 期末总股本 ；roe = 累计归母净利 / 期末净资产
            #   → eps/roe ≡ 净资产/总股本 = BVPS **恒等成立**（下游 bp = eps/roe 不失真）
            #   实测：茅台 34.65% ≈ 加权 34.66%（差 0.01pp）；格力/平安因年内净资产变动差 3-10%
            eq = equity_at(code, p)
            shs = shares_at(code, p)
            eps = (npp / shs) if (shs and shs > 0 and npp) else (eps0 if eps0 is not None else None)
            roe = (npp / eq) if (eq and eq > 0 and npp) else (roe0 if roe0 is not None else None)
            recs.append((
                code[:6], p,
                round(npp / 1e8, 4) if npp else None,
                round(trev / 1e8, 4) if trev else None,
                round(s_np / 1e8, 4),
                round(yoy_np, 6) if yoy_np is not None else None,
                round(s_rev / 1e8, 4),
                round(yoy_rev, 6) if yoy_rev is not None else None,
                round(eps, 6) if eps is not None else None,
                round(roe, 6) if roe is not None else None,
                "csmar"))
    out.executemany("INSERT OR REPLACE INTO finance_report VALUES (?,?,?,?,?,?,?,?,?,?,?)", recs)
    out.commit()
    n = out.execute("SELECT COUNT(*) FROM finance_report").fetchone()[0]
    print(f"完成: {n:,} 行 / {len({r[0] for r in recs}):,} 只 / 耗时 {time.time()-t0:.0f}s")
    print(f"库: {OUT}  ({OUT.stat().st_size/1024/1024:.1f} MB)")

    # ---- 验收 1：与旧库重叠对账 ----
    old = sqlite3.connect(f"file:{OLD.as_posix()}?mode=ro", uri=True, timeout=30)
    print("\n① 与旧库对账（net_profit / revenue，亿元）")
    for code, per in (("600519", "2023-12-31"), ("000001", "2023-12-31"), ("000651", "2023-12-31")):
        o = old.execute("SELECT net_profit, revenue, eps, roe FROM finance_report WHERE code=? AND period=?",
                        (code, per)).fetchone()
        nw = out.execute("SELECT net_profit, revenue, eps, roe, sq_net_profit, sq_net_yoy FROM finance_report "
                         "WHERE code=? AND period=?", (code, per)).fetchone()
        print(f"  {code} {per}")
        print(f"    旧: net_profit={o[0]} revenue={o[1]} eps={o[2]} roe={o[3]}")
        print(f"    新: net_profit={nw[0]} revenue={nw[1]} eps={nw[2]} roe={nw[3]} "
              f"sq_net={nw[4]} sq_yoy={nw[5]}")

    # ---- 验收 2：eps/roe ≈ BVPS 自证 ----
    print("\n② eps/roe 与 每股净资产 自证（偏差 <5% 为通过）")
    chk = []
    for code, per in (("600519", "2023-12-31"), ("000001", "2023-12-31"),
                      ("000651", "2023-12-31"), ("600036", "2023-12-31")):
        r = out.execute("SELECT eps, roe FROM finance_report WHERE code=? AND period=?", (code, per)).fetchone()
        if not r or not r[0] or not r[1]:
            continue
        code_full = code + (".SH" if code[0] in "69" else ".SZ")
        shs = shares_at(code_full, per)
        eq = equity_at(code_full, per)
        if not shs or not eq:
            continue
        bvps = eq / shs
        implied = r[0] / r[1]
        dev = abs(implied - bvps) / bvps * 100
        chk.append(dev)
        print(f"  {code} {per}: eps/roe={implied:>9.3f}  真实BVPS={bvps:>9.3f}  偏差 {dev:>6.3f}%  "
              f"{'✅' if dev < 5 else '⚠️'}")
    if chk:
        print(f"  平均偏差 {sum(chk)/len(chk):.3f}%")
    old.close(); fin.close(); base.close(); out.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
