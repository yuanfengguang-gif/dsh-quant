# 通联字段 ↔ 现有数据库字段映射（2026-10-15 实测比对）

> 目的：确认通联数据能否「完全覆盖」现有 4 个数据库的字段，作为「全量重建数据」的依据。
> 结论：**通联完全覆盖现有所有字段，且有大量富余**（日频市值、PE/PB、精确复权因子、披露日、7套行业、ST标注）。
> 下载策略：**下全字段**（按行计费，多字段不额外花钱，一次覆盖未来因子需求）。

---

## 一、行情 daily_bar（bars.db，14 字段）↔ getMktEqud

| 现有字段 | 通联字段 | 说明 |
|---|---|---|
| code | ticker | 通联 6 位；现有带 .SZ/.SH 后缀，需 `split('.')[0].zfill(6)` |
| date | tradeDate | |
| open | openPrice | |
| high | highestPrice | |
| low | lowestPrice | |
| close | closePrice | |
| preclose | preClosePrice(前复权)/actPreClosePrice(未复权) | 建议两列都存，便于复权对照 |
| volume | turnoverVol | 单位：股 |
| amount | turnoverValue | 单位：元 |
| turn | turnoverRate | |
| pct_chg | chgPct | 通联精确；根治 F-6（本地 80% 偏差） |
| is_st | —（无原生） | 用 secShortName 含 ST 兜底（实测 1302 只可标注） |
| adjust | accumAdjFactor | 累积前复权因子，根治 F-6 |
| source | 'datayes' | 标记 |

**通联额外字段（未来因子富余）**：marketValue(总市值)、negMarketValue(流通市值)、PE、PE1、PB、vwap、dealAmount(成交笔数)、isOpen、secID、secShortName、exchangeCD。

## 二、财务 finance_report（finance.db，11 字段）↔ 财务三表

| 现有字段 | 通联字段 | 说明 |
|---|---|---|
| code | ticker | |
| period | endDateRep（报告期截止日） | |
| net_profit | nIncomeAttrP（归母）/ nIncome（全部） | |
| revenue | tRevenue / revenue | |
| sq_net_profit | 单季净利（累计值差分，或通联单季字段） | |
| sq_net_yoy | 单季净利同比（可算） | |
| sq_revenue | 单季营收（累计差分） | |
| sq_rev_yoy | 单季营收同比（可算） | |
| eps | basicEps / dilutedEps | |
| roe | 净利 ÷ 净资产（利润表+资产负债表） | |
| source | 'datayes' | |

**通联额外字段**：publishDate(披露日)、actPubtime(实际披露时间戳)【根治 F-5】、完整费用结构（sellExp/adminExp/rDExp/finanExp/intExp…）、资产负债表全字段（净资产/总资产/存货/应收…）、现金流量表全字段。

## 三、市值 hist_mv（3 字段）↔ getMktEqud

| 现有 | 通联 | 说明 |
|---|---|---|
| month（月频） | tradeDate（日频） | 日频更优 |
| code | ticker | |
| circ_mv（流通市值） | negMarketValue（流通市值） | 日频，根治月频前向填充 |
| — | marketValue（总市值） | 富余 |

## 四、基础信息 stock_basic（6 字段）↔ getSecID + getEquIndustry

| 现有字段 | 通联字段 | 说明 |
|---|---|---|
| code | ticker/secID | |
| name | secShortName | |
| industry | industryName1/2/3（7套分类：申万2021/申万/中信/证监会/中证2021/中证2016/恒生） | 更全 |
| ipo_date | listDate | |
| out_date | （getSecID listStatusCD=DE 退市股有 listDate 等） | 根治 F-2 |
| status | listStatusCD（L上市/DE退市/S暂停） | |

**通联额外**：secFullName、cnSpell、ISIN、partyID、exchangeCD。

---

## 五、下载策略（修正）

1. **下全字段**：行情 getMktEqud 不下 field 参数（返回全部 24 字段）；财务三表下全字段。理由：按行计费（API_ROW_BASE），多字段不增加点数，但覆盖未来所有因子需求。
2. **聚焦 2019+ 回测期**：行情 2019+ 逐日；财务用 beginDate/endDate 只下 2019+ 报告期（省 85% 行数）。
3. **先实测点数**：充值后先下 1 天全市场行情 + 1 只财务，查 whoami 反推每行点数，再决定全量范围。

*生成：本机 · 2026-10-15*
