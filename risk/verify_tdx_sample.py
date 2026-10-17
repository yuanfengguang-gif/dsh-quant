# -*- coding: utf-8 -*-
"""risk/verify_tdx_sample.py —— 通达信样本数据验证（覆盖性 + 准确性 + 复权可用性）"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

A = Path(r"C:\Users\Administrator\.dsh\attachments\v1\files")
DAILY = A / "e7" / "e7b92f19c3820dc9b23917978e4090a1a19335d54166aaee570b7e58d80d95fc" / "日频样本.csv"
QFQ = A / "e0" / "e037e9440a15bc75ab808810025e860191a6ef9498d40a521f25739e35316807" / "前复权因子样本.csv"
HFQ = A / "61" / "6184d5507cd4dfd6b8dc56f99549b176975515e8d0fe0ccae93e86ef27a10112" / "后复权因子样本.csv"
BASE = Path(r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant")
BARS = BASE / "data" / "cache" / "bars.db"

print("=" * 70)
print("一、日频样本：字段覆盖性")
print("=" * 70)
d = pd.read_csv(DAILY, encoding="utf-8-sig")
print(f"行数 {len(d)}，股票 {d['code'].unique().tolist()}，日期 {d['datetime'].min()} ~ {d['datetime'].max()}")
print(f"字段（{len(d.columns)} 个）：{d.columns.tolist()}")

# 项目 daily_bar 需要的字段
need = ["code", "date", "open", "high", "low", "close", "preclose", "volume", "amount",
        "turn", "pct_chg", "is_st", "adjust"]
mapping = {"code": "code", "date": "datetime", "open": "open", "high": "high", "low": "low",
           "close": "close", "preclose": "pre_close", "volume": "volume", "amount": "amount",
           "turn": "turnover", "pct_chg": "pct_chg", "is_st": None, "adjust": None}
print("\n【字段映射】项目 daily_bar → 通达信：")
for k in need:
    v = mapping.get(k)
    mark = "✅" if v and v in d.columns else "❌"
    print(f"  {k:12s} → {str(v):12s} {mark}")
print("\n【通达信额外字段（富余）】：")
extra = [c for c in d.columns if c not in mapping.values()]
print("  " + ", ".join(extra))

print("\n" + "=" * 70)
print("二、准确性：通达信 vs 本地 bars.db（同一股票同一日期）")
print("=" * 70)
code = d["code"].iloc[0]
con = sqlite3.connect(str(BARS))
local = pd.read_sql(
    "SELECT code, date, open, high, low, close, volume, amount, turn, pct_chg "
    "FROM daily_bar WHERE code=? ORDER BY date", con, params=(code,))
con.close()
print(f"本地 bars.db 中 {code}：{len(local)} 行，{local['date'].min()} ~ {local['date'].max()}")

m = d.merge(local, left_on=["code", "datetime"], right_on=["code", "date"], suffixes=("_tdx", "_loc"))
print(f"日期交集：{len(m)} 天")
if len(m):
    for f in ["open", "high", "low", "close"]:
        diff = (m[f"{f}_tdx"] - m[f"{f}_loc"]).abs()
        print(f"  {f:6s}: 最大偏差 {diff.max():.4f}, 平均偏差 {diff.mean():.4f}")
    print(f"\n  turnover(通达信) vs turn(本地) 单位检查：")
    print(f"    通达信 前3值: {m['turnover'].head(3).tolist()}")
    print(f"    本地   前3值: {m['turn'].head(3).tolist()}")
    print(f"\n  volume(通达信) vs volume(本地) 单位检查：")
    print(f"    通达信 前3值: {m['volume_tdx'].head(3).tolist()}")
    print(f"    本地   前3值: {m['volume_loc'].head(3).tolist()}")
    print(f"    比值(本地/通达信): {(m['volume_loc']/m['volume_tdx']).head(3).round(2).tolist()}")
    print(f"\n  pct_chg 双方对比（前3天）：")
    print(f"    通达信: {m['pct_chg_tdx'].head(3).tolist()}")
    print(f"    本地  : {m['pct_chg_loc'].head(3).tolist()}")

print("\n【内部一致性自检（通达信样本自身）】")
bad_hl = ((d["high"] < d[["open", "close"]].max(axis=1)) | (d["low"] > d[["open", "close"]].min(axis=1))).sum()
d["calc_pct"] = (d["close"] / d["pre_close"] - 1) * 100
pct_diff = (d["calc_pct"] - d["pct_chg"]).abs()
vwap = d["amount"] * 10000 / (d["volume"] * 100)
vwap_dev = ((vwap - d["close"]).abs() / d["close"] * 100)
print(f"  high/low 越界行数: {bad_hl}")
print(f"  pct_chg 与 close/pre_close 自算偏差: 最大 {pct_diff.max():.4f} pp")
print(f"  均价(amount*1e4/(volume*100)) 与 close 偏差: 中位 {vwap_dev.median():.2f}%（推测 volume=手, amount=万元）")

print("\n" + "=" * 70)
print("三、复权因子可用性（关键：能否根治 F-6）")
print("=" * 70)
qfq = pd.read_csv(QFQ, encoding="utf-8-sig")
hfq = pd.read_csv(HFQ, encoding="utf-8-sig")
print(f"前复权因子：{len(qfq)} 行，股票 {qfq['股票代码'].unique().tolist()[:5]}")
print(f"  日期范围 {qfq['交易日期'].min()} ~ {qfq['交易日期'].max()}")
print(f"  因子范围 {qfq['复权因子'].min():.6f} ~ {qfq['复权因子'].max():.6f}")
print(f"后复权因子：{len(hfq)} 行，股票 {hfq['股票代码'].unique().tolist()[:5]}")
print(f"  日期范围 {hfq['交易日期'].min()} ~ {hfq['交易日期'].max()}")
print(f"  因子范围 {hfq['复权因子'].min():.6f} ~ {hfq['复权因子'].max():.6f}")

# 检查因子是否随时间变化（前复权应以最新日为基准，因子随时间变化）
print("\n【前复权因子时间序列抽样（000056.SZ）】")
s = qfq[qfq["股票代码"] == "000056.SZ"].copy()
s["交易日期"] = pd.to_datetime(s["交易日期"].astype(str), format="%Y%m%d")
s = s.sort_values("交易日期")
for idx in [0, len(s) // 4, len(s) // 2, len(s) * 3 // 4, -1]:
    row = s.iloc[idx]
    print(f"  {row['交易日期'].date()}: {row['复权因子']:.10f}")
uin = s["复权因子"].nunique()
print(f"  唯一值个数 {uin} / {len(s)} 行 → {'✅ 随时间变化（真正的复权因子）' if uin > 10 else '⚠️ 几乎不变'}")
