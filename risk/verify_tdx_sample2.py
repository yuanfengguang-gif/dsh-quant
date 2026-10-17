# -*- coding: utf-8 -*-
"""risk/verify_tdx_sample2.py —— 深挖：OHLC偏差原因 + 单位换算 + 复权因子正确性"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

A = Path(r"C:\Users\Administrator\.dsh\attachments\v1\files")
DAILY = A / "e7" / "e7b92f19c3820dc9b23917978e4090a1a19335d54166aaee570b7e58d80d95fc" / "日频样本.csv"
QFQ = A / "e0" / "e037e9440a15bc75ab808810025e860191a6ef9498d40a521f25739e35316807" / "前复权因子样本.csv"
HFQ = A / "61" / "6184d5507cd4dfd6b8dc56f99549b176975515e8d0fe0ccae93e86ef27a10112" / "后复权因子样本.csv"
M1 = A / "16" / "167787d2319c5c7e72485b2db3ad57fd38b223904354865a999a0914d4f64d9f" / "1分钟样本.csv"
BASE = Path(r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant")
BARS = BASE / "data" / "cache" / "bars.db"

d = pd.read_csv(DAILY, encoding="utf-8-sig")
con = sqlite3.connect(str(BARS))
loc = pd.read_sql("SELECT * FROM daily_bar WHERE code='300602.SZ' ORDER BY date", con)
con.close()

print("=" * 72)
print("一、本地数据属性（是否前复权？）")
print("=" * 72)
print(loc[["date", "open", "close", "adjust", "source"]].head(3).to_string(index=False))
print("adjust 取值:", loc["adjust"].unique().tolist(), " source:", loc["source"].unique().tolist())

print("\n" + "=" * 72)
print("二、逐日详细对比（前 8 天）")
print("=" * 72)
m = d.merge(loc, left_on=["code", "datetime"], right_on=["code", "date"], suffixes=("_tdx", "_loc"))
cols = ["datetime", "open_tdx", "open_loc", "close_tdx", "close_loc", "pct_chg_tdx", "pct_chg_loc"]
print(m[cols].head(8).to_string(index=False))

print("\n" + "=" * 72)
print("三、偏差性质分析（偏差是否恒定 = 复权差异？随机 = 数据差异？）")
print("=" * 72)
for f in ["open", "high", "low", "close"]:
    diff = m[f + "_tdx"] - m[f + "_loc"]
    rel = (diff / m[f + "_loc"] * 100)
    print(f"  {f:6s}: 偏差 min={diff.min():+.4f} max={diff.max():+.4f} mean={diff.mean():+.4f} "
          f"std={diff.std():.4f} | 相对偏差 mean={rel.mean():+.4f}%")
print("\n  → 若 std 极小(偏差恒定)=复权基准差异；std 大=数据源差异")

print("\n  通达信 vs 本地 比值（close_tdx / close_loc）：")
ratio = m["close_tdx"] / m["close_loc"]
print(f"    min={ratio.min():.6f} max={ratio.max():.6f} mean={ratio.mean():.6f} std={ratio.std():.6f}")

print("\n" + "=" * 72)
print("四、单位换算验证")
print("=" * 72)
r_vol = (m["volume_loc"] / m["volume_tdx"]).mean()
r_amt = (m["amount_loc"] / m["amount_tdx"]).mean()
r_turn = (m["turn"] / m["turnover"]).mean()
r_pct = (m["pct_chg_loc"] / m["pct_chg_tdx"]).mean()
print(f"  volume:  本地/通达信 = {r_vol:.4f}  → 通达信单位=手，×100=股")
print(f"  amount:  本地/通达信 = {r_amt:.4f}  → 系数 {r_amt:.1f}")
print(f"  turnover: 本地/通达信 = {r_turn:.6f} → 通达信=百分数，÷100=小数")
print(f"  pct_chg:  本地/通达信 = {r_pct:.6f} → 通达信=百分数，÷100=小数")
vwap = m["amount_tdx"] * 1000 / (m["volume_tdx"] * 100)
print(f"\n  均价检验 amount×1000/(volume×100): 与 close 中位偏差 "
      f"{(((vwap - m['close_tdx']).abs() / m['close_tdx']) * 100).median():.3f}%")

print("\n" + "=" * 72)
print("五、复权因子正确性（后复权：未复权价 × 后复权因子 = 后复权价）")
print("=" * 72)
hfq = pd.read_csv(HFQ, encoding="utf-8-sig")
hfq.columns = ["code", "date", "hfq_factor"]
hfq["date"] = pd.to_datetime(hfq["date"].astype(str), format="%Y%m%d")
s = hfq.sort_values("date")
print("  后复权因子单调性检查（应递增）:")
mono = (s["hfq_factor"].diff().dropna() >= -1e-9).mean()
print(f"    非递减占比 {mono*100:.2f}%  {'✅' if mono > 0.99 else '⚠️'}")
print(f"    起始 {s['date'].iloc[0].date()} 因子={s['hfq_factor'].iloc[0]:.6f}")
print(f"    结束 {s['date'].iloc[-1].date()} 因子={s['hfq_factor'].iloc[-1]:.6f}")
print(f"    累计涨幅倍数（后复权）: {s['hfq_factor'].iloc[-1]/s['hfq_factor'].iloc[0]:.4f}x")

qfq = pd.read_csv(QFQ, encoding="utf-8-sig")
qfq.columns = ["code", "date", "qfq_factor"]
qfq["date"] = pd.to_datetime(qfq["date"].astype(str), format="%Y%m%d")
q = qfq.sort_values("date")
print(f"\n  前复权因子: 起始 {q['date'].iloc[0].date()} 因子={q['qfq_factor'].iloc[0]:.6f}, "
      f"结束 {q['date'].iloc[-1].date()} 因子={q['qfq_factor'].iloc[-1]:.6f}")
print(f"    最新日因子={q['qfq_factor'].iloc[-1]:.6f}（应为 1.0 = 以最新日为基准的前复权）")

print("\n" + "=" * 72)
print("六、分钟数据（1分钟样本）字段与单位")
print("=" * 72)
m1 = pd.read_csv(M1, encoding="utf-8-sig")
print(f"  行数 {len(m1)}，字段 {m1.columns.tolist()}")
print(f"  code 格式: {m1['code'].unique().tolist()}（小写前缀，与日频 xxx.SZ 不同）")
print(f"  volume 前3: {m1['volume'].head(3).tolist()}, amount 前3: {m1['amount'].head(3).tolist()}")
vw = m1["amount"] / (m1["volume"] * 100)
print(f"  amount/(volume×100) 均值: {vw.mean():.4f}（对比 close {m1['close'].head(3).tolist()}）")
