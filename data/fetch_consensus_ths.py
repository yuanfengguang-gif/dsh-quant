# -*- coding: utf-8 -*-
"""data/fetch_consensus_ths.py —— 一致预期 EPS 快照（同花顺，零 key）

拉取机构一致预期 EPS（当前快照，非历史序列）。用于 revalue/tech_sentiment 类「当前信号」，
不可用于历史回测（无历史序列）。输出列：年度/预测机构数/最小值/均值/最大值。

用法：python data/fetch_consensus_ths.py [--limit N]
断点续传：logs/consensus_progress.txt
"""
import sqlite3
import sys
import time
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
PROGRESS = BASE / "logs" / "consensus_progress.txt"


def ths_eps_forecast(code6):
    url = f"https://basic.10jqka.com.cn/new/{code6}/worth.html"
    r = requests.get(url, headers={"User-Agent": UA, "Referer": "https://basic.10jqka.com.cn/"},
                     timeout=15)
    r.encoding = "gbk"
    dfs = pd.read_html(StringIO(r.text))
    for df in dfs:
        cols = [str(c) for c in df.columns]
        if any("每股收益" in c or "均值" in c for c in cols):
            return df
    return dfs[0] if dfs else pd.DataFrame()


def load_codes():
    con = sqlite3.connect(str(BASE / "data" / "cache" / "stock_basic.db"))
    codes = [r[0].split(".")[0].zfill(6) for r in con.execute(
        "SELECT code FROM stock_basic WHERE code LIKE '%.SH' OR code LIKE '%.SZ'").fetchall()]
    con.close()
    return codes


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    codes = load_codes()
    if args.limit:
        codes = codes[:args.limit]
    done = set()
    if PROGRESS.exists():
        done = {l.strip() for l in PROGRESS.read_text(encoding="utf-8").splitlines() if l.strip()}
    todo = [c for c in codes if c not in done]
    print(f"待拉 {len(todo)} 只（已完成 {len(done)}）", flush=True)

    con = sqlite3.connect(str(BASE / "data" / "cache" / "consensus.db"))
    con.execute("""CREATE TABLE IF NOT EXISTS consensus (
        code TEXT, year TEXT, n_inst REAL, eps_min REAL, eps_mean REAL, eps_max REAL,
        PRIMARY KEY(code, year))""")
    con.commit()
    n_ok = n_rows = 0
    for i, code in enumerate(todo):
        try:
            df = ths_eps_forecast(code)
            if not df.empty and "年度" in [str(c) for c in df.columns]:
                df.columns = [str(c).strip() for c in df.columns]
                for _, row in df.iterrows():
                    con.execute("INSERT OR REPLACE INTO consensus "
                                "(code, year, n_inst, eps_min, eps_mean, eps_max) VALUES (?,?,?,?,?,?)",
                                (code, str(row["年度"]),
                                 pd.to_numeric(row.get("预测机构数"), errors="coerce"),
                                 pd.to_numeric(row.get("最小值"), errors="coerce"),
                                 pd.to_numeric(row.get("均值"), errors="coerce"),
                                 pd.to_numeric(row.get("最大值"), errors="coerce")))
                    n_rows += 1
            n_ok += 1
            with open(PROGRESS, "a", encoding="utf-8") as f:
                f.write(code + "\n")
        except Exception as e:
            print(f"  {code} 失败: {str(e)[:60]}", flush=True)
        if (i + 1) % 50 == 0:
            print(f"  进度 {i+1}/{len(todo)}，{n_rows} 行", flush=True)
        time.sleep(0.3)
    con.commit()
    con.close()
    print(f"完成: {n_ok}/{len(todo)}", flush=True)


if __name__ == "__main__":
    main()
