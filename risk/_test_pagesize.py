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
        return e.code, {"_error": body.decode("utf-8")[:150]}, len(body)
    except Exception as e:
        return -1, {"_error": f"{type(e).__name__}: {e}"}, 0

# 1. whoami 额度
s, r, b = call("https://gw.datayes.com/aladdin_proxy/aladdin_llm_harness/api/v1/me")
print("=== whoami 额度 ===")
print("HTTP", s, json.dumps(r, ensure_ascii=False)[:800])

# 2. 测 getEquFancyFactors 不同 pagesize 阈值
print("\n=== getEquFancyFactors pagesize 阈值测试（tradeDate=20261014）===")
for ps in [1, 3, 5, 10, 20, 50]:
    url = f"https://gw.datayes.com/aladdin_proxy/data_api/api/market/getEquFancyFactors.json?tradeDate=20261014&pagesize={ps}"
    s, r, b = call(url)
    if isinstance(r, dict) and "_error" in r:
        print(f"  pagesize={ps}: HTTP {s}, {r['_error']}")
    else:
        data = r.get("data", [])
        n = len(data) if isinstance(data, list) else 0
        print(f"  pagesize={ps}: HTTP {s}, {n} 行, {b/1024:.1f}KB")
