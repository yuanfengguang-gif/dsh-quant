# -*- coding: utf-8 -*-
"""acquire_v11_data.py - 补七剑财说视频验证所需数据

需要的 4 个数据：
  1. SLV 白银 ETF            → 算金银比（金银比是视频的第二个指标）
  2. 美元指数                → 视频的第一个指标（缺钱晴雨表）
  3. 10年期美债收益率        → 视频的第一个指标
  4. 美联储基准利率          → 视频的第三个指标（最重要）
"""
import sys, time
from pathlib import Path
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CACHE = Path(r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant\data\cache\crisis")
import akshare as ak

ok, fail = [], []


def try_fetch(name, fn, save):
    for k in range(3):
        try:
            d = fn()
            if d is None or len(d) == 0:
                raise ValueError("空返回")
            d.columns = [str(c) for c in d.columns]
            d.to_csv(CACHE / save, index=False)
            print(f"  ✅ {name}: {len(d)} 行  列={list(d.columns)[:6]}")
            ok.append(name)
            return d
        except Exception as e:
            if k == 2:
                print(f"  ❌ {name}: {type(e).__name__}: {str(e)[:100]}")
                fail.append(name)
            else:
                time.sleep(2)


print("=" * 96)
print("【1. SLV 白银 ETF】")
print("=" * 96)
try_fetch("SLV", lambda: ak.stock_us_daily(symbol="SLV"), "us_SLV.csv")
if not (CACHE / "us_SLV.csv").exists():
    # 备用：新浪美股
    try_fetch("SLV(新浪)", lambda: ak.stock_us_daily(symbol="SLV", adjust=""), "us_SLV.csv")

print()
print("=" * 96)
print("【2. 美元指数（东财全球指数 UDI）】")
print("=" * 96)
try_fetch("美元指数", lambda: ak.index_global_hist_em(symbol="美元指数"), "em_global_udi.csv")

print()
print("=" * 96)
print("【3. 10 年期美债收益率】")
print("=" * 96)
# 试多种来源
for nm, fn in (
    ("新浪 .TNX", lambda: ak.index_us_stock_sina(symbol=".TNX")),
    ("东财 美国10年期国债", lambda: ak.bond_zh_us_rate()),
):
    try:
        d = fn()
        d.columns = [str(c) for c in d.columns]
        print(f"  ✅ {nm}: {len(d)} 行  列={list(d.columns)[:8]}")
        d.to_csv(CACHE / f"us_10y_{nm.split()[0]}.csv", index=False)
        ok.append(nm)
        break
    except Exception as e:
        print(f"  ❌ {nm}: {type(e).__name__}: {str(e)[:90]}")

print()
print("=" * 96)
print("【4. 美联储基准利率】")
print("=" * 96)
for nm, fn in (
    ("macro_bank_usa_interest_rate", lambda: ak.macro_bank_usa_interest_rate()),
    ("macro_bank_usa", lambda: ak.macro_bank_usa()),
):
    try:
        d = fn()
        d.columns = [str(c) for c in d.columns]
        print(f"  ✅ {nm}: {len(d)} 行  列={list(d.columns)[:8]}")
        print(f"     末行: {d.iloc[-1].to_dict()}")
        d.to_csv(CACHE / f"{nm}.csv", index=False)
        ok.append(nm)
        break
    except Exception as e:
        print(f"  ❌ {nm}: {type(e).__name__}: {str(e)[:90]}")

print()
print("=" * 96)
print(f"成功 {len(ok)} / 失败 {len(fail)}")
if fail:
    print("  失败:", fail)
print("=" * 96)
