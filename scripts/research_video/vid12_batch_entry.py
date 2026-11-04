import sys
from pathlib import Path
import numpy as np, pandas as pd, sqlite3
if hasattr(sys.stdout,"reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = Path(r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant")
CACHE = BASE/"data"/"cache"/"crisis"; DB = BASE/"data"/"cache"/"dividend_research.db"
def li(code):
    c=sqlite3.connect(f"file:{DB.as_posix()}?mode=ro",uri=True,timeout=30)
    d=pd.read_sql_query("SELECT date,close FROM idx_daily WHERE code=? ORDER BY date",c,params=(code,)); c.close()
    d["date"]=pd.to_datetime(d["date"]); return d.set_index("date")["close"].astype(float)
DIV=li("H30269"); TR=li("H20269")
div_rm=DIV.rolling(756,min_periods=250).max(); div_dd=DIV/div_rm-1
CR=[("2008 次贷","2007-06-01","2010-06-30"),("2011 欧债","2011-04-01","2013-06-30"),
    ("2015 A股股灾","2015-04-01","2017-06-30"),("2018 Q4","2018-09-01","2019-12-31"),
    ("2020 COVID","2020-01-01","2021-06-30"),("2022 加息","2022-01-01","2025-06-30")]
def first(cond,t0,t1):
    w=cond[(cond.index>=t0)&(cond.index<=t1)]; h=w[w.fillna(False)]
    return h.index[0] if len(h) else None
sig=(div_dd<=-0.20)&(div_dd.shift(1)>-0.20)

print("="*104)
print("【替代方案】既然信号出现后红利还要跌 22%，那「分批买」会不会比「一次买」更好？")
print("="*104)
print("  做法对比（买 100 万红利 ETF）：")
print("    一次性：信号当天全买")
print("    分批3月：信号后每月买 1/3")
print("    分批6月：信号后每月买 1/6")
print("    分批12月：信号后每月买 1/12")
print()
print(f"  {'危机':<14s}{'信号日':>12s}{'一次买成本':>11s}{'分3月':>9s}{'分6月':>9s}{'分12月':>9s}{'最优':>8s}")
res={}
for nm,t0,t1 in CR:
    T0,T1=pd.Timestamp(t0),pd.Timestamp(t1)
    d=first(sig,T0,T1)
    if d is None: print(f"  {nm:<14s}{'未触发':>12s}"); continue
    def avg_cost(nmonths):
        tot=0.0; w=0.0
        for k in range(nmonths):
            dt=d+pd.DateOffset(months=k)
            if dt>DIV.index[-1]: break
            p=float(DIV.asof(dt)); tot+=p; w+=1
        return tot/w if w else np.nan
    c1=float(DIV.asof(d))
    c3=avg_cost(3); c6=avg_cost(6); c12=avg_cost(12)
    best=min([("一次",c1),("分3月",c3),("分6月",c6),("分12月",c12)],key=lambda x:x[1])[0]
    res[nm]=(c1,c3,c6,c12)
    print(f"  {nm:<14s}{str(d.date()):>12s}{c1:>11.0f}{c3:>9.0f}{c6:>9.0f}{c12:>9.0f}{best:>8s}")

if res:
    print(f"\n  相对「一次买」的成本变化（负数=更便宜）：")
    print(f"  {'危机':<14s}{'分3月':>9s}{'分6月':>9s}{'分12月':>9s}")
    better={3:0,6:0,12:0}
    for nm,(c1,c3,c6,c12) in res.items():
        d3=c3/c1-1; d6=c6/c1-1; d12=c12/c1-1
        for k,v in ((3,d3),(6,d6),(12,d12)):
            if v<0: better[k]+=1
        print(f"  {nm:<14s}{d3:>+8.1%}{d6:>+8.1%}{d12:>+8.1%}")
    print(f"\n  比「一次买」更便宜的场次：分3月 {better[3]}/{len(res)}  分6月 {better[6]}/{len(res)}  分12月 {better[12]}/{len(res)}")
    a=np.array([[c3/c1-1,c6/c1-1,c12/c1-1] for (c1,c3,c6,c12) in res.values()])
    print(f"  中位改善：分3月 {np.median(a[:,0]):+.1%}  分6月 {np.median(a[:,1]):+.1%}  分12月 {np.median(a[:,2]):+.1%}")

print()
print("="*104)
print("【结合黄金】分批卖金 + 分批买红利（同步分批），对比一次性同步")
print("="*104)
GLD=pd.read_csv(CACHE/"us_GLD.csv"); GLD.columns=[str(c) for c in GLD.columns]
dc=[c for c in GLD.columns if str(c).lower() in ("date","日期")][0]
GLD[dc]=pd.to_datetime(GLD[dc]); cc=[c for c in GLD.columns if str(c).lower() in ("close","收盘")]
GLD=GLD.sort_values(dc).set_index(dc)[cc[0]].astype(float)
print(f"  {'危机':<14s}{'一次同步份额':>13s}{'分6月同步份额':>15s}{'改善':>9s}")
imp=[]
for nm,t0,t1 in CR:
    T0,T1=pd.Timestamp(t0),pd.Timestamp(t1)
    d=first(sig,T0,T1)
    if d is None: continue
    sh1=float(GLD.asof(d))/float(DIV.asof(d))
    tot=0.0
    for k in range(6):
        dt=d+pd.DateOffset(months=k)
        if dt>DIV.index[-1]: break
        tot+=float(GLD.asof(dt))/float(DIV.asof(dt))/6
    sh6=tot
    imp.append(sh6/sh1-1)
    print(f"  {nm:<14s}{sh1:>13.4f}{sh6:>15.4f}{sh6/sh1-1:>+8.1%}")
if imp:
    print(f"\n  分6月建仓份额改善：中位 {np.median(imp):+.1%}，最差 {min(imp):+.1%}，好于一次性 {sum(1 for x in imp if x>0)}/{len(imp)}")
