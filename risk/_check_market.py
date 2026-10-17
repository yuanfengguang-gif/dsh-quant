import json, sys, urllib.request, yaml
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant"
cfg = yaml.safe_load(open(BASE + r"\config\params.yaml", encoding="utf-8"))
token = cfg["data"]["datayes_token"]
H = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

def call(url):
    req = urllib.request.Request(url, headers=H)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
            return r.status, json.loads(body.decode("utf-8")), len(body)
    except urllib.error.HTTPError as e:
        body = e.read()
        return e.code, {"_error": body.decode("utf-8")[:120]}, len(body)
    except Exception as e:
        return -1, {"_error": f"{type(e).__name__}: {e}"}, 0

# 1. 最小化额度检查：getMktEqud 单股单天（含复权因子 + 市值字段）
s, r, b = call("https://gw.datayes.com/aladdin_proxy/data_api/api/market/getMktEqud.json"
               "?ticker=600519&beginDate=20261014&endDate=20261014"
               "&field=ticker,tradeDate,closePrice,accumAdjFactor,negMarketValue,turnoverValue")
print("=== 行情单股单天 ===")
if isinstance(r, dict) and "_error" in r:
    print("HTTP", s, r["_error"])
else:
    data = r.get("data", [])
    print("HTTP", s, "行数", len(data) if isinstance(data, list) else "?", "字节", b)
    if isinstance(data, list) and data:
        print("字段:", sorted(data[0].keys()))
        print("样例:", json.dumps(data[0], ensure_ascii=False))

# 2. 财务披露日检查：getFdmtISLT2018 单股（含 publishDate/actPubtime）
s, r, b = call("https://gw.datayes.com/aladdin_proxy/data_api/api/fundamental/getFdmtISLT2018.json"
               "?ticker=600519")
print("\n=== 财务利润表单股（披露日字段）===")
if isinstance(r, dict) and "_error" in r:
    print("HTTP", s, r["_error"])
else:
    data = r.get("data", [])
    print("HTTP", s, "行数", len(data) if isinstance(data, list) else "?", "字节", b)
    if isinstance(data, list) and data:
        d = data[0]
        for k in ["endDateRep", "publishDate", "actPubtime", "revenue", "nIncomeAttrP"]:
            print(f"  {k} = {d.get(k)}")
