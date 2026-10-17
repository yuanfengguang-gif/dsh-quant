# 通联因子公式推断清单（核心因子，待通联市场数据验证）

> 说明：通联精品因子是**黑盒，不公开公式**。本清单从因子名 + 学术/WorldQuant 标准定义**推断**公式，
> 供「下载通联市场数据后统一验证」用。置信度：★高（标准定义）／☆中（名字可推断）／？低（需通联口径）。
> 生成：2026-10-15

---

## 一、精品因子（Fundamental 基本面族，可自算/可验证）

### 质量 Quality（P1，加强 f_score）
| 因子名 | 推断公式 | 置信度 |
|---|---|---|
| ROE_Q | 单季净利润 ÷ 单季净资产 | ★ |
| ROE_TTM | TTM净利润 ÷ TTM净资产 | ★ |
| ROE_Q_YOYD | 单季ROE同比差 | ★ |
| ROE_TTM_YOYD | TTM ROE同比差 | ★ |
| RROC_Q | 单季ROE的环比变化（盈利质量趋势） | ☆ |
| OCFA | 经营现金流 ÷ 总资产 | ☆ |
| T_ACCR_IS / D_ACCR_IS | 利润表应计（净利润−经营现金流） | ★ |
| T_ACCR_BS / D_ACCR_BS | 资产负债表应计 | ★ |
| ROIC_Q | 投入资本回报率 = NOPAT ÷ 投入资本 | ★ |
| CFOA_Q | 经营现金流 ÷ 资产 | ☆ |
| DTOP | 股息率 = 每股分红 ÷ 股价 | ★ |
| DIV_PAIDRATIO | 股利支付率 | ★ |
| Q_SCORE | 质量综合评分（Piotroski 式） | ☆ |
| GOVERNANCE | 公司治理评分 | ? |

### 价值 Value（P1，加强 bp_value）
| 因子名 | 推断公式 | 置信度 |
|---|---|---|
| Q_ETOP / ETOP | 盈利收益率 = EPS ÷ 股价（=1/PE） | ★ |
| Q_STOP / STOP | 销售收益率 = 营收 ÷ 市值 | ★ |
| GR_PE_TTM / GR_PE_Q | 市盈率（TTM/单季） | ★ |
| GR_PB | 市净率 | ★ |
| GR_PS_TTM / GR_PS_Q | 市销率 | ★ |
| GR_PCF_TTM / GR_PCF_Q | 市现率 | ★ |
| AI_ETOP | 分析师一致预期盈利收益率 | ☆ |
| AI_ETOP_Z90/Z180 | 预期盈利收益率的90/180日zscore | ☆ |

### 成长 Growth（P1，加强 pead/a_factor）
| 因子名 | 推断公式 | 置信度 |
|---|---|---|
| SUDE | 盈利超预期（单季净利 vs 预期/历史） | ★ |
| SUDREV | 营收超预期 | ☆ |
| NP_Q_YOY | 单季净利同比 | ★ |
| NP_YTD_YOY | 累计净利同比 | ★ |
| NP_TTM_YOY | TTM净利同比 | ★ |
| NP_TTM_QOQ | TTM净利环比 | ★ |
| REV_Q_YOY | 单季营收同比 | ★ |
| REV_YTD_YOY | 累计营收同比 | ★ |
| REV_TTM_YOY | TTM营收同比 | ★ |
| LPNP_Q | 单季利润占比（利润结构） | ? |
| QES | 盈利质量/稳定性 | ? |

---

## 二、精品因子（另类数据族，免费源自算不了，需通联数值）

### 分析师预期 Analyst（P0，补 pead 空白）
| 因子名 | 推断公式 | 置信度 |
|---|---|---|
| AST_PROFIT_UPPCT | 分析师盈利上调比例 | ☆ |
| AST_RANK_UPPCT | 分析师评级上调比例 | ☆ |
| CON_DA_PE_20/40/60 | 一致预期PE的20/40/60日变化 | ☆ |
| CON_DA_PS_20/40/60 | 一致预期PS的变化 | ☆ |
| GSA | 分析师覆盖/评级综合 | ? |
| CON_SUDE / AI_SUDE | 一致预期/AI 盈利超预期 | ☆ |
| CON_NP_YOY / AI_NP_YOY | 一致预期/AI 净利同比 | ☆ |

### 机构持仓 Institution（P0，全新族）
| 因子名 | 推断公式 | 置信度 |
|---|---|---|
| HK_HOLDRATIO_ALL/B/C | 港股通持仓占比（全/沪/深） | ★ |
| HK_HOLDVOL_CHG_B20/60/120 | 港股通持仓量20/60/120日变化 | ☆ |
| FUND_TOP10_COUNT | 基金前十大重仓覆盖数 | ☆ |
| FUND_TOP10_WEIGHT_MEAN/MAX | 基金重仓权重均值/最大 | ☆ |
| FUND_TRACTION_20/60 | 基金资金牵引20/60日 | ? |
| NAIVE_WEIGHT_CHANGE_ASYM | 机构权重变化不对称性 | ? |

### 新闻/社交/研报 Alternative（P0/P2，全新族）
| 因子名 | 推断公式 | 置信度 |
|---|---|---|
| NEWS_NUM_30 | 30日新闻数量 | ☆ |
| NEWS_NUM_NEG_30 | 30日负面新闻数量 | ☆ |
| NEWS_NUM_VOL_30 | 30日新闻量波动 | ? |
| GTRA_BUY_PCT / SELL_PCT | 散户买入/卖出占比 | ☆ |
| GPOST_HOT | 股吧热度 | ☆ |
| AST_RPT_SENTIMENT_W | 研报情绪（周度） | ☆ |
| AST_RPT_SENTIMENT_Z730 | 研报情绪730日zscore | ☆ |
| FMZL_1Y_IPCNUM_SUM | 1年发明专利数 | ★ |

---

## 三、普通因子（244，WorldQuant/标准定义，大部分可自算）

### 质量/财务（WorldQuant 标准）
| 因子名 | 公式 | 置信度 |
|---|---|---|
| ASSI | 资产周转率（营收/总资产） | ★ |
| BLEV | 账面杠杆（总资产/净资产） | ★ |
| CMRA | 12月累计月收益 | ★ |
| CTOP | 现金流收益率（经营现金流/市值） | ★ |
| ETOP | 盈利收益率（EPS/股价） | ★ |
| EGRO | 盈利增长（5年EPS增长） | ★ |
| SUE | 标准化未预期盈利 | ★ |
| ROE / ROA | 净资产/总资产收益率 | ★ |
| TOBT | 换手率 | ★ |
| LCAP | 对数市值 | ★ |
| LFLO | 对数流通市值 | ★ |
| ILLIQUIDITY | Amihud 非流动性 | ★ |
| HBETA | 历史 beta | ★ |
| Volatility | 波动率 | ★ |

### 技术指标（可从 bars.db 自算）
MA/EMA/MACD/KDJ/RSI/CCI/BIAS/Boll/ROC/OBV/VR/ARBR/ATR 等 ~100 个 —— 均为标准技术指标，**公式公开、可从本地 bars.db 直接自算，无需通联**。

---

## 四、结论

1. **可自算的因子**（基本面族 + 普通因子技术指标，约 300+ 个）：公式已知或可推断，用**本地 bars.db/finance.db** 即可算，等通联市场数据（复权/披露日修复后）重新计算验证。
2. **需通联数值的因子**（另类数据族，约 30 个核心）：分析师预期/机构持仓/新闻情绪/社交热度/专利——免费源拿不到，只能用通联黑盒数值，**小批量下载月度调仓点**。
3. 本清单作为「待验证因子公式库」，与论文挖的因子公式一起，等通联市场数据就绪后统一走验证链。

*生成：本机 · 2026-10-15*
