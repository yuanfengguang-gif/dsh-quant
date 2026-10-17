# -*- coding: utf-8 -*-
"""risk/verify_turn_consistency.py —— DS-14：换手率口径抽验

目的：验证新库 `turn` 在 2019 年前后是否同口径、可回推——
  ① 文件自带 turnover(%)          ← 数据源给的
  ② 手算 volume(股) / (float_share(万股)×10000) × 100   ← 用股本自己算
  ③ 旧 bars.db 的 turn(小数)×100   ← 历史库口径
三者一致 → 换手率全历史同口径，铁律③（2019 前换手结论作废）可修订。

覆盖：10 只不同类型股票 × 8 个年份（2005/2010/2015/2018/2019/2020/2023/2026）
用法：python risk/verify_turn_consistency.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CACHE = Path(__file__).resolve().parent.parent / "data" / "cache"

STOCKS = [
    ("600519.SH", "茅台·高价"),
    ("000001.SZ", "平安·大盘"),
    ("000651.SZ", "格力·高分红"),
    ("600036.SH", "招行·银行"),
    ("300750.SZ", "宁德·次新"),
    ("002594.SZ", "比亚迪"),
    ("601988.SH", "中行·低价"),
    ("000002.SZ", "万科"),
    ("920819.BJ", "北交所"),
    ("600087.SH", "退市股"),
]
YEARS = ["2005", "2010", "2015", "2018", "2019", "2020", "2023", "2026"]


def main() -> int:
    con = sqlite3.connect(f"file:{(CACHE / 'tdx_base.db').as_posix()}?mode=ro", uri=True, timeout=60)
    con.execute(f"ATTACH DATABASE '{(CACHE / 'bars.db').as_posix()}' AS b")

    print(f"{'股票':22s}{'日期':12s}{'文件turn%':>10s}{'手算turn%':>10s}{'旧库turn%':>10s}"
          f"{'文件vs手算':>11s}{'旧库vs文件':>11s}  判定")
    print("=" * 108)
    ok = bad = miss = 0
    worst = []
    for code, tag in STOCKS:
        for y in YEARS:
            r = con.execute("""
                SELECT date, turnover, volume, float_share FROM daily
                WHERE code=? AND date LIKE ? AND volume>0 AND float_share>0
                ORDER BY date LIMIT 1""", (code, y + "%")).fetchone()
            if not r:
                miss += 1
                continue
            date, tor, vol, fs = r
            calc = vol / (fs * 10000.0) * 100.0
            old = con.execute(
                "SELECT turn FROM b.daily_bar WHERE code=? AND date=? AND adjust='qfq'",
                (code, date)).fetchone()
            old_pct = old[0] * 100 if (old and old[0] is not None) else None
            d1 = abs(calc - tor) / tor * 100 if tor else None
            d2 = abs(old_pct - tor) / tor * 100 if (old_pct and tor) else None
            if d1 is not None and d1 < 0.5:
                ok += 1
                mark = "✅"
            else:
                bad += 1
                mark = "⚠️"
                worst.append((code, date, tor, calc, d1))
            print(f"{code + ' ' + tag:22s}{date:12s}{tor:>10.4f}{calc:>10.4f}"
                  f"{(f'{old_pct:.4f}' if old_pct is not None else '（无）'):>10s}"
                  f"{(f'{d1:.3f}%' if d1 is not None else '-'):>11s}"
                  f"{(f'{d2:.2f}%' if d2 is not None else '-'):>11s}  {mark}")

    print("=" * 108)
    print(f"合计: 一致 {ok} / 异常 {bad} / 无数据 {miss}")
    if worst:
        print("\n异常明细:")
        for w in worst[:8]:
            print(f"  {w[0]} {w[1]}: 文件 {w[2]:.4f}% vs 手算 {w[3]:.4f}%（差 {w[4]:.2f}%）")

    # 分年统计（用全市场抽样：每年取 500 只，比较文件 turn 与手算）
    print("\n" + "=" * 108)
    print("分年全市场抽样（每年 500 只，文件 turn vs 手算 volume/流通股本）")
    print("=" * 108)
    for y in YEARS[:-1] + ["2025"]:
        rows = con.execute("""
            SELECT turnover, volume, float_share FROM daily
            WHERE date LIKE ? AND turnover IS NOT NULL AND volume>0 AND float_share>0
            LIMIT 500""", (y + "%",)).fetchall()
        if not rows:
            continue
        devs = [abs(v / (f * 10000.0) * 100.0 - t) / t * 100 for t, v, f in rows if t]
        devs.sort()
        print(f"  {y}: n={len(devs):>4}  中位偏差 {devs[len(devs)//2]:>7.4f}%  "
              f"P90 {devs[int(len(devs)*0.9)]:>7.4f}%  最大 {devs[-1]:>8.3f}%")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
