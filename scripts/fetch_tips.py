# -*- coding: utf-8 -*-
"""scripts/fetch_tips.py —— 抓美国财政部官方 10 年期 TIPS 实际收益率

来源：home.treasury.gov 的 daily_treasury_real_yield_curve（市场标准口径）
缓存：data/cache/tips10y.csv

用法：
    python scripts/fetch_tips.py            # 增量更新（从缓存最后日期起）
    python scripts/fetch_tips.py --full     # 全量重抓（2003 起）
"""
from __future__ import annotations
import sys, argparse, time
from io import StringIO
from pathlib import Path
from datetime import datetime

import pandas as pd
import requests

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "data" / "cache" / "tips10y.csv"
BASE_URL = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
            "daily-treasury-rates.csv/{y}/all?type=daily_treasury_real_yield_curve"
            "&field_tdr_date_value={y}&page&_format=csv")


def fetch_year(y: int, retries: int = 3) -> pd.DataFrame | None:
    url = BASE_URL.format(y=y)
    for k in range(retries):
        try:
            r = requests.get(url, timeout=45, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200 or len(r.text) < 50:
                raise RuntimeError(f"HTTP {r.status_code} len={len(r.text)}")
            df = pd.read_csv(StringIO(r.text))
            df.columns = [str(c).strip().strip('"') for c in df.columns]
            return df
        except Exception as e:
            if k == retries - 1:
                print(f"    ❌ {y}: {type(e).__name__}: {str(e)[:50]}")
            else:
                time.sleep(2 + 2 * k)
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    a = ap.parse_args()

    start_year = 2003
    old = None
    if not a.full and OUT.exists():
        try:
            old = pd.read_csv(OUT, parse_dates=["date"])
            if len(old):
                last_y = int(old["date"].max().year)
                start_year = max(2003, last_y)     # 从最后一年重抓，天然增量
                print(f"  增量更新：从 {start_year} 年开始（缓存已有 {len(old)} 行，"
                      f"至 {old['date'].max().date()}）")
        except Exception:
            old = None

    frames = []
    for y in range(start_year, datetime.now().year + 1):
        df = fetch_year(y)
        if df is not None:
            frames.append(df)
            print(f"    ✅ {y}: {len(df)} 行")

    if not frames:
        print("  ❌ 全部失败，沿用旧缓存")
        return 1

    all_df = pd.concat(frames, ignore_index=True)
    all_df["Date"] = pd.to_datetime(all_df["Date"], errors="coerce", format="mixed")
    all_df = all_df.dropna(subset=["Date"]).sort_values("Date")
    col = "10 YR" if "10 YR" in all_df.columns else next(c for c in all_df.columns if "10" in c)
    new = all_df[["Date", col]].dropna().copy()
    new.columns = ["date", "tips10y"]

    if old is not None and len(old):
        new = pd.concat([old, new], ignore_index=True)

    new = new.drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    new.to_csv(OUT, index=False)
    print(f"\n  ✅ 已保存 {OUT}")
    print(f"     {len(new)} 行  {new['date'].min().date()} ~ {new['date'].max().date()}")
    print(f"     最新 10 年期 TIPS 实际收益率：{new['tips10y'].iloc[-1]:.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
