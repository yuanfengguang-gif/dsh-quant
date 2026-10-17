# -*- coding: utf-8 -*-
"""data/inspect_csmar.py —— 查看 CSMAR 财务数据的列名（定位核心字段）"""
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
P = Path(r"D:\BaiduNetdiskDownload\A股上市公司财务数据（1990-2026.3.31）")
F = P / "年度最终合并.csv"

# 只读表头（nrows=0）
head = pd.read_csv(F, nrows=0, encoding="utf-8-sig")
cols = list(head.columns)
print(f"总列数: {len(cols)}\n")

KEYWORDS = ["证券代码", "年份", "股票简称", "报表类型", "行业", "公布",
            "营业总收入", "营业收入", "营业成本", "净利润", "归母",
            "每股收益", "研发", "销售费用", "管理费用", "财务费用",
            "资产总计", "净资产", "股东权益", "流动资产合计", "流动负债合计",
            "存货", "应收账款", "经营活动产生的现金流量净额",
            "净资产收益率", "总资产净利率", "毛利率", "资产负债率",
            "增长率", "员工"]
hits = []
for i, c in enumerate(cols):
    if any(k in str(c) for k in KEYWORDS):
        hits.append((i, c))
print(f"命中关键字段 {len(hits)} 个：")
for i, c in hits:
    print(f"  [{i:>3}] {c}")
