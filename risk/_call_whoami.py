import json, sys, urllib.request, yaml
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = r"D:\Programs\DSH Projects\DSH Quant"
cfg = yaml.safe_load(open(BASE + r"\config\params.yaml", encoding="utf-8"))
token = cfg["data"]["datayes_token"]
H = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

url = "https://gw.datayes.com/aladdin_proxy/aladdin_llm_harness/api/v1/me"
req = urllib.request.Request(url, headers=H)
try:
    with urllib.request.urlopen(req, timeout=40) as r:
        body = r.read()
        print("HTTP", r.status)
        print(json.dumps(json.loads(body.decode("utf-8")), ensure_ascii=False, indent=1))
except urllib.error.HTTPError as e:
    body = e.read()
    print("HTTP", e.code)
    print(body.decode("utf-8")[:2000])
