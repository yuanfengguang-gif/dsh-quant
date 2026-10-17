# -*- coding: utf-8 -*-
"""scripts/run_review.py —— 复盘报告（层8 复盘调整层）

读最新回测/前向/压力测试结果 + 数据审计，合成一份复盘报告（组合绩效 vs 预期 + 因子健康 + 数据健康 + 预警）。

用法：python scripts/run_review.py [--out report/review_YYYYMMDD.md]
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from risk.alert_engine import AlertEngine

LOGS = BASE / "logs"


def load_json(name):
    p = LOGS / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def parse_warnings(warns):
    """把 walk_forward 的 warning 字符串解析成结构化预警。"""
    factor_fail = {}
    drawdown = None
    for w in warns or []:
        m = re.search(r"因子 (\w+) 滚动.*ICIR=([-+0-9.]+)", w)
        if m:
            factor_fail[m.group(1)] = float(m.group(2))
        m2 = re.search(r"回撤 ([-+0-9.]+%)", w)
        if m2 and drawdown is None:
            drawdown = m2.group(1)
    return factor_fail, drawdown


def run_data_audit_quick():
    """快速数据审计 → 健康度。"""
    try:
        from risk.data_audit import DataAuditor
        auditor = DataAuditor()
        r = auditor.run(quick=True)
        return r
    except Exception as e:
        return {"health": None, "blocked": False, "fails": [], "error": str(e)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    fwd = load_json("walk_forward.json")
    stress = load_json("stress_test.json")
    audit = run_data_audit_quick()

    # 组合绩效
    fwd_m = (fwd or {}).get("metrics", {})
    fwd_excess = (fwd or {}).get("excess_annual")
    fwd_sharpe = fwd_m.get("sharpe")
    fwd_dd = fwd_m.get("max_drawdown")
    regime_now = (fwd or {}).get("regime_now", {})
    factor_fail, dd_str = parse_warnings((fwd or {}).get("warnings", []))

    # 预警引擎
    eng = AlertEngine()
    data_health = audit.get("health")
    alerts = eng.check(
        current_drawdown=fwd_dd,
        factor_icirs={**{f: None for f in (fwd or {}).get("factors", [])}, **factor_fail}
        if factor_fail else None,
        data_health=data_health,
        regime_state="bear" if regime_now.get("multiplier", 1.0) < 0.999 else "bull",
    )

    # 生成报告
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"# 复盘报告 · {now}", ""]
    lines.append("## 一、组合绩效（前向 2026 样本外）")
    if fwd:
        lines.append(f"- 净超额：**{fwd_excess:+.2%}**" if fwd_excess is not None else "- 净超额：N/A")
        lines.append(f"- 夏普：{fwd_sharpe:.2f}" if fwd_sharpe is not None else "- 夏普：N/A")
        lines.append(f"- 最大回撤：{fwd_dd:.2%}" if fwd_dd is not None else "- 回撤：N/A")
        lines.append(f"- 择时：{regime_now.get('state', 'N/A')}（乘数 {regime_now.get('multiplier', 'N/A')}）")
    else:
        lines.append("- 无 walk_forward.json（先跑 `python factors/walk_forward.py`）")
    lines.append("")

    lines.append("## 二、压力测试（危机窗口）")
    if stress and stress.get("crisis_windows"):
        lines.append("| 窗口 | 组合收益 | 基准收益 | 超额 | 组合回撤 | 基准回撤 |")
        lines.append("|---|---|---|---|---|---|")
        for w in stress["crisis_windows"]:
            lines.append(f"| {w['窗口']} | {w['组合收益']:+.1%} | {w['基准收益']:+.1%} | "
                         f"{w['超额']:+.1%} | {w['组合回撤']:.1%} | {w['基准回撤']:.1%} |")
    else:
        lines.append("- 无 stress_test.json（先跑 `python risk/stress_test.py`）")
    lines.append("")

    lines.append("## 三、因子健康")
    if factor_fail:
        lines.append("- **失效因子（滚动20日ICIR转负）**：")
        for n, v in factor_fail.items():
            lines.append(f"  - {n}: {v:+.3f}")
    else:
        lines.append("- 无因子失效（或未跑 walk_forward）")
    lines.append("")

    lines.append("## 四、数据健康")
    if data_health is not None:
        status = "🔴 阻断" if audit.get("blocked") else "🟢 放行"
        lines.append(f"- 健康度：**{data_health:.0f}/100**（{status}）")
        for f in audit.get("fails", []):
            lines.append(f"  - FAIL: {f}")
    else:
        lines.append(f"- 审计异常：{audit.get('error', 'N/A')}")
    lines.append("")

    lines.append("## 五、预警（5 类）")
    if alerts:
        for a in alerts:
            lines.append(f"- [{a.level}] **{a.type}**: {a.message}")
    else:
        lines.append("- 无预警")
    lines.append("")

    # 通知
    eng.notify(alerts)

    out = args.out or (BASE / "report" / f"review_{datetime.now():%Y%m%d_%H%M%S}.md")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n复盘报告已存：{out}")


if __name__ == "__main__":
    main()
