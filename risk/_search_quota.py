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

for q in ["额度", "余额", "用量", "账户", "计费"]:
    r = call("https://gw.datayes.com/aladdin_llm_mgmt/web/whitelist/api/search/mix?query=" + urllib.parse.quote(q))
    data = r.get("data", []) if isinstance(r, dict) else []
    print(f"\n===== 搜索「{q}」=====")
    if isinstance(data, list):
        for d in data[:5]:
            print(f"  [{d.get('nameEn')}] {d.get('name')} locked={d.get('locked')}")
    else:
        print("  ", json.dumps(r, ensure_ascii=False)[:300])
