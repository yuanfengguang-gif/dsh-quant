# -*- coding: utf-8 -*-
"""全市场日线批量下载（AkShare 新浪源）——baostock 免费服务不可用时的备源兜底。

与 bulk_loader.py（baostock 主源）同语义，但走 fetcher_akshare.ensure_daily（HTTP 新浪源，更稳）。
支持断点续传（cache.covers 判定）、失败重试、进度日志。

用法：
  python data/bulk_loader_akshare.py --limit 50    # 小样本验证
  python data/bulk_loader_akshare.py               # 全量（断点续传）
  python data/bulk_loader_akshare.py --status
"""
import argparse
import sqlite3
import sys
import time
from datetime import datetime
from multiprocessing import Pool
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from data.cache import DailyCache
from data.fetcher_akshare import ensure_daily

START_DATE = "2019-01-02"  # 首个交易日（2019-01-01 元旦休市），与 bar_meta 数据起点一致，保证 covers 断点续传命中
LOG_FILE = BASE / "logs" / "bulk_load_akshare.log"
PROGRESS_FILE = BASE / "logs" / "bulk_load_akshare_progress.txt"
CHECKPOINT_EVERY = 50
DEFAULT_WORKERS = 2


def log(msg):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_codes():
    # 仅上市（status='1'）股票，与 bulk_loader.py（baostock）口径一致；退市股由 backfill_delisted.py 单独处理
    con = sqlite3.connect(str(BASE / "data" / "cache" / "stock_basic.db"))
    codes = [r[0] for r in con.execute(
        "SELECT code FROM stock_basic WHERE status='1' ORDER BY code").fetchall()]
    con.close()
    return codes


def _worker(code):
    cache = DailyCache()
    last_err = None
    for attempt in range(3):
        try:
            df = ensure_daily(code, START_DATE, None, "qfq", cache=cache, retries=2)
            if df is None or df.empty:
                return (code, "empty", None)
            return (code, "ok", None)
        except Exception as e:
            last_err = str(e)[:80]
            if attempt < 2:
                time.sleep(2.0 * (2 ** attempt))
    return (code, "fail", last_err)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    if args.status:
        if PROGRESS_FILE.exists():
            print(PROGRESS_FILE.read_text(encoding="utf-8"))
        else:
            print("尚无 akshare 批量下载进度")
        return 0

    codes = load_codes()
    if args.limit:
        codes = codes[:args.limit]
    total = len(codes)
    log(f"akshare 日线批量下载: 共 {total} 只（{START_DATE} 起，qfq）")

    t0 = time.time()
    done = empty = fail = 0
    failed = []

    def handle(res):
        nonlocal done, empty, fail
        if res[1] == "ok":
            done += 1
        elif res[1] == "empty":
            empty += 1
        else:
            fail += 1
            failed.append((res[0], res[2]))

    if args.workers > 1 and total > 1:
        with Pool(args.workers) as pool:
            for i, res in enumerate(pool.imap_unordered(_worker, codes, chunksize=2), 1):
                handle(res)
                if i % CHECKPOINT_EVERY == 0:
                    el = time.time() - t0
                    rate = i / el
                    eta = (total - i) / rate if rate > 0 else 0
                    log(f"[进度] {i}/{total} 成功{done} 空{empty} 失败{fail} "
                        f"速率{rate:.2f}只/s 剩余约{eta/60:.0f}分钟")
    else:
        for i, code in enumerate(codes, 1):
            res = _worker(code)
            handle(res)
            if i % CHECKPOINT_EVERY == 0:
                el = time.time() - t0
                rate = i / el
                eta = (total - i) / rate if rate > 0 else 0
                log(f"[进度] {i}/{total} 成功{done} 空{empty} 失败{fail} "
                    f"速率{rate:.2f}只/s 剩余约{eta/60:.0f}分钟")

    el = time.time() - t0
    log(f"== 完成 == 处理 {total} 只，成功 {done}，空 {empty}，失败 {fail}，耗时 {el/60:.1f} 分钟")
    if failed:
        log(f"失败清单（前20）: {failed[:20]}")
    PROGRESS_FILE.write_text(
        f"最终 {datetime.now():%H:%M:%S} | 共 {total} | 成功 {done} | 空 {empty} | 失败 {fail}\n"
        + "\n".join(f"{c}: {r}" for c, r in failed[:20]), encoding="utf-8")
    return 0 if not fail else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n已中断")
        sys.exit(130)
