# -*- coding: utf-8 -*-
"""plot_fig2_fig3.py - 改进版图2 + 新增图3

fig2_aligned_at_s5.png  —— 六场危机对齐到卖金日，加粗中位路径
fig3_s5_asset_gap.png   —— 柱状图：卖金日各资产距自己本轮底部多远（含 20% 过滤线）
"""
import sys, sqlite3
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

BASE = Path(r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant")
CACHE = BASE / "data" / "cache" / "crisis"
DB = BASE / "data" / "cache" / "dividend_research.db"
OUT = Path(r"C:\Users\Administrator\ DSH 量化交易系统\_video_research")


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
DIV = li("H30269")
GLD = pd.read_csv(CACHE / "us_GLD.csv", parse_dates=["date"]).set_index("date")["close"].astype(float)

CR = [
    ("2008 次贷危机", "2007-06-01", "2010-06-30"),
    ("2011 欧债危机", "2011-04-01", "2013-06-30"),
    ("2015 A股股灾", "2015-04-01", "2017-06-30"),
    ("2018 Q4 调整", "2018-09-01", "2019-12-31"),
    ("2020 COVID", "2020-01-01", "2021-06-30"),
    ("2022 A股熊市", "2022-01-01", "2025-06-30"),
]


def px(s, dt):
    if dt in s.index:
        return float(s.loc[dt])
    i = s.index.get_indexer([dt], method="nearest")[0]
    return float(s.iloc[i])


def analyse(t0, t1):
    seg = HS300[(HS300.index >= t0) & (HS300.index <= t1)].dropna()
    trough = seg.idxmin()
    top = seg[seg.index <= trough].idxmax()
    low = float(seg.min())
    after = seg[seg.index > trough]
    hit = (after / low - 1)[(after / low - 1) >= 0.15]
    trig = hit.index[0] if len(hit) else None
    return {"top": top, "trough": trough, "low": low, "trig": trig}


# ══════════════════ 图 2 改进版 ══════════════════
fig2, ax2 = plt.subplots(figsize=(14, 8))
COLORS = {"2008 次贷危机": "#1e40af", "2011 欧债危机": "#0891b2", "2015 A股股灾": "#16a34a",
          "2018 Q4 调整": "#ca8a04", "2020 COVID": "#ea580c", "2022 A股熊市": "#7c3aed"}
paths = {}
for nm, t0, t1 in CR:
    st = analyse(t0, t1)
    if st["trig"] is None:
        continue
    trig = st["trig"]
    lo, hi = trig - pd.Timedelta(days=180), trig + pd.Timedelta(days=730)
    s = HS300[(HS300.index >= lo) & (HS300.index <= hi)]
    if len(s) < 60:
        continue
    x = np.array([(d - trig).days / 30.44 for d in s.index])
    y = s.values / px(HS300, trig) * 100
    paths[nm] = (x, y)
    ax2.plot(x, y, color=COLORS[nm], lw=1.5, alpha=0.55, label=nm)

# 中位路径：按月取插值中位
grid = np.arange(-6, 25, 0.5)
mat = []
for nm, (x, y) in paths.items():
    mat.append(np.interp(grid, x, y))
med = np.median(np.array(mat), axis=0)
ax2.plot(grid, med, color="black", lw=3.2, label="六场中位数", zorder=8)

ax2.axvline(0, color="#dc2626", lw=3)
ax2.axhline(100, color="#9ca3af", ls=":", lw=1.2)
ax2.annotate("卖金买ETF = 第 0 天", xy=(0, 0.02), xycoords=("data", "axes fraction"),
             xytext=(8, 0), textcoords="offset points", color="#dc2626",
             fontsize=12, fontweight="bold")
# 中位路径关键点
for m in (12, 24):
    v = np.interp(m, grid, med)
    ax2.scatter([m], [v], s=90, color="black", zorder=9)
    ax2.annotate(f"{m}个月后中位 {v:.0f}", xy=(m, v), xytext=(6, 10),
                 textcoords="offset points", fontsize=10, fontweight="bold")
ax2.set_xlabel("距「卖金买ETF」的月数", fontsize=12)
ax2.set_ylabel("沪深300（卖金日 = 100）", fontsize=12)
ax2.set_title("把六场危机对齐到「卖金买ETF」那一天之后，沪深300 怎么走\n"
              "粗黑线 = 六场中位数；细彩线 = 各场危机", fontsize=14, fontweight="bold")
ax2.grid(alpha=0.3, ls=":")
ax2.legend(fontsize=9.5, loc="upper left", ncol=2, framealpha=0.92)
fig2.tight_layout()
f2 = OUT / "fig2_aligned_at_s5.png"
fig2.savefig(f2, dpi=140, bbox_inches="tight")
plt.close(fig2)
print(f"✅ {f2.name}")

# ══════════════════ 图 3：柱状图 ══════════════════
rows = []
for nm, t0, t1 in CR:
    st = analyse(t0, t1)
    if st["trig"] is None:
        continue
    gaps = {}
    for k, s in (("沪深300", HS300), ("红利低波", DIV), ("黄金", GLD)):
        seg = s[(s.index >= t0) & (s.index <= st["trig"])]
        gaps[k] = px(s, st["trig"]) / float(seg.min()) - 1 if len(seg) > 20 else np.nan
    gaps["nm"] = nm
    gaps["trig"] = st["trig"]
    rows.append(gaps)

fig3, ax3 = plt.subplots(figsize=(14, 7))
xs = np.arange(len(rows))
w = 0.26
b1 = ax3.bar(xs - w, [r["沪深300"] * 100 for r in rows], w, label="沪深300", color="#2563eb")
b2 = ax3.bar(xs, [r["红利低波"] * 100 for r in rows], w, label="红利低波（515450跟踪）", color="#16a34a")
b3 = ax3.bar(xs + w, [r["黄金"] * 100 for r in rows], w, label="黄金（GLD）", color="#d97706")
ax3.axhline(20, color="#dc2626", ls="--", lw=2.2)
ax3.annotate("20% 过滤线：红利涨幅超过它 → 不买", xy=(-0.45, 20),
             xytext=(0, 5), textcoords="offset points", ha="left",
             color="#dc2626", fontsize=11, fontweight="bold",
             bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#dc2626", alpha=0.9))
for bars in (b1, b2, b3):
    for r in bars:
        h = r.get_height()
        ax3.annotate(f"{h:.0f}%", xy=(r.get_x() + r.get_width() / 2, h),
                     xytext=(0, 3), textcoords="offset points",
                     ha="center", fontsize=9)
ax3.set_xticks(xs)
ax3.set_xticklabels([f"{r['nm']}\n卖金日 {r['trig'].date()}" for r in rows], fontsize=9.5)
ax3.set_ylabel("距自己本轮底部的涨幅（%）", fontsize=12)
ax3.set_ylim(0, 68)
ax3.set_title("卖金买ETF 那一天，三类资产各自「距自己的底部」多远\n"
              "理想状态：股票在底部附近（低），黄金已涨起来（高，说明卖在了相对高位）",
              fontsize=14, fontweight="bold")
ax3.legend(fontsize=10.5, loc="upper left")
ax3.grid(axis="y", alpha=0.3, ls=":")
fig3.tight_layout()
f3 = OUT / "fig3_s5_asset_gap.png"
fig3.savefig(f3, dpi=140, bbox_inches="tight")
plt.close(fig3)
print(f"✅ {f3.name}")

print("\n" + "=" * 96)
print("【图 3 数据】")
print("=" * 96)
print(f"  {'危机':<16s}{'卖金日':>12s}{'沪深300距底':>13s}{'红利距底':>11s}{'黄金距底':>11s}{'判定':>8s}")
for r in rows:
    ok = r["红利低波"] <= 0.20
    print(f"  {r['nm']:<16s}{str(r['trig'].date()):>12s}{r['沪深300']*100:>12.1f}%"
          f"{r['红利低波']*100:>10.1f}%{r['黄金']*100:>10.1f}%{'买' if ok else '不买':>8s}")
