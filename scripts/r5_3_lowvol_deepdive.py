# -*- coding: utf-8 -*-
"""scripts/r5_3_lowvol_deepdive.py —— R5-3 数据补全 + 红利低波专项深挖

任务：515450 补数据 / 费率 / 跟踪指数 / 分年表现（牛市检验）/ 行业集中度
产出：reports/r5_3_lowvol_deepdive.json
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, r"C:\Users\Lenovo\.dsh\skills\tdx-aidata")
sys.path.insert(0, r"C:\Users\Lenovo\.dsh\skills\tdx-aidata\lib")

from tdxaidata import tqs  # noqa: E402

START = "2005-01-01"
END = "2026-10-17"
LOWVOL = ["512890.SH", "515450.SH", "515100.SH", "515300.SH"]
PURE = ["510880.SH", "515080.SH", "515180.SH"]
BENCH = "510300.SH"
ALL = LOWVOL + PURE + [BENCH]

IDX_CODE = {
    "中证红利低波动指数": ("H30269", "中证红利低波动"),
    "中证红利低波动100指数": ("930955", "红利低波100"),
    "沪深300红利低波动指数": ("无", "沪深300红利低波动（代码未取到）"),
    "标普中国A股大盘红利低波50指数": ("无", "标普中国A股大盘红利低波50（代码未取到）"),
    "上证红利指数": ("000015", "红利指数"),
    "中证红利指数": ("000922", "中证红利"),
    "沪深300指数": ("000300", "沪深300"),
}


def fetch(code: str, adj: str = "back"):
    r = tqs.get_market_data(field_list=["Close"], stock_list=[code], period="1d",
                            start_time=START, end_time=END, dividend_type=adj)
    c = r.get("Close")
    if c is None or len(c) == 0:
        return None
    s = c.iloc[:, 0].dropna()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def metrics(px: pd.Series) -> dict:
    r = px.pct_change().dropna()
    if len(r) < 2:
        return {}
    nav = px / px.iloc[0]
    ann = float(nav.iloc[-1] ** (252 / len(r)) - 1)
    dd = float((nav / nav.cummax() - 1).min())
    return {"annual": round(ann, 4), "vol": round(float(r.std() * np.sqrt(252)), 4),
            "sharpe": round(float(r.mean() / r.std() * np.sqrt(252)), 3) if r.std() > 0 else None,
            "max_drawdown": round(dd, 4), "start": str(px.index[0])[:10], "end": str(px.index[-1])[:10],
            "n_days": int(len(px))}


def main() -> int:
    import akshare as ak
    out = {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "meta": {"task": "R5-3 数据补全 + 红利低波深挖", "pool": ALL,
                    "note": "收益用通达信后复权（含分红再投）；费率/跟踪标的用天天基金基本概况"}}

    series = {}
    out["etf"] = {}
    for code in ALL:
        b = fetch(code, "back")
        if b is None:
            out["etf"][code] = {"error": "无数据"}
            continue
        series[code] = b
        out["etf"][code] = metrics(b)
        out["etf"][code]["n_splits"] = 0
        try:
            ov = ak.fund_overview_em(symbol=code[:6]).iloc[0]
            def fee(x):
                m = re.search(r"([\d.]+)%", str(x))
                return round(float(m.group(1)) / 100, 4) if m else 0.0
            out["etf"][code].update({
                "name": ov.get("基金简称"), "fee_mgmt": fee(ov.get("管理费率")),
                "fee_custody": fee(ov.get("托管费率")), "fee_sales": fee(ov.get("销售服务费率")),
                "tracking": ov.get("跟踪标的"), "aum": str(ov.get("净资产规模")),
            })
            out["etf"][code]["fee_total"] = round(out["etf"][code]["fee_mgmt"] + out["etf"][code]["fee_custody"] + out["etf"][code]["fee_sales"], 4)
        except Exception as e:
            out["etf"][code].update({"name": "", "fee_mgmt": "无", "fee_custody": "无", "fee_sales": "无", "tracking": "无", "error_fee": str(e)[:80]})
        print(code, out["etf"][code].get("name"), "fee", out["etf"][code].get("fee_total"), "track", out["etf"][code].get("tracking"), flush=True)

    # 跟踪指数成分
    out["indices"] = {}
    for name, (code, label) in IDX_CODE.items():
        item = {"code": code, "name": label, "n_constituents": None}
        if code != "无":
            try:
                df = ak.index_stock_cons_csindex(symbol=code)
                item["n_constituents"] = int(len(df))
                item["index_name_api"] = df["指数名称"].iloc[0] if "指数名称" in df.columns else None
            except Exception as e:
                item["error"] = str(e)[:80]
        out["indices"][name] = item

    # 分年收益
    years = list(range(2019, 2027))
    yearly = {}
    for y in years:
        row = {"year": y, "bench": None, "lowvol": {}, "pure": {}}
        for code in ALL:
            if code not in series:
                continue
            s = series[code]
            sy = s[(s.index >= pd.Timestamp(f"{y}-01-01")) & (s.index <= pd.Timestamp(f"{y}-12-31"))]
            if len(sy) < 20:
                continue
            ret = float(sy.iloc[-1] / sy.iloc[0] - 1)
            if code == BENCH:
                row["bench"] = round(ret, 4)
            elif code in LOWVOL:
                row["lowvol"][code] = round(ret, 4)
            else:
                row["pure"][code] = round(ret, 4)
        b = row["bench"]
        row["type"] = ("牛" if b is not None and b > 0.15 else ("熊" if b is not None and b < -0.10 else "震荡"))
        lows = [v for v in row["lowvol"].values()]
        row["lowvol_mean"] = round(float(np.mean(lows)), 4) if lows else None
        row["mean_excess"] = round(row["lowvol_mean"] - b, 4) if (row["lowvol_mean"] is not None and b is not None) else None
        yearly[str(y)] = row
    out["yearly"] = yearly
    bull = [v["mean_excess"] for v in yearly.values() if v["type"] == "牛" and v["mean_excess"] is not None]
    bear = [v["mean_excess"] for v in yearly.values() if v["type"] == "熊" and v["mean_excess"] is not None]
    out["summary_year"] = {"bull_mean_excess": round(float(np.mean(bull)), 4) if bull else None,
                           "bear_mean_excess": round(float(np.mean(bear)), 4) if bear else None,
                           "n_bull": len(bull), "n_bear": len(bear)}

    # 行业集中度（最新季度前十大）
    out["holdings"] = {}
    for code in LOWVOL + PURE:
        try:
            df = ak.fund_portfolio_hold_em(symbol=code[:6], date="2026")
            if df is None or len(df) == 0:
                raise RuntimeError("空")
            q = df["季度"].iloc[0]
            d = df[df["季度"] == q].head(10)
            top = []
            for _, r in d.iterrows():
                top.append({"code": str(r["股票代码"]).zfill(6), "name": r["股票名称"], "weight": round(float(r["占净值比例"]) / 100, 4)})
            # 行业（通达信细分行业 + 申万一级近似映射）
            SW_MAP = {
                "地方性银行": "银行", "全国性银行": "银行", "股份制银行": "银行", "银行": "银行",
                "煤炭开采": "煤炭", "焦炭": "煤炭",
                "电力": "公用事业", "燃气": "公用事业", "水务": "公用事业",
                "高速公路": "交通运输", "铁路": "交通运输", "港口": "交通运输", "航运": "交通运输", "机场": "交通运输",
                "钢铁": "钢铁", "特钢": "钢铁",
                "房地产开发": "房地产", "园区开发": "房地产",
                "建筑装饰": "建筑装饰", "基础建设": "建筑装饰", "房屋建设": "建筑装饰",
                "服装家纺": "纺织服饰", "纺织": "纺织服饰",
                "食品加工": "食品饮料", "饮料制造": "食品饮料", "白酒": "食品饮料", "食品饮料": "食品饮料",
                "油气开采": "石油石化", "石油化工": "石油石化", "炼化及贸易": "石油石化",
                "中药": "医药生物", "化学制药": "医药生物", "生物制品": "医药生物",
                "通用设备": "机械设备", "专用设备": "机械设备", "自动化设备": "机械设备",
                "白色家电": "家用电器", "黑色家电": "家用电器", "小家电": "家用电器",
                "公路铁路": "交通运输", "航运港口": "交通运输",
                "冶钢原料": "钢铁", "能源金属": "有色金属", "工业金属": "有色金属", "小金属": "有色金属",
            }
            inds = {}
            for t in top:
                suffix = ".SH" if t["code"].startswith(("6", "5")) else ".SZ"
                try:
                    info = tqs.get_stock_info(t["code"] + suffix)
                    ind = info.get("rs_hyname") or "无"
                except Exception:
                    ind = "无"
                t["industry_tdx"] = ind
                t["industry"] = SW_MAP.get(ind, ind)
                inds[t["industry"]] = round(inds.get(t["industry"], 0) + t["weight"], 4)
            top5 = sorted(inds.items(), key=lambda x: -x[1])[:5]
            out["holdings"][code] = {"quarter": q, "top10": top, "top10_weight": round(sum(t["weight"] for t in top), 4),
                                     "industries": dict(top5), "ind_sum": round(sum(v for _, v in top5), 4),
                                     "first": top[0] if top else None}
            print(code, q, "top10", out["holdings"][code]["top10_weight"], "ind", top5, flush=True)
        except Exception as e:
            out["holdings"][code] = {"error": str(e)[:100]}

    # 前十大重合度（4 只低波）
    sets = []
    for code in LOWVOL:
        h = out["holdings"].get(code, {})
        sets.append(set(t["code"] for t in h.get("top10", [])))
    overlap = set.intersection(*sets) if all(sets) else set()
    out["overlap"] = {"n_common_in_top10": len(overlap), "codes": sorted(overlap)}

    rp = BASE / "reports" / "r5_3_lowvol_deepdive.json"
    rp.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("saved", rp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
