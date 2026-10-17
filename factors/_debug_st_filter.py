# -*- coding: utf-8 -*-
"""临时：验证 code6 提取修复是否正确。"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = Path(__file__).resolve().parent.parent
CACHE = BASE / "data" / "cache"

con = sqlite3.connect(f"file:{CACHE / 'stock_basic.db'}?mode=ro", uri=True)
sb = pd.read_sql("SELECT code, name FROM stock_basic WHERE name LIKE '%ST%'", con)
con.close()

sb["code6_old"] = sb["code"].astype(str).str.zfill(6)               # 旧（bug）
sb["code6_new"] = sb["code"].astype(str).str.split(".").str[0].str.zfill(6)  # 新（修复）

print("旧 code6 样本:", sb["code6_old"].head(3).tolist())
print("新 code6 样本:", sb["code6_new"].head(3).tolist())
print("000639 在新 code6:", (sb["code6_new"] == "000639").any())
print("新 code6 全为 6 位数字:", sb["code6_new"].str.fullmatch(r"\d{6}").all())
