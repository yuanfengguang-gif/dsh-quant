# -*- coding: utf-8 -*-
"""_video_research/acquire_all.py —— 系统性地把验证所需数据全部下载

已确认可达的境内路由：
  · 东财全球指数 ak.index_global_hist_em  → 纳指(1991起)/标普/道指/恒生
  · 新浪 akshare                          → A股/ETF/美股(2004起)
  · 中证指数 akshare                      → 指数 PE/股息率（仅 20 日）
  · 基金 akshare fund_etf_fund_info_em    → ETF 净值/分红
  · QVIX akshare                          → 中国波指（需重试）

不可达：Yahoo / CBOE / FRED / Stooq（TLS 层 SSL EOF）
"""
import sys, time, json
from pathlib import Path
import pandas as pd
import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CACHE = Path(r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant\data\cache\crisis")
CACHE.mkdir(parents=True, exist_ok=True)
import akshare as ak

ok, fail = [], []


def retry(fn, name, tries=3, sleep=2):
    for k in range(tries):
        try:
            return fn()
        except Exception as e:
            if k == tries - 1:
                print(f"  ❌ {name}: {type(e).__name__}: {str(e)[:110]}")
                fail.append(name)
                return None
            time.sleep(sleep)


print("=" * 100)
print("【1. 东财全球指数：长历史（验证视频 01 / 05）】")
print("=" * 100)
GLOBAL = {
    "纳斯达克": "em_global_ndx.csv",
    "标普500": "em_global_spx.csv",
    "道琼斯": "em_global_djia.csv",
    "恒生指数": "em_global_hsi.csv",
    "日经225": "em_global_n225.csv",
    "上证指数": "em_global_sh.csv",
    "沪深300": "em_global_hs300.csv",
}
for name, fn in GLOBAL.items():
    d = retry(lambda n=name: ak.index_global_hist_em(symbol=n), f"东财 {name}")
    if d is None:
        continue
    d.columns = [str(c) for c in d.columns]
    dc = next(c for c in d.columns if "日期" in c)
    d[dc] = pd.to_datetime(d[dc])
    d = d.sort_values(dc)
    d.to_csv(CACHE / fn, index=False)
    print(f"  ✅ {name:<8s} {len(d):>5d} 行  {d[dc].min().date()} ~ {d[dc].max().date()}  → {fn}")
    ok.append(name)

print()
print("=" * 100)
print("【2. 4 只红利 ETF 净值/分红（验证视频 10）】")
print("=" * 100)
ETFS = {
    "510720": "红利国企ETF国泰",
    "159277": "港股通红利ETF富国",
    "159332": "央企红利ETF富国",
    "159399": "现金流ETF国泰",
    "510880": "红利ETF华泰柏瑞（对照）",
    "515450": "515450 红利低波50ETF南方（我方持仓）",
    "515100": "515100 红利低波100ETF景顺（我方持仓）",
}
for code, name in ETFS.items():
    d = retry(lambda c=code: ak.fund_etf_fund_info_em(
        fund=c, start_date="20180101", end_date="20261231"), f"ETF {code}")
    if d is None or len(d) == 0:
        continue
    d.columns = [str(c) for c in d.columns]
    d.to_csv(CACHE / f"etf_{code}_nav.csv", index=False)
    dc = "净值日期"
    d[dc] = pd.to_datetime(d[dc])
    print(f"  ✅ {code} {name:<30s} {len(d):>5d} 行  {d[dc].min().date()} ~ {d[dc].max().date()}")
    ok.append(code)

print()
print("=" * 100)
print("【3. 中国波指 QVIX（视频 06 的中国版）】")
print("=" * 100)
QVIX = ["index_option_300etf_qvix", "index_option_50etf_qvix",
        "index_option_500etf_qvix", "index_option_cyb_qvix",
        "index_option_kcb_qvix"]
for fn in QVIX:
    d = retry(lambda f=fn: getattr(ak, f)(), f"QVIX {fn}")
    if d is None or len(d) == 0:
        continue
    d.columns = [str(c) for c in d.columns]
    d.to_csv(CACHE / f"qvix_{fn.replace('index_option_', '')}.csv", index=False)
    print(f"  ✅ {fn:<32s} {len(d):>5d} 行  列={list(d.columns)[:5]}")
    ok.append(fn)
    break   # 拿到一个就够，避免超时

print()
print("=" * 100)
print("【4. 中证指数 PE/股息率（验证视频 02）—— 试全历史】")
print("=" * 100)
for code in ("H30269", "000922", "930955"):
    d = retry(lambda c=code: ak.stock_zh_index_value_csindex(symbol=c), f"csindex {code}")
    if d is None:
        continue
    d.columns = [str(c) for c in d.columns]
    d.to_csv(CACHE / f"csindex_{code}.csv", index=False)
    print(f"  ✅ {code}: {len(d)} 行  列={list(d.columns)[-6:]}")
    print(f"     最新：{d.iloc[0].to_dict()}")
    ok.append(f"csindex_{code}")

print()
print("=" * 100)
print(f"【完成】成功 {len(ok)} 项 / 失败 {len(fail)} 项")
print("=" * 100)
if fail:
    print("  失败：", fail)
print("\n  缓存目录现有文件：")
for f in sorted(CACHE.glob("em_global_*.csv")):
    print(f"    {f.name}  {f.stat().st_size/1024:.0f} KB")
for f in sorted(CACHE.glob("etf_*_nav.csv")):
    print(f"    {f.name}  {f.stat().st_size/1024:.0f} KB")
for f in sorted(CACHE.glob("qvix_*.csv")):
    print(f"    {f.name}  {f.stat().st_size/1024:.0f} KB")
