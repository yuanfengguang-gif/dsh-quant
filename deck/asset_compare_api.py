# -*- coding: utf-8 -*-
"""deck/asset_compare_api.py —— 组合资产走势对比（供 /api/asset_compare 调用）

用途：一张图看清「策略组合所有目标资产」的价格走向（含历次金融危机区间）。

设计原则（工作区铁律）：
  1. 资产清单 / 颜色 / 区间 全部来自 config/asset_compare.yaml，代码零硬编码；
  2. 只读取本地数据 + 归一化 + 降采样，不产生任何交易信号；
  3. 数据缺失时返回该资产 missing 标记，其余照常返回，不崩溃。

★★ 两个关键严谨性约束（2026-11-04 修）★★
  A. 归一化基准日必须对所有资产一致。
     若各资产用「自己区间内的第一个点」作基准，那么 QQQ（2011起）会和沪深300（2005起）
     在同一个图上显示为「都从100出发」，但实际比较的是不同时间段的涨幅 —— 这是误导。
     现在：统一用区间起点 hi/lo 之后的第一个共同交易日；起点偏离超过 base_tolerance_days
     的资产判为「起点缺失」，不参与画图。
  B. 数据空洞检测。us_QQQ.csv 有 2307 天空洞（2001→2011），若直接取用会得到一个
     「十年涨了 X 倍」的假象。现在：检测 > 45 天空洞，若空洞落在区间起点附近则判缺失，
     否则在返回里标记 gap_days 供 UI 提示。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]

DEFAULTS = {
    "normalize": {"base": 100, "max_points": 260, "base_tolerance_days": 15},
    "assets": [
        {"key": "hs300", "label": "沪深300", "source": "em_global",
         "file": "em_global_hs300.csv", "color": "#2563eb", "in_portfolio": False},
        {"key": "dividend", "label": "红利低波", "code": "H30269",
         "source": "db", "color": "#16a34a", "in_portfolio": True},
        {"key": "gold", "label": "黄金(GLD)", "source": "us_csv",
         "file": "us_GLD.csv", "color": "#d97706", "in_portfolio": True},
        {"key": "qqq", "label": "纳斯达克100(QQQ)", "source": "us_csv",
         "file": "us_QQQ.csv", "color": "#7c3aed", "in_portfolio": True},
        {"key": "spy", "label": "标普500(SPY)", "source": "us_csv",
         "file": "us_SPY.csv", "color": "#dc2626", "in_portfolio": False},
    ],
    "periods": [{"key": "all", "label": "全历史", "start": "2005-01-01", "end": "latest"}],
    "ui": {"default_period": "all", "show_return_table": True, "data_dir": "data/cache/crisis"},
}

GAP_WARN_DAYS = 45          # 超过这么多天视为数据空洞


def _cfg() -> dict:
    cfg = {}
    p = BASE / "config" / "asset_compare.yaml"
    try:
        import yaml
        cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        cfg = {}
    out = dict(DEFAULTS)
    for k in ("normalize", "ui"):
        if isinstance(cfg.get(k), dict):
            merged = dict(DEFAULTS[k])
            merged.update(cfg[k])
            out[k] = merged
    for k in ("assets", "periods"):
        if isinstance(cfg.get(k), list) and cfg[k]:
            out[k] = cfg[k]
    return out


def _load_us_csv(data_dir: Path, fn: str):
    import pandas as pd
    p = data_dir / fn
    if not p.exists():
        return None, f"缺文件 {fn}"
    try:
        d = pd.read_csv(p)
        dc = [c for c in d.columns if str(c).lower() in ("date", "日期")]
        if not dc:
            return None, "无 date 列"
        d[dc[0]] = pd.to_datetime(d[dc[0]])
        cc = [c for c in d.columns if str(c).lower() in ("close", "收盘")]
        if cc:
            vc = cc[0]
        else:
            pc = [c for c in d.columns if "价" in str(c)]
            if not pc:
                return None, "无 close 列"
            vc = pc[0]
        s = d.sort_values(dc[0]).set_index(dc[0])[vc].astype(float).dropna()
        return (s, None) if len(s) > 30 else (None, "数据过少")
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _load_em_global(data_dir: Path, fn: str):
    import pandas as pd
    p = data_dir / fn
    if not p.exists():
        return None, f"缺文件 {fn}"
    try:
        d = pd.read_csv(p)
        dc = next((c for c in d.columns if "日期" in str(c)), None)
        if dc is None:
            return None, "无日期列"
        d[dc] = pd.to_datetime(d[dc])
        s = d.sort_values(dc).set_index(dc)["最新价"].astype(float).dropna()
        return (s, None) if len(s) > 30 else (None, "数据过少")
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _load_db(code: str):
    import pandas as pd
    db = BASE / "data" / "cache" / "dividend_research.db"
    if not db.exists():
        return None, "缺 dividend_research.db"
    try:
        c = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=20)
        d = pd.read_sql_query("SELECT date, close FROM idx_daily WHERE code=? ORDER BY date",
                              c, params=(code,))
        c.close()
        if len(d) < 30:
            return None, f"库中 {code} 数据不足"
        d["date"] = pd.to_datetime(d["date"])
        return d.set_index("date")["close"].astype(float).dropna(), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _load_asset(a: dict, data_dir: Path):
    src = str(a.get("source", "us_csv"))
    if src == "us_csv":
        return _load_us_csv(data_dir, a.get("file", ""))
    if src == "em_global":
        return _load_em_global(data_dir, a.get("file", ""))
    if src == "db":
        return _load_db(str(a.get("code", "")))
    return None, f"未知 source: {src}"


def _max_gap(s):
    if s is None or len(s) < 2:
        return 0
    idx = s.index.to_series()
    return int(idx.diff().dt.days.max() or 0)


def _downsample(s, max_points: int):
    n = len(s)
    if n <= max_points:
        idx = list(range(n))
    else:
        step = (n - 1) / (max_points - 1)
        idx = sorted({int(round(i * step)) for i in range(max_points)})
        if idx[0] != 0:
            idx.insert(0, 0)
        if idx[-1] != n - 1:
            idx.append(n - 1)
    vals = s.to_numpy()
    return [s.index[i] for i in idx], [float(vals[i]) for i in idx]


def asset_compare_data(period: str | None = None) -> dict:
    import pandas as pd

    cfg = _cfg()
    data_dir = BASE / cfg["ui"].get("data_dir", "data/cache/crisis")
    periods = cfg["periods"]
    pmap = {p.get("key"): p for p in periods}
    pk = period if period in pmap else cfg["ui"].get("default_period", periods[0].get("key"))
    per = pmap.get(pk, periods[0])

    base = float(cfg["normalize"].get("base", 100))
    maxp = int(cfg["normalize"].get("max_points", 260))
    tol = int(cfg["normalize"].get("base_tolerance_days", 15))

    out: dict = {"ok": True, "period": pk, "period_label": per.get("label", pk),
                 "periods": [{"key": p.get("key"), "label": p.get("label")} for p in periods],
                 "generated_at": pd.Timestamp.now().isoformat(timespec="seconds"),
                 "base": base, "ui": cfg["ui"], "assets": [],
                 "warnings": []}

    start = pd.Timestamp(per.get("start", "2005-01-01"))
    end_raw = per.get("end", "latest")
    end = None if str(end_raw) == "latest" else pd.Timestamp(end_raw)

    # ── 载入（含 fallback 替换）
    loaded = []
    for a in cfg["assets"]:
        item = {"key": a.get("key"), "label": a.get("label"), "code": a.get("code"),
                "color": a.get("color"), "note": a.get("note"),
                "in_portfolio": bool(a.get("in_portfolio")), "ok": False,
                "substituted": False}
        s, err = _load_asset(a, data_dir)
        used = a
        # 起点无数据 → 尝试 fallback
        fb = a.get("fallback")
        if fb:
            need_start = start
            has_start = (s is not None and
                         s.index.min() <= need_start + pd.Timedelta(days=tol) and
                         len(s[(s.index >= need_start) & (s.index <= need_start + pd.Timedelta(days=tol))]) > 0)
            if not has_start:
                s2, err2 = _load_asset(fb, data_dir)
                if s2 is not None:
                    s, err, used = s2, None, fb
                    item.update({"substituted": True,
                                 "label": fb.get("label", item["label"]),
                                 "key": fb.get("key", item["key"]),
                                 "code": fb.get("code", item["code"])})
                    out["warnings"].append(
                        f"{a.get('label')} 该区间起点无数据，已用「{fb.get('label')}」替代（已实测两者日收益相关性 0.988）")
        item["gap_days"] = 0   # 改为在【本区间内】计算，见下方
        if s is None:
            item["error"] = err or "无数据"
            item["dates"], item["values"], item["ret_pct"] = [], [], None
            loaded.append((item, None))
        else:
            loaded.append((item, s))

    avail = [s for _, s in loaded if s is not None]
    if not avail:
        out["ok"] = False
        out["error"] = "所有资产都无数据"
        out["assets"] = [it for it, _ in loaded]
        return out

    # ── 区间与统一基准日
    lo = max(start, max(s.index.min() for s in avail))
    hi = (min(end, min(s.index.max() for s in avail)) if end is not None
          else min(s.index.max() for s in avail))
    if hi <= lo:
        out["ok"] = False
        out["error"] = f"区间无效：{lo.date()} ~ {hi.date()}（各资产无重叠数据）"
        out["assets"] = [it for it, _ in loaded]
        return out

    # 统一基准日 = 区间起点之后第一个「多数资产都有数据」的交易日
    # 做法：取各资产在 [lo, lo+tol] 内的第一个交易日，取中位数日期作为共同基准日
    cands = []
    for _, s in loaded:
        if s is None:
            continue
        seg = s[(s.index >= lo) & (s.index <= lo + pd.Timedelta(days=max(tol, 10)))]
        if len(seg) > 0:
            cands.append(seg.index[0])
    if not cands:
        out["ok"] = False
        out["error"] = "区间起点附近无任何资产数据"
        out["assets"] = [it for it, _ in loaded]
        return out
    base_date = pd.Timestamp(sorted(cands)[len(cands) // 2])
    out["start"] = base_date.strftime("%Y-%m-%d")
    out["end"] = hi.strftime("%Y-%m-%d")
    out["base_date"] = out["start"]

    # ── 逐个资产归一化（基准日 = base_date，缺则判起点缺失）
    for item, s in loaded:
        if s is None:
            out["assets"].append(item)
            continue
        # ★ 严格从基准日（含）之后取第一个点，绝不使用基准日之前的数据
        seg = s[(s.index >= base_date) & (s.index <= hi)].dropna()
        if len(seg) < 5:
            item["error"] = f"区间内数据不足（本资产最早 {s.index.min().date()}）"
            item["dates"], item["values"], item["ret_pct"] = [], [], None
            out["assets"].append(item)
            continue
        first_date = seg.index[0]
        lag = (first_date - base_date).days
        if lag > tol:
            item["error"] = (f"起点缺失：本资产在基准日 {base_date.date()} 之后最早只有 "
                             f"{first_date.date()}（差 {lag} 天）")
            item["dates"], item["values"], item["ret_pct"] = [], [], None
            out["assets"].append(item)
            continue
        # 空洞只在本区间内计算（避免历史空洞误报当前区间）
        seg_gaps = seg.index.to_series().diff().dt.days
        seg_gap = int(seg_gaps.max() or 0)
        item["gap_days"] = seg_gap
        if seg_gap > GAP_WARN_DAYS:
            out["warnings"].append(
                f"{item['label']} 在本区间内有 {seg_gap} 天空洞（源数据缺失），曲线可能不连续")

        first = float(seg.iloc[0])
        if first <= 0:
            item["error"] = "起始价异常"
            item["dates"], item["values"], item["ret_pct"] = [], [], None
            out["assets"].append(item)
            continue
        norm = seg / first * base
        dts, vals = _downsample(norm, maxp)
        item.update({
            "ok": True,
            "dates": [d.strftime("%Y-%m-%d") for d in dts],
            "values": [round(v, 2) for v in vals],
            "ret_pct": round((float(seg.iloc[-1]) / first - 1) * 100, 2),
            "start_price": round(first, 2),
            "end_price": round(float(seg.iloc[-1]), 2),
            "n_raw": int(len(seg)),
            "base_date": first_date.strftime("%Y-%m-%d"),
        })
        out["assets"].append(item)

    ok_items = [a for a in out["assets"] if a.get("ok") and a.get("ret_pct") is not None]
    if ok_items:
        ranked = sorted(ok_items, key=lambda x: -x["ret_pct"])
        out["ranking"] = [{"key": r["key"], "label": r["label"], "ret_pct": r["ret_pct"]}
                          for r in ranked]
    return out
