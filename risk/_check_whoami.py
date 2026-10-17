import json, os, sys, urllib.parse, urllib.request, yaml
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = r"D:\Programs\DSH Projects\DSH Quant"
cfg = yaml.safe_load(open(os.path.join(BASE, "config", "params.yaml"), encoding="utf-8"))
token = cfg["data"]["datayes_token"]
H = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

def call(url):
    req = urllib.request.Request(url, headers=H)
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"_error": f"HTTP {e.code}: {e.read().decode('utf-8')[:300]}"}
    except Exception as e:
        return {"_error": f"{type(e).__name__}: {e}"}

# 1. api_info 查 whoami 定义
r = call("https://gw.datayes.com/aladdin_llm_mgmt/web/whitelist/api?nameEn=whoami")
d = r.get("data", r) if isinstance(r, dict) else r
print("===== api_info[whoami] =====")
if isinstance(d, dict):
    print("  httpMethod:", d.get("httpMethod"), " httpUrl:", d.get("httpUrl"))
    print("  chargeType:", d.get("chargeType"))
    print("  全部字段:", sorted(d.keys()))
else:
    print("  ", json.dumps(r, ensure_ascii=False)[:500])

# 2. 直接尝试调用 whoami
url = "https://gw.datayes.com/aladdin_proxy/data_api/api/whoami"
r = call(url)
print("\n===== 调用 whoami =====")
print(json.dumps(r, ensure_ascii=False)[:1000])
