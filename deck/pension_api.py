# -*- coding: utf-8 -*-
"""deck/pension_api.py —— 养老方案面板数据（供 /api/pension 调用）

设计原则（工作区铁律）：
  只做「读取配置 + 调用计算 + 返回 JSON」，不硬编码任何业务数据。
  所有参数来自 config/pension_plan.yaml；所有数字由 scripts/monitor_pension_plan.py 实时计算。
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
BASE_DIR = BASE


def _load(module_name: str, file_path: Path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def pension_data(asof: str | None = None) -> dict:
    """返回养老方案面板所需的全部数据"""
    try:
        mp = _load("monitor_pension_plan", BASE / "scripts" / "monitor_pension_plan.py")
    except Exception as e:
        return {"ok": False, "error": f"无法加载监控模块: {type(e).__name__}: {e}"}

    try:
        cfg = mp.load_cfg()
    except Exception as e:
        return {"ok": False, "error": f"无法读取配置: {type(e).__name__}: {e}"}

    import numpy as np
    import pandas as pd
    from datetime import date
    asof = asof or date.today().isoformat()

    out = {"ok": True, "asof": asof, "generated_at": pd.Timestamp.now().isoformat(timespec="seconds"),
           "plan": cfg.get("plan", {}), "layers": cfg.get("layers", {}),
           "entry": cfg.get("entry", {}), "constraints": cfg.get("constraints", {})}

    # 配比 + 行业集中度（来自配置，不硬编码）
    assets = cfg.get("assets", [])
    # 加权只统计 A 股资产（GLD/QQQ 无行业归属），按 A 股权重归一
    _a = [x for x in assets if x.get("weight", 0) > 0 and x.get("asset_class") is None]
    _aw = sum(x.get("weight", 0) for x in _a) or 1.0
    tot_top3 = sum(x.get("weight", 0) * (x.get("top3_industry") or 0) for x in _a) / _aw
    tot_bank = sum(x.get("weight", 0) * (x.get("bank_share") or 0) for x in _a) / _aw
    out["assets"] = [{
        "code": a.get("code"), "name": a.get("name"), "weight": a.get("weight"),
        "top3_industry": a.get("top3_industry"), "bank_share": a.get("bank_share"),
        "asset_class": a.get("asset_class"),
        "amount": int(round(cfg["plan"]["capital"] * a.get("weight", 0))),
    } for a in assets]
    out["portfolio_industry"] = {"top3": tot_top3, "bank": tot_bank}

    # 核心信号
    sig_cfg = cfg["signals"]["dividend_abs"]
    try:
        d = mp.load_index(sig_cfg["index_code"])
        d = d[d["date"] <= pd.Timestamp(asof)].reset_index(drop=True)
        cur_dy = float(d["dy_ttm"].iloc[-1])
        sell_th = float(sig_cfg["sell_below"])
        buy_th = float(sig_cfg["buy_above"])
        # 20 年历史位置（交叉验证用）
        hist = d["dy_ttm"].dropna().to_numpy(float)
        pos20 = float((hist < cur_dy).mean())
        out["signal"] = {
            "index": sig_cfg["index_code"], "index_name": sig_cfg.get("index_name"),
            "dividend_yield": cur_dy,
            "sell_below": sell_th, "buy_above": buy_th,
            "check_freq": sig_cfg.get("check_freq", "monthly"),
            "history_position": pos20,
            "action": ("卫星仓应空仓" if cur_dy <= sell_th
                       else "卫星仓应满仓" if cur_dy >= buy_th
                       else "不动"),
            "gap_to_sell": cur_dy - sell_th,
            "gap_to_buy": cur_dy - buy_th,
            "last_date": str(d["date"].iloc[-1])[:10],
        }
    except Exception as e:
        out["signal"] = {"error": f"{type(e).__name__}: {e}"}

    # 黄金换红利信号（v5 两层闸门，用户 2026-10-26 确认）
    try:
        out["gold_switch"] = mp.gold_switch_signal(cfg, asof)
    except Exception as e:
        out["gold_switch"] = None
        out["gold_switch_error"] = f"{type(e).__name__}: {e}"

    # 实物黄金监控看板（v3.0：黄金已移出组合，只保留看板）
    try:
        out["gold_dashboard"] = mp.gold_dashboard(cfg, asof)
    except Exception as e:
        out["gold_dashboard"] = None
        out["gold_dashboard_error"] = f"{type(e).__name__}: {e}"
    # 兼容旧字段
    try:
        out["gold_timing"] = mp.gold_timing_signal(cfg, asof)
    except Exception:
        out["gold_timing"] = None

    # v2.5 三信号组合
    try:
        out["combo"] = mp.satellite_combo(cfg, asof)
    except Exception:
        out["combo"] = None

    # ERP 温度计（仅参考）
    try:
        erp_cfg = cfg["signals"]["erp_thermometer"]
        dz = mp.load_index(erp_cfg["index_code"])
        bond = mp.load_bond()
        dz = dz.merge(bond, on="date", how="left")
        dz = dz[(dz["date"] <= pd.Timestamp(asof)) & dz["bond10y"].notna()].reset_index(drop=True)
        if len(dz) > 300:
            dz["erp"] = np.where(dz["pe_ttm"] > 0,
                                 1.0 / dz["pe_ttm"] - dz["bond10y"] / 100.0, np.nan)
            ev = dz["erp"].dropna()
            cur_erp = float(ev.iloc[-1])
            pct3 = float(mp.rolling_pct(dz["erp"].to_numpy(float),
                                        int(erp_cfg.get("window", 750)))[-1])
            allp = float((ev.to_numpy(float) < cur_erp).mean())
            band = None
            for lo, hi, nm, fhs, flw in (erp_cfg.get("bands") or []):
                if lo <= cur_erp < hi:
                    band = {"name": nm, "lo": lo, "hi": hi, "fwd_hs": fhs, "fwd_lw": flw}
                    break
            out["erp"] = {
                "index": erp_cfg["index_code"], "index_name": erp_cfg.get("index_name"),
                "value": cur_erp, "pct3y": pct3, "pct_all": allp,
                "band": band, "alert_below": float(erp_cfg.get("alert_below", 0.03)),
                "alert": cur_erp < float(erp_cfg.get("alert_below", 0.03)),
                "bands": [{"name": b[2], "lo": b[0], "hi": b[1],
                           "fwd_hs": b[3], "fwd_lw": b[4]} for b in (erp_cfg.get("bands") or [])],
                "pe": float(dz["pe_ttm"].iloc[-1]),
                "bond10y": float(dz["bond10y"].iloc[-1]),
            }
        else:
            out["erp"] = None
    except Exception:
        out["erp"] = None

    # 股息率绝对值（交叉验证）
    try:
        out["dividend_level"] = mp.dividend_level(cfg)
    except Exception:
        out["dividend_level"] = None

    # 银行强弱
    try:
        out["bank"] = mp.bank_strength(cfg)
    except Exception:
        out["bank"] = None

    # 信号战绩
    try:
        out["track_record"] = mp.signal_track_record(cfg)
    except Exception:
        out["track_record"] = None

    # 建仓回本
    try:
        out["breakeven"] = mp.entry_breakeven_stats(cfg)
    except Exception:
        out["breakeven"] = None

    # 异常报警
    try:
        out["alerts"] = [{"title": a, "detail": b} for a, b in mp.price_alerts(cfg, asof)]
    except Exception:
        out["alerts"] = []

    # ETF 价格
    try:
        codes = [a["code"] for a in cfg["assets"]]
        prices, src = mp.get_etf_prices(codes, asof)
        out["prices"] = {"source": src, "data": prices}
    except Exception:
        out["prices"] = {"source": "取数失败", "data": {}}

    # 建仓进度
    ent = cfg.get("entry", {})
    start = ent.get("start_date")
    if start:
        st = pd.Timestamp(start)
        passed = (pd.Timestamp(asof).year - st.year) * 12 + (pd.Timestamp(asof).month - st.month)
        dead = st + pd.DateOffset(months=int(ent.get("wait_deadline_months", 12)))
        out["entry_progress"] = {
            "started": True, "start": str(st.date()), "months_passed": int(passed),
            "months_remaining": max(0, int(ent.get("wait_deadline_months", 12)) - passed),
            "deadline": str(dead.date()), "due": pd.Timestamp(asof) >= dead,
        }
    else:
        out["entry_progress"] = {"started": False}

    # 配对候选（来自配置）
    # 未来任务：知识库待办（O 系列）
    try:
        import sqlite3 as _sq3
        _kb = BASE_DIR / "data" / "cache" / "research_kb.db"
        _c = _sq3.connect(f"file:{_kb.as_posix()}?mode=ro", uri=True, timeout=15)
        _rows = _c.execute(
            "SELECT oid, title, priority, detail, status FROM open_item "
            "WHERE status != 'done' ORDER BY priority, oid").fetchall()
        _c.close()
        out["open_items"] = [{"id": r[0], "title": r[1], "priority": r[2],
                             "note": r[3], "status": r[4]} for r in _rows]
    except Exception as _e:
        out["open_items"] = []
        out["open_items_error"] = f"{type(_e).__name__}: {_e}"

    out["pairing_candidates"] = cfg.get("pairing_candidates", [])
    out["exploration"] = cfg.get("exploration", {})

    return out


if __name__ == "__main__":
    import json
    print(json.dumps(pension_data(), ensure_ascii=False, indent=1, default=str)[:3000])
