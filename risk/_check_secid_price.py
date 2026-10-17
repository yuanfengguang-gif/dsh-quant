import json
import sys
import urllib.parse
import urllib.request

import yaml

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = r"D:\Programs\DSH Projects\DSH Quant"
cfg = yaml.safe_load(open(BASE + r"\config\params.yaml", encoding="utf-8"))
H = {"Authorization": f"Bearer {cfg['data']['datayes_token']}", "Accept": "application/json"}


def info(name_en):
    url = "https://gw.datayes.com/aladdin_llm_mgmt/web/whitelist/api?nameEn=" + urllib.parse.quote(name_en)
    req = urllib.request.Request(url, headers=H)
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            d = json.loads(r.read().decode("utf-8")).get("data", {})
            return d
    except Exception as e:
        return {"_error": str(e)}


# getSecID 的 nameEn 候选
for ne in ["getSecID", "getSecIDList", "Astock_basic_info", "getEquIndustry"]:
    d = info(ne)
    if "_error" in d or not d:
        print(f"{ne}: 查询失败/无")
        continue
    print(f"\n=== {ne}（{d.get('name')}）===")
    print(f"  chargeType: {d.get('chargeType')}   priceAmountCent: {d.get('priceAmountCent')}")
    print(f"  httpUrl: {d.get('httpUrl')}")
    ps = d.get("parametersInput") or []
    if isinstance(ps, list):
        print(f"  入参 {len(ps)}: {[p.get('nameEn') for p in ps if isinstance(p, dict)]}")
    # 输出字段数（估算每行数据量）
    po = d.get("parametersOutput") or []
    print(f"  出参字段数: {len(po) if isinstance(po, list) else '?'}")
