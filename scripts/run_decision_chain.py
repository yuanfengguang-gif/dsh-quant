# -*- coding: utf-8 -*-
"""scripts/run_decision_chain.py —— 决策链一键运行（L0 择时 → L1 机会池 → L2 Pitch → 每日信号）

把主系统每日链（18:30 全链）的「决策侧」串成一条命令，省去逐个手动跑。
注意：数据侧（分钟 7z + 日线增量）在 data/daily_pipeline.py（依赖主系统分钟目录 + baostock），不在此链。

链式顺序（同 deck_server 消费的 JSON 源）：
  1. L0 择时   ：data/traffic_light.py          → output/dynamic_regime.json（仓位档）+ traffic_light.json
  2. L1 机会池 ：factors/opportunities/scan.py --pitch → logs/opp_pool_*.json
  3. L2 Pitch  ：factors/opportunities/pitch_v2.py      → logs/pitch_deck_*.json
  4. L1 信号   ：factors/combo_daily_signal.py --topn 20 → output/daily_signal.json

用法：python scripts/run_decision_chain.py [--skip-l0] [--skip-l1] [--skip-l2]
"""
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PY = sys.executable

STEPS = [
    ("L0 择时", ["data/traffic_light.py"]),
    ("L1 机会池", ["factors/opportunities/scan.py", "--pitch"]),
    ("L2 Pitch", ["factors/opportunities/pitch_v2.py"]),
    ("L1 信号", ["factors/combo_daily_signal.py", "--topn", "20"]),
]


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-l0", action="store_true")
    ap.add_argument("--skip-l1", action="store_true")
    ap.add_argument("--skip-l2", action="store_true")
    args = ap.parse_args()

    skip = set()
    if args.skip_l0:
        skip.add("L0 择时")
    if args.skip_l1:
        skip.add("L1 机会池")
        skip.add("L1 信号")
    if args.skip_l2:
        skip.add("L2 Pitch")

    results = []
    t0 = time.time()
    for name, cmd in STEPS:
        if name in skip:
            print(f"[跳过] {name}", flush=True)
            continue
        print(f"[运行] {name}: python {' '.join(cmd)}", flush=True)
        try:
            r = subprocess.run([PY] + cmd, cwd=str(BASE), capture_output=True, text=True,
                               timeout=1800)
            ok = r.returncode == 0
            tail = (r.stdout or r.stderr or "").strip()[-200:]
            print(f"  {'✓' if ok else '✗'} 退出码 {r.returncode}\n  {tail}\n", flush=True)
            results.append((name, ok, tail))
        except subprocess.TimeoutExpired:
            print(f"  ✗ 超时（>30min）\n", flush=True)
            results.append((name, False, "超时"))
        except Exception as e:
            print(f"  ✗ 异常: {e}\n", flush=True)
            results.append((name, False, str(e)[:100]))

    el = (time.time() - t0) / 60
    print(f"\n=== 决策链完成（{el:.1f} 分钟）===")
    for name, ok, _ in results:
        print(f"  {'✓' if ok else '✗'} {name}")
    print("\n产出 JSON 供 deck_server 消费：")
    print("  - output/dynamic_regime.json（择时档位）")
    print("  - logs/opp_pool_*.json（机会池）")
    print("  - logs/pitch_deck_*.json（Pitch Deck，待 /api/decide 审批）")
    print("  - output/daily_signal.json（每日信号）")


if __name__ == "__main__":
    main()
