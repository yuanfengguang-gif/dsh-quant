# -*- coding: utf-8 -*-
"""deck/paper_api.py —— 模拟盘数据接口

读 data/cache/paper.db（由 scripts/paper_trade.py 写入）与 config/paper_trading.yaml。
"""
from __future__ import annotations
import sqlite3
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parents[1]
DB = BASE / "data" / "cache" / "paper.db"
CFG = BASE / "config" / "paper_trading.yaml"


def _cfg() -> dict:
    try:
        import yaml
        with open(CFG, encoding="utf-8") as f:
            return yaml.safe_load(f)["sim"]
    except Exception:
        return {}


def paper_data() -> dict:
    out = {"ok": False, "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    try:
        cfg = _cfg()
        out["sim"] = {
            "name": cfg.get("name"),
            "capital": cfg.get("capital"),
            "cash_pool_months": cfg.get("cash_pool_months"),
            "monthly_withdrawal": cfg.get("monthly_withdrawal"),
            "start_date": cfg.get("start_date"),
            "build_days": cfg.get("build_days"),
            "build_tranches": cfg.get("build_tranches"),
        }
        out["assets"] = [
            {"code": a["code"], "name": a["name"], "weight": a["weight"]}
            for a in (cfg.get("assets") or [])
        ]
        if not DB.exists():
            out["error"] = "模拟盘数据库不存在，请先运行 python scripts/paper_trade.py"
            return out

        con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
        nav = pd.read_sql_query("SELECT * FROM nav_daily ORDER BY date", con)
        try:
            hold = pd.read_sql_query(
                "SELECT * FROM holdings WHERE date=(SELECT MAX(date) FROM holdings)", con)
        except Exception:
            hold = pd.DataFrame()
        con.close()

        if len(nav) == 0:
            out["error"] = "还没有净值记录，请先运行 scripts/paper_trade.py"
            return out

        nav["nav"] = pd.to_numeric(nav["nav"], errors="coerce")
        nav["total"] = pd.to_numeric(nav["total"], errors="coerce")
        # 先算回撤列，再取 last（顺序不能反）
        nav["peak"] = nav["total"].cummax()
        nav["dd"] = nav["total"] / nav["peak"] - 1
        last = nav.iloc[-1]
        cap = float(cfg.get("capital") or 1_500_000)
        days = max(1, (pd.Timestamp(last["date"]) - pd.Timestamp(nav["date"].iloc[0])).days)
        mdd = float(nav["dd"].min())
        ann = (float(last["nav"]) ** (365.25 / days) - 1) if days > 3 else None

        bench_v, excess = None, None
        if pd.notna(last.get("bench")):
            bench_v = float(last["bench"])
            excess = (float(last["nav"]) - bench_v) * 100

        out["latest"] = {
            "date": str(last["date"]),
            "total": float(last["total"]),
            "invested": float(last["invested"]),
            "cash": float(last["cash"]),
            "nav": float(last["nav"]),
            "bench": bench_v,
            "pnl": float(last["total"]) - cap,
            "pnl_pct": float(last["nav"]) - 1.0,
            "dd": float(last["dd"]),
            "pos": last.get("pos"),
        }
        out["stats"] = {
            "mdd": mdd,
            "ann": ann,
            "days": days,
            "records": int(len(nav)),
            "excess_pp": excess,
        }
        out["history"] = [
            {"date": str(r.date), "total": float(r.total), "invested": float(r.invested),
             "cash": float(r.cash), "nav": float(r.nav),
             "bench": (None if pd.isna(r.bench) else float(r.bench)),
             "dd": float(r.dd), "pos": r.pos}
            for r in nav.itertuples()
        ]
        if len(hold):
            out["holdings"] = [
                {"code": str(r.code), "shares": float(r.shares),
                 "price": float(r.price), "mv": float(r.mv),
                 "weight": float(r.mv) / float(hold["mv"].sum()) if hold["mv"].sum() else 0}
                for r in hold.itertuples()
            ]
        else:
            out["holdings"] = []

        # 建仓进度：从 history 里数「建仓中」→「满仓」的切换
        try:
            _cc = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=15)
            _m = dict(_cc.execute("SELECT k,v FROM sim_meta").fetchall())
            _cc.close()
        except Exception:
            _m = {}
        total_t = int(_m.get("build_total") or cfg.get("build_tranches") or 5)
        done_t = int(_m.get("build_done") or 0)
        out["build"] = {"total": total_t, "done": done_t,
                        "spent": float(_m.get("spent") or 0),
                        "pos": last.get("pos")}
        out["ok"] = True
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


if __name__ == "__main__":
    import json, sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps(paper_data(), ensure_ascii=False, indent=2, default=str))
