# -*- coding: utf-8 -*-
"""data/fetch_bars_history_tencent.py —— 用腾讯 K 线补拉 2010-2018 历史日线（baostock 被封后的替代源）

腾讯 K 线（web.ifzq.gtimg.cn，零 key，不封 IP，三入口轮换）拉 2010-2018 日线。
口径：前复权 qfq（腾讯等差口径，高分红老股早年价格可能 ≤0 → 抛错跳过并记录）。
注意：腾讯 K 线无成交额(amount)、无 pct_chg、无 is_st 列——落库时 amount=NaN、pct_chg 用 close 自算、is_st=0。

用法：python data/fetch_bars_history_tencent.py [--start 2010-01-01 --end 2018-12-31] [--limit N]
断点续传：logs/bars_history_tencent_progress.txt
"""
import functools
import math
import re
import sqlite3
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import requests

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TENCENT_KLINE_HOSTS = ["https://web.ifzq.gtimg.cn",
                       "https://proxy.finance.qq.com/ifzqgtimg",
                       "https://ifzq.gtimg.cn"]
_tencent_host_down_until = {}
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

PROGRESS = BASE / "logs" / "bars_history_tencent_progress.txt"


def get_prefix(code):
    c = str(code).split(".")[0].zfill(6)
    if c.startswith(("4", "8", "92")):
        return "bj"
    if c.startswith(("6", "5")):
        return "sh"
    return "sz"


def norm_ticker(code):
    c = str(code).strip().lower()
    if "." in c:
        return c.split(".")[0].zfill(6)
    for p in ("sh", "sz", "bj"):
        c = c.replace(p, "")
    return c.zfill(6)


def _http(url, params):
    for host in TENCENT_KLINE_HOSTS:
        if _tencent_host_down_until.get(host, 0) > time.time():
            continue
        try:
            r = requests.get(host + url, params={"param": params},
                             headers={"User-Agent": UA, "Referer": "https://gu.qq.com/"},
                             timeout=(8, 20))
            payload = r.json() if r.text.strip() else {}
        except Exception:
            _tencent_host_down_until[host] = time.time() + 120
            continue
        if payload.get("msg") == "param error":
            raise ValueError(f"参数错误: {params}")
        if isinstance(payload.get("data"), dict) and payload["data"]:
            return payload["data"], host
        _tencent_host_down_until[host] = time.time() + 120
    raise RuntimeError("腾讯 K 线三入口均不可用（被限流，稍后重试）")


def tencent_kline_daily(code, start, end):
    """拉单只股票日线（qfq，自动分页）。返回 DataFrame(date/open/high/low/close/volume)。"""
    symbol = get_prefix(code) + norm_ticker(code)
    first = datetime.strptime(start, "%Y-%m-%d").date()
    last = datetime.strptime(end, "%Y-%m-%d").date()
    by_date, used = {}, []
    cursor = first
    while cursor <= last:
        stop = min(cursor + pd.Timedelta(days=699).to_pytimedelta(), last)
        data, host = _http("/appstock/app/fqkline/get",
                           f"{symbol},day,{cursor.isoformat()},{stop.isoformat()},640,qfq")
        if host not in used:
            used.append(host)
        node = data.get(symbol)
        items = (node or {}).get("qfqday") or (node or {}).get("day")
        if not isinstance(items, list):
            raise RuntimeError(f"{symbol} 返回格式变化")
        for it in items:
            d = it[0]
            o, h, l, c = float(it[1]), float(it[3]), float(it[4]), float(it[2])
            if min(o, h, l, c) <= 0:
                raise RuntimeError(f"{symbol} {d} 价格≤0（等差 qfq 副作用）")
            by_date[d] = {"date": d, "open": o, "high": h, "low": l, "close": c,
                          "volume": float(it[5])}
        cursor = stop + pd.Timedelta(days=1)
    rows = [by_date[k] for k in sorted(by_date)]
    if not rows:
        raise RuntimeError(f"{symbol} 区间内 0 根（未上市/停牌）")
    return pd.DataFrame(rows)


def load_codes():
    con = sqlite3.connect(str(BASE / "data" / "cache" / "stock_basic.db"))
    codes = [r[0] for r in con.execute(
        "SELECT code FROM stock_basic WHERE code LIKE '%.SH' OR code LIKE '%.SZ'").fetchall()]
    con.close()
    return codes


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2010-01-01")
    ap.add_argument("--end", default="2018-12-31")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    codes = load_codes()
    if args.limit:
        codes = codes[:args.limit]
    done = set()
    if PROGRESS.exists():
        done = {l.strip() for l in PROGRESS.read_text(encoding="utf-8").splitlines() if l.strip()}
    todo = [c for c in codes if c not in done]
    print(f"待拉 {len(todo)} 只（已完成 {len(done)}）: {args.start} ~ {args.end}", flush=True)

    con = sqlite3.connect(str(BASE / "data" / "cache" / "bars.db"))
    n_ok = n_rows = 0
    t0 = time.time()
    for i, code in enumerate(todo):
        try:
            df = tencent_kline_daily(code, args.start, args.end)
            df["code"] = code
            df["adjust"] = "qfq"
            df["source"] = "tencent"
            df["preclose"] = df["close"].shift(1)
            df["turn"] = None
            df["amount"] = None
            df["is_st"] = 0
            df["pct_chg"] = df["close"].pct_change()
            df = df[["code", "date", "open", "high", "low", "close", "preclose",
                     "volume", "amount", "turn", "pct_chg", "is_st", "adjust", "source"]]
            df.to_sql("daily_bar", con, if_exists="append", index=False)
            con.commit()
            n_ok += 1
            n_rows += len(df)
            with open(PROGRESS, "a", encoding="utf-8") as f:
                f.write(code + "\n")
        except Exception as e:
            print(f"  {code} 失败: {str(e)[:60]}", flush=True)
        if (i + 1) % 50 == 0:
            el = (time.time() - t0) / 60
            print(f"  进度 {i+1}/{len(todo)}，成功 {n_ok}，{n_rows} 行，{el:.1f} 分钟，"
                  f"{n_ok/el:.1f} 只/分", flush=True)
    con.close()
    print(f"完成: 成功 {n_ok}/{len(todo)}，{n_rows} 行", flush=True)


if __name__ == "__main__":
    main()
