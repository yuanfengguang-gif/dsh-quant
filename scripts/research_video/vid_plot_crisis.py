# -*- coding: utf-8 -*-
"""plot_crisis_curves.py - 六场危机：沪深300 / 红利低波 / 黄金 对比曲线 + 卖金买ETF 标注

产出两张图：
  fig1_crisis_panels.png  —— 2×3 面板，每场危机一条曲线组，标注底部与卖金买ETF时点
  fig2_aligned_at_s5.png  —— 以「卖金买ETF」那天为 0 对齐，看之后 24 个月走势
"""
import sys, sqlite3
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Patch

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
DIV = li("H30269")        # 红利低波价格指数（515450 跟踪，515100 同底）
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
    # ★ 修正：顶部必须是「底部之前」的最高点，否则窗口延伸到反弹期会把顶部认成反弹后
    trough = seg.idxmin()
    top = seg[seg.index <= trough].idxmax()
    low = float(seg.min())
    after = seg[seg.index > trough]
    bounce = after / low - 1
    hit = bounce[bounce >= 0.15]
    trig = hit.index[0] if len(hit) else None
    # 红利过滤
    div_above = np.nan
    ok_filter = None
    if trig is not None:
        dlow = float(DIV[(DIV.index >= t0) & (DIV.index <= trig)].min())
        div_above = px(DIV, trig) / dlow - 1
        ok_filter = div_above <= 0.20
    return {"top": top, "trough": trough, "low": low, "trig": trig,
            "div_above": div_above, "ok": ok_filter}


fig, axes = plt.subplots(2, 3, figsize=(21, 11))
axes = axes.ravel()

for k, (nm, t0, t1) in enumerate(CR):
    ax = axes[k]
    st = analyse(t0, t1)
    top = st["top"]
    end = (st["trig"] + pd.Timedelta(days=730)) if st["trig"] is not None else top + pd.Timedelta(days=730)
    x0 = top - pd.Timedelta(days=60)
    win = (HS300.index >= x0) & (HS300.index <= end)
    base_h = px(HS300, top)
    base_d = px(DIV, top)
    base_g = px(GLD, top)

    idx = HS300.index[win]
    ax.plot(idx, HS300[win] / base_h * 100, color="#2563eb", lw=2.0, label="沪深300")
    d_win = DIV[(DIV.index >= x0) & (DIV.index <= end)]
    ax.plot(d_win.index, d_win / base_d * 100, color="#16a34a", lw=2.0, label="红利低波(515450跟踪)")
    g_win = GLD[(GLD.index >= x0) & (GLD.index <= end)]
    ax.plot(g_win.index, g_win / base_g * 100, color="#d97706", lw=2.2, label="黄金(GLD)")

    ax.axhline(100, color="#9ca3af", ls=":", lw=1)
    # 沪深300 底部
    ax.axvline(st["trough"], color="#6b7280", ls="--", lw=1.3, alpha=0.8)
    ax.annotate("沪深300\n见底", xy=(st["trough"], ax.get_ylim()[0]),
                xytext=(0, 6), textcoords="offset points",
                ha="center", va="bottom", fontsize=8.5, color="#6b7280")

    # 卖金买ETF 时点
    if st["trig"] is not None:
        y = px(HS300, st["trig"]) / base_h * 100
        color = "#dc2626" if st["ok"] else "#f59e0b"
        ax.axvline(st["trig"], color=color, ls="-", lw=2.2, alpha=0.85)
        ax.scatter([st["trig"]], [y], marker="*", s=340, color=color,
                   edgecolor="white", linewidth=1.2, zorder=6)
        label = "【买】卖金买ETF" if st["ok"] else "【不买】红利已涨%.0f%%" % (st["div_above"] * 100)
        ax.annotate(f"{label}\n{st['trig'].date()}", xy=(st["trig"], y),
                    xytext=(10, -32), textcoords="offset points",
                    fontsize=9, color=color, fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.35", fc="white", ec=color, alpha=0.92))
    else:
        ax.text(0.5, 0.5, "无 15% 反弹触发", transform=ax.transAxes,
                ha="center", fontsize=11, color="#dc2626")

    sub = f"卖金时：红利距底 {st['div_above']*100:.0f}%" if st["div_above"] == st["div_above"] else ""
    ax.set_title(f"{nm}\n{sub}", fontsize=12, fontweight="bold")
    ax.grid(alpha=0.25, ls=":")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%y/%m"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=4))
    ax.tick_params(labelsize=8.5)
    ax.set_ylabel("归一化（危机顶=100）", fontsize=9)
    if k == 0:
        ax.legend(fontsize=9, loc="upper left", framealpha=0.9)

fig.suptitle("六场金融危机：沪深300 / 红利低波 / 黄金 走势对比（危机顶=100）\n"
             "红/橙竖线 = 卖金买ETF 时点；灰虚线 = 沪深300 见底",
             fontsize=15, fontweight="bold", y=0.995)
fig.tight_layout(rect=[0, 0, 1, 0.965])
f1 = OUT / "fig1_crisis_panels.png"
fig.savefig(f1, dpi=130, bbox_inches="tight")
plt.close(fig)
print(f"✅ {f1.name}")

# ── 图 2：以「卖金买ETF」为 0 对齐
fig2, ax2 = plt.subplots(figsize=(13, 7.5))
colors = ["#1d4ed8", "#0ea5e9", "#16a34a", "#eab308", "#f97316", "#dc2626"]
rows = []
for k, (nm, t0, t1) in enumerate(CR):
    st = analyse(t0, t1)
    if st["trig"] is None:
        continue
    trig = st["trig"]
    lo = trig - pd.Timedelta(days=180)
    hi = trig + pd.Timedelta(days=730)
    s = HS300[(HS300.index >= lo) & (HS300.index <= hi)]
    if len(s) < 60:
        continue
    x = [(d - trig).days / 30.44 for d in s.index]
    y = s.values / px(HS300, trig) * 100
    ax2.plot(x, y, color=colors[k % len(colors)], lw=1.9, label=nm, alpha=0.9)
    rows.append((nm, st))

ax2.axvline(0, color="#dc2626", lw=2.4)
ax2.axhline(100, color="#9ca3af", ls=":", lw=1)
ax2.text(0.3, ax2.get_ylim()[0] if False else 0.03, "卖金买ETF = 第 0 天",
         transform=ax2.get_xaxis_transform(), color="#dc2626", fontsize=10, fontweight="bold")
ax2.set_xlabel("距「卖金买ETF」的月数", fontsize=11)
ax2.set_ylabel("沪深300（卖金日 = 100）", fontsize=11)
ax2.set_title("六场危机对齐到「卖金买ETF」时点后，沪深300 的相对走势", fontsize=14, fontweight="bold")
ax2.grid(alpha=0.3, ls=":")
ax2.legend(fontsize=9.5, loc="upper left")
fig2.tight_layout()
f2 = OUT / "fig2_aligned_at_s5.png"
fig2.savefig(f2, dpi=140, bbox_inches="tight")
plt.close(fig2)
print(f"✅ {f2.name}")

# ── 文字汇总
print("\n" + "=" * 100)
print("【图注数据汇总】")
print("=" * 100)
print(f"  {'危机':<16s}{'沪深300底':>12s}{'卖金日':>12s}{'红利距底':>10s}{'判定':>8s}")
for nm, st in rows:
    print(f"  {nm:<16s}{str(st['trough'].date()):>12s}{str(st['trig'].date()):>12s}"
          f"{st['div_above']*100:>9.0f}%{'买' if st['ok'] else '不买':>8s}")
