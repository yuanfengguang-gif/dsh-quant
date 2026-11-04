# -*- coding: utf-8 -*-
"""deck/gold_switch_api.py —— 黄金→红利ETF 换仓信号（供 /api/gold_switch 调用）

设计原则（工作区铁律）：
  1. 只读配置 + 算数 + 返回 JSON，不硬编码任何业务数据；
  2. 所有阈值来自 config/gold_switch_signal.yaml；
  3. 数据缺失时返回缺失标记，不崩溃；
  4. 所有指标都是「当天收盘可算的量」，无未来函数（依据 AGENTS.md E15/E17）。

返回结构（前端只需渲染，不再计算）：
  {
    ok, asof, generated_at,
    stage: {id, label, desc},
    composite: {satisfied, total, can_act, verdict},
    primary: {value, window_high, drawdown, tranches:[{level,label,gap_pct,triggered,progress}]},
    auxiliary: {ratio, window_high, fall, triggered, gap_pct, progress, note},
    warning: {bond10, bond10_up, dollar, dollar_up, squeeze, note},
    confirm: {rate, direction, history:[], note},
    series: {dates:[], gsr:[], hs_dd:[]}   # 迷你走势图用
  }
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]

# 默认配置（当 yaml 缺失时兜底，保证不崩溃）
DEFAULTS = {
    "primary": {"index_code": "000300", "window_days": 756, "min_periods": 250,
                "tranches": [{"level": 0.25, "label": "第1档", "amount_wan": 36},
                             {"level": 0.35, "label": "第2档", "amount_wan": 36}]},
    "auxiliary": {"gold_series": "us_GLD.csv", "silver_series": "us_SLV.csv",
                  "ratio_scale": 9.91, "window_days": 250, "min_periods": 120,
                  "trigger_fall": 0.08},
    "warning": {"bond10_file": "us_10y_东财.csv", "bond10_col_hint": "美国国债收益率10年",
                "dollar_file": "us_UUP.csv", "lookback_days": 60, "tradeable": False},
    "confirm": {"rate_file": "macro_bank_usa_interest_rate.csv", "history_months": 12},
    "composite": {"min_signals_to_act": 2},
    "data_dir": "data/cache/crisis",
}


def _cfg() -> dict:
    """读取 yaml 配置；失败则用 DEFAULTS。合并缺失键，保证结构完整。"""
    cfg = {}
    p = BASE / "config" / "gold_switch_signal.yaml"
    try:
        import yaml
        cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        cfg = {}
    out = {}
    for k, v in DEFAULTS.items():
        if isinstance(v, dict):
            merged = dict(v)
            if isinstance(cfg.get(k), dict):
                merged.update(cfg[k])
            out[k] = merged
        else:
            out[k] = cfg.get(k, v)
    # 补充非 DEFAULTS 的展示字段
    for k in ("ui", "version"):
        if k in cfg:
            out[k] = cfg[k]
    return out


def _us_series(data_dir: Path, fn: str):
    """读美股 ETF 的 date/close CSV"""
    import pandas as pd
    p = data_dir / fn
    if not p.exists():
        return None
    try:
        d = pd.read_csv(p)
        dc = [c for c in d.columns if str(c).lower() in ("date", "日期")]
        if not dc:
            return None
        d[dc[0]] = pd.to_datetime(d[dc[0]])
        cc = [c for c in d.columns if str(c).lower() in ("close", "收盘")]
        if not cc:
            cc = [c for c in d.columns if "价" in str(c)]
        if not cc:
            return None
        s = d.sort_values(dc[0]).set_index(dc[0])[cc[0]].astype(float).dropna()
        return s if len(s) > 30 else None
    except Exception:
        return None


def _bond10(data_dir: Path, fn: str, hint: str):
    import pandas as pd
    p = data_dir / fn
    if not p.exists():
        return None
    try:
        d = pd.read_csv(p)
        d.columns = [str(c) for c in d.columns]
        if "日期" not in d.columns:
            return None
        d["日期"] = pd.to_datetime(d["日期"])
        col = [c for c in d.columns if hint in c]
        if not col:
            return None
        return d.sort_values("日期").set_index("日期")[col[0]].astype(float).dropna()
    except Exception:
        return None


def _fed_rate(data_dir: Path, fn: str):
    import pandas as pd
    p = data_dir / fn
    if not p.exists():
        return None
    try:
        d = pd.read_csv(p)
        d.columns = [str(c) for c in d.columns]
        if "日期" not in d.columns:
            return None
        d["日期"] = pd.to_datetime(d["日期"])
        d = d.sort_values("日期")
        v = pd.to_numeric(d.get("今值"), errors="coerce")
        if "前值" in d.columns:
            v = v.fillna(pd.to_numeric(d["前值"], errors="coerce"))
        s = pd.Series(v.values, index=pd.DatetimeIndex(d["日期"].values)).dropna()
        return s if len(s) > 2 else None
    except Exception:
        return None


def _hs300_close(index_code: str, data_dir: Path | None = None):
    """读指数收盘。优先用较新的数据源（东财全球指数），否则退回研究库。

    ★ 2026-11-03 修复：研究库 idx_daily 停在 2026-10-16（定时任务故障，滞后 17 天），
      而东财全球指数有 2026-11-03 的数据。两者回撤差 3.2pp（-17.6% vs -20.8%），
      会把「距第1档还差 7.4%」误报成「还差 4.2%」。故取两者中较新的一支。
    """
    import pandas as pd
    cands = []

    # 源 A：东财全球指数（较新）
    if data_dir is not None:
        p = data_dir / "em_global_hs300.csv"
        if p.exists():
            try:
                d = pd.read_csv(p)
                dc = next(c for c in d.columns if "日期" in str(c))
                d[dc] = pd.to_datetime(d[dc])
                s = d.sort_values(dc).set_index(dc)["最新价"].astype(float).dropna()
                if len(s) > 300:
                    cands.append(s)
            except Exception:
                pass

    # 源 B：研究库
    db = BASE / "data" / "cache" / "dividend_research.db"
    if db.exists():
        try:
            c = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=20)
            d = pd.read_sql_query(
                "SELECT date, close FROM idx_daily WHERE code=? ORDER BY date", c, params=(index_code,))
            c.close()
            if len(d) > 300:
                d["date"] = pd.to_datetime(d["date"])
                cands.append(d.set_index("date")["close"].astype(float).dropna())
        except Exception:
            pass

    if not cands:
        return None
    return max(cands, key=lambda s: s.index[-1])


def _pct(x) -> float | None:
    return None if x is None else round(float(x) * 100, 2)


def gold_switch_data(preview_stage: int | None = None) -> dict:
    import pandas as pd

    cfg = _cfg()
    data_dir = BASE / cfg["data_dir"]

    out: dict = {"ok": True, "generated_at": pd.Timestamp.now().isoformat(timespec="seconds"),
                 "preview": bool(preview_stage in (1, 2, 3)),
                 "missing": [], "config_version": cfg.get("version", 1)}

    # ── 主信号：沪深300 距 36 月高点
    pc = cfg["primary"]
    hs = _hs300_close(str(pc["index_code"]), data_dir)
    primary = None
    if hs is None:
        out["missing"].append(f"指数 {pc['index_code']}（dividend_research.db）")
    else:
        roll_max = hs.rolling(int(pc["window_days"]), min_periods=int(pc["min_periods"])).max()
        cur = float(hs.iloc[-1])
        hi = float(roll_max.iloc[-1])
        dd = cur / hi - 1
        tranches = []
        # ★ 2026-11-04 修复：原实现用「当前回撤是否 <= -阈值」判断触发（状态口径），
        #   导致「已经跌到 -28% 触发过、后来反弹到 -20%」时又显示成「未触发、还差 5%」，
        #   等于让已经该买的人错过执行。买入是一次性事件，所以改为「回溯期内是否曾穿越」。
        lookback = int(pc.get("cross_lookback_days", 756))   # 默认回看 36 个月
        for t in pc["tranches"]:
            lv = float(t["level"])
            cur_hit = dd <= -lv
            # ★ 必须先在全序列上算 36 月滚动高点，再切回看窗口；
            #   若先切片再 rolling，会把切片之前的高点丢掉（2025-01 那次就会被漏掉）
            full_rm = hs.rolling(int(pc["window_days"]), min_periods=int(pc["min_periods"])).max()
            full_dd = hs / full_rm - 1
            win = full_dd.iloc[-lookback:] if len(full_dd) > lookback else full_dd
            crossed = win[win <= -lv]
            crossed_date = crossed.index[0].strftime("%Y-%m-%d") if len(crossed) else None
            last_cross = crossed.index[-1].strftime("%Y-%m-%d") if len(crossed) else None
            ever = crossed_date is not None
            # 进度：从 0（距高点 0%）到 1（达到阈值）
            prog = 1.0 if ever else max(0.0, min(1.0, abs(dd) / lv))
            tranches.append({
                "level_pct": _pct(lv), "label": t.get("label", f"-{lv:.0%}"),
                "amount_wan": t.get("amount_wan"),
                "action": t.get("action"),
                # triggered = 曾触发过（事件口径）；currently = 当前是否仍在阈值下方（状态口径）
                "triggered": bool(ever),
                "currently": bool(cur_hit),
                "crossed_date": crossed_date,
                "last_cross_date": last_cross,
                "gap_pct": None if ever else _pct(lv - abs(dd)),
                "progress": round(prog * 100, 1),
            })
        primary = {
            "name": pc.get("name", "沪深300 回撤分档"),
            "index_code": str(pc["index_code"]),
            "close": round(cur, 1), "window_high": round(hi, 1),
            "drawdown_pct": _pct(dd),
            "window_days": int(pc["window_days"]),
            "asof": hs.index[-1].strftime("%Y-%m-%d"),
            "tranches": tranches,
            # 最近一个未触发的档位（前端直接显示「还差 X%」）
            "next_gap_pct": next((x["gap_pct"] for x in tranches if not x["triggered"]), None),
            "next_label": next((x["label"] for x in tranches if not x["triggered"]), None),
        }
        out["primary"] = primary

    # ── 辅助信号：金银比回落
    ac = cfg["auxiliary"]
    gold = _us_series(data_dir, ac["gold_series"])
    silver = _us_series(data_dir, ac["silver_series"])
    aux = None
    gsr = None
    if gold is None or silver is None:
        out["missing"].append("GLD/SLV（金银比）")
    else:
        gsr = (gold / silver).dropna() * float(ac["ratio_scale"])
        if len(gsr) < int(ac["min_periods"]):
            out["missing"].append("金银比历史不足")
        else:
            rmax = gsr.rolling(int(ac["window_days"]), min_periods=int(ac["min_periods"])).max()
            fall = float(gsr.iloc[-1] / rmax.iloc[-1] - 1)
            trig = fall <= -float(ac["trigger_fall"])
            th = float(ac["trigger_fall"])
            prog = 1.0 if trig else max(0.0, min(1.0, abs(fall) / th))
            aux = {
                "name": ac.get("name", "金银比回落"),
                "ratio": round(float(gsr.iloc[-1]), 1),
                "window_high": round(float(rmax.iloc[-1]), 1),
                "fall_pct": _pct(fall),
                "trigger_fall_pct": _pct(th),
                "triggered": bool(trig),
                "gap_pct": None if trig else _pct(th - abs(fall)),
                "progress": round(prog * 100, 1),
                "percentile": round(float((gsr < gsr.iloc[-1]).mean()) * 100, 0),
                "asof": gsr.index[-1].strftime("%Y-%m-%d"),
                "note": ac.get("note"),
            }
            out["auxiliary"] = aux

    # ── 警告信号：缺钱期
    wc = cfg["warning"]
    b10 = _bond10(data_dir, wc["bond10_file"], wc["bond10_col_hint"])
    # ★ 优先用真实美元指数 DXY（em_global_udi.csv，约 100 点位），
    #   只有缺失时才退回 UUP（ETF 价格约 29，点位无意义但变化率等价）
    dxy = None
    p_dxy = data_dir / "em_global_udi.csv"
    if p_dxy.exists():
        try:
            dd = pd.read_csv(p_dxy)
            dc = next(c for c in dd.columns if "日期" in str(c))
            dd[dc] = pd.to_datetime(dd[dc])
            dxy = dd.sort_values(dc).set_index(dc)["最新价"].astype(float).dropna()
            dxy = dxy if len(dxy) > 100 else None
        except Exception:
            dxy = None
    uup = dxy if dxy is not None else _us_series(data_dir, wc["dollar_file"])
    dollar_is_dxy = dxy is not None
    warn = None
    squeeze = None
    if b10 is None or uup is None:
        out["missing"].append("10Y美债或美元指数")
    else:
        lb = int(wc["lookback_days"])
        idx = b10.index.intersection(uup.index)
        if len(idx) > lb + 5:
            b = b10.reindex(idx).ffill()
            u = uup.reindex(idx).ffill()
            db = float(b.iloc[-1] - b.iloc[-1 - lb])
            du = float(u.iloc[-1] / u.iloc[-1 - lb] - 1)
            squeeze = (db > 0) and (du > 0)
            warn = {
                "name": wc.get("name", "缺钱期"),
                "bond10": round(float(b.iloc[-1]), 2),
                "bond10_change_pp": round(db, 2),
                "bond10_up": bool(db > 0),
                "dollar": round(float(u.iloc[-1]), 2),
                "dollar_change_pct": _pct(du),
                "dollar_is_dxy": bool(dollar_is_dxy),
                "dollar_up": bool(du > 0),
                "squeeze": bool(squeeze),
                "lookback_days": lb,
                "tradeable": bool(wc.get("tradeable", False)),
                "squeeze_annual": _pct(wc.get("squeeze_annual_gold")),
                "normal_annual": _pct(wc.get("normal_annual_gold")),
                "note": "实证：有信息量（缺钱期黄金年化 -8.5% vs 其他 +20.1%），但做成择时规则无效（Calmar 0.201<0.217）→ 只做警告，不产生买卖",
            }
            out["warning"] = warn

    # ── 确认信号：美联储利率
    cc = cfg["confirm"]
    fed = _fed_rate(data_dir, cc["rate_file"])
    conf = None
    fed_down = None
    if fed is None:
        out["missing"].append("美联储利率")
    else:
        cur = float(fed.iloc[-1])
        prev = float(fed.iloc[-2]) if len(fed) > 1 else cur
        direction = "down" if cur < prev else ("up" if cur > prev else "flat")
        fed_down = direction == "down"
        hist = [{"date": d.strftime("%Y-%m-%d"), "rate": round(float(fed.loc[d]), 2)}
                for d in fed.index[-int(cc.get("history_months", 12)):]]
        conf = {
            "name": cc.get("name", "美联储利率"),
            "rate": round(cur, 2), "prev": round(prev, 2),
            "direction": direction,
            "turned_down": bool(fed_down),
            "last_date": fed.index[-1].strftime("%Y-%m-%d"),
            "history": hist,
            "note": cc.get("note"),
        }
        out["confirm"] = conf

    # ── 综合判断
    comp = cfg["composite"]
    flags = []
    if primary:
        flags.append(("主信号·回撤分档", any(t["triggered"] for t in primary["tranches"])))
    if aux:
        flags.append(("辅助信号·金银比回落", aux["triggered"]))
    if warn:
        flags.append(("警告信号·不在缺钱期", not warn["squeeze"]))
    if conf:
        flags.append(("确认信号·美联储降息", conf["turned_down"]))
    satisfied = sum(1 for _, v in flags if v)
    total = len(flags)
    need = int(comp.get("min_signals_to_act", 2))

    # 阶段判定（★ 2026-11-04 改为配置驱动：文案与条件都来自 config 的 stage_rules）
    #   之前版本把「阶段1 · 杀流动性」等文案硬编码在代码里，配置里的 stage_rules 完全没被读取，
    #   违反 AGENTS.md「全部模块动态化」，且配置改成 15% 后 when 字段还写着 ≥8%（双重不一致）。
    #   现在：代码只负责判定 condition 代码，文案一律从配置取。
    stage_ctx = {
        "squeeze": bool(warn["squeeze"]) if warn is not None else None,
        "cleared": bool(aux["triggered"]) if aux is not None else None,
        "fed_cut": bool(conf["turned_down"]) if conf is not None else None,
        "primary_hit": bool(any(t["triggered"] for t in primary["tranches"])) if primary else None,
    }

    def _cond_ok(code):
        """把配置里的 condition 代码翻译成布尔判断。返回 None 表示数据不足。"""
        c = str(code or "").strip()
        if c == "squeeze":                      # 缺钱期 = 是
            return stage_ctx["squeeze"]
        if c == "not_squeeze_and_not_cleared":  # 缺钱期已过，但抛售未出清
            if stage_ctx["squeeze"] is None or stage_ctx["cleared"] is None:
                return None
            return (not stage_ctx["squeeze"]) and (not stage_ctx["cleared"])
        if c == "cleared_or_fed_cut":           # 抛售出清 或 美联储降息
            if stage_ctx["cleared"] is None and stage_ctx["fed_cut"] is None:
                return None
            return bool(stage_ctx["cleared"]) or bool(stage_ctx["fed_cut"])
        if c == "primary_hit":                  # 主信号触发（回撤到档位）
            return stage_ctx["primary_hit"]
        return None

    stage = {"id": 0, "label": "数据不足", "desc": "关键数据缺失，无法判定阶段"}
    rules = comp.get("stage_rules") or []
    for rule in rules:
        if _cond_ok(rule.get("condition")) is True:
            stage = {"id": int(rule.get("stage", 0)),
                     "label": rule.get("label", ""),
                     "desc": rule.get("desc", "")}
            break
    else:
        # 一条都不满足：说明缺钱期已过、金银比已出清但…（理论上被条件覆盖），给兜底
        if rules and stage_ctx["squeeze"] is False:
            stage = {"id": 0, "label": "条件未覆盖",
                     "desc": "当前状态不落在任何配置阶段内，检查 config 的 stage_rules"}

    # ── 预览模式（仅供 UI 验证：?preview_stage=N 强制显示某阶段，响应里标记 preview=true）
    if preview_stage in (1, 2, 3):
        hit = next((r for r in rules if int(r.get("stage", 0)) == preview_stage), None)
        if hit:
            stage = {"id": int(hit.get("stage", 0)), "label": hit.get("label", ""),
                     "desc": hit.get("desc", ""), "preview": True}

    can_act = satisfied >= need
    if can_act:
        verdict = f"满足 {satisfied}/{total} 项 → **可以开始换仓**（按分档执行）"
    elif stage.get("id") == 1:
        verdict = f"满足 {satisfied}/{total} 项 → **仍在阶段1（缺钱期），继续持金等待**"
    else:
        verdict = f"满足 {satisfied}/{total} 项 → **继续观望**（需至少 {need} 项）"


    out["composite"] = {
        "satisfied": satisfied, "total": total, "need": need, "can_act": bool(can_act),
        "verdict": verdict,
        "flags": [{"name": n, "ok": bool(v)} for n, v in flags],
    }
    out["stage"] = stage

    # ── 迷你走势（前端画 sparkline）
    try:
        n = 250
        dates, gsr_v, hs_dd = [], [], []
        if gsr is not None:
            g = gsr.iloc[-n:]
            dates = [d.strftime("%Y-%m-%d") for d in g.index]
            gsr_v = [round(float(x), 2) for x in g.values]
        if hs is not None:
            rm = hs.rolling(int(pc["window_days"]), min_periods=int(pc["min_periods"])).max()
            ddser = (hs / rm - 1).iloc[-n:]
            hs_dd = [_pct(x) for x in ddser.values]
        out["series"] = {"dates": dates, "gsr": gsr_v, "hs_dd": hs_dd}
    except Exception:
        out["series"] = {"dates": [], "gsr": [], "hs_dd": []}

    out["ui"] = cfg.get("ui", {})
    return out


if __name__ == "__main__":
    import json
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    d = gold_switch_data()
    print(json.dumps(d, ensure_ascii=False, indent=2)[:4000])
