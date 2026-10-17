# -*- coding: utf-8 -*-
"""QF-LLM 可视化看板生成器：把 runs/ 的 JSON 渲染成自包含 HTML（可自动刷新）。"""
from __future__ import annotations

import glob
import json
import os
from datetime import datetime


def _f(x, nd=4):
    if x is None:
        return "-"
    try:
        return f"{float(x):.{nd}f}"
    except Exception:
        return str(x)


def _bar(val, vmax, width_px=110):
    frac = min(abs(val) / vmax, 1.0) if vmax > 0 else 0.0
    color = "#2ecc71" if val >= 0 else "#e74c3c"
    return (f'<span style="display:inline-block;width:{width_px}px;background:#eee;height:9px;'
            f'border-radius:3px;vertical-align:middle;margin-right:6px;">'
            f'<span style="display:block;width:{frac*100:.0f}%;height:9px;background:{color};'
            f'border-radius:3px;"></span></span>')


def generate_report(runs_dir: str, out_html: str) -> str:
    runs_dir = os.path.abspath(runs_dir)
    pool = []
    pool_path = os.path.join(runs_dir, "pool.json")
    if os.path.exists(pool_path):
        with open(pool_path, encoding="utf-8") as f:
            pool = json.load(f)

    rounds = []
    for rf in sorted(glob.glob(os.path.join(runs_dir, "round_*.json"))):
        with open(rf, encoding="utf-8") as f:
            rounds.append((os.path.basename(rf), json.load(f)))

    total_cand = sum(len(r[1].get("candidates", [])) for r in rounds)
    total_kept = sum(len(r[1].get("kept", [])) for r in rounds)
    elim = (total_cand - total_kept) / total_cand * 100 if total_cand else 0.0

    all_abs_ic = [abs(c.get("rank_ic", 0)) for _, r in rounds
                  for c in r.get("candidates", []) if "rank_ic" in c]
    vmax = max(all_abs_ic) if all_abs_ic else 0.0001

    H = []
    H.append('<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">')
    H.append('<meta http-equiv="refresh" content="20">')
    H.append('<title>QF-LLM 因子挖掘看板</title>')
    H.append('''<style>
body{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;margin:24px;color:#222;background:#f7f8fa}
h1{font-size:22px;margin:0 0 4px}
h2{font-size:17px;margin:28px 0 8px;border-left:4px solid #3498db;padding-left:8px}
.stats{display:flex;gap:14px;flex-wrap:wrap;margin:12px 0}
.stat{background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:10px 16px;min-width:110px}
.stat b{display:block;font-size:20px;color:#3498db}
table{border-collapse:collapse;width:100%;background:#fff;font-size:13px;margin:8px 0}
th,td{border:1px solid #e5e7eb;padding:6px 8px;text-align:left}
th{background:#f0f3f7}
.keep{color:#27ae60;font-weight:600}
.drop{color:#e74c3c;font-weight:600}
.summary{background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:12px 16px;white-space:pre-wrap;font-size:13px;line-height:1.6}
.muted{color:#888;font-size:12px}
</style></head><body>''')

    H.append('<h1>QF-LLM 因子挖掘看板</h1>')
    H.append(f'<div class="muted">生成时间 {datetime.now():%Y-%m-%d %H:%M:%S} · '
             f'数据源 bars.db（全市场 qfq）· 页面每 20s 自动刷新</div>')
    H.append('<div class="stats">')
    H.append(f'<div class="stat"><b>{len(rounds)}</b>轮</div>')
    H.append(f'<div class="stat"><b>{total_cand}</b>候选</div>')
    H.append(f'<div class="stat"><b>{total_kept}</b>入池</div>')
    H.append(f'<div class="stat"><b>{len(pool)}</b>池内因子</div>')
    H.append(f'<div class="stat"><b>{elim:.0f}%</b>淘汰率</div>')
    H.append('</div>')

    # ---- 因子池 ----
    H.append('<h2>当前因子池</h2>')
    if pool:
        H.append('<table><tr><th>因子</th><th>|RankIC|</th><th>|ICIR|</th><th>覆盖率</th>'
                 '<th>最大相关</th><th>原始方向</th><th>总分</th></tr>')
        for p in pool:
            ic_abs = p.get("ic_abs", abs(p.get("rank_ic", 0)))
            ir_abs = p.get("ir_abs", abs(p.get("ic_ir", 0)))
            d = p.get("direction", 1)
            H.append(f'<tr><td>{p.get("name","?")}</td><td>{_f(ic_abs)}</td>'
                     f'<td>{_f(ir_abs,2)}</td><td>{_f(p.get("coverage"),3)}</td>'
                     f'<td>{_f(p.get("max_corr"),3)}</td>'
                     f'<td>{"正向" if d > 0 else "反向(已取反)"}</td>'
                     f'<td>{_f(p.get("total"),3)}</td></tr>')
        H.append('</table>')
    else:
        H.append('<div class="muted">暂无入池因子</div>')

    # ---- 逐轮 ----
    for fname, r in rounds:
        rnd = r.get("round", "?")
        H.append(f'<h2>第 {rnd} 轮 · {fname}</h2>')
        cands = r.get("candidates", [])
        if cands:
            H.append('<table><tr><th>因子</th><th>RankIC</th><th>ICIR</th><th>覆盖率</th>'
                     '<th>最大相关</th><th>总分</th><th>结论</th><th>IC 幅值</th></tr>')
            for c in cands:
                if "error" in c:
                    H.append(f'<tr><td>{c.get("name","?")}</td>'
                             f'<td colspan="7" class="muted">❌ {c["error"][:200]}</td></tr>')
                else:
                    keep = bool(c.get("pass"))
                    ic = c.get("rank_ic", 0)
                    H.append(f'<tr><td>{c.get("name","?")}</td><td>{_f(ic)}</td>'
                             f'<td>{_f(c.get("ic_ir"))}</td><td>{_f(c.get("coverage"),3)}</td>'
                             f'<td>{_f(c.get("max_corr"),3)}</td><td>{_f(c.get("total"),3)}</td>'
                             f'<td class="{"keep" if keep else "drop"}">'
                             f'{"✅入池" if keep else "❌淘汰"}</td>'
                             f'<td>{_bar(ic, vmax)}</td></tr>')
            H.append('</table>')
        s = r.get("summary", "")
        if s:
            H.append(f'<div class="summary">{s}</div>')

    H.append('</body></html>')
    os.makedirs(os.path.dirname(os.path.abspath(out_html)), exist_ok=True)
    with open(out_html, "w", encoding="utf-8") as f:
        f.write("\n".join(H))
    return out_html


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="runs")
    ap.add_argument("--out", default="report.html")
    a = ap.parse_args()
    print("report written:", generate_report(a.runs, a.out))
