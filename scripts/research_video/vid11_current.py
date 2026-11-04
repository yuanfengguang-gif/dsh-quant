import sys, sqlite3
from pathlib import Path
import numpy as np, pandas as pd
if hasattr(sys.stdout,"reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = Path(r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant")
CACHE = BASE/"data"/"cache"/"crisis"; DB = BASE/"data"/"cache"/"dividend_research.db"
def usc(s):
    d=pd.read_csv(CACHE/f"us_{s}.csv"); dc=[c for c in d.columns if c.lower() in ("date","日期")][0]
    d[dc]=pd.to_datetime(d[dc]); cc=[c for c in d.columns if c.lower() in ("close","收盘")]
    return d.sort_values(dc).set_index(dc)[(cc[0] if cc else [c for c in d.columns if "价" in c][0])].astype(float)
def emidx(fn):
    d=pd.read_csv(CACHE/fn); dc=next(c for c in d.columns if "日期" in c)
    d[dc]=pd.to_datetime(d[dc]); return d.sort_values(dc).set_index(dc)["最新价"].astype(float)
GLD=usc("GLD"); SLV=usc("SLV"); UUP=usc("UUP"); HS300=emidx("em_global_hs300.csv")
b=pd.read_csv(CACHE/"us_10y_东财.csv"); b.columns=[str(c) for c in b.columns]; b["日期"]=pd.to_datetime(b["日期"])
c10=[c for c in b.columns if "美国国债收益率10年" in c][0]; B10=b.set_index("日期")[c10].astype(float).dropna()
r=pd.read_csv(CACHE/"macro_bank_usa_interest_rate.csv"); r.columns=[str(c) for c in r.columns]
r["日期"]=pd.to_datetime(r["日期"]); r=r.sort_values("日期")
fv=pd.to_numeric(r["今值"],errors="coerce").fillna(pd.to_numeric(r["前值"],errors="coerce"))
FED=pd.Series(fv.values,index=pd.DatetimeIndex(r["日期"].values)).dropna()
gsr=(GLD/SLV).dropna()*9.91

print("="*96); print("【A3 修正】2008-10 后「三年」黄金涨幅（之前算错成到2026年）"); print("="*96)
low_d=pd.Timestamp("2008-11-12"); low_v=float(GLD.loc[low_d])
for H,lab in ((365,"1年"),(730,"2年"),(1095,"3年")):
    end=low_d+pd.Timedelta(days=H)
    if end<=GLD.index[-1]:
        v=float(GLD.asof(end))
        print(f"  谷底 {low_d.date()} {low_v:.1f} → {lab}后 {end.date()} {v:.1f}  涨幅 {v/low_v-1:+.1%}")
print(f"  （视频说三年涨 180%、到 1921 美元。GLD 是 1/10 盎司，1921/10≈192，与上面 3 年值对照）")

print()
print("="*96); print("【当前读数 + 距离买卖点还有多远】"); print("="*96)
last=pd.Timestamp.min
# 沪深300 距 36 月高点
hs=HS300.dropna()
roll_max=hs.rolling(756,min_periods=250).max()
dd_now=float(hs.iloc[-1]/roll_max.iloc[-1]-1)
print(f"  沪深300  {float(hs.iloc[-1]):.0f}   距36月高点 {dd_now:+.1%}")
for th,lab in ((-0.25,"第1档"),(-0.35,"第2档")):
    gap=dd_now-th
    print(f"     {lab} 阈值 {th:.0%} → {'✅已触发' if dd_now<=th else f'还差 {gap:.1%}'}")
# 金银比
g=gsr.dropna(); gmax=g.rolling(250,min_periods=120).max()
gf=float(g.iloc[-1]/gmax.iloc[-1]-1)
print(f"  金银比    {float(g.iloc[-1]):.1f}    距250日高点 {gf:+.1%}   （视频阈值 ≤-8%）")
print(f"      → {'✅ 已满足「抛售出清」条件' if gf<=-0.08 else f'还差 {-0.08-gf:.1%}'}")
print(f"      历史分位 {float((g<g.iloc[-1]).mean()):.0%}")
# 10Y + 美元
b10=B10.reindex(hs.index).ffill(); uup=UUP.reindex(hs.index).ffill()
need=60
if len(hs)>need:
    db=float(b10.iloc[-1]-b10.iloc[-1-need]); du=float(uup.iloc[-1]/uup.iloc[-1-need]-1)
    print(f"  10Y美债   {float(b10.iloc[-1]):.2f}%   60日变化 {db:+.2f}pp  {'↑' if db>0 else '↓'}")
    print(f"  美元指数  {float(uup.iloc[-1]):.1f}    60日变化 {du:+.1%}  {'↑' if du>0 else '↓'}")
    sq = (db>0) and (du>0)
    print(f"     → 缺钱期(阶段1) {'⚠️ 是 —— 视频说这时候别抄底' if sq else '✅ 否'}")
# 美联储
print(f"  美联储    {float(FED.iloc[-1]):.2f}%  （最近一次 {FED.index[-1].date()}）")
if len(FED)>2:
    print(f"     最近方向 {'↓降息' if FED.iloc[-1]<FED.iloc[-2] else ('↑加息' if FED.iloc[-1]>FED.iloc[-2] else '→持平')}")

print()
print("="*96); print("【三个指标合成判断】"); print("="*96)
ok_g = gf<=-0.08
ok_sq = not sq if len(hs)>need else None
print(f"  ① 金银比抛售出清：{'✅ 满足' if ok_g else '❌ 未满足'}")
print(f"  ② 不在缺钱期：  {'✅ 满足' if ok_sq else '❌ 未满足（仍在阶段1）'}")
print(f"  ③ 美联储转向降息：{'✅' if FED.iloc[-1]<FED.iloc[-2] else '❌ 仍在高位'}（当前 {float(FED.iloc[-1]):.2f}%）")
n_ok=sum([ok_g, bool(ok_sq), FED.iloc[-1]<FED.iloc[-2]])
print(f"\n  三项满足 {n_ok}/3 → " + ("可以开始换仓" if n_ok>=2 else "继续观望，别动手"))
