# -*- coding: utf-8 -*-
"""shot_pension_gs.py - 用真实浏览器（Playwright + msedge）验证 /pension 页面新卡片

按 AGENTS.md：只看 HTTP 200 不算完成，必须打开页面、抓 JS 错误、截图确认。
"""
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright

OUT = Path(r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant\reports")
OUT.mkdir(parents=True, exist_ok=True)
URL = "http://127.0.0.1:8787/pension"

errors, console = [], []
with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge", headless=True)
    pg = b.new_page(viewport={"width": 1600, "height": 1200})
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: console.append((m.type, m.text)) if m.type in ("error", "warning") else None)
    pg.goto(URL, wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(7000)

    # 检查新卡片是否渲染
    checks = {}
    for sel, name in (
        ("#gs-stage", "阶段横幅"),
        ("#gs-progress", "进度条容器"),
        ("#gs-verdict", "综合判断"),
        ("#gs-tbl", "明细表"),
        ("#gs-note", "脚注"),
    ):
        try:
            el = pg.query_selector(sel)
            checks[name] = bool(el and (el.inner_text() or "").strip() not in ("", "加载中…"))
        except Exception:
            checks[name] = False

    stage_txt = (pg.inner_text("#gs-stage") or "")[:200] if pg.query_selector("#gs-stage") else ""
    verdict_txt = (pg.inner_text("#gs-verdict") or "")[:250] if pg.query_selector("#gs-verdict") else ""
    prog_txt = (pg.inner_text("#gs-progress") or "")[:400] if pg.query_selector("#gs-progress") else ""

    # 进度条数量
    bars = pg.eval_on_selector_all("#gs-progress div[style*='height:10px']", "els => els.length")

    # 截图：整页 + 新卡片
    pg.screenshot(path=str(OUT / "pension_gs_full.png"), full_page=True)
    try:
        card = pg.query_selector("#gs-progress")
        if card:
            box = card.bounding_box()
            if box:
                pg.screenshot(path=str(OUT / "pension_gs_card.png"),
                              clip={"x": max(0, box["x"] - 30), "y": max(0, box["y"] - 110),
                                    "width": min(1600, box["width"] + 60), "height": box["height"] + 160})
    except Exception as e:
        print(f"  卡片截图失败: {e}")
    b.close()

print("=" * 90)
print("【渲染检查】")
print("=" * 90)
for k, v in checks.items():
    print(f"  {'✅' if v else '❌'} {k}")
print(f"\n  进度条数量：{bars}（应有 3 条：主信号2档 + 金银比1条）")
print(f"\n  阶段：{stage_txt}")
print(f"  判断：{verdict_txt}")
print(f"\n  进度区文本前 400 字：\n    " + prog_txt.replace("\n", " / "))

print("\n" + "=" * 90)
print("【JS 错误】")
print("=" * 90)
if errors:
    for e in errors:
        print(f"  ❌ {e}")
else:
    print("  ✅ 无 pageerror")
errs = [c for c in console if c[0] == "error"]
print(f"  console error 数量：{len(errs)}")
for t, m in errs[:5]:
    print(f"    {t}: {m[:160]}")

print(f"\n截图：{OUT / 'pension_gs_full.png'}")
print(f"      {OUT / 'pension_gs_card.png'}")
