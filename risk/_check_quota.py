import json, os, sys, urllib.request, yaml
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = r"D:\Programs\DSH Projects\DSH Quant"
cfg = yaml.safe_load(open(os.path.join(BASE, "config", "params.yaml"), encoding="utf-8"))
token = cfg["data"]["datayes_token"]
H = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

def call(url):
    req = urllib.request.Request(url, headers=H)
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            b = r.read()
            j = json.loads(b.decode("utf-8"))
            d = j.get("data", [])
            n = len(d) if isinstance(d, list) else "?"
            return r.status, n
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")[:100]
    except Exception as e:
        return -1, f"{type(e).__name__}: {e}"

GW = "https://gw.datayes.com/aladdin_proxy/data_api/api"
tests = [
    ("getSecID 上市股", f"{GW}/master/getSecID.json?assetClass=E&listStatusCD=L"),
    ("getMktEqud 行情1天", f"{GW}/market/getMktEqud.json?tradeDate=20261012&field=ticker,closePrice"),
    ("getEquFancyFactorsInfo 元数据", f"{GW}/market/getEquFancyFactorsInfo.json"),
    ("getFdmtISLT2018 财务", f"{GW}/fundamental/getFdmtISLT2018.json?ticker=600519"),
    ("getEquFancyFactors 主表1天", f"{GW}/market/getEquFancyFactors.json?tradeDate=20261012&pagesize=5"),
]
for name, url in tests:
    s, n = call(url)
    print(f"{name}: HTTP {s}, 数据={n}")
