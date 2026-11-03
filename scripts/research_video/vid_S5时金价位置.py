import sys, sqlite3
from pathlib import Path
import numpy as np, pandas as pd
if hasattr(sys.stdout,"reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
CACHE = Path(r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant\data\cache\crisis")
def usc(s): return pd.read_csv(CACHE/f"us_{s}.csv",parse_dates=["date"]).set_index("date")["close"].astype(float)
def emidx(fn):
    d=pd.read_csv(CACHE/fn); dc=next(c for c in d.columns if "日期" in c)
    d[dc]=pd.to_datetime(d[dc]); return d.sort_values(dc).set_index(dc)["最新价"].astype(float)
GLD=usc("GLD"); SPX=emidx("em_global_spx.csv"); HS300=emidx("em_global_hs300.csv")

CR=[("2008","2007-06-01","2012-12-31",SPX),("2011","2011-04-01","2013-12-31",SPX),
    ("2015","2015-04-01","2018-12-31",HS300),("2020","2020-01-01","2022-06-30",SPX),
    ("2022","2022-01-01","2026-06-30",SPX)]
def st(series,t0,t1):
    seg=series[(series.index>=t0)&(series.index<=t1)].dropna()
    if len(seg)<60: return None
    tr=seg.idxmin(); top=seg[seg.index<=tr].idxmax(); af=seg[seg.index>tr]
    if len(af)<20: return None
    lo=float(seg.min()); b=af/lo-1; h=b[b>=0.15]
    return {"top":top,"trough":tr,"low":lo,"trig":h.index[0] if len(h) else None}

print("="*104)
print("【在 S5 触发那天卖金：黄金处于什么位置】")
print("="*104)
print(f"  {'危机':<8s}{'S5触发日':>12s}{'当时金价':>10s}{'此前12月最高':>13s}{'占前高':>9s}{'之后12月黄金最高':>17s}{'之后还能涨':>11s}")
rt=[]
for nm,t0,t1,b in CR:
    s=st(b,t0,t1)
    if s is None or s["trig"] is None: continue
    d=s["trig"]
    if d not in GLD.index: d=GLD.index[GLD.index.get_indexer([d],method="nearest")[0]]
    v=float(GLD.loc[d])
    hi12=float(GLD[(GLD.index<=d)&(GLD.index>=d-pd.Timedelta(days=365))].max())
    nxt=GLD[(GLD.index>d)&(GLD.index<=d+pd.Timedelta(days=365))]
    hip=float(nxt.max()) if len(nxt)>60 else np.nan
    rt.append(v/hi12)
    print(f"  {nm:<8s}{str(d.date()):>12s}{v:>10.1f}{hi12:>13.1f}{v/hi12:>8.0%}{hip:>17.1f}{(hip/v-1):>10.1%}")
print(f"\n  在 S5 卖金，平均卖在「此前 12 个月最高价」的 {np.mean(rt):.0%}")
print(f"  （即：卖在相对高位，但卖不到最高点）")
