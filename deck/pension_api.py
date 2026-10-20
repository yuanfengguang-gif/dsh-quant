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

    import pandas as pd
    from datetime import date
    asof = asof or date.today().isoformat()

    out = {"ok": True, "asof": asof, "generated_at": pd.Timestamp.now().isoformat(timespec="seconds"),
           "plan": cfg.get("plan", {}), "layers": cfg.get("layers", {}),
           "entry": cfg.get("entry", {}), "constraints": cfg.get("constraints", {})}

    # 配比 + 行业集中度（来自配置，不硬编码）
    assets = cfg.get("assets", [])
    tot_top3 = sum(a.get("weight", 0) * a.get("top3_industry", 0) for a in assets)
    tot_bank = sum(a.get("weight", 0) * a.get("bank_share", 0) for a in assets)
    out["assets"] = [{
        "code": a.get("code"), "name": a.get("name"), "weight": a.get("weight"),
        "top3_industry": a.get("top3_industry"), "bank_share": a.get("bank_share"),
        "amount": int(round(cfg["plan"]["capital"] * a.get("weight", 0))),
    } for a in assets]
    out["portfolio_industry"] = {"top3": tot_top3, "bank": tot_bank}

    # 核心信号
    sig_cfg = cfg["signals"]["dividend_pct"]
    try:
        d = mp.load_index(sig_cfg["index_code"])
        d = d[d["date"] <= pd.Timestamp(asof)].reset_index(drop=True)
        pct = mp.rolling_pct(d["dy_ttm"].to_numpy(float), int(sig_cfg["window"]))
        cur_pct = float(pct[-1]) if not pd.isna(pct[-1]) else None
        out["signal"] = {
            "index": sig_cfg["index_code"], "index_name": sig_cfg.get("index_name"),
            "dividend_yield": float(d["dy_ttm"].iloc[-1]),
            "percentile": cur_pct,
            "expensive": float(sig_cfg["expensive"]), "cheap": float(sig_cfg["cheap"]),
            "action": ("卫星仓全卖" if cur_pct is not None and cur_pct <= sig_cfg["expensive"]
                       else "卫星仓买回" if cur_pct is not None and cur_pct >= sig_cfg["cheap"]
                       else "不动"),
            "last_date": str(d["date"].iloc[-1])[:10],
        }
        mp_ = cur_pct
    except Exception as e:
        out["signal"] = {"error": f"{type(e).__name__}: {e}"}

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
    out["pairing_candidates"] = cfg.get("pairing_candidates", [])
    out["exploration"] = cfg.get("exploration", {})

    return out


if __name__ == "__main__":
    import json
    print(json.dumps(pension_data(), ensure_ascii=False, indent=1, default=str)[:3000])
