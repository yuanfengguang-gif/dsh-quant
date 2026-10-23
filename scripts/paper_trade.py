# -*- coding: utf-8 -*-
"""scripts/paper_trade.py —— 养老模拟盘：每日跟踪收益

用法：
    python scripts/paper_trade.py              # 增量更新到今天
    python scripts/paper_trade.py --asof 2026-10-28
    python scripts/paper_trade.py --rebuild    # 清空重跑

数据：ETF 日线缓存到 data/cache/paper.db（首次拉全量，之后增量）
输出：reports/模拟盘日报_<date>.md + data/paper/nav_history.csv
"""
from __future__ import annotations
import sys, time, sqlite3, argparse
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parents[1]
CFG_PATH = BASE / "config" / "paper_trading.yaml"
DB = BASE / "data" / "cache" / "paper.db"
OUTDIR = BASE / "reports"
DATADIR = BASE / "data" / "paper"


def load_cfg() -> dict:
    import yaml
    with open(CFG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)["sim"]


def db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, timeout=30)
    c.execute("""CREATE TABLE IF NOT EXISTS etf_daily(
        code TEXT, date TEXT, close REAL, PRIMARY KEY(code, date))""")
    c.execute("""CREATE TABLE IF NOT EXISTS nav_daily(
        date TEXT PRIMARY KEY, invested REAL, cash REAL, total REAL,
        nav REAL, bench REAL, pos TEXT)""")
    c.execute("CREATE TABLE IF NOT EXISTS sim_meta(k TEXT PRIMARY KEY, v TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS bench_daily(date TEXT PRIMARY KEY, close REAL)")
    c.execute("""CREATE TABLE IF NOT EXISTS holdings(
        date TEXT, code TEXT, shares REAL, price REAL, mv REAL, PRIMARY KEY(date, code))""")
    return c


def fetch_us(code: str, start: str, end: str, retries: int = 4) -> pd.DataFrame:
    """美股 ETF：取美元价，按当日中行中间价折成人民币（这样下游代码不用改）"""
    import akshare as ak
    fx_path = BASE / "data" / "cache" / "usdcny.csv"
    last = None
    for k in range(retries):
        try:
            df = ak.stock_us_daily(symbol=code)
            df.columns = [str(c) for c in df.columns]
            df["date"] = pd.to_datetime(df["date"])
            s = df.set_index("date")["close"].astype(float)
            s = s[(s.index >= pd.Timestamp(start)) & (s.index <= pd.Timestamp(end))]
            if len(s) == 0:
                # 美股当日尚未收盘 / 数据未更新 → 正常返回空表，不当作失败
                return pd.DataFrame(columns=["date", "close"])
            # 汇率
            if fx_path.exists():
                fx = pd.read_csv(fx_path, index_col=0, parse_dates=True).iloc[:, 0]
            else:
                f = ak.currency_boc_sina(symbol="美元", start_date="20050101", end_date="20261021")
                f.columns = [str(c) for c in f.columns]
                f["日期"] = pd.to_datetime(f["日期"])
                fx = f.set_index("日期")["央行中间价"].astype(float) / 100.0
                fx_path.parent.mkdir(parents=True, exist_ok=True)
                fx.to_csv(fx_path)
            fxs = fx.reindex(s.index).ffill()
            # 央行中间价通常比美股晚 1 天发布；缺失时沿用最近一个可用汇率，
            # 否则 dropna 会把整行删掉，导致美股价格永远更新不进来（R157 修复）
            if fxs.isna().any():
                fxs = fxs.fillna(float(fx.dropna().iloc[-1]))
            cny = (s * fxs).dropna()
            if len(cny) == 0:
                raise RuntimeError("人民币折算后为空")
            return pd.DataFrame({"date": cny.index.strftime("%Y-%m-%d"), "close": cny.to_numpy()})
        except Exception as e:
            last = e
            time.sleep(2 + 2 * k)
    raise RuntimeError(f"{code}(US) 取数失败：{type(last).__name__}: {last}")


_TDX_PKG_URL = "https://www.tdx.com.cn/products/data/data/g4day/{ymd}.zip"
_TDX_CACHE_DIR = BASE / "data" / "cache" / "tdx_pkg"


def _tdx_day_closes(ymd: str) -> dict | None:
    """下载并解析通达信官网某一交易日的盘后包，返回 {6位代码: 收盘价}。

    非交易日 / 当日包尚未发布（官网 404）返回 None；不抛错。
    解析结果按日缓存到 data/cache/tdx_pkg/{ymd}.json，避免重复下载 2.6MB。
    """
    import json, io, zipfile, struct, math
    import requests

    cf = _TDX_CACHE_DIR / f"{ymd}.json"
    if cf.exists():
        try:
            return json.loads(cf.read_text(encoding="utf-8"))
        except Exception:
            pass

    url = _TDX_PKG_URL.format(ymd=ymd)
    r = requests.get(url, timeout=(10, 90))
    if r.status_code == 404:
        return None                       # 非交易日或尚未发布
    if r.status_code != 200 or not r.content.startswith(b"PK"):
        raise RuntimeError(f"通达信盘后包 {ymd} 异常：HTTP {r.status_code}，非 zip")

    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(z.namelist())
    short = ymd[2:]
    out = {}
    for mkt in ("sh", "sz", "bj"):
        cn, mn = f"{mkt}{short}.cod", f"{mkt}{short}.md1"
        if cn not in names or mn not in names:
            continue
        cod, md1 = z.read(cn), z.read(mn)
        if len(cod) % 150 or len(md1) % 512:
            continue
        for off in range(0, len(cod), 150):
            rec = cod[off:off + 150]
            code = rec[0:6].rstrip(b"\x00 ").decode("ascii", "replace")
            if len(code) != 6 or not code.isdigit():
                continue
            seq = struct.unpack("<H", rec[32:34])[0]
            blk = md1[seq * 512:(seq + 1) * 512]
            if len(blk) != 512:
                continue
            close = struct.unpack("<d", blk[36:44])[0]     # 收盘价（不是最低价！）
            if math.isfinite(close) and close > 0:
                out[code] = round(float(close), 4)

    if not out:
        return None
    _TDX_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cf.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def fetch_etf_tdx(code: str, start: str, end: str,
                  max_days: int = 40, retries: int = 2) -> pd.DataFrame:
    """通达信官网盘后包 —— A 股 / ETF 的【第一优先数据源】

    每个交易日一个全市场包（约 2.6MB），按日缓存解析结果。
    区间工作日数超过 max_days 时不走这条（避免一次下载上百个包），
    交给腾讯 K 线（历史更深）。区间内无数据返回空表，不抛错。
    """
    d0, d1 = pd.Timestamp(start), pd.Timestamp(end)
    days = [d for d in pd.date_range(d0, d1, freq="B")]
    if not days or len(days) > max_days:
        return pd.DataFrame(columns=["date", "close"])

    rows, last_err = [], None
    for d in days:
        ymd = d.strftime("%Y%m%d")
        closes = None
        for k in range(retries):
            try:
                closes = _tdx_day_closes(ymd)
                break
            except Exception as e:
                last_err = e
                time.sleep(1 + k)
        if closes and str(code) in closes:
            rows.append({"date": d.strftime("%Y-%m-%d"), "close": float(closes[str(code)])})

    if rows:
        return pd.DataFrame(rows).drop_duplicates("date").sort_values("date").reset_index(drop=True)
    if last_err is not None and len(days) == 1:
        # 单日且每个包都下载失败 → 视为真失败，让上层走备选
        raise RuntimeError(f"{code} 通达信盘后包取数失败：{type(last_err).__name__}: {last_err}")
    return pd.DataFrame(columns=["date", "close"])


def fetch_etf_tencent(code: str, start: str, end: str, count: int = 640,
                      retries: int = 3) -> pd.DataFrame:
    """腾讯 K 线（不复权）—— A 股 / ETF 的【主数据源】

    依据工作区 a-stock-data §1.2：腾讯是 mootdx K 线失效后的主力源，
    零鉴权、不封 IP、当日收盘后即可取到当天数据；东财只用于其独有数据。

    返回列 date(str) / close(float)。区间内无数据时返回空表（不抛错）。
    """
    import requests
    hosts = ["https://web.ifzq.gtimg.cn", "https://proxy.finance.qq.com/ifzqgtimg",
             "https://ifzq.gtimg.cn"]
    sym = ("sh" if str(code).startswith(("5", "6")) else "sz") + str(code)
    param = f"{sym},day,,,{int(count)},"          # 末尾空 = 不复权
    last_err = None
    for k in range(retries):
        for h in hosts:
            try:
                r = requests.get(h + "/appstock/app/fqkline/get", params={"param": param},
                                 headers={"Referer": "https://gu.qq.com/"}, timeout=(8, 20))
                if r.status_code != 200 or not r.text.strip():
                    raise RuntimeError(f"HTTP {r.status_code}")
                payload = r.json()
                node = (payload.get("data") or {}).get(sym) or {}
                items = node.get("day") or node.get("qfqday") or []
                rows = []
                for it in items:
                    d = str(it[0])[:10]
                    if start <= d <= end:
                        rows.append({"date": d, "close": float(it[2])})
                if rows:
                    df = pd.DataFrame(rows).drop_duplicates("date").sort_values("date")
                    return df.reset_index(drop=True)
                return pd.DataFrame(columns=["date", "close"])   # 当日行情尚未生成
            except Exception as e:
                last_err = e
        time.sleep(2 + 2 * k)
    raise RuntimeError(f"{code} 腾讯取数失败：{type(last_err).__name__}: {last_err}")


def fetch_etf(code: str, start: str, end: str, retries: int = 4) -> pd.DataFrame:
    """取 ETF 日线（不复权收盘价）。主源新浪（全历史），备源东财。"""
    import akshare as ak

    def _sina():
        sym = ("sh" if code.startswith(("5", "6")) else "sz") + code
        df = ak.fund_etf_hist_sina(symbol=sym)
        df.columns = [str(c) for c in df.columns]
        d = df[["date", "close"]].copy()
        d["date"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m-%d")
        d["close"] = pd.to_numeric(d["close"], errors="coerce")
        d = d.dropna()
        return d[(d["date"] >= start) & (d["date"] <= end)]

    def _em():
        df = ak.fund_etf_hist_em(symbol=code, period="daily",
                                 start_date=start.replace("-", ""),
                                 end_date=end.replace("-", ""), adjust="")
        df.columns = [str(c) for c in df.columns]
        d = df[["日期", "收盘"]].copy()
        d.columns = ["date", "close"]
        d["date"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m-%d")
        d["close"] = pd.to_numeric(d["close"], errors="coerce")
        return d.dropna()

    last = None
    for k in range(retries):
        # ① 通达信官网盘后包（第一优先）+ ② 腾讯 K 线（第二优先，同时补齐通达信当日包未发布的那天）
        d_tdx = d_tx = None
        try:
            d_tdx = fetch_etf_tdx(code, start, end)
        except Exception as e:
            last = e
        try:
            d_tx = fetch_etf_tencent(code, start, end)
        except Exception as e:
            last = e
        frames = [x for x in (d_tdx, d_tx) if x is not None and len(x)]
        if frames:
            merged = pd.concat(frames, ignore_index=True)
            merged = (merged.drop_duplicates("date", keep="first")
                            .sort_values("date").reset_index(drop=True))
            return merged
        # ③ 新浪（全历史，不封 IP）
        try:
            d = _sina()
            if d is not None and len(d):
                return d
        except Exception as e:
            last = e
        # ④ 东财（末位兜底）
        try:
            d = _em()
            if d is not None and len(d):
                return d
        except Exception as e:
            last = e
        time.sleep(2 + 2 * k)
    raise RuntimeError(f"{code} 取数失败：{type(last).__name__}: {last}")


def update_etf_cache(c, codes, start, end, markets=None):
    """增量更新 ETF 缓存；markets: {code: 'cn'|'us'}"""
    markets = markets or {}
    for code in codes:
        row = c.execute("SELECT MAX(date) FROM etf_daily WHERE code=?", (code,)).fetchone()
        have = row[0] if row and row[0] else None
        s = start if not have else (pd.Timestamp(have) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        if s > end:
            continue
        try:
            d = (fetch_us if markets.get(code) == "us" else fetch_etf)(code, s, end)
            if len(d):
                c.executemany("INSERT OR REPLACE INTO etf_daily(code,date,close) VALUES(?,?,?)",
                              [(code, r.date, float(r.close)) for r in d.itertuples()])
                c.commit()
                print(f"  ETF {code}: +{len(d)} 行（{d['date'].iloc[0]} ~ {d['date'].iloc[-1]}）")
        except Exception as e:
            print(f"  ⚠️ ETF {code} 更新失败（沿用旧缓存）：{e}")


def update_bench_remote(start, end):
    """从网络补基准（H20269 全收益）到 dividend_research.db，失败不致命"""
    try:
        import akshare as ak
        df = ak.stock_zh_index_hist_csindex(symbol="H20269",
                                           start_date=start.replace("-", ""),
                                           end_date=end.replace("-", ""))
        if df is None or len(df) == 0:
            return 0
        df.columns = [str(x) for x in df.columns]
        d = df[["日期", "收盘"]].copy()
        d.columns = ["date", "close"]
        d["date"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m-%d")
        d["close"] = pd.to_numeric(d["close"], errors="coerce")
        d = d.dropna()
        src = BASE / "data" / "cache" / "dividend_research.db"
        cc = sqlite3.connect(src, timeout=30)
        cc.execute("CREATE TABLE IF NOT EXISTS idx_daily(code TEXT, date TEXT, open REAL, high REAL, "
                   "low REAL, close REAL, amount REAL, pe_ttm REAL, PRIMARY KEY(code,date))")
        cc.executemany(
            "INSERT OR REPLACE INTO idx_daily(code,date,close) VALUES('H20269',?,?)",
            [(r.date, float(r.close)) for r in d.itertuples()])
        cc.commit(); cc.close()
        return len(d)
    except Exception as e:
        print(f"  ⚠️ 基准补数失败（沿用本地）：{type(e).__name__}: {str(e)[:60]}")
        return 0


def fetch_bench(c, start, end):
    """基准：红利低波全收益 H20269（来自 dividend_research.db）"""
    src = BASE / "data" / "cache" / "dividend_research.db"
    c2 = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True, timeout=30)
    d = pd.read_sql_query(
        "SELECT date,close FROM idx_daily WHERE code='H20269' AND date>=? AND date<=? ORDER BY date",
        c2, params=(start, end))
    c2.close()
    if len(d) == 0:
        print("  ⚠️ 基准在该区间无数据（本地基准库截至 2026-10-16），超额收益暂不可算")
        return
    d["date"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m-%d")
    c.executemany("INSERT OR REPLACE INTO bench_daily(date,close) VALUES(?,?)",
                  [(r.date, float(r.close)) for r in d.itertuples()])
    c.commit()


def build_schedule(cfg):
    """固定日历建仓日程：start_date 起 build_days 自然日内分 N 次等额买入。

    返回计划日期列表（自然日）。实际成交落在「第一个 >= 计划日 的交易日」，
    这样即使数据还没到，日程也不会坍缩成 1 天。
    """
    start = pd.Timestamp(cfg["start_date"])
    days = int(cfg["build_days"])
    n = int(cfg["build_tranches"])
    if n <= 1:
        return [start.strftime("%Y-%m-%d")]
    step = days / (n - 1)
    return [(start + pd.Timedelta(days=round(k * step))).strftime("%Y-%m-%d")
            for k in range(n)]


def simulate(cfg, c, asof: str):
    """逐日模拟：建仓 → 持有 → 每月提款 → 分红入账"""
    codes = [a["code"] for a in cfg["assets"]]
    w = {a["code"]: float(a["weight"]) for a in cfg["assets"]}
    cap = float(cfg["capital"])
    mwd = float(cfg["monthly_withdrawal"])
    pool = mwd * int(cfg["cash_pool_months"])
    invest = cap - pool
    fee_buy = float(cfg["fee"]["buy"])

    plan = build_schedule(cfg)                      # 计划日（自然日）
    per = invest / len(plan)                        # 每次投入金额
    shares = {k: 0.0 for k in codes}
    cash = cap                                      # 现金初始 = 全部本金
    spent = 0.0
    done = set()                                    # 已执行的批次序号

    ph = ",".join("?" * len(codes))
    px = {}
    rows = c.execute(
        f"SELECT code,date,close FROM etf_daily WHERE code IN ({ph}) AND date>=? AND date<=? ORDER BY date",
        (*codes, cfg["start_date"], asof)).fetchall()
    for code, dt, cl in rows:
        px.setdefault(dt, {})[code] = float(cl)
    # 补齐：某只 ETF 当天停牌/缺数据 → 用最近一次已知价（避免市值算成 0）
    _last = {}
    for dt in sorted(px.keys()):
        for code in codes:
            if code in px[dt]:
                _last[code] = px[dt][code]
            elif code in _last:
                px[dt][code] = _last[code]
    bd = dict(c.execute("SELECT date,close FROM bench_daily WHERE date>=? AND date<=?",
                        (cfg["start_date"], asof)).fetchall())
    _last_bench = None   # 基准数据可能比行情晚一天发布，用前值延续
    all_dates = sorted(px.keys())

    # 分红表
    divs = {}
    for code, lst in (cfg.get("known_dividends") or {}).items():
        for dt, amt in (lst or []):
            divs.setdefault(dt, []).append((code, float(amt)))

    nav0 = None
    bench0 = None
    hist = []
    last_month = None

    for dt in all_dates:
        p = px[dt]
        # ── 建仓：计划日到了（且当天有行情）就执行该批次
        for bi, pd_day in enumerate(plan):
            if bi in done or dt < pd_day:
                continue
            if not all(k in p and p[k] > 0 for k in codes):
                continue
            done.add(bi)
            for code in codes:
                if code not in p or p[code] <= 0:
                    continue
                amt = per * w[code] / sum(w.values())
                amt_net = amt * (1 - fee_buy)
                shares[code] += amt_net / p[code]
                spent += amt
                cash -= amt
        # ── 分红入账
        for code, amt in divs.get(dt, []):
            if shares.get(code, 0) > 0:
                cash += shares[code] * amt
        # ── 月度提款
        ym = dt[:7]
        # 跨了几个月就提几次款（电脑停机多日也能补上）
        _n_month = 0
        if last_month is not None and ym != last_month:
            _a = int(last_month[:4]) * 12 + int(last_month[5:7])
            _b = int(ym[:4]) * 12 + int(ym[5:7])
            _n_month = max(0, _b - _a)
        if _n_month > 0:
            need = mwd * _n_month
            if cash >= need:
                cash -= need
            else:
                short = need - cash
                cash = 0.0
                mv = {k: shares[k] * p.get(k, 0) for k in codes}
                tot = sum(mv.values())
                if tot > 0:
                    for k in codes:
                        sell_amt = short * mv[k] / tot
                        shares[k] = max(0.0, shares[k] - sell_amt / p[k])
        last_month = ym

        mv = sum(shares[k] * p.get(k, 0) for k in codes)
        total = mv + cash
        if nav0 is None:
            nav0 = cap
        b = bd.get(dt)
        if b is not None and bench0 is None:
            bench0 = float(b)
        if b is not None:
            _last_bench = float(b)
        else:
            b = _last_bench
        bench = (float(b) / bench0) if (b is not None and bench0) else np.nan
        pos = "建仓中" if len(done) < len(plan) else "满仓"
        hist.append({"date": dt, "invested": mv, "cash": cash, "total": total,
                     "nav": total / nav0, "bench": bench, "pos": pos})

    return hist, plan, shares, cash, done


def report(cfg, hist, sched):
    last = hist[-1]
    df = pd.DataFrame(hist)
    # 回撤
    df["peak"] = df["total"].cummax()
    df["dd"] = df["total"] / df["peak"] - 1
    mdd = float(df["dd"].min())
    days = (pd.Timestamp(last["date"]) - pd.Timestamp(hist[0]["date"])).days or 1
    ann = (last["nav"] ** (365.25 / days) - 1) if days > 3 else np.nan

    L = []
    L.append(f"# 养老模拟盘日报 · {last['date']}")
    L.append("")
    L.append(f"> 方案：**{cfg['name']}**　|　本金 **{cfg['capital']:,.0f}** 元")
    L.append(f"> 建仓日程：{sched[0]} ~ {sched[-1]}（{len(sched)} 个交易日等额买入）")
    L.append("")
    L.append("## 一、今天的结果")
    L.append("")
    L.append("| 项目 | 金额 / 比例 |")
    L.append("|---|---|")
    L.append(f"| **总资产** | **{last['total']:,.0f} 元** |")
    L.append(f"| 持仓市值 | {last['invested']:,.0f} 元 |")
    L.append(f"| 现金 | {last['cash']:,.0f} 元 |")
    pnl = last["total"] - cfg["capital"]
    L.append(f"| **累计盈亏** | **{pnl:+,.0f} 元（{last['nav']-1:+.2%}）** |")
    if not np.isnan(last["bench"]):
        L.append(f"| 基准（红利低波全收益） | {last['bench']-1:+.2%} |")
        L.append(f"| **超额** | **{(last['nav']-last['bench'])*100:+.2f} 个百分点** |")
    L.append(f"| 最大回撤 | {mdd:.2%} |")
    if not np.isnan(ann):
        L.append(f"| 年化（按 {days} 天折算） | {ann:+.2%} |")
    L.append("")
    L.append("## 二、逐日净值")
    L.append("")
    L.append("| 日期 | 总资产 | 净值 | 日涨跌 | 基准 | 状态 |")
    L.append("|---|---|---|---|---|---|")
    prev = None
    for r in hist:
        chg = "—" if prev is None else f"{(r['nav']/prev-1)*100:+.2f}%"
        bv = "—" if (isinstance(r['bench'], float) and np.isnan(r['bench'])) else f"{r['bench']:.4f}"
        L.append(f"| {r['date']} | {r['total']:,.0f} | {r['nav']:.4f} | {chg} | {bv} | {r['pos']} |")
        prev = r["nav"]
    L.append("")
    L.append("## 三、说明")
    L.append("")
    L.append("- **这是模拟盘，不是真实持仓**。用来在建仓前看清真实波动。")
    L.append(f"- **本模拟按「一周全额建仓」，与正式方案的「10 万立即 + 140 万等 12 个月」不同**，"
             f"目的是给真实建仓做对照基准。")
    L.append(f"- 现金池 {cfg['cash_pool_months']} 个月（{cfg['monthly_withdrawal']*int(cfg['cash_pool_months']):,.0f} 元），"
             f"每月提款 {cfg['monthly_withdrawal']:,.0f} 元，现金不足时按比例卖份额。")
    L.append("- 分红按 `config/paper_trading.yaml` 的 `known_dividends` 计入现金；"
             "实际公告金额出来后需更新。")
    L.append("- 价格为不复权收盘价（分红单独入账，所以收益率是真实的）。")
    L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", default=None)
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args()
    cfg = load_cfg()
    asof = a.asof or datetime.now().strftime("%Y-%m-%d")
    c = db()
    if a.rebuild:
        for t in ("nav_daily", "bench_daily"):
            c.execute(f"DELETE FROM {t}")
        c.commit()
        print("  已清空净值历史")

    print("=" * 78)
    print(f"【养老模拟盘】{cfg['name']}   运行日 {asof}")
    print("=" * 78)
    codes = [x["code"] for x in cfg["assets"]]
    print("  [1/3] 更新 ETF 日线缓存…")
    _mk = {a["code"]: a.get("market", "cn") for a in cfg["assets"]}
    update_etf_cache(c, codes, cfg["start_date"], asof, _mk)
    print("  [2/3] 更新基准…")
    _n = update_bench_remote(cfg["start_date"], asof)
    if _n:
        print(f"  基准补数 +{_n} 行")
    fetch_bench(c, cfg["start_date"], asof)
    print("  [3/3] 模拟…")
    hist, sched, shares, cash, done = simulate(cfg, c, asof)
    if not hist:
        print("  ❌ 无数据，无法模拟")
        return 1
    c.execute("DELETE FROM nav_daily")
    c.executemany("INSERT OR REPLACE INTO nav_daily(date,invested,cash,total,nav,bench,pos) "
                  "VALUES(?,?,?,?,?,?,?)",
                  [(r["date"], r["invested"], r["cash"], r["total"], r["nav"],
                    None if (isinstance(r["bench"], float) and np.isnan(r["bench"])) else r["bench"],
                    r["pos"]) for r in hist])
    c.commit()

    # 持久化当日持仓
    _last_px = {}
    # 按「每只标的各自最近可用价」取，不能用全表最大日期：
    # 美股当日未收盘时该日没有行，会被记成 0，导致持仓市值凭空消失（E27）
    _rows = c.execute("""SELECT e.code, e.close FROM etf_daily e
        WHERE e.date = (SELECT MAX(date) FROM etf_daily
                        WHERE code = e.code AND date <= ?)""",
                      (hist[-1]["date"],)).fetchall()
    for _c, _cl in _rows:
        _last_px[_c] = float(_cl)
    c.execute("DELETE FROM holdings WHERE date=?", (hist[-1]["date"],))
    c.executemany("INSERT OR REPLACE INTO holdings(date,code,shares,price,mv) VALUES(?,?,?,?,?)",
                  [(hist[-1]["date"], k, float(shares[k]), _last_px.get(k, 0.0),
                    float(shares[k]) * _last_px.get(k, 0.0)) for k in shares])
    c.commit()

    # 建仓进度写入 sim_meta
    c.execute("INSERT OR REPLACE INTO sim_meta(k,v) VALUES('build_done',?)", (str(len(done)),))
    c.execute("INSERT OR REPLACE INTO sim_meta(k,v) VALUES('build_total',?)", (str(len(sched)),))
    _invest = float(cfg["capital"]) - float(cfg["monthly_withdrawal"]) * int(cfg["cash_pool_months"])
    _spent = _invest * len(done) / len(sched) if sched else 0.0
    c.execute("INSERT OR REPLACE INTO sim_meta(k,v) VALUES('spent',?)", (f"{_spent:.2f}",))
    c.commit()

    DATADIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(hist).to_csv(DATADIR / "nav_history.csv", index=False, encoding="utf-8-sig")
    OUTDIR.mkdir(parents=True, exist_ok=True)
    txt = report(cfg, hist, sched)
    out = OUTDIR / f"模拟盘日报_{hist[-1]['date']}.md"
    out.write_text(txt, encoding="utf-8")

    last = hist[-1]
    print("-" * 78)
    if last["date"] != asof:
        print(f"  数据截至 {last['date']}（运行日 {asof}，当日行情尚未生成，属正常）")
    print(f"  总资产 {last['total']:,.0f} 元   净值 {last['nav']:.4f}   "
          f"盈亏 {last['total']-cfg['capital']:+,.0f} 元")
    print(f"  持仓 {last['invested']:,.0f}   现金 {last['cash']:,.0f}   天数 {len(hist)}")
    print(f"\n  报告：{out}")
    print(f"  历史：{DATADIR / 'nav_history.csv'}")
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
