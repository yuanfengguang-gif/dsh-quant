import json, os, sys, urllib.parse, urllib.request, yaml
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = r"C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant"
cfg = yaml.safe_load(open(os.path.join(BASE, "config", "params.yaml"), encoding="utf-8"))
token = cfg["data"]["datayes_token"]
H = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

def call(url):
    req = urllib.request.Request(url, headers=H)
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"_error": f"{type(e).__name__}: {e}"}

for ne in ["getEquFancyFactors", "getMktEqud"]:
    r = call("https://gw.datayes.com/aladdin_llm_mgmt/web/whitelist/api?nameEn=" + urllib.parse.quote(ne))
    d = r.get("data", r) if isinstance(r, dict) else r
    print(f"\n===== {ne} =====")
    if not isinstance(d, dict):
        print("  原始:", json.dumps(r, ensure_ascii=False)[:300])
        continue
    for k in ["chargeType", "priceAmountCent", "priceInternalOnly", "faq", "curlExample", "operationGuide", "limitConfigs"]:
        v = d.get(k)
        if v is not None:
            s = json.dumps(v, ensure_ascii=False)
            print(f"  {k}: {s[:800]}")
