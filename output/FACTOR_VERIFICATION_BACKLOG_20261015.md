# 待验证因子库总表（论文因子 + 通联因子，等通联市场数据后统一验证）

> 生成：2026-10-15。用途：把所有「待验证因子」整合成一份清单，明确「可自算 vs 需通联数值」，
> 作为「下载通联市场数据后统一走验证链」的输入。验证链 = ICIR 海选 → 去重闸门 → 组合层 T+1 → 分年度 holdout。

---

## 一、因子总览

| 来源 | 可本地自算 | 需通联另类数据 | 小计 |
|---|---|---|---|
| 论文因子（16 篇） | 18 个公式 | 32 个定义 | 50 |
| 通联精品因子（208） | ~140 个标准定义 | ~68 个另类 | 208 |
| 通联普通因子（244） | ~240 个（标准+技术指标） | ~4 个 | 244 |
| **合计** | **~398** | **~104** | **502** |

---

## 二、论文因子明细（50 个）

### A. 可本地自算（18 个公式，用 bars.db + finance.db 即可算）

| 论文 | 公式（逆波兰式） | 机制 |
|---|---|---|
| B1 q-factor | `REV_YOY SUE ADD TS_RANK20` | 盈利改善+惊喜 |
| B1 | `EP BP ADD TS_RANK20` | 价值（EP+BP） |
| B1 | `ACCEL SUE ADD TS_RANK20` | 盈利加速度+惊喜 |
| B4 价值复活 | `BP SUE ADD TS_RANK20` | 价值×质量交叉 |
| B4 | `EP ACCEL ADD TS_RANK20` | 价值×成长交叉 |
| B4 | `BP ACCEL MUL REV_YOY ADD TS_RANK20` | 价值×加速×营收共振 |
| B5 不确定性 | `VOLAT STD20 DIV` | 波动率/其标准差 |
| B5 | `VOL_CHG VOLAT MA20 SUB SIGN VOLAT MUL` | 波动上行方向×水平 |
| B5 | `V_RET VOLAT DIV TS_RANK20` | 波动调整收益 |
| C1 关注度 | `TURN VOL_CHG ADD TS_RANK20 NEG` | 换手+量变（反转） |
| C1 | `RET5 TURN MUL TS_RANK20 NEG` | 收益×换手（反转） |
| C1 | `RET ABS VOL_CHG MUL TS_RANK20 NEG` | 绝对收益×量变（反转） |
| C5 彩票 | `RET MAX3 NEG` | 低MAX溢价 |
| C5 | `RET MAX3 TS_RANK20 NEG` | MAX时序排名反转 |
| C5 | `RET MAX3 VOLAT DIV NEG` | 波动标准化MAX反转 |
| D5 非参数 | `VOLAT TS_RANK20 RET20 GATE` | 低波动门控动量 |
| D5 | `SUE TS_RANK20 RET5 GATE` | SUE门控反转 |
| D5 | `AMIHUD TS_RANK20 REV_YOY GATE` | 流动性门控反转 |

### B. 需另类数据（32 个定义，需通联/第三方数据）

| 论文 | 因子 | 数据需求 | 通联对应 |
|---|---|---|---|
| A1 ML | ML 预期收益×3 | 高维特征+训练 | 需自建 ML 通道 |
| B3 劳动份额 | 劳动经营杠杆/劳动份额/固定成本比率/DOL代理×4 | 员工薪酬明细 | 财务附注（可自算，但需薪酬字段） |
| A4 新闻情绪 | LLM新闻情绪×4 | 新闻文本 | NEWS_NUM_30/NEG_30 |
| C4 商业新闻 | 新闻主题关注×4 | 新闻文本 | 新闻/社交情绪族 |
| D1 惰性价格 | 文本惰性×3 | 披露文本 | AST_RPT_SENTIMENT |
| D2 气候暴露 | 气候beta×3 | 电话会议文本 | 无（第三方） |
| D3 可持续 | 绿色-棕色/碳强度×5 | ESG/碳排放 | 无（第三方） |
| D4 碳风险 | 碳强度×2 | 碳排放数据 | 无（第三方） |
| B2 供应链 | 供应链创新暴露×1 | 客户-供应商 | 无（第三方） |
| C2C3 散户 | ROIB×3 | 逐笔订单流 | 无（交易所数据） |

---

## 三、通联因子（核心可入池部分）

### A. 可自算（标准定义，本地数据即可，约 140 精品 + 240 普通）
- 质量：ROE_Q/TTM, ROIC_Q, OCFA, 应计, DTOP, DIV_PAIDRATIO…
- 价值：ETOP, STOP, GR_PE/PB/PS/PCF…
- 成长：SUDE, NP_YOY, REV_YOY, NP_TTM_YOY…
- 普通因子：ASSI/BLEV/CMRA/CTOP/ETOP/EGRO/SUE/ROE/ROA + 技术指标（MA/EMA/MACD/KDJ/RSI…）

### B. 需通联数值（另类数据，约 68 精品）
- 分析师预期：AST_PROFIT_UPPCT, CON_DA_PE/PS, GSA, AI_*
- 机构持仓：HK_HOLDRATIO, HK_HOLDVOL_CHG, FUND_TOP10, FUND_TRACTION
- 新闻/社交：NEWS_NUM_*, GTRA_*, XTRA_*, GPOST_*, AST_RPT_SENTIMENT
- 专利：FMZL_1Y_*

---

## 四、验证前置条件（数据准备）

| 数据 | 状态 | 用途 |
|---|---|---|
| 本地 bars.db（844万行行情）+ finance.db（财务） | ✅ 已有 | 验证「可自算」因子（约 398 个） |
| 通联市场数据（行情复权因子 + 财务披露日） | ⏳ 待下载 | 修复 F-5/F-6 + 提供干净数据重算 |
| 通联另类因子数值（分析师/机构/新闻） | ⏳ 待下载（小批量月度点） | 验证「另类」因子（约 104 个） |

---

## 五、验证步骤（等数据就绪后执行）

1. **可自算因子**：18 论文公式 + ~140 精品标准 + ~240 普通标准 → 用本地数据算 → 验证链。
2. **需通联另类因子**：~68 精品另类（分析师/机构/新闻）→ 下载月度调仓点数值 → 验证链。
3. **第三方数据因子**（ESG/碳/供应链/订单流）→ 暂缓（数据源缺失，标记待办）。
4. 全部通过验证链的因子 → 入池（P0/P1 分档 + 适用域）。

---

## 六、产出文件索引

- 论文因子公式：`logs/paper_factors_generated.json`（50 个）
- 通联因子公式推断：`output/DATAYES_FACTOR_FORMULAS_20261015.md`
- 本总表：`output/FACTOR_VERIFICATION_BACKLOG_20261015.md`
- 追踪表：`CORE_ISSUE_TRACKER.md`（D-09 + A-10）

*生成：本机 · 2026-10-15*
