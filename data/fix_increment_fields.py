# -*- coding: utf-8 -*-
"""data/fix_increment_fields.py —— 回填通达信增量行的缺失字段（DS-01b / DS-05）

背景（CORE_ISSUE_TRACKER.md 第九节）：
  `tdx_daily_update.py::write_bars` 历史版本从不计算 `turn`、并把 `is_st` 写死 0，
  且批内 `groupby.shift(1)` 让每批首日 `preclose/pct_chg` 为空 →
  2026-10-12 ~ 10-16 共 27,860 行（每日 5,572 只）turn 全空、is_st 全 0、10-12 的 pct_chg 全空。

本脚本做三件事：
  1) turn  = 成交量(股) / (ActiveCapital(万股) × 10000)   ← 与历史段同口径（小数比率）
  2) is_st = stock_info_tdx.IsSTGP（当前状态；历史段由 patch_is_st / is_st_inferred 负责）
  3) preclose / pct_chg / change = 用「同库同口径的前一交易日 close」兜底（只补空值）
  4) DS-05：删除 bars.db 里 16 行 source='baostock' / adjust='none' 残留（先备份到 logs/）

用法：
  python data/fix_increment_fields.py --dry-run   # 只看会改多少行，不写库
  python data/fix_increment_fields.py             # 实际执行
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent.parent
CACHE = BASE / "data" / "cache"
BARS = CACHE / "bars.db"
TDX = CACHE / "bars_tdx.db"
META = CACHE / "tdx_meta.db"
LOGS = BASE / "logs"
LOGS.mkdir(exist_ok=True)


def load_meta():
    con = sqlite3.connect(f"file:{META.as_posix()}?mode=ro", uri=True, timeout=10)
    cap, st = {}, {}
    for code, ac, iss in con.execute("SELECT code, ActiveCapital, IsSTGP FROM stock_info_tdx"):
        try:
            cap[code] = float(ac)
        except (TypeError, ValueError):
            continue
        st[code] = 1 if str(iss).strip() == "1" else 0
    con.close()
    return cap, st


def fix_one(db: Path, adjust: str, cap: dict, st: dict, dry: bool) -> dict:
    con = sqlite3.connect(str(db))
    if not dry:
        con.execute("PRAGMA synchronous=OFF")
    stats = {"db": db.name, "adjust": adjust, "rows": 0,
             "turn_before_null": 0, "is_st_before": 0, "preclose_before_null": 0,
             "turn_fixed": 0, "is_st_fixed": 0, "preclose_fixed": 0}

    rows = con.execute(
        "SELECT code, date, volume, turn, is_st, preclose, pct_chg FROM daily_bar "
        "WHERE adjust=? AND source='tdx_api' ORDER BY code, date", (adjust,)).fetchall()
    stats["rows"] = len(rows)
    stats["turn_before_null"] = sum(1 for r in rows if r[3] is None)
    stats["is_st_before"] = sum(1 for r in rows if r[4] == 1)
    stats["preclose_before_null"] = sum(1 for r in rows if r[5] is None)
    print(f"\n=== {db.name}（adjust={adjust}）增量行 {len(rows):,}")
    print(f"    改前: turn 空 {stats['turn_before_null']:,} | is_st=1 {stats['is_st_before']:,} | "
          f"preclose 空 {stats['preclose_before_null']:,}")
    if not rows:
        con.close()
        return stats

    # 前一交易日 close 缓存（同库同 adjust）
    prev_cache: dict[tuple[str, str], float | None] = {}

    def prev_close(code: str, date: str):
        key = (code, date)
        if key in prev_cache:
            return prev_cache[key]
        r = con.execute(
            "SELECT close FROM daily_bar WHERE code=? AND adjust=? AND date<? "
            "ORDER BY date DESC LIMIT 1", (code, adjust, date)).fetchone()
        prev_cache[key] = r[0] if r else None
        return prev_cache[key]

    upd_turn, upd_st, upd_pre = [], [], []
    for code, date, vol, turn, is_st, pre, pct in rows:
        c = cap.get(code)
        t_new = (float(vol) / (c * 10000.0)) if (c and vol) else None
        if turn is None and t_new is not None and t_new > 0:
            upd_turn.append((t_new, code, date))
        s_new = st.get(code, 0)
        if is_st != s_new:
            upd_st.append((s_new, code, date))
        if pre is None:
            p = prev_close(code, date)
            if p:
                upd_pre.append((p, code, date))

    stats["turn_fixed"] = len(upd_turn)
    stats["is_st_fixed"] = len(upd_st)
    stats["preclose_fixed"] = len(upd_pre)
    print(f"    将修: turn {len(upd_turn):,} | is_st {len(upd_st):,} | preclose {len(upd_pre):,}")

    if dry:
        con.close()
        return stats

    with con:
        if upd_turn:
            con.executemany(
                "UPDATE daily_bar SET turn=? WHERE code=? AND date=? AND adjust=?", 
                [(t, c, d, adjust) for t, c, d in upd_turn])
        if upd_st:
            con.executemany(
                "UPDATE daily_bar SET is_st=? WHERE code=? AND date=? AND adjust=?",
                [(s, c, d, adjust) for s, c, d in upd_st])
        if upd_pre:
            con.executemany(
                "UPDATE daily_bar SET preclose=? WHERE code=? AND date=? AND adjust=? AND preclose IS NULL",
                [(p, c, d, adjust) for p, c, d in upd_pre])
            # 补完 preclose 后重算 pct_chg（+ 若存在 change 列也一并补）
            _cols = [r[1] for r in con.execute("PRAGMA table_info(daily_bar)")]
            _set = "pct_chg = close/preclose - 1.0"
            if "change" in _cols:
                _set += ", change = close - preclose"
            con.execute(
                f"UPDATE daily_bar SET {_set} "
                "WHERE adjust=? AND source='tdx_api' AND preclose IS NOT NULL AND preclose>0 "
                "AND (pct_chg IS NULL OR " + ("change IS NULL" if "change" in _cols else "0") + ")",
                (adjust,))

    # 改后统计
    after = con.execute(
        "SELECT COUNT(*), SUM(turn IS NULL), SUM(is_st=1), SUM(preclose IS NULL), SUM(pct_chg IS NULL) "
        "FROM daily_bar WHERE adjust=? AND source='tdx_api'", (adjust,)).fetchone()
    stats["after"] = {"rows": after[0], "turn_null": after[1], "is_st_1": after[2],
                      "preclose_null": after[3], "pct_chg_null": after[4]}
    print(f"    改后: turn 空 {after[1]:,} | is_st=1 {after[2]:,} | preclose 空 {after[3]:,} | "
          f"pct_chg 空 {after[4]:,}")
    con.close()
    return stats


def crossfill_tdx_preclose(dry: bool) -> dict:
    """bars_tdx 的 unadj 增量首日（2026-10-12）在 unadj 口径下没有更早的行 →
    preclose 仍为空。用 bars.db(qfq) 的同日 pct_chg 反推 unadj preclose：
        preclose_unadj = close_unadj / (1 + pct_chg)
    （pct_chg 是日内同比，除权日之外与价格口径无关；作为兜底足够）
    这样 fix_bars_increment 再跑时不会把 NULL 覆盖回 bars.db。
    """
    src = sqlite3.connect(f"file:{BARS.as_posix()}?mode=ro", uri=True)
    pct = {(r[0], r[1]): r[2] for r in src.execute(
        "SELECT code, date, pct_chg FROM daily_bar WHERE adjust='qfq' AND source='tdx_api' "
        "AND pct_chg IS NOT NULL")}
    src.close()
    con = sqlite3.connect(str(TDX))
    rows = con.execute(
        "SELECT code, date, close FROM daily_bar WHERE adjust='unadj' AND source='tdx_api' "
        "AND preclose IS NULL").fetchall()
    upd = []
    for code, date, close in rows:
        p = pct.get((code, date))
        if p is not None and close and (1 + p) > 0:
            upd.append((close / (1 + p), code, date))
    print(f"\n=== bars_tdx unadj 交叉补 preclose: 待补 {len(rows):,} → 可补 {len(upd):,}")
    if upd and not dry:
        with con:
            con.executemany(
                "UPDATE daily_bar SET preclose=? WHERE code=? AND date=? AND adjust='unadj' "
                "AND preclose IS NULL", upd)
            _cols = [r[1] for r in con.execute("PRAGMA table_info(daily_bar)")]
            _set = "pct_chg = close/preclose - 1.0"
            if "change" in _cols:
                _set += ", change = close - preclose"
            con.execute(f"UPDATE daily_bar SET {_set} WHERE adjust='unadj' AND source='tdx_api' "
                        "AND preclose IS NOT NULL AND preclose>0 AND pct_chg IS NULL")
        left = con.execute("SELECT COUNT(*) FROM daily_bar WHERE adjust='unadj' AND "
                           "source='tdx_api' AND preclose IS NULL").fetchone()[0]
        print(f"    补后仍空: {left:,}")
    con.close()
    return {"todo": len(rows), "filled": len(upd)}


def check_index_rows(dry: bool) -> dict:
    """★2026-10-17 更正：bars.db 里 source='baostock' 的 16 行不是残留，而是
    `SH.000300` 沪深300指数日线（2026-09-17~2026-10-16，由 fetch_index_daily.py 每日维护）。
    → **不能删**（删了就丢指数）。按用户原则「保留的且通达信能取到 → 切通达信」，
      应把 fetch_index_daily.py 切换到通达信（实测 `000300.SH` 与库内值完全一致），
      并把代码格式从 `SH.000300`（前缀式）统一为 `000300.SH`（后缀式）。
    该切换归属 T3/T4，本脚本只做检测与登记。
    """
    con = sqlite3.connect(f"file:{BARS.as_posix()}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT code, COUNT(*), MIN(date), MAX(date), adjust, source "
        "FROM daily_bar WHERE source='baostock' GROUP BY code, adjust, source").fetchall()
    print(f"\n=== DS-05（已更正）source='baostock' 的 {len(rows)} 组：")
    for r in rows:
        print(f"    {r[0]}: {r[1]} 行  {r[2]} ~ {r[3]}  adjust={r[4]}  source={r[5]}")
    print("    ⚠️ 这是沪深300指数序列，**不删除**；待 T3 切到通达信（000300.SH）")
    con.close()
    return {"groups": len(rows), "action": "keep-pending-switch"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    dry = args.dry_run
    print(f"{'[DRY-RUN] ' if dry else ''}增量行字段回填  {datetime.now():%Y-%m-%d %H:%M:%S}")

    cap, st = load_meta()
    print(f"元数据: 流通股本 {len(cap):,} 只 | IsSTGP=1 {sum(st.values()):,} 只")

    out = {"ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "dry_run": dry, "jobs": []}
    out["jobs"].append(fix_one(TDX, "unadj", cap, st, dry))
    out["jobs"].append(fix_one(BARS, "qfq", cap, st, dry))
    out["crossfill"] = crossfill_tdx_preclose(dry)
    out["index_rows"] = check_index_rows(dry)

    if not dry:
        p = LOGS / f"fix_increment_fields_{datetime.now():%Y%m%d_%H%M%S}.json"
        p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n报告: {p}")
        print("\n下一步验收: python risk\\verify_bars_switch.py  （看 [4c]/[4d] turn 缺失应为 0）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
