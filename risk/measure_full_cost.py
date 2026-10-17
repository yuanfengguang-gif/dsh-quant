# -*- coding: utf-8 -*-
"""risk/measure_full_cost.py —— 下载1个月行情样本，测算全量成本

1. whoami 查初始额度
2. 下载最近 ~20 个交易日（约1个月）全市场行情（全字段，按 tradeDate 逐日）
3. whoami 查下载后额度
4. 反推每行点数 → 全量（2010-2026 ~3900 交易日）总点数 → 总成本（100元=1000M点）
"""
import json, os, sqlite3, sys, time, urllib.parse, urllib.request, yaml

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant"

cfg = yaml.safe_load(open(os.path.join(BASE, "config", "params.yaml"), encoding="utf-8"))
token = cfg["data"]["datayes_token"]
H = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

WHOAMI = "https://gw.datayes.com/aladdin_proxy/aladdin_llm_harness/api/v1/me"
EQUID = "https://gw.datayes.com/aladdin_proxy/data_api/api/market/getMktEqud.json"


def call(url, timeout=90):
    req = urllib.request.Request(url, headers=H)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            return r.status, json.loads(body.decode("utf-8")), len(body)
    except urllib.error.HTTPError as e:
        body = e.read()
        return e.code, {"_error": body.decode("utf-8")[:200]}, len(body)
    except Exception as e:
        return -1, {"_error": f"{type(e).__name__}: {e}"}, 0


def whoami():
    s, r, _ = call(WHOAMI)
    print(f"[whoami] HTTP {s}")
    if s == 200:
        print("  ", json.dumps(r, ensure_ascii=False)[:800])
    else:
        print("  ", json.dumps(r, ensure_ascii=False)[:300])
    return r


def fetch_day(trade_date):
    rows, pagenum = [], 1
    while True:
        url = EQUID + "?" + urllib.parse.urlencode({"tradeDate": trade_date, "pagenum": pagenum, "pagesize": 1000})
        s, r, _ = call(url)
        if s != 200:
            return None, f"HTTP {s} {json.dumps(r, ensure_ascii=False)[:120]}"
        data = r.get("data", [])
        if not data:
            break
        rows.extend(data)
        if len(data) < 1000:
            break
        pagenum += 1
        time.sleep(0.15)
    return rows, None


def main():
    # 最近 20 个交易日
    con = sqlite3.connect(os.path.join(BASE, "data", "cache", "bars.db"))
    dates = [r[0] for r in con.execute(
        "SELECT DISTINCT date FROM daily_bar ORDER BY date DESC LIMIT 20")]
    con.close()
    dates = sorted(dates)
    print(f"样本交易日 {len(dates)} 个：{dates[0]} ~ {dates[-1]}")

    print("\n=== 下载前额度 ===")
    whoami()

    print(f"\n=== 下载 {len(dates)} 天全市场行情（全字段）===")
    total_rows = 0
    per_day = []
    for d in dates:
        d8 = d.replace("-", "")
        rows, err = fetch_day(d8)
        if err:
            print(f"  {d} 失败: {err}")
            if "402" in err or "额度" in err:
                print("  额度用尽，停止")
                break
            time.sleep(0.5)
            continue
        n = len(rows)
        total_rows += n
        per_day.append(n)
        print(f"  {d}: {n} 行", flush=True)
        time.sleep(0.15)

    print(f"\n样本合计：{total_rows} 行，平均每天 {total_rows//len(per_day) if per_day else 0} 行")

    print("\n=== 下载后额度 ===")
    whoami()


if __name__ == "__main__":
    main()
