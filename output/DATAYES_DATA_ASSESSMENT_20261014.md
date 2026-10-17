# 通联数据(DataYes)能否满足项目全部数据需求 —— 评估报告（2026-10-14）

> 依据：通联 DataAPI 官方目录（api_catalog / api_mix_search / api_info，访客模式实查，无需 token）。
> 结论：**能覆盖 ~95% 的项目数据需求，且核心字段在「免费体验版(TRIAL)」即可调用；唯一硬缺口是 ST 标记字段（is_st 无原生字段，需用证券状态/简称兜底）和因子库（锁定付费版）。**

---

## 一、逐库字段级对照

### 1. 行情 bars.db（需求：open/high/low/close/preclose/volume/amount/turn/pct_chg/is_st/复权）

对应 API：`Astock_market_daily`（`getMktEqud`），**TRIAL 可调**，限流 10次/秒·2000次/天。

| 我们的字段 | 通联字段 | 有无 | 说明 |
|---|---|---|---|
| open | openPrice | ✅ | |
| high | highestPrice | ✅ | |
| low | lowestPrice | ✅ | |
| close | closePrice | ✅ | |
| preclose | actPreClosePrice / preClosePrice | ✅ | 前者未复权、后者前复权 |
| volume | turnoverVol | ✅ | 单位：股 |
| amount | turnoverValue | ✅ | 单位：元 |
| turn | turnoverRate | ✅ | 日换手率 |
| pct_chg | chgPct | ✅ | |
| **复权因子** | **accumAdjFactor** | ✅✅ | **累积前复权因子**，前复权价=未复权价×因子 —— **根治 F-6（qfq 以查询日为基准的坑）** |
| is_st | — | ❌ | 无原生 ST 字段，需 `getSecID`(listStatusCD) 或证券简称判断 |

**额外白送的**（我们原来要单独建库的）：
- `marketValue` 总市值、`negMarketValue` **流通市值**（日频，替代我们月频 hist_mv）
- `PE`/`PE1`/`PB` 估值（直接可做价值因子）
- `vwap`、`dealAmount` 成交笔数、`isOpen` 开盘标记

### 2. 市值 hist_mv.db（需求：流通市值）

对应：`getMktEqud` 的 `negMarketValue`（流通市值）+ `marketValue`（总市值），**日频**，TRIAL 可调。
→ 比我们现在「2020 起月频 + 前向填充」的 hist_mv 好一个量级。

### 3. 财务 finance.db（需求：净利润/营收/单季/EPS/ROE + 披露日）

| 需求 | 通联 API | 有无 | TRIAL |
|---|---|---|---|
| 财务摘要 70+ 指标（营收/净利/EPS/ROE/毛利率/负债率…） | `fdmtNew` | ✅ | ✅ |
| **实际披露日 ann_date** | `getEquReportPredisclo` 的 `actDate` | ✅✅ | ✅ 根治 F-5（固定 60 日延迟的坑） |
| 业绩预告 | `getFdmtEfV2` | ✅ | ✅ |
| 业绩快报(PIT，保留修正前) | `getFdmtEe` | ✅ | ✅ |
| 单季拆解 | fdmtNew 系列 | ⚠️ 需实调确认字段 | 大概率有 |

### 4. 基础信息 stock_basic.db（代码/名称/行业/上市/退市/状态）

| 需求 | 通联 API | 有无 | TRIAL |
|---|---|---|---|
| 证券编码/上市状态/上市时间 | `getSecID`（含 `listStatusCD`，可筛退市 DE） | ✅ | ✅ 解决 F-2 退市股 |
| 公司基本信息 | `getPartyID` | ✅ | ✅ |
| 行业分类（申万2021） | `industry_structure` | ✅ | ✅ |

### 5. 因子库（项目新需求，对标/补短板族）

| 需求 | 通联 API | 有无 | TRIAL |
|---|---|---|---|
| 424 因子 | `getStockFactorsDateRange` / `Pro` / `OneDay` | ✅ | ❌ **locked，需个人版** |
| A股精品因子 | `getEquFancyFactors` / `Lite` | ✅ | ❌ locked |
| 精品因子基础信息 | `getEquFancyFactorsInfo` | ✅ | ❌ locked |

---

## 二、结论：能满足「全部要求」吗？

| 需求项 | 通联 | 结论 |
|---|---|---|
| 行情 OHLCV+额+换手+涨跌 | ✅ 一个 API 全有 | 满足 |
| **复权因子** | ✅ accumAdjFactor | **满足（根治 F-6）** |
| **流通市值** | ✅ negMarketValue 日频 | **满足（比现库更好）** |
| **财务披露日** | ✅ actDate | **满足（根治 F-5）** |
| 退市股 | ✅ getSecID listStatusCD | 满足（根治 F-2 前提） |
| 财务/单季 | ✅ fdmtNew + 预告/快报 | 满足（单季需实调确认） |
| 行业/基础信息 | ✅ getSecID/getPartyID/industry_structure | 满足 |
| **ST 标记** | ❌ 无原生字段 | **缺口①**：需 getSecID 状态枚举或证券简称「ST」兜底 |
| **因子库 424+精品** | ✅ 有但 locked | **缺口②**：需个人版 1299/年 |
| **历史数据范围** | 免费版仅「近一月」 | **缺口③**：历史需个人版 |

---

## 三、关键判断（诚实）

1. **通联一个 `getMktEqud` 接口，就把我们 bars.db + hist_mv.db 两个库的核心字段全包了**，还附带复权因子、PE/PB——这是免费源（akshare/baostock）做不到的字段完整性。
2. **免费版(TRIAL)能调的字段已经非常全**（行情全字段+复权因子+市值+披露日+退市状态），限制只是「近一月」数据范围，不是字段缺失。
3. **真正的付费门槛只有三样**：因子库(424+精品)、历史数据范围、以及可能的 ST 状态枚举。
4. 之前我误判「复权需要付费」——更正：复权因子 `accumAdjFactor` 就在 TRIAL 可调的日行情接口里。

---

## 四、验证计划（免费版内「充分验证」能验到什么）

**免费版能验证（近一月数据，需 token）**：
- 复权因子 accumAdjFactor 是否与除权除息日对齐（抽 3-5 只近期分红股）
- negMarketValue 流通市值与收盘价的量级一致性
- turnoverValue/turnoverVol/turnoverRate 三者自洽性（金额/量=价）
- getEquReportPredisclo 的 actDate 与真实披露日是否一致
- getSecID 能否返回退市股（listStatusCD=DE 抽 3 只已退市股）

**免费版验证不了（历史/因子库）**：
- 退市股 2019+ 历史覆盖（F-2）、复权因子历史精度（F-6）、披露日历史完整性（F-5）
- 因子库 424+精品（locked）

> 所以严格说：免费版能验证「字段是否齐全 + 近一月数据是否自洽」，验证不了「历史数据质量 + 因子库」——这两项恰是决定是否付费的关键，只能靠付费版实测。

---

*生成：本机实查 DataYes 官方 API 目录 · 2026-10-14*
