# -*- coding: utf-8 -*-
"""临时：解析 DataYes API 目录（从 web_fetch 落盘文件），列出与我们项目需求相关的接口。"""
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SRC = Path(r"C:\Users\ADMINI~1\AppData\Local\Temp\dsh-spill-lNnoEI\session-9b95bdce838b\0b089b820ea3-web_fetch.txt")
raw = SRC.read_text(encoding="utf-8-sig", errors="replace")  # utf-8-sig 去掉 BOM
# web_fetch 落盘文件格式：前几行是 "Fetched URL" / "External web content..."，真正的 JSON 在 "data:{...}" 那一行
for line in raw.splitlines():
    line = line.strip()
    if line.startswith("data:{"):
        raw = line[5:]
        break
j = json.loads(raw)
cats = j["data"]

# 展平所有 api
apis = []
def walk(nodes):
    for c in nodes:
        for a in c.get("apiList", []):
            apis.append(a)
        walk(c.get("childrenList", []))

walk(cats)

# 需求关键词
keywords = ["复权", "adjust", "行情", "退市", "delist", "ST", "披露", "ann", "单季", "市值",
            "marketValue", "marketCap", "股本", "股东", "财务", "fdmt", "收盘", "收盘价", "日线", "equd"]

print(f"总 API 数：{len(apis)}")
print("\n=== 与我们需求相关的接口 ===")
for a in apis:
    name = a.get("name", "")
    en = a.get("nameEn", "")
    summ = a.get("summary", "")
    blob = f"{name} {en} {summ}"
    if any(k.lower() in blob.lower() for k in keywords):
        print(f"\n[{en}] {name}")
        print(f"  URL: {a.get('httpUrl','')}")
        print(f"  {summ[:160]}")

print("\n\n=== 全部接口名（nameEn）清单 ===")
for a in apis:
    print(f"  {a.get('nameEn',''):<32} {a.get('name','')}")
