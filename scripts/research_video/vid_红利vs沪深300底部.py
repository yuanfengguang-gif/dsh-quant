import sys, sqlite3
from pathlib import Path
import numpy as np, pandas as pd
if hasattr(sys.stdout,"reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = Path(r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant")
CACHE=BASE/"data"/"cache"/"crisis"; DB=BASE/"data"/"cache"/"dividend_research.db"
def li(code):
    c=sqlite3.connect(f"file:{DB.as_posix()}?mode=ro",uri=True,timeout=30)
    d=pd.read_sql_query("SELECT date,close FROM idx_daily WHERE code=? ORDER BY date",c,params=(code,)); c.close()
    d["date"]=pd.to_datetime(d["date"]); return d.set_index("date")["close"].astype(float)
def emidx(fn):
    d=pd.read_csv(CACHE/fn); dc=next(c for c in d.columns if "日期" in c)
    d[dc]=pd.to_datetime(d[dc]); return d.sort_values(dc).set_index(dc)["最新价"].astype(float)
HS300=emidx("em_global_hs300.csv"); PX100=li("930955"); PX50=li("H30269"); GLD=pd.read_csv(CACHE/"us_GLD.csv",parse_dates=["date"]).set_index("date")["close"].astype(float)
CR=[("2008 次贷","2007-06-01","2010-06-30"),("2011 欧债","2011-04-01","2013-06-30"),
    ("2015 A股股灾","2015-04-01","2017-06-30"),("2018 Q4","2018-09-01","2019-12-31"),
    ("2020 COVID","2020-01-01","2021-06-30"),("2022 加息","2022-01-01","2025-06-30")]
print("="*112)
print("【红利低波自己的底部 vs 沪深300 底部 —— 差多少个月】")
print("="*112)
print(f"  {'危机':<16s}{'沪深300底':>12s}{'红利低波底':>12s}{'红利低波100底':>14s}{'时间差':>10s}{'沪深300后续跌幅':>17s}")
for nm,t0,t1 in CR:
    seg_h=HS300[(HS300.index>=t0)&(HS300.index<=t1)]
    if len(seg_h)<60: continue
    th=seg_h.idxmin()
    seg_d=PX50[(PX50.index>=t0)&(PX50.index<=t1)]
    seg_1=PX100[(PX100.index>=t0)&(PX100.index<=t1)]
    if len(seg_d)<60 or len(seg_1)<60: continue
    td=seg_d.idxmin(); t1_=seg_1.idxmin()
    diff=(td-th).days/30.44
    # 红利底部之后，沪深300 还跌多少
    after_h=seg_h[(seg_h.index>=td)&(seg_h.index<=th)]
    extra = (float(after_h.min())/float(after_h.iloc[0])-1) if len(after_h)>5 else 0.0
    print(f"  {nm:<16s}{str(th.date()):>12s}{str(td.date()):>12s}{str(t1_.date()):>14s}{diff:>+9.0f}月{extra:>16.1%}")
print()
print("  说明：时间差 > 0 表示红利比沪深300【晚】见底；< 0 表示【早】见底")
print("        「沪深300后续跌幅」= 从红利见底那天起，沪深300 还要继续跌多少")
