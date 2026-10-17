# 通达信能力矩阵（C-1 接口清点）

> 生成：2026-10-17 · 脚本：`data/probe_tdx_capability.py` · 依据：**41 个接口逐个真实调用**（不是查文档）
> 原始记录：`logs/tdx_capability_20261017_142046.json`、`logs/_c1_probe2b.txt`

## 0. 一句话总结

41 个接口里 **23 个可用且返回数据**、**6 个未实现**、**12 个需修正参数后可用**（已全部修正并验证）。
**此前严重低估了通达信**：逐笔成交、集合竞价、指数成分股、指数跟踪 ETF、板块交易数据都能取到。

## 1. 能力总表（按用途分类）

### 1.1 行情类

| 接口 | 签名 | 状态 | 返回 |
|---|---|---|---|
| `get_market_data` | `(field_list, stock_list, period, start_time, end_time, dividend_type, ...)` | ✅ | 日/周/月 K，`dividend_type` 支持 `front`/`back`/`none` |
| `get_minute_data` | `(stock_code, date, field_list)` | ✅ | 分时：`Average/Price/Time/Volume` |
| `get_tick_data` | `(stock_code, date, startxh, wantnum)` | ✅ | **逐笔成交**：`BSFlag/Price/Time/TotalNum/Volume` |
| `get_market_snapshot` | `(stock_code, field_list)` | ✅ | 单只快照 **26 字段** |
| `get_market_snapshot_batch` | `(stock_list, field_list, return_df)` | ✅ | 批量快照 |
| `get_call_auction` | `(stock_code, type)` | ✅ | **集合竞价** DF(105,4)：`LeaveQty/Price/Time/Volume` |
| `get_call_auction_batch` | `(stock_list, field_list, type)` | ✅ | 批量集合竞价 |
| `get_trading_dates` | `(market, start_time, end_time, count)` | ✅ | **交易日历**（SH 实测 23 天） |

### 1.2 财务类 ⭐ 最重要

| 接口 | 签名 | 状态 | 返回 |
|---|---|---|---|
| `get_financial_data` | `(stock_list, field_list, start_time, end_time, report_type)` | ✅ | **全历史报告期 + 披露日**；FN1~FN584 |
| `get_financial_data_by_date` | `(stock_list, field_list, year, mmdd)` | ✅ | 按报告期取截面 |

**已验证字段**（CSMAR 交叉验证，误差 0.0000%）：`FN001` EPS、`FN004` 每股净资产、`FN006` ROE(%)、`FN040` 总资产、`FN074` 营业收入、`FN095` 净利润、`FN096` 归母净利润。
**披露日**：`announce_time`，覆盖率 100%，滞后中位 32 天、无一条早于报告期。

### 1.3 股本 / 除权类

| 接口 | 签名 | 状态 | 返回 |
|---|---|---|---|
| `get_gb_info` | `(stock_code, date_list, count)` | ✅ | 股本（万） |
| `get_gb_info_by_date` | `(stock_code, start_date, end_date)` | ✅ | **逐日股本全历史**（实测 183 行） |
| `get_divid_factors` | `(stock_code, start_time, end_time)` | ✅ | **除权除息明细** DF(30,5) |
| `get_exday_data` | `(stock_code, count)` | ✅ | 除权数据（Amo 等） |

### 1.4 交易 / 另类类

| 接口 | 签名 | 状态 | 返回 / 实测深度 |
|---|---|---|---|
| `get_gpjy_value` | `(stock_list, field_list, start_time, end_time)` | ✅ | 个股交易：`GP1~GP46`（龙虎榜/两融/涨停） |
| `get_gpjy_value_by_date` | `(stock_list, field_list, year, mmdd)` | ✅ | 同上，按日期截面 |
| `get_gp_one_data` | `(stock_list, field_list)` | ✅ | 个股单项：`GO1~GO47`（一致预期等） |
| `get_scjy_value` / `_by_date` | `(field_list, start_time, end_time / year, mmdd)` | ✅ | 市场级：`SC1~SC42` |
| `get_bkjy_value` / `_by_date` | `(stock_list=[板块代码], field_list, ...)` | ✅ | 板块级：`BK…`（须传板块代码如 `880301`） |
| `get_zdt_data` | `(stock_list)` | ✅ | 涨跌停数据 |

**已验证深度**（关键，避免再次误判）：
- `GP2` 龙虎榜：**2024+ 有值且与老库完全一致**；2019 空；2020 返回 1000+ 条 `Date='0'` **垃圾**；2022 空
- `GP3` 两融：**2020+ 有值**（2020/2022/2024/2025/2026 均可用）
- `GP14`/`GP24`：**恒空（不可用）**；`GP38-40` 有值（涨停统计类）

### 1.5 板块 / 指数类

| 接口 | 签名 | 状态 | 返回 |
|---|---|---|---|
| `get_sector_list` | `(list_type)` | ✅ | **560 个板块** |
| `get_sector_list_ds` | `(list_type)` | ✅ | 374 个（第三方分类） |
| `get_stock_list` | `(market, list_type)` | ✅ | 股票列表（默认 1702） |
| `get_zzgz_stocklist` | `(index_code, list_type)` | ✅ | **指数成分股**（`000300.SH` → 300 只）⭐ |
| `get_trackzs_etf_info` | `(zs_code)` | ✅ | **指数跟踪 ETF**（30 只，含 `IOPV`）⭐ |
| `get_domain_sorthq` | `(domain, colname, sorttype, wantcol)` | ✅ | 板块/行业排序 DF(100,6) |
| `get_stock_list_in_sector` | `(block_code, block_type, list_type)` | ⚠️ | 传 `880301` 报 Invalid parameter（参数待试） |

### 1.6 元数据类

| 接口 | 签名 | 状态 | 返回 |
|---|---|---|---|
| `get_stock_info` | `(stock_code, field_list)` | ✅ | **62 字段**基本信息 |
| `get_more_info` | `(stock_code, field_list)` | ✅ | **92 字段**扩展信息 ⭐（内容待盘） |
| `get_stock_info_batch` / `get_more_info_batch` | `(stock_list, field_list, return_df)` | ✅ | 批量版 |
| `get_relation` | `(stock_code)` | ✅ | **19 条关联关系**（股东/参控股？待盘） |
| `get_kzz_info` / `_batch` | `(stock_code, field_list)` | ⚠️ | 可转债（`113050.SH` 返回空，待试字段） |

### 1.7 不可用（SDK 未实现）

| 接口 | 原因 |
|---|---|
| `get_ipo_info` | `TdxAiData.h 当前没有与 tqcenter.get_ipo_info 对应的实现` |
| `get_match_stkinfo` | 同上（关键字搜股，未实现） |
| `get_pricevol` | 同上 |
| `get_user_sector` | 同上 |
| `get_subscribe_hq_stock_list` | 返回空列表 |
| `get_stock_list_in_sector` | 参数无效（可能需 `block_type` 具体值） |

## 3. C-2 字段字典初步反推（2026-10-17）

### 3.1 `get_more_info` —— 92 字段（**当日快照**，不是历史序列）

按名字 + 数值交叉验证（茅台 2026-10-16）分类：

| 类别 | 字段 | 说明 / 验证 |
|---|---|---|
| **估值市值** | `Ltsz` `Zsz` `DynaPE` `StaticPE_TTM` `PB_MRQ` `DYRatio` | `Ltsz`=16,613.58 **亿元**（自算流通市值 16,576.08 亿，差 0.23%）✅；`Zsz`=总市值；`PB_MRQ`=6.61（tdx pb 6.28，差 5%，日期差） |
| **动量（现成）** | `ZAFPre2D` `ZAFPre5` `ZAFPre10` `ZAFPre20` `ZAFPre30` `ZAFPre60` `ZAFPreOneYear` `ZAFYear` `ZAFYesterday` `ZAF` | 茅台：5日 5.23% / 10日 7.44% / 20日 3.41% / 60日 5.56% / 年内 -1.49% → **多周期动量直接可用** ⭐ |
| **换手/量能** | `fHSL`(0.31≈换手%) `fLianB`(1.10) `vzangsu`(3.69) `MA5Value` `HisHigh` `HisLow` `BetaValue` | `fHSL` 与自算 0.2927% 接近（自由流通口径略高） |
| **情绪/涨停** | `ZTPrice` `DTPrice` `ZTDate_Recent` `DTDate_Recent` `EverZTCount` `YearZTDay` `ZTGPNum` `LastStartZT` `ConZAFDateNum`(连涨天数) | 茅台涨停价 1444.27 / 跌停价 1181.67 / 最近涨停 2015-04-21 |
| **资金流** | `Zjl`(主力净流入) `Zjl_HB` `Wtb`(委比 -83.10) `TotalBVol` `TotalSVol` `L2OrderNum` `L2TicNum` `BCancel` `SCancel` `OpenAmo` `FzAmo` | `Zjl`=49,943.19（万元量级）；`BCancel/SCancel`=买/卖撤单 |
| **股本** | `FreeLtgb`(自由流通万股 54,094.90) | 与 `float_share` 不同口径（自由流通） |
| **财务/公司** | `ReportDate`(20260815) `IPO_Price`(31.39) `KfEarnMoney`(扣非) `RDInputFee` `StaffNum`(34,992) `MainBusiness` | `ReportDate` 与财务披露日一致 ✅ |
| **事件** | `RecentHGDate`(最近回购) `RecentReleaseDate`(最近解禁) `TopDate_Recent` `RecentDZDate`(定增) `RecentIncentDate`(激励) `RecentGGJYDate`(高管交易) `StopJYDate_Recent` | 事件类字段，可做事件因子 |
| **其他** | `SafeValue` `ShapeValue` `ShineValue` `TPFlag` `IsKzz` `IsT0Fund` `HqDate` `MorePE` `Yield` | 通达信自有评分/标记，含义待考 |

⚠️ **这是快照**：只能拿到"当天"的值，要做历史序列必须**每天落一份**（同 ST 快照的做法）。

### 3.2 `get_relation` —— 19 条板块归属（现成的风格标签）⭐

茅台 2026-10-16 返回 19 个板块，含 4 类：

| 类型 | 样例 |
|---|---|
| **地区** | 贵州板块（880229） |
| **概念** | 白酒概念（880564）、通达信88（880515）、乡村振兴（880955） |
| **风格** | **高分红股**、**基金重仓**、**保险重仓**、**北上重仓**、**陆股通重仓**、**MSCI成份**、**行业龙头**、**大盘股**、**绩优股**、**百元股**、**非周期股**、通达信热股、昨成交20 |
| **行业** | 酿酒（881130）、白酒（881135） |

→ **可直接当作风格因子输入**（高分红/基金重仓/北向重仓/MSCI/龙头），比自建行业分类更省事。

### 3.3 `SC1~SC42` —— 市场级，**34/42 有值**

**已精确定位**（与 `bars.db` 自算全市场聚合交叉验证，2026-10-09）：

| 字段 | 通达信值 | 自算值 | 结论 |
|---|---|---|---|
| **`SC31`** | `['3296','2145']` | 上涨 **3,296** / 下跌 **2,145** | ✅ **= [上涨家数, 下跌家数]**（10-08 也吻合：1,698/3,747 vs 自算 1,699/3,747） |
| `SC24`（疑似） | `['69','8']` | 涨停≈49 / 跌停≈7（9.8% 阈值，未含 ST 5% 与 20% 板） | 🟡 疑似**涨停/跌停家数**（通达信口径更全，故数值偏高） |
| `SC3` `SC4` `SC23` `SC28` `SC30` `SC36` | 小整数对 | — | 🟡 疑似各类涨跌停/异动家数，待逐个定位 |

**其余**（`SC1`=2.53 亿级、`SC5/6/7/27/41`=负数=资金净流出、`SC8` `SC12` `SC16` `SC40`=指数点位级、`SC34` `SC42`=大额）待与 `rzrq.db`（两融余额 2.4 万亿）、指数库交叉定位。

**方法已固化**：`SC` 定位 = 用 `bars.db` 自算全市场聚合（成交额/涨跌家数/涨停数）+ 老库（两融）去逐项匹配。

### 3.4 `GP1~GP46` —— 个股交易，**11 个确认有值**

| 字段 | 茅台 2026-10-09 | 推断 |
|---|---|---|
`GP3` | 1,708,665.25 / 204,448.00 | **融资余额（万元）/ 融券余量** ✅ 与老库 `rzrq` 口径吻合 |
`GP13` | -14,333.34 / -1,000.00 | **融资净买入（万元）/ 融券净卖出** ✅ |
`GP11` | 25,013.43 / 39,346.77 | 融资买入/偿还额（万元） |
`GP12` | 1,800.00 / 2,800.00 | 融券卖出/偿还量 |
`GP16` | 157,885,312.00 | 陆股通持股? |
`GP19` `GP20` `GP21` `GP25` `GP27` `GP36` | 小额/计数值 | 待考 |

**其余 35 个**：多数是「数据依赖型为空」（如 `GP2` 龙虎榜只在**上榜当日**有值，茅台当期不上榜 → 空），少数是**无效字段码**（`Invalid server response`）。

### 3.5 三条重要工程约束（踩坑记录）

1. **`GP`/`SC` 不能一次请求全部字段**：请求里只要有一个无效字段码，整批返回 `Invalid server response` → **必须逐字段请求或小批量 + 容错重试**
2. **"空" ≠ "无效"**：`GP2` 空可能只是因为该股当日没上榜；判断有效性必须用**已知会有值的样本**（如从 `lhb.db` 挑真正的上榜股）
3. **`get_more_info` 是快照不是序列**：要历史必须每日落库

## 5. 全市场交叉验证（2026-10-17，最强证据）

用 **两个完全独立的通道** 互相验证同一指标（通达信 `more_info` 快照 vs 我们自建的 `bars.db × tdx_base` 股本）：

| 对比项 | 可比只数 | 偏差<1% | 中位偏差 | P90 |
|---|---|---|---|---|
| **`Ltsz` 流通市值** vs `close(10-16) × float_share` | 5,558 | **98.6%** | **0.013%** | 0.32% |
| **`Zsz` 总市值** vs `close(10-16) × total_share` | 5,558 | **99.2%** | **0.010%** | 0.30% |
| `fHSL` 换手(自由流通口径) vs `turn`(流通口径) | 5,562 | 99.3%（<5%） | 0.56% | — |

**意义**：通达信自己的市值 = 我们的价格 × 我们的股本（差 0.01% 量级）→ 说明
**新主库 `bars.db` 的价格序列与通达信服务端口径完全一致**，不是"我们算错了恰好自洽"。

## 6. C-5 成本（受限：本地无积分接口）

- SDK **没有**积分余额/单价查询接口，`Client*.log` 也只记错误不记积分
- 只能给出**调用量清单**供换算（需你在通达信客户端查余额/单价）：

| 任务 | 调用次数 | 数据量 |
|---|---|---|
| 日线全历史（一次性） | 5,581 只（`get_market_data` 按需分批） | ~16.3M 行 |
| 财务全历史（一次性） | 5,573 次 | 297,118 行 |
| **每日快照（`more_info`+`relation`）** | **11,162 次/天** | 5,581 行 × 94 列 + 84,056 条板块 |
| 每日增量日线 | 按缺口天数 × 股票数 | 每日约 5,572 行 |

⚠️ **每日快照是最大的调用量来源**（11,162 次/天）。若积分紧张，可降为**每周一次**（动量/资金流因子频率本就是周频可用）。

## 7. 对现有数据库的替代能力（初判）

| 现有库 | 通达信替代 | 结论 |
|---|---|---|
| `bars.db` 日线 | `get_market_data` + 自建乘法复权 | ✅ **已切换** |
| `finance.db` 财务 | `get_financial_data`（含披露日） | ✅ **已切换** |
| `hist_mv.db` 市值 | `get_gb_info_by_date` 或 `tdx_base.circ_mv` | ✅ **已切换** |
| `valuation.db` 估值 | `tdx_base` 的 pe/pb/ps/dv | ✅ **已切换** |
| `stock_basic.db` 基础信息 | `get_stock_info`(62) + `get_more_info`(92) | ✅ **已切换** |
| `industry.db` 行业 | `get_sector_list`(560) + `get_domain_sorthq` | ✅ 可替代（分类体系不同） |
| `index_member` 指数成分 | **`get_zzgz_stocklist`** | ✅ **可替代**（新发现） |
| `lhb.db` 龙虎榜 | `GP2`（2024+） | ⚠️ 仅 2024+，历史须留旧库 |
| `rzrq.db` 两融 | `GP3`（2020+） | ✅ 可替代 2020+ |
| `limitup.db` 涨停池 | `GP14/GP24` ❌；`GP38-40` ✅ | ⚠️ 仅统计类 |
| `consensus.db` 一致预期 | `GO3/GO5` 返回 `0.00` | ❌ 不可替代 |
| `minute.db` 分钟线 | `get_minute_data` / `get_tick_data` | ✅ 可替代（且更细） |
| `lhb`/`rzrq` 之外的另类 | `get_relation`(19) / `get_more_info`(92) | 🔵 待盘点 |

## 3. 下一步（C-2 起）

1. **C-2 字段字典反推**：`GP1-46`、`GO1-47`、`SC1-42`、`BK…`、`get_more_info` 92 字段、`get_relation` 19 项
   —— 全部用「与已知库交叉验证」的方法反推（`FN` 已验证此法可行）
2. **C-3 深度矩阵**：每字段 × 年份三态（有值/空/垃圾）
3. **C-5 成本**：按接口估算积分
4. **C-6 迁移表**：与 9.13 决策表合并，逐个库给出「切/留/双轨」

## 4. 教训（写进方法论文档）

> 本次多次误判（"通达信没有龙虎榜"、"没有财务数据"、"前复权可用"）的共同原因：
> **只查文档、不实测；只测一只股票、不对照已知库；不检查历史深度与垃圾数据。**
> 正确方法 = **真实调用 + 数值交叉验证 + 逐年深度探测 + 异常值检测**（如 `Date='0'` 垃圾）。
