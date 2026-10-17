# 通联因子库入池预分析 + 下载优先级方案（2026-10-15）

> 依据：`output/datayes_factor_catalog.json`（精品 208 + 普通 244 因子清单）。
> 目的：① 分析哪些因子可入项目因子池；② 制定 1280M 额度的下载优先级。
> 状态：**因子清单已拿到，因子值下载因额度 402 暂时阻塞**，本分析基于清单（不依赖额度）。

---

## 一、因子库全景

### 精品因子 208 个（4 大类 / 13 子类）

| 大类 category1 | 数量 | 子类 | 代表因子 | 项目现状 |
|---|---|---|---|---|
| **Fundamental** | 89 | Growth 27 / Quality 48 / Value 14 | SUDE, NP_YOY, ROE, ROIC, OCFA, ETOP, STOP, GR_PB | 部分已有（f_score/bp_value/sue） |
| **Market_Sentiment** | 33 | Low_Freq 19 / High_Freq 14 | UDSL, TA_ENTROPY, APB_SKEW, BCVP, OCVP | 有 sentiment，无高频 |
| **Institution_Sentiment** | 37 | Analyst 12 / HK_Inst 12 / Other 13 | CON_DA_PE, AST_*, HK_HOLD*, FUND_TOP10* | **完全缺失** ⭐ |
| **Alternative** | 49 | AI 14 / 研报情绪 4 / 专利 5 / 社交 21 / 新闻 5 | AI_*, AST_RPT_SENTIMENT, FMZL_*, GTRA_*, NEWS_* | **完全缺失** ⭐ |

### 普通因子 244 个字段（WorldQuant 风格 + 技术指标）

- **财务/基本面**（~90）：ASSI, BLEV, CMRA, CTOP, ETOP, EPS, ROE, ROA, SUE, EGRO, 各类增长率
- **技术指标**（~100）：MA/EMA/MACD/KDJ/RSI/CCI/BIAS/Boll/ROC/OBV/VR/ARBR…（**项目能从 bars.db 自算，无需下载**）
- **动量/波动/流动性**（~50）：REVS, RSTR, VOL, Volatility, HBETA, ILLIQUIDITY, LCAP, LFLO

---

## 二、与项目因子池对照（关键结论）

项目现有因子池（8 因子 + 10 锚点）覆盖：**价值 / 量价 / 质量 / 成长 / 反转 / 情绪**。

**通联因子库最大价值 = 补充项目完全缺失的「另类数据」因子族**：

| 缺失族 | 精品因子 | 对应论文 | 价值 |
|---|---|---|---|
| **分析师一致预期** | CON_DA_PE/PS, AST_PROFIT_UPPCT, GSA, AI_* | A4/C4（分析师/新闻）、B1（盈利） | ⭐⭐⭐ 项目只有 pead（业绩预告），无分析师一致预期 |
| **机构持仓** | HK_HOLDRATIO_*, HK_HOLDVOL_CHG_*, FUND_TOP10_*, FUND_TRACTION_* | B2（供应链/机构）、C2/C3（机构行为） | ⭐⭐⭐ 完全空白 |
| **新闻情绪** | NEWS_NUM_*, NEWS_NUM_NEG_*, NEWS_NUM_VOL_* | A4（ChatGPT 新闻）、C4（商业新闻） | ⭐⭐⭐ 完全空白 |
| **社交媒体热度** | GTRA_*, XTRA_*, GPOST_* | C1（投资者关注）、C2（散户） | ⭐⭐ 关注度反转的 A 股实现 |
| **研报情绪** | AST_RPT_SENTIMENT_* | D1（文本惰性代理） | ⭐⭐ |
| **高频微观结构** | BCVP/OCVP/CORR_VPL/UPP/DDP/VOLL/MINTVAL_* | D5（非参数特征） | ⭐⭐ 低频项目可作稳健性因子 |
| **专利** | FMZL_1Y_* | B4（无形资产） | ⭐ |

---

## 三、入池候选（分三档）

### P0 档（最缺，直接补短板，优先下载）
1. **分析师预期**：`astProfitUppct`（分析师盈利上调）、`conDaPE60`（一致预期 PE 变化）、`aiSude/aiNpYOY`（AI 盈利超预期）→ 补 pead 族
2. **机构持仓**：`hkHoldRatioAll`（港股通持仓占比）、`fundT10Count`（基金前十持仓数）、`naiveWeightChgAsym`（机构权重变化不对称）→ 全新族
3. **新闻情绪**：`NEWS_NUM_30`, `NEWS_NUM_NEG_30`（新闻数/负面新闻数）→ 全新族

### P1 档（加强现有，第二优先）
4. **质量族**：`roeQ`, `roeTTM`, `rrocQ`, `dtop`（ROE/ROE变化/股息）→ 加强 f_score
5. **价值族**：`etopQ`, `stopQ`, `grPB`（盈利收益率/销售收益率/市净率）→ 加强 bp_value
6. **成长族**：`sude`, `npQYOY`, `revQYOY`（盈利超预期/净利同比/营收同比）→ 加强 pead/a_factor

### P2 档（补充/探索，第三优先）
7. **社交热度**：`gpostHot`, `gtraBuyPct`, `xtraBuyPct`（股吧热度/散户买卖占比）
8. **高频**：`bcvp05M20D`, `upp01M20D`, `voll01M20D`
9. **研报情绪**：`astRptSentiW`, `astRptSentiZ730`

---

## 四、下载方案（1280M 额度，待额度恢复后执行）

### 关键约束
- 因子接口 `getEquFancyFactors` 的 `priceAmountCent=100000000`（1亿），**点数消耗疑似极高**（实测约 12 行因子值后额度耗尽，需付费版确认）。
- 精品因子分 10 张表，主表 `getEquFancyFactors` 返回 table1-3（~60 因子），分表 6-10 返回其余。

### 方案（务实，先小后大）
```
第一步【验证】额度恢复后，先下载 1 天主表全市场（~5000 行），实测点数消耗，反推 1280M 能下多少。
第二步【P0】若点数允许，优先下载 P0 档因子（分析师/机构/新闻），2019-2026 全市场。
第三步【P1】其次 P1 档（质量/价值/成长）。
第四步【P2】最后 P2 档（社交/高频/研报）。
```

### 数据量估算（供点数反推参考）
- 主表 ~60 因子，一行 = 股票×天×60 因子，约 2KB
- 2019-2026 全市场（~4500 只 × ~1700 天）≈ 765 万行
- 若按 `priceAmountCent=1亿` 且 1 行=1 亿点，则 765 万行需 7.65 万亿点，**远超 1280M** → 必须只下关键因子子集或降频（如月度调仓点）

---

## 五、下一步（等额度恢复）

1. 额度恢复 → 跑 `data/fetch_datayes_factors.py` 实测 1 天，反推点数。
2. 根据反推结果，确定「能下载多少因子 × 多少时间跨度」。
3. 按 P0→P1→P2 顺序下载，下载后走验证链（ICIR→去重→组合层）筛选入池。
4. 论文挖因子功能（`factors/paper_factor_miner.py`）的公式化结果，与下载的另类因子交叉验证。

---

*生成：本机 · 2026-10-15（因子值下载因额度 402 待恢复）*
