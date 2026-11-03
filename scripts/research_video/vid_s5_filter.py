# -*- coding: utf-8 -*-
"""verify_s5_filter.py - 给 S5 加「红利不追高」过滤器，能否修好 2022 那场

发现的问题：
  2022-2024 那场，红利低波在 2022-10-31 就见底并开始上涨，
  而沪深300 到 2024-09 才见底。等沪深300 反弹15%时（2024-05），
  红利已比自己底部高 28-30% → 买红利 = 追高，之后36个月只涨 0.1%

测试两种规则：
  规则 A（原方案）：沪深300 自低点反弹 ≥15% → 买
  规则 B（加过滤）：沪深300 反弹 ≥15% 且 红利距自己低点 ≤20% → 买
  规则 C（更严）：沪深300 反弹 ≥15% 且 红利距自己低点 ≤15% → 买
评价：买入后 24/36 个月，「换仓组合」相对「一直持金」的倍数
"""
import sys, sqlite3
from pathlib import Path
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant")
CACHE = BASE / "data" / "cache" / "crisis"
DB = BASE / "data" / "cache" / "dividend_research.db"


def li(code):
    c = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    d = pd.read_sql_query("SELECT date,close FROM idx_daily WHERE code=? ORDER BY date", c, params=(code,))
    c.close()
    d["date"] = pd.to_datetime(d["date"])
    return d.set_index("date")["close"].astype(float)


def emidx(fn):
    d = pd.read_csv(CACHE / fn)
    dc = next(c for c in d.columns if "日期" in c)
    d[dc] = pd.to_datetime(d[dc])
    return d.sort_values(dc).set_index(dc)["最新价"].astype(float)


HS300 = emidx("em_global_hs300.csv")
PX50 = li("H30269")        # 红利低波价格（买入价）
TR50 = li("H20269")        # 红利低波全收益（持有收益）
GLD = pd.read_csv(CACHE / "us_GLD.csv", parse_dates=["date"]).set_index("date")["close"].astype(float)

CR = [("2008 次贷", "2007-06-01", "2010-06-30"), ("2011 欧债", "2011-04-01", "2013-06-30"),
      ("2015 A股股灾", "2015-04-01", "2017-06-30"), ("2018 Q4", "2018-09-01", "2019-12-31"),
      ("2020 COVID", "2020-01-01", "2021-06-30"), ("2022 加息", "2022-01-01", "2025-06-30")]


def px(s, dt):
    if dt in s.index:
        return float(s.loc[dt])
    i = s.index.get_indexer([dt], method="nearest")[0]
    return float(s.iloc[i])


def find_s5(t0, t1, max_div_above_low=None):
    """返回 (触发日 or None, 说明)"""
    seg = HS300[(HS300.index >= t0) & (HS300.index <= t1)].dropna()
    if len(seg) < 60:
        return None, "数据不足"
    trough = seg.idxmin()
    low = float(seg.min())
    after = seg[seg.index > trough]
    bounce = after / low - 1
    cands = bounce[bounce >= 0.15]
    if len(cands) == 0:
        return None, "无15%反弹"
    if max_div_above_low is None:
        return cands.index[0], "首个15%反弹"
    # 需要同时满足「红利距自己低点 ≤ 阈值」
    dseg = PX50[(PX50.index >= t0)]
    div_low_so_far = np.inf
    for d in cands.index:
        lowd = float(PX50[(PX50.index >= t0) & (PX50.index <= d)].min())
        p = px(PX50, d)
        if p / lowd - 1 <= max_div_above_low:
            return d, f"红利距底 {p/lowd-1:.1%}（≤{max_div_above_low:.0%}）"
    return None, f"所有15%反弹时红利都已涨超 {max_div_above_low:.0%}"


print("=" * 118)
print("【规则 A / B / C 触发情况对比】")
print("=" * 118)
print(f"  {'危机':<16s}{'A 无过滤':>14s}{'B 红利≤20%':>14s}{'C 红利≤15%':>14s}")
trigs = {}
for nm, t0, t1 in CR:
    row = []
    for k, th in (("A", None), ("B", 0.20), ("C", 0.15)):
        d, note = find_s5(t0, t1, th)
        row.append(str(d.date()) if d is not None else "不买")
        trigs[(nm, k)] = d
    print(f"  {nm:<16s}{row[0]:>14s}{row[1]:>14s}{row[2]:>14s}")

print()
print("=" * 118)
print("【结果：买入后 N 个月，「换仓组合」相对「一直持金」的倍数】")
print("=" * 118)


def outcome(nm, t0, t1, trig, H_months):
    if trig is None:
        return 1.0
    end = trig + pd.Timedelta(days=int(H_months * 30.44))
    g_sell = px(GLD, trig)
    div_buy = px(TR50, trig)
    gl = 0.0
    sk = 1.0 * g_sell / div_buy      # 1 单位黄金全换成红利
    final = gl * px(GLD, end) + sk * px(TR50, end)
    base = px(GLD, end)
    return final / base


for H in (24, 36):
    print(f"\n  ── 持有 {H} 个月 ──")
    print(f"  {'危机':<16s}{'A 无过滤':>12s}{'B 红利≤20%':>14s}{'C 红利≤15%':>14s}")
    A, B, C = [], [], []
    for nm, t0, t1 in CR:
        a = outcome(nm, t0, t1, trigs[(nm, "A")], H)
        b = outcome(nm, t0, t1, trigs[(nm, "B")], H)
        c = outcome(nm, t0, t1, trigs[(nm, "C")], H)
        A.append(a); B.append(b); C.append(c)
        print(f"  {nm:<16s}{a:>12.2f}{b:>14.2f}{c:>14.2f}")
    print(f"  {'中位数':<16s}{np.median(A):>12.2f}{np.median(B):>14.2f}{np.median(C):>14.2f}")
    print(f"  {'最差':<16s}{min(A):>12.2f}{min(B):>14.2f}{min(C):>14.2f}")
    print(f"  {'跑赢持金':<16s}{sum(1 for x in A if x>1)}/6{'':>10s}"
          f"{sum(1 for x in B if x>1)}/6{'':>10s}{sum(1 for x in C if x>1)}/6")

print()
print("=" * 118)
print("【2022 那场的细节：规则 B 为什么选择「不买」】")
print("=" * 118)
nm, t0, t1 = "2022 加息", "2022-01-01", "2025-06-30"
d, note = find_s5(t0, t1, 0.20)
print(f"  规则 B 结果：{note}")
print(f"  沪深300 底部 2024-09-13，红利低波底部 2022-10-31")
print(f"  2024-05-06（沪深300 反弹15%）时：")
p = px(PX50, pd.Timestamp("2024-05-06"))
lowd = float(PX50[(PX50.index >= "2022-01-01") & (PX50.index <= "2024-05-06")].min())
print(f"     红利低波价格 {p:.1f}，此前低点 {lowd:.1f} → 已涨 {p/lowd-1:.1%}")
print(f"     → 超过 20% 阈值，规则 B 判定「追高」，不买")
gp = px(GLD, pd.Timestamp("2024-05-06"))
gl = float(GLD[GLD.index <= "2024-05-06"].min())
print(f"     同期黄金 {gp:.1f}，此前低点 {gl:.1f} → 已涨 {gp/gl-1:.1%}")
