# -*- coding: utf-8 -*-
"""risk/verify_qfq_third_source.py —— qfq 第三源验证（补强项 ①）

思路：完全不依赖「复权因子 zip」，改用**除权明细**（`get_divid_factors`：每 10 股派息/送股/配股）
+ **原始价的前收盘**，按教科书公式自算前复权乘数，再与主库用的 `h(t)/h(最新)` 对比。

公式：
  理论除权价 = (Pc − B/10 + (A/10)×Pa) / (1 + S/10 + A/10)
       Pc=除权日前收盘, B=现金分红(元/10股), S=送股(股/10股), A=配股(股/10股), Pa=配股价
  事件乘数 k = Pc / 理论除权价          （保收益）
  自算前复权乘数 qfq_self(t) = 1 / Π_{事件日 ≤ t} k
  与主库 h(t)/h(last) 对比（后者已用于 tdx_qfq.db）

用法：python risk/verify_qfq_third_source.py
"""
from __future__ import annotations

import bisect
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\Lenovo\.dsh\skills\tdx-aidata")
sys.path.insert(0, r"C:\Users\Lenovo\.dsh\skills\tdx-aidata\lib")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from tdxaidata import tqs

import csv
import io
import zipfile

CACHE = Path(__file__).resolve().parent.parent / "data" / "cache"
HFQ = Path(r"D:\BaiduNetdiskDownload\复权因子\复权因子_后复权.zip")

STOCKS = ["600519.SH", "000001.SZ", "000651.SZ", "600036.SH", "000858.SZ", "300750.SZ"]


def load_h(code: str) -> dict:
    with zipfile.ZipFile(HFQ) as zf:
        try:
            raw = zf.read(f"{code}.csv").decode("utf-8-sig", errors="replace")
        except KeyError:
            return {}
    out = {}
    for row in csv.DictReader(io.StringIO(raw)):
        try:
            out[row["交易日期"].strip()] = float(row["复权因子"])
        except (KeyError, TypeError, ValueError):
            pass
    return out


def main() -> int:
    base = sqlite3.connect(f"file:{(CACHE / 'tdx_base.db').as_posix()}?mode=ro", uri=True, timeout=60)
    main_db = sqlite3.connect(f"file:{(CACHE / 'bars.db').as_posix()}?mode=ro", uri=True, timeout=60)

    print(f"{'股票':12s}{'事件数':>6s}{'校验点数':>8s}{'中位偏差':>10s}{'最大偏差':>10s}  判定")
    print("=" * 76)
    all_dev = []
    for code in STOCKS:
        df = tqs.get_divid_factors(stock_code=code)
        if df is None or len(df) == 0:
            print(f"{code:12s}  无除权事件")
            continue
        # 前收盘序列（原始价）
        pc_map = {}
        for d, pc, c in base.execute(
                "SELECT date, pre_close, close FROM daily WHERE code=? ORDER BY date", (code,)):
            pc_map[d] = pc if pc else c

        events = []
        for dt, row in df.iterrows():
            d = str(dt)[:10]
            B = float(row.get("Bonus") or 0)
            S = float(row.get("ShareBonus") or 0)
            A = float(row.get("Allotment") or 0)
            Pa = float(row.get("AllotPrice") or 0)
            if B == 0 and S == 0 and A == 0:
                continue
            Pc = pc_map.get(d)
            if not Pc:
                # 找最近的更早收盘
                r = base.execute("SELECT close FROM daily WHERE code=? AND date<? ORDER BY date DESC LIMIT 1",
                                 (code, d)).fetchone()
                Pc = r[0] if r else None
            if not Pc:
                continue
            theo = (Pc - B / 10.0 + A / 10.0 * Pa) / (1.0 + S / 10.0 + A / 10.0)
            if theo <= 0:
                continue
            events.append((d, Pc / theo))
        events.sort()
        if not events:
            print(f"{code:12s}  {len(df):>4d}  （无可计算事件）")
            continue

        ev_dates = [e[0] for e in events]
        # 前缀积
        prefix = []
        p = 1.0
        for _, k in events:
            p *= k
            prefix.append(p)

        h = load_h(code)
        if not h:
            print(f"{code:12s}  {len(events):>4d}  （无后复权因子对照）")
            continue
        h_last = h[max(h)]
        total = prefix[-1]
        # 严格推导（单事件例子验证）：
        #   k = Pc/理论除权价 > 1；后复权因子 h(t) = Π_{事件日 ≤ t} k
        #   （事件后 h 变大：raw 9 × h 1.111 = 10 = 事件前 raw 10 × h 1.0 ✓）
        #   前复权乘数 = h(t)/h(最新) = prefix(≤t) / 全部积
        checks = [d for d in sorted(h) if d >= events[0][0]][::max(1, len(h) // 40)]
        devs = []
        for d in checks:
            i = bisect.bisect_right(ev_dates, d) - 1
            pr = prefix[i] if i >= 0 else 1.0
            qfq_self = pr / total
            qfq_ours = h[d] / h_last
            if qfq_ours > 0:
                devs.append(abs(qfq_self - qfq_ours) / qfq_ours * 100)
        if not devs:
            continue
        devs.sort()
        all_dev.extend(devs)
        med, mx = devs[len(devs) // 2], devs[-1]
        flag = "✅" if med < 1 else ("🟡" if med < 5 else "❌")
        print(f"{code:12s}{len(events):>6d}{len(devs):>8d}{med:>9.3f}%{mx:>9.2f}%  {flag}")

    if all_dev:
        all_dev.sort()
        print("=" * 76)
        print(f"合计 {len(all_dev):,} 个校验点 | 中位偏差 {all_dev[len(all_dev)//2]:.3f}% | "
              f"P90 {all_dev[int(len(all_dev)*0.9)]:.2f}% | 最大 {all_dev[-1]:.2f}%")
    base.close()
    main_db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

