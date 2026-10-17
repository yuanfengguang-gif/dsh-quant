import yaml, json, urllib.request
BASE = r"D:\Programs\DSH Projects\DSH Quant"
cfg = yaml.safe_load(open(BASE + r"\config\params.yaml", encoding="utf-8"))
t = cfg["data"]["datayes_token"]
print("我用的 token 指纹：", t[:8] + "..." + t[-8:], f"（长度 {len(t)}）")
print("token 完整值前16位：", t[:16])

H = {"Authorization": f"Bearer {t}", "Accept": "application/json"}

def call(url):
    req = urllib.request.Request(url, headers=H)
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")[:200]
    except Exception as e:
        return -1, str(e)

print("\n[whoami]", call("https://gw.datayes.com/aladdin_proxy/aladdin_llm_harness/api/v1/me"))
print("[业务: 1股1天行情]", call("https://gw.datayes.com/aladdin_proxy/data_api/api/market/getMktEqud.json?ticker=600519&beginDate=20261014&endDate=20261014&field=ticker,closePrice"))
print("[业务: 因子元数据]", call("https://gw.datayes.com/aladdin_proxy/data_api/api/market/getEquFancyFactorsInfo.json"))
