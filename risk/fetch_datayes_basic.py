# -*- coding: utf-8 -*-
"""risk/fetch_datayes_basic.py —— 下载通联基础信息（免费/低成本元数据）

内容：
  1. 退市股清单（getSecID listStatusCD=DE）—— 免费，用于幸存者偏差评估
  2. 上市股清单（getSecID listStatusCD=L）—— 免费，用于补名称/状态
  3. 行业分类（getEquIndustry）—— 用于行业中性化
用法：python risk/fetch_datayes_basic.py
"""
import json
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = Path(__file__).resolve().parent.parent
cfg = yaml.safe_load((BASE / "config" / "params.yaml").read_text(encoding="utf-8"))
H = {"Authorization": f"Bearer {cfg['data']['datayes_token']}", "Accept": "application/json"}
GW = "https://gw.datayes.com/aladdin_proxy/data_api/api"
SECID = f"{GW}/master/getSecID.json"
INDUSTRY = f"{GW}/equity/getEquIndustry.json"
DB = BASE / "data" / "cache" / "datayes_basic.db"


def call(url, params=None, timeout=120):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=H)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            b = r.read()
            return r.status, json.loads(b.decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, {"_error": e.read().decode("utf-8")[:200]}
    except Exception as e:
        return -1, {"_error": f"{type(e).__name__}: {e}"}


def fetch_paged(base_url, params, tag):
    """分页拉取全部数据。"""
    rows, page, ps = [], 1, 2000
    while True:
        p = dict(params)
        p.update({"pagenum": page, "pagesize": ps})
        s, r = call(base_url, p)
        if s != 200:
            print(f"  {tag} 第{page}页 HTTP {s}: {json.dumps(r, ensure_ascii=False)[:150]}")
            break
        data = r.get("data", [])
        if not isinstance(data, list) or not data:
            break
        rows.extend(data)
        print(f"  {tag} 第{page}页 +{len(data)}（累计 {len(rows)}）", flush=True)
        if len(data) < ps:
            break
        page += 1
        time.sleep(0.15)
    return rows


def main():
    con = sqlite3.connect(str(DB))
    con.execute("PRAGMA synchronous=OFF")

    # 1) 退市股清单
    print("=== 1. 退市股清单（listStatusCD=DE）===")
    de = fetch_paged(SECID, {"assetClass": "E", "listStatusCD": "DE"}, "退市")
    if de:
        import pandas as pd
        df = pd.DataFrame(de)
        df.to_sql("sec_delisted", con, if_exists="replace", index=False)
        con.commit()
        print(f"  退市股 {len(df)} 条，字段：{list(df.columns)}")
        print(f"  样例：{df.head(2).to_dict('records')}")

    # 2) 上市股清单
    print("\n=== 2. 上市股清单（listStatusCD=L）===")
    ls = fetch_paged(SECID, {"assetClass": "E", "listStatusCD": "L"}, "上市")
    if ls:
        import pandas as pd
        df2 = pd.DataFrame(ls)
        df2.to_sql("sec_listed", con, if_exists="replace", index=False)
        con.commit()
        print(f"  上市股 {len(df2)} 条")

    # 3) 行业分类
    print("\n=== 3. 行业分类（getEquIndustry）===")
    ind = fetch_paged(INDUSTRY, {}, "行业")
    if ind:
        import pandas as pd
        df3 = pd.DataFrame(ind)
        df3.to_sql("equ_industry", con, if_exists="replace", index=False)
        con.commit()
        print(f"  行业记录 {len(df3)} 条")
        if "industry" in df3.columns:
            print(f"  行业体系：{df3['industry'].dropna().unique().tolist()}")

    # 汇总
    print("\n" + "=" * 56)
    for t in [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]:
        n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t}: {n:,} 行")
    con.close()
    print(f"\n库：{DB}")


if __name__ == "__main__":
    main()
