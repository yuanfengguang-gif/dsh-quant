# 开源因子挖掘模型对比报告（7 项目 4 步评估）

> 生成：2026-10-14（通宵任务）
> 方法：7 个子代理并行，每个读完整 README + 核心源码 + LICENSE + 论文/benchmark/issue，严格区分「有据可查 / README 自述 / 推测」。
> 背景：我们的 formula_miner 已复刻 AlphaGPT（公式语言+StackVM+LLM 引擎），踩过的坑：35% 非法公式、同构因子霸榜（换手变体）、截面 ICIR 高但组合层失效。

---

## 一、结论（TL;DR）

**没有「唯一完美模型」，最优是组合。** 七个项目里，方法论真正「有同行评审证据」且「License 干净可抄」的只有两个半：**alpha-foundry（源方法 AlphaSAGE 有 ICLR 2026 A 股 benchmark）+ gplearn（FactorBench/Warm Start GP 两篇论文）+ RD-Agent（NeurIPS 2025）**。

**推荐组合方案**：

| 层 | 采用 | 来源 | 理由 |
|---|---|---|---|
| **生成层（公式语言）** | 强类型 CFG + SemKind forbid 表 | **alpha-foundry** | 从源头杜绝 35% 非法公式 + 同构因子（cs_rank 对单调变换不变等） |
| **生成策略** | 课程式 prompt（简单→复杂→连续失败换向） | RD-Agent | 防浅尝辄止 |
| **搜索层** | Warm Start GP（进化式增强） | **gplearn** | 树结构 0% 非法公式，warm start 从已验证因子起变异 |
| **去重/入池** | 行为正交池（per_t_pnl Pearson + 三道门 + OOS） | **alpha-foundry** | 挡换手变体（我们第 1 轮 turn_mid_prox 变体 -0.61 相关正是它要挡的） |
| **去重补充** | 正交化边际 IC（残差化后 IC>阈值才入池） | money-agent | 强制新因子必须有正交边际贡献 |
| **验证链** | 保留我们的组合层 T+1 五步（ICIR→组合层→holdout→正交→容量） | 本机已有 | 这是我们的优势，几乎所有项目都缺这一环 |

**一句话**：把 alpha-foundry 的「强类型 CFG + 行为正交池」抄进我们的 formula_miner 作为生成+去重层升级，把 gplearn 的 Warm Start GP 作为搜索增强器，其余项目的思路按需借鉴，验证链保持我们自己的组合层裁决。

---

## 二、7 项目对比表

| 项目 | License | 证据等级 | 核心方法论 | 解决我们的三个坑？ | 可抄代码 |
|---|---|---|---|---|---|
| **alpha-foundry** | ✅ MIT | 源方法 ICLR2026 A股 benchmark（IC 0.079/ICIR 0.496/Sharpe 1.71）；自身零 benchmark | 强类型 CFG + GP/GFlowNet + 行为正交池 + 4 道验证门 | ✅✅✅ 三坑全解（设计上） | 是 |
| AlphaGPT | ✅ Apache-2.0 | **零**（主流程是 Solana meme 非 A 股；无 benchmark；Issues 关闭） | 公式语言+StackVM+REINFORCE；但主流程无 action mask、无 OOS、无去重、无截面因子 | ❌（原版三坑都没解） | 是（times.py 有泄漏 token 需删） |
| **Qlib + RD-Agent** | ✅ MIT | NeurIPS 2025 论文；效果作者自报 | Qlib=手工因子库158/360；RD-Agent=提假设→写因子→组合回测→因子库累积闭环 | 部分（去重只按名字，弱） | 是（但 RD-Agent 仅 Linux） |
| alpha-mining-system | ✅ MIT | 零（19 star） | 裸 eval + GP随机噪声 + Deep空壳 + 假数据 | ❌ | 是（但空心） |
| alphaminingv2 | ❌ 无 license | 零（4 star） | LLM 工具协议 + 结构指纹去重 + 相位状态机 | 部分（设计好，但 region 硬编码 USA，去重未接入主流程） | 否 |
| money-agent | ❌ 无 license | 零（16 star） | 原生 Python + 硬编码假组合指标 + 字符串级 GP | ❌（组合层指标是假的） | 否 |
| **gplearn** | ✅ BSD-3 | FactorBench + Warm Start GP 两篇论文 | 树形 GP + 0% 非法公式 + hall_of_fame 去重 | 部分（0 非法✅，但同构+组合失效更重，论文实锤） | 是 |

---

## 三、关键发现（诚实披露）

### 1. 所有项目都踩了我们同样的坑（或根本没解决）
- **「截面 ICIR 高但组合层失效」**：FactorBench 实测 gplearn 训练 IC 高但测试期 RankIC 转负；money-agent 的组合层指标是硬编码假值（sharpe=icir*1.5）；alphaminingv2 根本不做组合层验证（只优化 Brain 单因子 Sharpe）。
- **「同构因子霸榜」**：Warm Start GP 实测传统 GP 10 次跑 7 次出相同因子（相关 0.87）；几乎所有项目要么没去重，要么去重是字符级（抓不到数学等价同构）。
- **我们的 formula_miner 已经领先**：公式语言 + StackVM + 语义去重 + 组合层裁决，这套组合比 7 个项目里的大多数都完整。缺的是「强类型约束」（防非法公式从源头）+「行为正交去重」（挡换手变体）。

### 2. License 红线（只能抄 MIT/BSD 的）
- ✅ 可抄代码：alpha-foundry（MIT）、Qlib/RD-Agent（MIT）、alpha-mining-system（MIT）、gplearn（BSD-3）。
- ❌ 只能借鉴思路：alphaminingv2、money-agent（无 LICENSE = All Rights Reserved）。

### 3. 最值钱的三个「直接可抄」模块（按价值）
1. **alpha-foundry 的强类型 CFG + SemKind forbid 表**：`cs_rank` 对严格单调变换不变 → 禁止其子节点是 RANKED/NORMALIZED；`tanh(rank)≈恒等` → 剪；`mul_const(·,±1)` → 剪。这把「同构因子」在**生成源头**剪掉，而不是挖出来再 dedup。
2. **alpha-foundry 的行为正交池准入**：per_t_pnl Pearson 相关（不是语法相似）+ 三道门（近克隆 R²>0.5 拒 / Δ=|IC|·(1−R²)<floor 拒 / OOS holdout 末 25% 方向盈利才入池）+ leave-one-out prune。
3. **gplearn 的 Warm Start GP 四招**：warm start 从已验证因子起 / 固定树结构+受限交叉 / 种群去重 / 多结构并行——直击同构霸榜。

---

## 四、对我们的 formula_miner 的具体升级计划

**Phase 1（最高价值，直接抄 alpha-foundry）**：
1. 把「token 序列 + StackVM 后置校验」升级为「强类型 CFG + 生成时 legal_mask」——非法率 35%→接近 0。
2. 加 SemKind forbid 表（cs_rank/cs_zscore/tanh 的不变群剪枝）——同构霸榜从源头缓解。
3. 去重从「截面 Spearman vs 锚点」升级为「per_t_pnl 行为正交 + 三道门 + OOS holdout」——挡换手变体（第 1 轮的 -0.61 教训）。

**Phase 2（搜索增强，抄 gplearn）**：
4. 加 Warm Start GP：从 5 个已有效因子（amihud/ma200_trend/mom_120/bp/f_score）起变异，固定树结构+受限交叉。
5. 加 parsimony 抗 bloat + OOB 双重校验。

**Phase 3（闭环，抄 RD-Agent）**：
6. 「超当前因子池 SOTA 才入库」+ 因子池累积 + 每轮与 SOTA 对比。
7. 课程式生成 prompt（简单优先→渐进复杂→连续失败换方向）。

**Phase 4（调度，抄 alphaminingv2 思路）**：
8. Creative/Improvement 相位状态机 + PLATEAU 检测（防原地打转）。

**不引入的**：原生 Python + 软黑名单（money-agent/alpha-mining-system 的退化做法）、Brain 单因子目标函数（alphaminingv2）、名字去重（RD-Agent 短板）、全样本 Pearson novelty（alpha-foundry 作者自己批判的伪多样）。

---

## 五、重大纠偏（AlphaGPT 调研的诚实发现）

1. **imbue-bit/AlphaGPT 主流程是 Solana meme 加密版，不是 A 股**——A 股只是根目录独立脚本 `times.py`（单 ETF 时序 `[5,T]` 挖因子，**无截面 RankIC/ICIR**）。
2. **HKUST arXiv:2308.00016 是另一个无关项目**（LLM 人机交互挖因子，EMNLP 2025 Demo），与仓库同名但零代码关系。我们之前的命名混淆需纠正。
3. **Gao-Yimeng fork 的「中国股市」改造是半成品**（off-by-one bug：vocab_size=17 但 INPUT_DIM=6 未改，token 索引系统性错位）。
4. **原版 AlphaGPT 无 benchmark、无去重、无组合层验证、主流程无 OOS**。

**结论：我们的 formula_miner 不是「复刻 AlphaGPT」，而是「公式语言+StackVM+REINFORCE 的方法论提炼 + 大幅自研扩展」**——截面化（bars.db 全市场）、去重闸门、组合层 T+1 五步验证链，都是原版没有、我们自研的。**我们在「A 股截面因子挖掘」上已经领先原版 AlphaGPT。**

---

## 六、待办
- [x] 7 项目 4 步评估（全部完成，本报告）。
- [ ] 深验证 + LLM 第 2 轮最终结果收尾。
- [ ] 数据补拉（2010-2018 历史 + 两融 + 一致预期）。
- [ ] 决策链接线（L0 红绿灯 + L2 Pitch + L1 因子池 + 执行）。
