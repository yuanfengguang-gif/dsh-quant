# 核心问题追踪表（Core Issue Tracker）

> 目的：固化「昨天到今天」发现的关键问题、决策与后续动作，避免丢失。
> 维护：deepseek-harness-quant 本机 · 最后更新 **2026-10-17**（新增第九节：通达信数据源切换后审计与修复）
> 状态标记：⏳进行中 ｜ ✅已完成 ｜ 🔵待实施 ｜ ⏸搁置 ｜ ❌放弃

---

## 一、决策记录（2026-10-14 用户拍板）

| ID | 问题 | 决策 | 状态 | 下一步动作 |
|---|---|---|---|---|
| **D-01** | 社保等 tushare 专属数据（shebao.db） | **暂缓**：记着，先验证「免费数据挖不出新 alpha」再买 token | ⏸ 搁置 | — |
| **D-02** | 15 个有效因子何时正式入池 | **长历史验证后入池**：等 baostock 2010-2018 到位，在 2010-2026 重验后再入池 | 🔵 待实施（等 T-01） | baostock 拉完 → 核对 → 长历史三层验证 → 入池 |
| **D-03** | 矿机升级做到什么深度 | **直接上完整版**：抄 alpha-foundry 的完整 SemKind 强类型 CFG + 生成时 legal_mask | 🔵 待实施 | 读 alpha-foundry grammar.py → 移植 SemKind 类型系统 |
| **D-04** | 决策链做到什么程度 | **完整复刻主系统 L0→L2→L1→执行** | 🔵 待实施 | 复刻 L0 择时→L2 Pitch 审批→L1 因子池→执行全链 |
| **D-05** | 主系统私有因子公式（~16 个） | **放弃**：纯靠矿机挖新的 | ✅ 已决策 | — |
| **D-06** | 因子挖掘自动化 | **分两步**：① 现在缺新因子 → **每天自动挖**；② 累计到 **40 个有效因子**后 → 改**每周自动挖** | 🔵 待实施 | 建每日自动挖掘任务 + 40 目标计数器 |
| **D-07** | 因子组合前向模拟盘验证 | **要做**：因子组合接入纸面交易前向验证（复用 portfolio/paper_account 骨架） | ✅ 已落地 | `factors/walk_forward.py` + `holdout_split.py`（见 A-07 结论） |
| **D-08** | 数据源升级（通联 DataYes） | **评估完成，待用户决定**：通联覆盖 ~95% 需求（行情全字段+复权因子+流通市值+披露日 actDate+退市状态），缺口=ST标记字段+因子库(424+精品，locked)+历史范围 | 🔵 待用户拍板 | 见 `output/DATAYES_DATA_ASSESSMENT_20261014.md`；免费版只能验「近一月」，历史+因子库需个人版 1299/年 |
| **D-09** | 论文因子 + 通联因子的验证策略 | **先保存公式，等通联市场数据下载后统一验证**：① 论文挖的因子先只生成公式保存（不本地验证）；② 通联因子是黑盒（不公开公式），从因子名推断公式保存；③ 等通联市场数据（行情/财务/复权/披露日）下载完毕后，用干净数据统一走验证链（ICIR→去重→组合层T+1） | ✅ 已决策（2026-10-15） | 见 A-10 |

---

## 二、进行中的后台任务

| ID | 任务 | 状态 | 备注 |
|---|---|---|---|
| **T-01** | baostock 全量重拉 2010-2018（安全版） | ⏳ pwsh-82 | 单登录+串行 0.3s+backoff；产出 source='baostock' |
| **T-02** | 矿机升级版运行（行为正交+forbid+WarmStart） | ⏳ pwsh-81 | LLM 20 + WarmStart 20 = 40 候选 |

---

## 三、待办清单（含依赖关系）

| ID | 待办 | 优先级 | 依赖 | 状态 |
|---|---|---|---|---|
| **A-01** | baostock 拉完 → 核对行数 + close 连续性 → 删 source='tencent' 4.97M 行 | 高 | T-01 | 🔵 待 T-01 |
| **A-02** | 2010-2026 长历史重新三层验证 15 因子 → 正式入池（三件套） | 高 | A-01, D-02 | 🔵 待 A-01 |
| **A-03** | 移植 alpha-foundry 完整 SemKind 强类型 CFG（D-03） | 高 | T-02 完成后 | 🔵 待实施 |
| **A-04** | 完整复刻决策链 L0→L2→L1→执行（D-04） | 中 | — | 🔵 待实施 |
| **A-05** | 建「每日自动挖掘」机制 + 40 有效因子目标计数器（D-06） | 中 | A-03 | 🔵 待 A-03 |
| **A-06** | 11 个新挖有效因子走验证链（ICIR 海选→组合层→分年度 holdout→前向） | 高 | D-08 | 🔵 待实施 | 来源：`logs/formula_miner_directed_{value,growth}.json`（价值 5 + 成长 6，主线「基本面−收益/波动」） |
| **A-07** | 组合构建 + 前向验证 + 层4 风控（三级止损+个股止损联动择时）结论归档 | 高 | 已完成 | ✅ | 最终（止损择时联动）：全样本 净超额+6.95%/夏普1.42/回撤−15.31%；前向2026 净超额+8.01%/夏普0.30/回撤−14.64%；危机窗口抗跌（2022超额+18.7%/2024微盘股+28.5%）。见 `output/PORTFOLIO_BUILD_REPORT_20261014.md` + `risk/stress_test.py` |
| **A-08** | 数据缺陷修复（P0：is_st 全0 / 退市股148缺失 / qfq复权80%偏差） | 高 | D-08 | 🔵 待 D-08 | 见 `output/DATA_DIAGNOSTIC_REPORT_20261014.md`；换通联/tushare 源可根治 F-1/F-2/F-5/F-6 |
| **A-09** | ★优化择时信号（等通联数据修好后继续） | 高 | A-08, D-08 | 🔵 待 A-08 | 用更快信号（MA50/20日动量）gate 个股止损，减少 MA200 滞后；当前 MA200 慢信号致前向2026回撤−14.64%（vs 无条件止损−1.29%）。结论已固化于 HANDOFF.md 与 `risk/stress_test.py` |
| **A-10** | 论文因子公式 + 通联因子公式 → 等通联市场数据后统一验证入池 | 高 | A-08 | 🔵 待 A-08 | 总表：`output/FACTOR_VERIFICATION_BACKLOG_20261015.md`（502 因子：~398 可自算 + ~104 需另类）；论文因子：`logs/paper_factors_generated.json`（16 篇，18 公式 + 32 定义）；通联因子推断：`output/DATAYES_FACTOR_FORMULAS_20261015.md`；验证链 = ICIR 海选→去重闸门→组合层 T+1→分年度 holdout |

---

## 四、已完成（通宵任务归档，供上下文）

| 项 | 产出 |
|---|---|
| 7 项目因子挖掘选型 | `output/factor_mining_model_comparison_20261014.md`（组合=alpha-foundry CFG + gplearn GP + 行为正交池 + 我们的验证链） |
| 深验证（双中性+Brinson+容量） | `output/deep_validation_conclusion_20261014.md`（amihud/f_score/bp/turn_mid 真 alpha） |
| 验收工具拆分 | `validation/quality_{exposure_check,brinson_industry,decay_check}.py` |
| 因子池归档 | `output/factor_pool_report_20261013.md` + `factors/FACTOR_FORMULA_CATALOG.md` + `factors/FACTOR_FALSIFICATION_LOG.md` |
| 决策链一键脚本 | `scripts/run_decision_chain.py` |
| 数据 fetcher | `data/fetch_{bars_history_tencent,rzrq_em,consensus_ths,bars_history_baostock}.py` |
| Windows 计划任务 | LWQuant-* 6 个（已建） |

---

## 五、执行顺序建议（按依赖）

```
T-01(baostock) ──► A-01(核对+删腾讯) ──► A-02(长历史验证15因子入池)
T-02(矿机) ──► A-03(完整 SemKind) ──► A-05(每日自动挖+40目标)
A-04(决策链完整复刻) ← 独立，可与上面并行
```

---

## 六、设计方向（2026-10-14 用户确认）

> 项目定位：个人低频量化，追求「确定性盈利」（高胜率+低回撤+稳定复利）+ 执行自动化 + 预警复盘。

| 方向 | 决策 | 关键参数 |
|---|---|---|
| **③ 组合构建层** | 补「组合分散 + 中性化 + 回撤约束」（这是确定性盈利的地基） | 10~20 只持仓、等权/风险平价、行业×市值中性、目标 夏普>1 / 回撤<15% / 年化 15~25% |
| **④ 自动执行层** | 全自动 + 预警兜底，分两步（半自动指令清单→稳定后全自动） | 券商 QMT/PTrade/掘金 API；先生成指令清单一键确认，跑稳后开全自动开关 |
| **⑤ 预警机制** | 5 类预警，通知后复盘调整 | 回撤>10% / 因子滚动ICIR失效 / 执行异常(下单失败·一字板) / 数据异常 / 择时防御期；微信(Server酱/企业微信)+邮件 |

## 七、系统架构（6 层，基于定位）

```
数据层 → 因子层 → 组合构建层(③) → 自动执行层(④) → 监控预警层(⑤) → 复盘调整层
```

## 八、组合构建方案（2026-10-14 用户确认）

> 对比主系统（等权+择时+硬过滤）、行业标准（均值方差/风险平价/HRP）、GitHub 开源（PyPortfolioOpt/Riskfolio-Lib）后优选。
> 核心结论：**对个人低频，简单等权 + 择时 > 复杂优化**（主系统 17 年实证 + DeMiguel 2009）。

| 环节 | 方案 | 理由 |
|---|---|---|
| ① 因子合成 | 15 个已验证因子（或最优子集）等权合成综合得分 | combo 层验证过的正 alpha |
| ② 选股 | 综合得分 Top 10~20 只（中性化后） | 分散、抗单股暴雷 |
| ③ 权重 | **等权**（首选）/ 风险平价（备选） | 等权最稳健、可复现、有实证 |
| ④ 中性化 | 行业×市值双中性（复用 validate_deep） | 不赌单一行业/大小盘 |
| ⑤ 硬过滤 | ST / 流动性 / 退市（复用 equal_weight_timing） | 防垃圾股 |
| ⑥ 择时 | Regime 五档 → 总仓位（复用 timing.py） | 主系统实证唯一有效 alpha |

> 待确认的核心指标：持仓数量(10/15/20) / 因子子集 / 调仓频率 / 择时是否硬接线 / 回撤止损阈值 / 中性化强度 / 目标区间(夏普>1·回撤<15%·年化15~25%)。

## 九、通达信数据源切换后 · 审计与修复（2026-10-17）

> **背景**：2026-10-16 完成「免费多源（tushare/baostock/akshare/东财/腾讯）→ 通达信」切换。
> 历史行情 = 一次性外部导入；每日行情 = 通达信 API 增量。
>
> **两个库的关系（务必记住）**：
> | 库 | 角色 | 内容 | 谁写 | 谁读 |
> |---|---|---|---|---|
> | `data/cache/bars.db` | **主库 / 消费端** | 只有 qfq，15,700,238 行，2000-04-03 ~ 2026-10-16，可写 | `switch_to_tdx_bars.py`(一次性) + `fix_bars_increment.py`(每日) | **140 个代码文件**（因子/组合/回测/风控/门户） |
> | `data/cache/bars_tdx.db` | **源库 / 生产端** | qfq 15,672,362 + **unadj 700,861** + `adj_factor` 1,848 万 + `stock_info` | `import_tdx.py`(文件导入) + `tdx_daily_update.py`(API 增量) | 18 个文件，全是导入/生产/校验工具，**无一个在交易链路上** |
>
> 行数对账：`bars.db.qfq 15,700,222 = bars_tdx.qfq 15,672,362 + 增量 27,860`（精确相等）。
> **bars_tdx.db 不能停/删**：每日增量入口 + 复权因子 + 那 673,001 行历史原始价只在它里面。
>
> 审计产出：`output/DATA_SOURCE_MIGRATION_AUDIT_20261017.md`（含全部 file:line）、
> `output/DATA_FOUNDATION_QUALITY_REPORT_20261016.md`（数据质量）

### 9.1 修复任务（按优先级）

| ID | 问题 | 严重度 | 影响 | 前置 | 状态 |
|---|---|---|---|---|---|
| **DS-01** | 每日增量 `turn` 全空 / `is_st` 恒 0 / 首日 `preclose+pct_chg` 全空（`data/tdx_daily_update.py::write_bars`） | 🔴 高 · **每天恶化** | 最近 5 个交易日 5,572 行/天 全坏；turn_low 主仓口径 + ST 过滤 + pct_chg 因子在最新数据上全错；20 个交易日 ≈ 11 万行 | 无 | 🔵 **待做（用户已同意，稍后一起做）** |
| **DS-02** | 北交所 247 只「整只不在主库」（`adj_factor` 表里 0 行因子 → 算不出 qfq） | 🟡 中 | 2020-06 起缺口 177,055 行中 **99.6% 来自此**；`bars_tdx` 有 597 只北交所，`bars.db` 只有 350 只 | 无 | 🔵 待做（二选一：定性为「已知边界」写文档 / 补北交所复权因子） |
| **DS-03** | pre-2017 长历史蓝筹缺失（`qfq_factor` 早期为负值被 `>0` 过滤；茅台 2001-2016 缺） | 🟡 中 | 全历史缺 673,001 行中约 49.6 万行；只影响 2017 前长历史回测 | **先定 `qfq_factor` 语义** | 🔵 待做（可缓） |
| **DS-04** | `stock_info_snapshot.IsSTGP=1` 只有 1 只（`stock_info_tdx` 是 201 只）→ 每日 ST 快照写入损坏 | 🟡 中 | 「逐日积累历史 ST 序列」这条长期解**当前无效**，每天浪费积累天数 | 无 | ✅ **2026-10-17 已修**：根因是 `tdx_daily_update.py:232` 的 `INSERT ... SELECT * FROM _tmp_snap` **列序错位**（name←IsSTGP、IsSTGP←IsQuitGP…整行错位）→ 改为显式列名；`IsSTGP` 一律以 `stock_info_tdx` 为准；已重建 2026-10-16 快照（**5,581 行 / ST 201 / HS300 300 / 名称正确**） |
| **DS-05** | `bars.db.daily_bar` 残留 16 行 `source='baostock'` / `adjust='none'` | 🟢 低 | 让「单一数据源」这句话不成立 | 无 | ✅ **已改判**：不是残留，是 `SH.000300` 沪深300指数序列（在用）→ **不删**，待 T3 切通达信（`000300.SH`，实测取值完全一致） |
| **DS-06** | `data/cache.py` 的 `bars_incr.db` 双库写路由（主库现已可写，路由已失效）+ `minute.db` 死引用（9 文件，文件不存在） | 🟢 低 | 纯误导，容易让人以为数据写进了别处 | 无 | 🔵 待做（纯减法） |
| **DS-07** | `finance.db`（旧 akshare 财报，无披露日）**64 处 / 39 文件** 仍被引用 | 🔴 高 | 机会扫描、因子挖掘、因子复现全在用它；无 PIT | `finance_csmar.db` 已就绪 | 🔵 待做（**方案：在 `data/cache.py` 加源适配器，只改 1-2 个文件，不动 39 个调用点**） |
| **DS-08** | `stock_basic.db`（旧基础信息）**58 处 / 38 文件** 仍被引用 | 🔴 高 | 横切依赖，几乎每个脚本都用 | `tdx_meta.universe/stock_info_tdx` 已就绪 | 🔵 待做（同上，走适配器） |
| **DS-09** | `hist_mv.db`（流通市值，仅 `2020-01` 起，**且连大盘股都缺：茅台 0 行、招行 69/82、宁德 49/82、五粮液 75/82**）**36 处 / 24 文件** | 🔴 高 | **① 它是「核心脚本起点 2020-06」的真正原因；② 它自己覆盖就不全 → 现在的市值中性化在这些股票上本来就是坏的** | — | ✅ **已验证可完整重建**（见 9.4 能力验证） |
| **DS-10** | `finance_quality.db`（19 处/14 文件）、`valuation.db`（18 处/9 文件） | 🟡 中 | F-Score 只用 finance_quality 一个库（完全未切换） | CSMAR 指标 / `get_more_info` | 🔵 待做 |
| **DS-11** | 断链引用：`unified.db`(28处)/`finance_ts.db`(19)/`macro.db`(14)/`epu.db`(8)… 共 **21 个库名 ~90 处** 指向不存在的文件 | 🟡 中 | 包在 try/except 里→**静默降级**，典型的"看着跑通、其实没数据" | 无 | 🔵 待做 |
| **DS-12** | 例外保留：`lhb.db`(龙虎榜)、`limitup.db`(涨停池)、`rzrq.db`(两融)、`consensus.db`(一致预期) | — | **通达信无对应，不能停** | — | ✅ 已记录（代码/文档需标注「外部补充源」） |
| **DS-13** | 回测窗口是否下延到 2000（见 D-10） | 🟡 中 | 决定 2000-2020 那 27 年数据能不能真正用起来 | DS-09、DS-14 | 🔵 待你拍板 |
| **DS-14** | 铁律③复核：通达信 `turn` 在 2000-2018 **已 100% 非空**，与「2019 前换手结论作废」的前提冲突 | 🟡 中 | 若验证通过 → 换手类因子可解锁 2019 前窗口 | 需抽验通话口径 | 🔵 待做 |
| **DS-15** | **财务「单季口径」重建**：旧 `finance.db` 有 `sq_net_profit/sq_net_yoy/sq_revenue/sq_rev_yoy`（单季+单季同比），新 `finance_csmar` **没有单季列**（只有累计/单期） | 🟡 中 | 切库后任何用单季指标的因子（SUE、单季增速、单季 surprise）会**取不到字段或口径悄悄变化** | DS-07 | 🔵 待做（Q1=累计；Q2=H1−Q1；Q3=9M−H1；Q4=FY−9M；同比用同季） |
| **DS-16** | **估值自算管道**（`valuation.db` 的替代路径）：PE/PB/PS/PCF | 🟡 中 | 现在估值系因子（bp_value 等）依赖只有 2020-06 起的旧库 | DS-09（未复权价+股本） | 🔵 待做（PE=总市值/净利润TTM；PB=总市值/净资产；PS=总市值/营收TTM；总市值=Zgb×未复权close） |
| **DS-17** | **数据可信起点重评估**（用户 2026-10-17 要求）：**不要沿用"2020-06 最干净"的旧结论**——那是基于旧数据源的判断。T0/T1 完成后，按**新数据源**逐项量化（PIT 覆盖率 / is_st 精确度 / turn 口径一致率 / 市值完整性 / 退市股覆盖 / 各字段缺失率），重新确定「可信起点」 | 🔴 高 | 直接决定**主回测窗口**与**因子验证窗口**从哪年开始才可信 | DS-01、DS-04、DS-09、DS-14、DS-15 | 🔵 待做（T4 阶段） |
| **DS-20** | **【2026-10-17 新发现·已修复】qfq 因子源缺陷**：原用 `raw × h(t)/h(最新)`（h 来自后复权因子 zip）。第三源验证发现 h **不是纯事件乘数**（末次除权后仍漂移 +1.63%），与事件法偏差最高 ~30% | 🔴 高 | 历史 qfq 有系统偏差，动量/反转类因子直接受害 | `get_divid_factors` | ✅ **2026-10-17 已修复**：① `data/fetch_tdx_dividends.py` 抓全市场除权明细（**58,929 条 / 5,460 只 / 1990-2026**）；② `data/build_qfq_from_events.py` 用教科书公式自算（`k = 前收盘/理论除权价`，`f(t)=Π(≤t)k/Π_all k`，停牌日用之前最近收盘）；③ 重建并切换 `bars.db`（16,373,178 行）。**验收：涨跌幅异常 46,558 行 → 1,299 行（-97.2%）；2005 年 2.814% → 0.022%** |
| **DS-22** | **【用户提问触发】历史 ST 区间重建**：通达信只有**当前** `IsSTGP`（201 只）+ 每日快照（今天起），**无戴帽/摘帽日期**；`is_st_inferred` P=0.82/R=0.70；两标签在 2010-2019 仅重叠 **113** 个股票-半年 | 🔴 高 | ST 剔除对组合年化影响 **-8.8pp** | akshare `stock_info_change_name` | ✅ **2026-10-17 已完成**：① `data/fetch_name_history_par.py` 抓 **5,581 只简称变更序列**（并发 8，**0.19 秒/只**，1,030 秒完成；**1,955 只有记录 / 663 只曾 ST / 1,292 只从未 ST**，其余 3,626 只无记录）；② 关键验证：**当前 201 只 ST 股全部有名称记录、0 只落在无记录集合** → "无记录 ⇒ 从未 ST" 成立；③ `data/rebuild_is_st.py` 按四级规则重建（R1 从未ST→0、R2 曾ST→用推断、R3 名称滞后/无记录→特殊处理、R4 ≥2020-06→真值不动），**应用 560,863 行变更**（备份表 `is_st_backup_20261017`）；④ **效果：误判 7.8% → 2.1%（一致率 92.2%→97.9%），对组合年化影响 0.88pp → 0.14pp** |
| **DS-21** | `finance_quality.db` 每期仅 ~350 只（`scan.py` 要求 ≥1000）→ `gross_margin` 恒缺失、`scan.py` KeyError | 🟡 中 | 机会扫描链一直缺毛利因子（既有断点） | 无 | ✅ **2026-10-17 已修**：`data/rebuild_finance_quality.py`（CSMAR 源）→ **325,903 行 / 5,978 只 / 每期 5,600 只**（16 倍覆盖），`gp_margin` 非空 97.5%；已切换，旧库归档 |
| **DS-18** | **旧库的通达信替代能力实测**：`GP01~GP46`（龙虎榜/两融/涨停）、`GO1~GO47`（一致预期）、`SC01~SC42`（市场级）是否真有值 | 🟡 中 | 决定 `lhb/rzrq/limitup/consensus` 能否退役（见 9.11 更正） | 无 | ✅ **已完成，结论见 9.16**：龙虎榜仅 2024+（数值与老库完全一致）、两融 2020+、涨停仅统计类可替代、**一致预期不可替代**（全 0.00） |
| **DS-19** | **库 → 数据源 → 更新通道 审计**（用户 2026-10-17 要求）：每个最终库用了哪个数据源、有没有更新通道、有没有"无源/孤儿"库 | 🟡 中 | 防止"库里是旧数据但没人知道" | 无 | 🟡 **初版已完成**（`risk\audit_db_sources.py` → `logs\db_source_map_*.json`），更新通道列待精确化 |

### 9.2 数据源引用迁移现状（审计结论）

| 状态 | 代码文件数 | 说明 |
|---|---|---|
| ✅ 只用新库（已切换） | **98** | |
| ⚠️ 新旧混用（半切换） | **56** | |
| ❌ 只用旧库（完全未切换） | **31** | |

新库使用度：`bars.db` 304 处/140 文件（主力）、`bars_tdx.db` 34/18、**`tdx_meta.db` 仅 7/5**、**`finance_csmar.db` 仅 5/4**、`datayes_basic.db` 7/4 → **新库除行情外基本闲置**。

### 9.3 被本次切换取代 / 需重定基线的旧条目

| 旧条目 | 原内容 | 现状 |
|---|---|---|
| **D-08** | 待用户决定是否买通联 DataYes | ⏸ **已作废**——改用通达信（全量 16-22 元 vs 通联 17 万） |
| **D-09 / A-10** | 等通联数据后统一验证论文+通联因子 | ⚠️ **需重定基线**：通联 token 在本机是占位符，`502` 因子是粗估（真实可枚举 = 论文 18 公式 + 32 定义） |
| **T-01 / A-01 / A-02** | baostock 重拉 2010-2018 → 核对 → 删腾讯源 → 长历史重验 15 因子 | ⚠️ **与通达信切换重叠**：行情历史已由通达信接管，需确认是否还需要 baostock 段；`bars.db` 已无 tencent 源（旧源只在 `daily_bar_legacy` 备份里） |
| **A-08** | 数据缺陷 F-1/F-2/F-5/F-6 | 🔁 部分已由本轮解决：F-5 有披露日（CSMAR）、F-6 有独立复权因子；F-1 is_st 见 DS-04/D-3；F-2 退市股见审计（337 只仅 25 只有行情） |

### 9.4 通达信能力验证（2026-10-17 实测，回答「新数据源是否已解决老库问题」）

> 结论：**老库的历史局限，通达信基本都能解，缺的是"代码没切 + 衍生库没重建"。**

| 老库/老问题 | 通达信能否替代 | 实测证据 |
|---|---|---|
| `stock_basic.db` 基础信息（5,561×6：code/name/industry/ipo_date/out_date/status） | ✅ **能，且更全** | `tdx_meta.universe`(code,name,market) + `stock_info_tdx`(63 列：`IsSTGP` 201 只 / `IsQuitGP` / `BelongHS300/SGT/RZRQ` / **`J_start`=上市日**（平安 19910403 ✅） / `ActiveCapital`+`J_zgb` 股本 / `rs_hyname` 行业 / `tdx_dyname` 地域 / `blockzscode` 板块) + `datayes_basic.sec_delisted`(**精确退市日**) |
| `finance.db` 老财报（319,089×11，**无披露日 → 无法 PIT**） | ✅ **能，且质变** | `finance_csmar.db.fin_core`(95,435×41，含 **`publish_date`** 非空 83.8%) + `fin_core_q`(325,903×37)；旧库的 `sq_net_profit/sq_net_yoy/sq_revenue/sq_rev_yoy`（单季口径）新库没有列，但**可由季度累计值差分算出**（需代码加工，不是数据缺失） |
| `hist_mv.db` 流通市值（**只有 2020-01 起，且覆盖不全**） | ✅ **能重建全历史（2000 起）** | ① `tqs.get_gb_info_by_date(stock_code, start_date, end_date)` → **逐日流通股本**（茅台 6,022 条 2001-08-27~2026；平安 6,328 条 2000-01-04~2026；单位=股）；② `tqs.get_market_data(...)` 默认即返回**未复权原始价**（茅台 2001-08-27 = 34.51，与 bars_tdx 的 unadj 完全一致）→ **流通市值 = Ltgb × 未复权 close** |
| `valuation.db` 估值（2020-06 起：peTTM/pbMRQ/psTTM/pcfNcfTTM/turn/isST） | 🟡 **部分可替代** | `turn` ✅（**bars.db 全历史 2000-2026 已 100% 非空**）；PE/PB/PS 可由「总市值(Zgb×未复权 close) ÷ CSMAR 净利润/净资产」**自算**；`isST` 历史仍只能近似（`is_st_inferred`，P0.82/R0.70）；`tradestatus` 停牌可由"当日有无成交"推断 |
| 北交所复权因子 | ❌ **真缺** | 247 只北交所股票在 `adj_factor` 表 **0 行** → 算不出 qfq → 整只不在主库（见 DS-02） |
| 历史 ST（PIT） | ❌ **真缺** | 通达信只有当前 `IsSTGP`；2020-06 前只能推断/披露（见 DS-04、D-3） |

**另需注意的两个坑（重建时要处理）**：
1. **市值必须用未复权价**：主库 `bars.db` 只有 qfq，直接 `qfq_close × 股本` 会**系统性低估历史市值**（qfq 越早越小）。必须用 `bars_tdx` 的 unadj 或重新取未复权价。
2. **`hist_mv.circ_mv` 单位**：按数值反推 ≈ **百万元**（平安 2020-01：303,870.66 → 约 3,039 亿元 ✅）；重建时须显式换算，不要沿用。

### 9.5 新增待你拍板的决策

| ID | 问题 | 选项 | 状态 |
|---|---|---|---|
| **D-10** | 回测窗口是否下延（2020-06 → 更早） | A) 保持 2020-06（稳，但浪费 20 年数据）；**B) 重建 hist_mv 到 2000 后下延（✅ 已实测可行，见 9.4）**；C) 过渡期先用 `--no-neutral` 跑长窗口做稳健性检验（今天就能跑） | 🔵 待拍板 |
| **D-11** | 北交所是否纳入股票池 | A) 不纳入（记为已知边界）；B) 补北交所复权因子后纳入（247 只） | 🔵 待拍板 |
| **D-12** | 4 个无通达信替代的旧库（lhb/limitup/rzrq/consensus）如何处置 | A) 保留并标注「外部补充源」；B) 找通达信替代接口；C) 停用相关功能 | 🔵 待拍板 |
| **D-13** | 迁移窗口内（10/19 前）4 个周任务怎么处理 | **A) 临时 Disable，迁移+回归后一起启用（推荐，见 9.9）**；B) 只 Disable DecisionChain；C) 不 Disable，赶在 10/19 前完成 T3 | ✅ **已拍板：A（2026-10-17 用户确认临时禁用）** |

### 9.6 建议执行顺序（**初版 · 已被 9.7 修订，仅留档**）

> 排序原则：先止血 → 再解锁能力 → 再做数据源对齐 → 最后清理。
> 每批都能**独立验收**，做坏了可以单独回滚。

| 批次 | 内容 | 预计工作量 | 风险 | 做完得到什么 |
|---|---|---|---|---|
| **第 1 批（止血）** | **DS-01** 修 `tdx_daily_update.py::write_bars`（turn / is_st / preclose+pct_chg）+ 回填 2026-10-12~16 的 27,860 行；**DS-05** 清 16 行 baostock 残留 | ~30 分钟 | 极低（只动增量函数 + 精确回填） | 最新数据不再每天变坏；主库成为"纯通达信单源" |
| **第 2 批（解锁窗口）** | **DS-09** 用 `get_gb_info_by_date`（逐日流通股本）× 未复权价重建 `hist_mv` 到 2000 年（**顺带修掉"茅台 0 行"等自残缺**） | ~半天 | 低（写新库，不碰主库） | ① 市值中性化恢复正确 ② `DEFAULT_START=2020-06` 的窗口约束解除 ③ 2000-2020 的 20 年数据第一次真正可用 |
| **第 3 批（财务对齐）** | **DS-07** 在 `data/cache.py` 加源适配器（`finance.db` → `finance_csmar.db`）+ **DS-15** 单季口径差分 | ~1 天 | 中（影响 39 个文件，但只改 1-2 处入口） | 机会扫描/因子挖掘/因子复现全部拿到 **PIT 披露日** |
| **第 4 批（基础信息对齐）** | **DS-08** 适配器（`stock_basic.db` → `tdx_meta.universe` + `stock_info_tdx` + `datayes_basic.sec_delisted`） | ~半天 | 中（38 个文件受益） | 上市/退市日、行业、ST、指数归属全部来自新库 |
| **第 5 批（清理）** | **DS-11** 断链清理（21 个库名 ~90 处）、**DS-06** 死路由/`minute.db`、**DS-04** ST 快照修复 | ~半天 | 低 | 消除"静默降级"；历史 ST 序列开始正常积累 |
| **第 6 批（可选/研究）** | **DS-16** 估值自算管道、**DS-14** turn 口径验证（解铁律③）、**DS-03** pre-2017 蓝筹补回、**DS-02** 北交所 | 1-2 天 | 中 | 2019 前换手因子解锁、长历史完整 |

**保留不动**：DS-12 的 4 个旧库（`lhb`/`limitup`/`rzrq`/`consensus`）。

#### 第 1 批验收标准（DS-01 + DS-05）

1. `python risk\verify_bars_switch.py` 的 **[4c] `tdx_api` 行 turn 缺失 = 0**、**[4d] 近 5 个交易日 turn 缺失 = 0**
2. `2026-10-12` 的 **`pct_chg` 空白 = 0**（该日现在 5,572 行全空）
3. `2026-10-12` ~ `10-16` 每天 **`is_st=1` 应为 201 只量级**（现在恒 0）
4. `python data\run_daily_update.ps1` 再跑一次 → 两步退出码均 **0**
5. `bars.db` 里 `source` 只剩 `tdx` / `tdx_api`（baostock 残留清零）

#### 第 2 批验收标准（DS-09 重建 hist_mv）

1. 覆盖 **2000-01 ~ 2026-10**，股票数 **≥ 5,500**
2. **茅台必须有 82+ 个月**（现在 0 行）；招行/宁德不再缺月（现在 69/49）
3. 与旧 `hist_mv` 重叠段（2020-01 起）抽查 3 个月，偏差 **< 1%**（若一致则说明单位换算正确）
4. **不出现"越早市值越小"的系统性偏差**（证明用的是未复权价而不是 qfq 价）
5. 单位显式写进表结构注释（旧库是 `百万元` 口径，需换算/统一）

#### 需你先确认的 3 件事

| # | 待确认 | 选项 |
|---|---|---|
| 1 | 从第 1 批开始，还是直接做第 2 批（一次拿掉窗口+茅台缺失两个问题）？ | 建议**先 1 后 2**（第 1 批半小时、风险最低） |
| 2 | 第 2 批重建的市值写**新库**（如 `mv_tdx.db`）还是**原地重建** `hist_mv.db`？ | 建议**新库**（`hist_mv.db` 保留做对照，验收通过后再切） |
| 3 | 第 3/4 批的适配器改法：改 `data/cache.py` 一处收口，还是逐个改调用点？ | 建议**收口**（改 1-2 处 vs 改 77 处） |

---

### 9.7 修订版执行方案（2026-10-17 二次评估 · **待你确认**）

#### 为什么改排序（三个新证据推翻了初版）

| 新证据 | 影响 |
|---|---|
| **本地 `复权因子_前复权.zip`(154MB) + `复权因子_后复权.zip`(159MB) 都还在**；`全A日K` 27 个 zip（2000-2026，1.0GB）也在 | `qfq_factor` 出现负值（茅台 2001 年 -8.79）**更像是当年解析写错，而不是数据缺**。→ **DS-03（pre-2017 蓝筹）+ DS-02（北交所）共享同一根因**，可一次修掉，且顺带产出**全历史未复权价** |
| `tqs.get_divid_factors` 可用（茅台 30 条除权明细、平安 23 条）；**北交所 430047.BJ = 0 条** | 有除权明细可**自算复权因子**并交叉校验；北交所可能**根本无除权** → 其 qfq = unadj，可直接补 |
| **4 个周任务将在 10/19（周一）跑**：AfterCloseScan 17:35 / DailyPipeline 18:30 / DecisionChain 18:40 / FactorDaily 19:15 | 其中 `scan.py` 依赖 4 个旧库、`combo_daily_signal.py` 走因子池 → **适配器要在 10/19 前完成，否则下周一仍跑在旧数据上** |

**关键返工风险**：初版把 DS-09（重建市值）排第 2，但市值必须用**未复权价**；未复权价要靠复权引擎产出。**先做 DS-09 会返工**。

#### 修订后的顺序：三轨道并行 + 一个收口点

```
T0 止血（30 分钟，独立，立即做）
   DS-01 增量字段(turn/is_st/preclose/pct_chg) + 回填 27,860 行
   DS-05 清 16 行 baostock 残留
        │
        ├──────────────┬─────────────────────────┬──────────────────────┐
        ▼              ▼                         ▼                      ▼
   T1a 复权引擎     T1b 股本引擎              T3 代码对齐             （并行）
   (解 DS-03+DS-02)  (供 DS-09/14/16)          DS-06 → 适配器
   重解析两个 zip    get_gb_info_by_date        DS-07+15+10 / DS-08
   + divid_factors   全市场逐日 Ltgb/Zgb        （收口在 data/cache.py）
   校验 + 产出 unadj
        └──────┬───────┘                         │
               ▼                                 ▼
        T2 派生层（依赖 T1a+T1b）           T3 收尾
        DS-09 hist_mv 重建 2000            DS-04 ST 快照修复
        DS-16 估值自算 PE/PB/PS            DS-11 断链清理（必须在替代源接上之后）
        DS-14 turn 复算校验
               │
               ▼
        T4 收口验证（依赖全部）
        DS-13 窗口下延 + 重跑因子验证链 + 重跑组合层 T+1
```

| 阶段 | 任务 | 依赖 | 可并行 | 预估 | 风险 |
|---|---|---|---|---|---|
| **T0** | DS-01 + DS-05 | 无 | 与所有 | **30 分钟** | 极低 |
| **T1a** | 复权引擎：重解析 `复权因子_前复权.zip` + `全A日K`(unadj) + `get_divid_factors` 校验 → 产出**全历史未复权价 + 正确复权因子** | 无（本地文件） | 与 T1b / T3 | **2-4 小时** | 中（要定因子口径）· **✅ 用户已确认要做（2026-10-17）** |
| **T1b** | 股本引擎：`get_gb_info_by_date` 全市场逐日 Ltgb/Zgb → `tdx_base.db` | 无 | 与 T1a / T3 | **1-2 小时**（API 遍历 ~5,600 只） | 低 |
| **T3a** | DS-06：清 `bars_incr.db` 死路由 + `_wprobe` 逻辑（**必须在适配器之前**，否则适配器建在错路由上） | 无 | 与 T1a/T1b | 1 小时 | 低 |
| **T3b** | DS-07 + DS-15 + DS-10 **一次设计到位**（同一个 `data/cache.py` 收口点：财务 + 单季差分 + quality/valuation） | T3a | 与 T1a/T1b | 1 天 | 中 |
| **T3c** | DS-08：基础信息适配器（`stock_basic` → `tdx_meta` + `datayes_basic`） | T3a | 与 T1a/T1b | 半天 | 中 |
| **T2a** | DS-09：`hist_mv` 重建到 2000（Ltgb × unadj close） | T1a + T1b | — | 1-2 小时 | 低 |
| **T2b** | DS-16：估值自算（总市值 ÷ CSMAR 净利润/净资产） | T2a | — | 2-3 小时 | 中 |
| **T2c** | DS-14：turn 复算校验（用 Ltgb 复算，对比 TDX 的 turn，决定铁律③） | T1b | 与 T2a/T2b | 1-2 小时 | 低 |
| **T4** | DS-04 + DS-11（收尾清理）、DS-13（窗口下延）、**重跑因子验证链 + 组合层 T+1** | 全部 | — | 半天-1 天 | 中 |

**关键路径**：T0 → T1a/T1b → T2a → T2b → T4 ≈ **2 天**（与 10/19 周任务吻合，但没有余量）。
**并行红利**：T3（代码对齐）与 T1/T2（数据）完全解耦，可同时推进；T1a 与 T1b 也可同时跑。

#### 明确**不能**并行的 6 组（有硬依赖）

1. T1a/T1b → T2a（市值要未复权价 + 逐日股本）
2. T2a → T2b（PE/PB 要总市值）
3. T3a → T3b/T3c（适配器要建在干净的 `cache.py` 上）
4. T3b → DS-11（**先接上 CSMAR 替代 `finance_ts.db`，再删断链**，否则逻辑止损功能真没了）
5. 全部 → DS-13（窗口下延要市值+is_st+turn 就绪）
6. 全部 → 因子验证链重跑（否则验证的是旧数据）

### 9.8 连带影响清单（改这些地方会同时受影响）

> 这张表是"改动波及面"清单，实施时必须逐项核对，否则会出现"数据换了、别处没跟上"。

#### A. 数据一致性（4 项）

| # | 连带点 | 说明 |
|---|---|---|
| A1 | `bars.db.bar_meta` 表 | 补行/重建 bars.db 后必须重建 `bar_meta`（否则依赖它的代码读到旧日期范围） |
| A2 | `bars_legacy_backup_20261016.db`（2.7GB） | 这是**唯一回滚点**；在动 bars.db 前必须先确认它完好，或另存一份 |
| A3 | `tdx_meta.is_st_inferred` | 若 is_st 方案变化（DS-04/铁律），推断表要按新口径重算 |
| A4 | `logs/` 里基于旧数据的产出 | `portfolio_builder.json`、`formula_miner_results.json`、`stop_alerts_*.json` 等**应标记作废**，避免后续引用旧结论 |

#### B. 代码收口点（5 项）

| # | 连带点 | 说明 |
|---|---|---|
| B1 | `data/cache.py::normalize_units()` | 它**按 source 判断单位**（tushare→×1000/×100）；source 体系换了，这个函数要么简化要么重写（HANDOFF 卡点 3） |
| B2 | `data/cache.py::_inc_paths()` / `_writable()` / `_wprobe` | 废弃 `bars_incr.db` 时同步删；否则适配器建在错路由上 |
| B3 | `deck/live_api.py::_bars_version()` | 它 glob `data\cache\bars_incr_*.db` 做缓存键 → 废 incr 库时同步改 |
| B4 | `deck/system_live.py::DBS` + `_probe_one` | 写死 5 个库（bars/finance/finance_quality/minute/hist_mv）；换库要同步，且 `tabs[0]` 取表逻辑要修（现在把 `daily_bar_legacy` 当主表） |
| B5 | `factors/fscore.py` | 只用 `finance_quality.db`；换 CSMAR 后可**补齐 P9（资产周转）**——旧库因缺 `total_assets` 一直计 null，CSMAR 有 `total_assets`+`revenue`，切完 F-Score 从 8/9 变 9/9 |

#### C. 口径变化 → 结果会变（4 项，必须披露+重跑）

| # | 口径 | 变化 | 后果 |
|---|---|---|---|
| C1 | **行业分类** | 旧 `stock_basic.industry` = "J66货币金融服务"（证监会门类）→ 新 `rs_hyname` = "全国性银行"（通达信行业，更细） | **行业中性化/行业暴露/行业轮动结果全变** |
| C2 | **turn 单位** | `bars.db.turn` = 小数（0.0028=0.28%）；`valuation.db.turn` = 百分数（0.5455=0.55%） | 混用会差 **100 倍**；`turn_low` 主仓口径必须明确用哪个 |
| C3 | **code 格式** | `finance.db`/`valuation.db` = 6 位（"000001"）；`bars.db`/`stock_basic.db` = 带后缀（"000001.SZ"） | 适配器必须统一转换（HANDOFF 坑①：`zfill(6)` 会静默失效） |
| C4 | **市值单位** | 旧 `hist_mv.circ_mv` ≈ 百万元（平安 2020-01：303,870.66 ≈ 3,039 亿） | 重建/切换时不能混用 |

#### D. 配置 / 文档 / 开源（3 项）

| # | 连带点 | 说明 |
|---|---|---|
| D1 | `config/*.yaml` | **AGENTS.md 架构铁律**：库路径/单位/字段映射**禁止硬编码**，必须进配置 + 提供 `.example`。适配器必须配置化 |
| D2 | `docs/数据说明.md` + `HANDOFF.md` | HANDOFF L33「turn 2019 前缺失」、L220「isST 2020-06 起」、§2.1/2.2 库清单、§八 环境事实，**全部需要同步更新**（否则下个会话又按旧信息做事） |
| D3 | 开源包数据边界 | 新建的 `tdx_base.db` / `mv_tdx.db` 属**行情衍生数据，禁止进开源包**（AGENTS.md 铁律②），需 `.gitignore` + 只放获取脚本 |

#### E. 运行层（3 项，已实测）

| # | 连带点 | 现状 | 要做什么 |
|---|---|---|---|
| E1 | **7 个计划任务** | `DSHQuant-TDX-DailyUpdate`(日 17:30) ✅；`LWQuant-AfterCloseScan`(周 17:35→10/19) → `scan.py --pitch`（**依赖 4 个旧库**）；`LWQuant-DailyPipeline`(周 18:30) → `daily_pipeline.py`（引用 minute.db）；`LWQuant-DecisionChain`(周 18:40) → `run_decision_chain.py`；`LWQuant-DeckGuard`(每 30min) → `ensure_deck.py`；`LWQuant-DevDriver`(每小时) → `dev_auto.py`（**只引用不存在的 unified.db**，等于空转）；`LWQuant-FactorDaily`(周 19:15) → `combo_daily_signal.py` | 逐个核对依赖并决定「切新库 / 停用 / 改名」；`DevDriver` 要么接上真库要么停掉 |
| E2 | `risk/audit_bars_gap.py` 闸门基线 | 现在有 673,001 缺口 → 永远 exit 1 | 修完 DS-02/DS-03 后期望值改为「0 或已知边界（北交所 247 只）」，否则闸门恒红失去意义 |
| E3 | **因子验证链已入池的结论** | `data/factorpool/output/` 的三件套是**基于旧数据**通过验证链的 | 换数据后**必须重跑** ICIR→去重→组合层 T+1→holdout；期间旧结论应标「待复核」 |

---

### 9.9 四个周任务 × 本轮迁移任务的关系（2026-10-17 实测）

**结论：它们是迁移产物的"最终消费者"，也是天然回归测试；而且这条链现在本来就是半断的——不要为了赶 10/19 牺牲迁移质量。**

#### 依赖与产出（实测）

| 任务 | 时间 | 跑的脚本 | 直接读的库 | 关键产出 / 输入 |
|---|---|---|---|---|
| **LWQuant-AfterCloseScan** | 周 17:35 | `factors/opportunities/scan.py --pitch` | `bars.db` 🆕 + **`finance.db` / `finance_quality.db` / `hist_mv.db` / `stock_basic.db`（4 个旧库）** | 产出 `opportunity_winrates.json`、机会池；输入 `auction_signal*.json` / `factor_manifest_*.json` / `pitch_priority_badges_*.json` |
| **LWQuant-DailyPipeline** | 周 18:30 | `data/daily_pipeline.py` | `bars.db` 🆕 + **`minute.db`（文件不存在＝死引用）** | 纯编排器（subprocess 调下游），自身无库直读产出 |
| **LWQuant-DecisionChain** | 周 18:40 | `scripts/run_decision_chain.py` | 不直接读库（纯编排） | 输入 `daily_signal.json` / `dynamic_regime.json` / `opp_pool_*.json` / `pitch_deck_*.json` |
| **LWQuant-FactorDaily** | 周 19:15 | `factors/combo_daily_signal.py --topn 20` | `bars.db` 🆕，但 `import factors.import_qf_pool` → **间接读 `finance.db` + `hist_mv.db`** | 产出 `combo_signal_latest.json` |

#### 现状断点（这才是重点）

| 链路中间产物 | 是否存在 | 后果 |
|---|---|---|
| `logs/opp_pool_*.json` | ❌ **不存在** | DecisionChain 的输入缺失 |
| `logs/pitch_v2_*.json` | ❌ **不存在** | Pitch 层没产出 |
| `logs/pitch_track_pool_*.json` | ❌ **不存在** | **`risk/stop_monitor.py` 监测 0 只的直接原因**（实盘止损监测没有输入池） |
| `logs/daily_signal_*.json` | ❌ **不存在** | DecisionChain 输入缺失 |
| `logs/tech_pitch_*.json` | ✅ 有（10-14/15/16 每天） | 唯一在稳定产出的 |
| `logs/combo_signal_latest.json` | ✅ 有（10-16 19:49） | FactorDaily 确实跑通并产出 |

→ 所以 10/19 那 4 个任务里：**DecisionChain 因输入不存在必然空转**、**AfterCloseScan 会跑在 4 个旧库上**、**FactorDaily 间接依赖 2 个旧库**、**DailyPipeline 引用不存在的 minute.db**。

#### 与迁移任务的三层关系

1. **数据层**：它们是 `DS-07/DS-08/DS-09` 的消费者 —— 迁移做完了，这条链才第一次能跑在干净数据上
2. **验证层**：它们是**最好的端到端回归测试** —— 适配器改完跑一次，就知道新库能不能撑起真实业务
3. **时间层**：10/19 17:35 起连跑 4 个 → 若迁移只做一半（例如 `hist_mv` 换了但适配器没换），会产出**前后口径不一致**的结果

#### 建议（D-13 见 9.5）

| 方案 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| A（推荐） | 迁移窗口内**临时 Disable** 这 4 个周任务；T0+T1a+T1b+T3 做完、回归通过后一起启用 | 干净、无口径混杂、不赶工 | 本周一不出机会池（**但它本来就断的，实际损失≈0**） |
| B | 只 Disable `DecisionChain`（输入不存在，必失败），其余 3 个照跑 | 改动最小 | AfterCloseScan 仍跑旧库，产出与迁移后不一致 |
| C | 不 Disable，先把 T3 适配器赶在 10/19 前完成 | 周一如期跑新数据 | 压缩质量、返工风险高（T3 需 1-1.5 天） |

---

### 9.10 口径说明（回答「窗口下延是什么」「4 个旧库为什么保留」）

#### A. 「窗口下延」到底指什么

**字面**：把脚本里写死的回测起点往前挪（往历史方向延）。

**现状**：
```python
factors/portfolio_builder.py:50   DEFAULT_START = "2020-06-01"   # 注释：# hist_mv / turn 覆盖边界
factors/combo_validate.py:48      DEFAULT_START = "2020-06-01"
backtest/bt_engine.py:364         --start default="2020-01-01"
```
即所有回测/验证默认只跑 **2020-06 ~ 2025-12（约 1,358 个交易日）**。

**下延 = 把这个起点改成更早的日期，样本从 1,358 个交易日扩到几千个**：

| 档位 | 起点 | 样本长度 | 覆盖的市场环境 |
|---|---|---|---|
| 现状 | 2020-06 | ~1,358 交易日 | 结构牛 + 2022 熊 + 2024 微盘（≈1.5 个周期） |
| B1 | 2015-01 | ~2,700 | + 2015 杠杆牛/股灾、2016 熔断 |
| B2 | 2010-01 | ~4,000 | + 2010-2014 震荡、2013 钱荒 |
| B3 | 2000-04 | ~6,400 | + 2001-2005 长熊、**2006-2007 大牛（+400%）**、**2008 崩盘（-70%）** |

**但「下延」不等于改一个常量**，它要求 4 件事同时就绪：
1. **市值中性化**要覆盖早期 → 需要 DS-09 重建 `hist_mv`
2. **is_st** 在早期可信（或明确接受近似）
3. **turn** 在早期可用 → DS-14 验证（通达信已 100% 非空，但要验口径）
4. **改脚本默认值 + 重跑验证链**（不是替换，而是**长短窗口双跑**）

**我建议的做法（不是二选一）**：把窗口拆成两个用途——
- **主口径窗口**（决策依据）：**保持 2020-06**（数据最干净）
- **稳健性窗口**（判因子是否过拟合）：**2010-2026 或 2000-2026**
- 判据：**两个窗口方向一致**才算因子稳；方向相反 = 该因子是 2020-2025 这一段行情的产物

#### B. 为什么 `lhb.db` / `limitup.db` / `rzrq.db` / `consensus.db` 必须保留

1. **通达信基本没有**（已枚举全部 **41 个 `get_*` 接口**，逐个核对）：

   | 旧库 | 通达信对应接口 | 结论 |
   |---|---|---|
   | `lhb.db` 龙虎榜 | **无** | ❌ 真缺 |
   | `consensus.db` 一致预期 | **无**（无分析师预测类接口） | ❌ 真缺 |
   | `limitup.db` 涨停/炸板池 | 有 `get_zdt_data(stock_list)` "批量查询股票涨跌停数据"，但**只有当前快照、签名无 start_time/end_time**；而 `limitup.db` 需要的是**历史逐日累积的池**（`zt_pool` 882 行） | ⚠️ **不能替代历史**，仅可作当日实时补充 |
   | `rzrq.db` 两融 | `get_gpjy_value` / `get_bkjy_value` / `get_scjy_value` 是"个股/板块/市场交易数据"且**支持日期区间**，但**字段清单未确认**（docstring 为空） | ⚠️ **待探明字段**，可能在里面；但即便有也建议保留旧库做交叉校验 |
2. **它们被代码真实使用**（不是僵尸库）：
   | 旧库 | 代码引用 | 谁在用 |
   |---|---|---|
   | `lhb.db` 龙虎榜 | **13 处 / 5 文件** | `data/daily_accumulate.py`（每日累积）、`factors/reproduce_factors.py`（因子复现） |
   | `limitup.db` 涨停/炸板池 | **9 处 / 3 文件** | `daily_accumulate.py`、`fetcher_advanced.py`（机会类型之一） |
   | `rzrq.db` 两融 | **4 处 / 2 文件** | `data/fetch_rzrq_em.py`（619 万行，资金面因子） |
   | `consensus.db` 一致预期 | **4 处 / 2 文件** | `data/fetch_consensus_ths.py`（分析师因子） |
3. **牵着你的核心方法论**：牛散蒸馏体系里**龙虎榜席位行为是核心证据**（多个 skill 引用 `.db` 的席位数据）；涨停池是机会扫描的一类机会；两融是资金面。停掉它们不是"少个数据源"，是**砍掉一类因子 + 断一个功能**。
4. **维护成本极低**：都是小库（lhb 32MB / limitup 0.2MB / consensus 0.6MB / rzrq 544MB），累积脚本已存在，不需要额外投入。
5. **目标要修正**：
   - ❌ 原目标："所有数据都切到通达信"
   - ✅ 正确目标：**"行情 / 财务 / 基础信息 → 通达信；另类数据 → 保留现有源，并在配置里登记为『外部补充源』"**
   - 落地：在 `config/data_sources.yaml` 里登记每个库的「来源 / 更新方式 / 是否外部补充 / 取代关系」，既是 AGENTS.md 的配置化要求，也防止以后有人误以为漏切了。

### 9.11 【重大更正】通达信其实能提供 lhb / rzrq / limitup / consensus

> 2026-10-17 用户要求复查后，在官方文档 `C:\Users\Administrator\.dsh\skills\tdx-aidata\docs\tdxaidata使用文档.md` §9 F.7 里找到完整字段表。
> **我此前"通达信没有这些"的判断是错的**（只看了接口名没查字段）。

| 旧库 | 通达信字段（文档原文） | 接口 | 历史可取？ |
|---|---|---|---|
| **`lhb.db` 龙虎榜** | `GP02` 买入/卖出总计(万元)；`GP08`/`GP09` 机构买卖；`GP17` 营业部买卖；`GP18` 沪深股通；`GP37` 上榜类型连续交易日；`GP42` 专业机构买卖净额；市场级 `SC16~SC19` | `get_gpjy_value(field_list=[...], start_time, end_time)` | ✅ **支持日期区间** |
| **`rzrq.db` 两融** | `GP03` 融资余额/融券余量；`GP11` 融资买入/偿还；`GP12` 融券卖出/偿还；`GP13` 融资净买入/融券净卖出；`GP31`/`GP32` 转融券；市场级 `SC01` 沪深京融资余额 | 同上 / `get_scjy_value` | ✅ **支持日期区间** |
| **`limitup.db` 涨停** | `GP14` 涨停金额/开板次数；`GP24` 首次涨停时间/最大封单额；`GP36` 竞价涨停买；`GP38~GP40` 涨停统计（次数/首板封板率/连板率）；市场级 `SC03`/`SC04` 涨停/跌停家数；另有 `get_zdt_data`（仅当前快照） | 同上 | ✅ 个股级可；**"当日涨停池名单"横截面需逐日快照累积** |
| **`consensus.db` 一致预期** | `GO3` 目标价；`GO4~GO25` T/T+1/T+2 的 EPS/净利润/营收/营业利润/每股净资产/ROE/PE；`GO29`/`GO30` 机构持股；`GO26~GO28` 解禁/预约披露 | `get_gp_one_data(field_list=[GO*])` | ❌ **无日期参数，只返回当前值** → 历史只能从现在起逐日快照 |

**修正后的结论**：
- `lhb.db`、`rzrq.db` → **可以替代**（有历史，且字段比旧库更全）
- `limitup.db` → **大部分可替代**（个股统计可回溯；"池名单"需自建逐日快照）
- `consensus.db` → **只能替代"当前值"**，历史仍是旧库 + 从现在开始积累

→ **D-12 的选项要改**，DS-12「保留 4 库」的说法要改成「3 库可退役 / 1 库保留历史」。

### 9.12 【新发现】`daily_pipeline.py` 里两个隐藏断点

`data/daily_pipeline.py` 是四个周任务里真正编排全部下游的入口（它依次调 `scan.py` → `pitch_v2.py` → `tech_pitch_v3.py` → `position_stop_check.py` → `take_profit_check.py` → `pool_layers.py` → `report/daily_signal.py` → `timing_system.py` → `position_monitor.py` → `pitch_track.py`）。它内部有 2 个断点：

| # | 位置 | 问题 | 后果 |
|---|---|---|---|
| 1 | L149-150：`run_step(... "incremental_daily_tushare.py")` | **日线增量仍在用 tushare**，而 `config/params.yaml` 的 tushare token 是占位符 → 该步**必失败** | 若 `run_step` 失败中断，后续 `scan.py`/`pitch_track.py` 全不跑 → **这就是 `opp_pool_*.json` / `pitch_track_pool_*.json` / `daily_signal_*.json` 全部缺失的可能原因**（→ 也解释 `stop_monitor` 监测 0 只） |
| 2 | L105：`code LIKE 'sh.%' OR code LIKE 'sz.%'` | 用的是**旧 baostock 代码格式**（`sh.600000`），而新库是 `600000.SH` | 该"数据完整性检查"恒返回 0 → 触发误判分支 |

→ 这两条要并入 T0（DS-01）一起修：**日线增量步骤改为调用通达信链路（或直接删掉该步，由 `run_daily_update.ps1` 负责）**；代码格式断言改为 `%.SH / %.SZ`。

### 9.13 数据库保留 / 替换决策表（2026-10-17 · 按"保留的且通达信能取 → 切通达信"原则）

#### 原则的 4 个例外（"能取到"≠"该切"）

| # | 例外 | 实测证据 | 正确处理 |
|---|---|---|---|
| 1 | **一致预期没有历史** | `get_gp_one_data(GO3/GO5)` 只返回**当前值**（签名无日期参数）；返回 `'0.00'` 表示该股无覆盖 | **双轨**：历史留旧 `consensus.db`，今日起用 TDX 逐日快照追加 |
| 2 | **市场级另类数据历史浅** | `get_scjy_value(SC1 两融余额)`：2024-01 ✅ / **2022-01 ❌ 空**；`SC3`（涨停家数）2025-01 ✅ | 市场级只能做"向前增量"，历史靠旧库 |
| 3 | **个股级另类数据深度有限** | `get_gpjy_value(GP3 融资余额)`：**2022-01 ✅**（更早未测）；龙虎榜字段因测试股无上榜数据**尚未验证** | 切换前必须用"重叠段校验"确认 TDX 能覆盖旧库起始年，否则会丢历史 |
| 4 | **退市日通达信没有** | `get_stock_info` 62 字段中 `DelistDate/QuitDate/OutDate` **均返回空**；只有 `IsQuitGP`(0/1) 与 `J_start`(上市日) | `datayes_basic.sec_delisted.delistDate` **不可替代，必须保留** |

#### 决策表（22 个库文件）

| 分类 | 库文件 | 数据源（切后） | 依据 |
|---|---|---|---|
| **A. 保留 + 切通达信**（10） | `bars.db` | 通达信（已切） | 行情主库 |
| | `bars_tdx.db` | 通达信（已切） | 每日增量入口 + adj_factor + unadj |
| | `tdx_meta.db` | 通达信（已切） | 元数据/ST/指数/板块 |
| | `hist_mv.db` | **通达信派生**（Ltgb × 未复权close） | 可重建 2000-2026（DS-09） |
| | `valuation.db` | **通达信+CSMAR 自算**（PE/PB/PS）+ turn 取 bars.db | DS-16；isST 历史仍近似 |
| | `lhb.db` | **通达信 GP2/GP8/GP9/GP17/GP18/GP37/GP42** | 支持日期区间（待验历史深度） |
| | `rzrq.db` | **通达信 GP3/GP11/GP12/GP13/GP31/GP32 + SC1** | 个股级 ≥2022 ✅ |
| | `limitup.db` | **通达信 GP14/GP24/GP36/GP38-40 + SC3/SC4** | 池名单需自建逐日快照 |
| | `industry.db` | **通达信 rs_hyname / get_sector_list** | 注意行业体系变化（见 C1） |
| | `consensus.db` | 通达信 GO3~GO25（**仅当前值**） | 双轨，见例外 1 |
| **B. 替换/停用**（4） | `finance.db` | → `finance_csmar.db` | CSMAR 有 PIT + 949 列 |
| | `stock_basic.db` | → `tdx_meta.universe/stock_info_tdx` | 6 字段全部有对应（J_start/IsSTGP/IsQuitGP/行业/指数） |
| | `finance_quality.db` | → `finance_csmar.db` 重算 | CSMAR 有 ROA/OCF/毛利率/负债率（并可补 P9） |
| | `datayes_factors.db` | → 无（0 字节、来源未登记） | 直接废弃 |
| **C. 必须保留（通达信取不到）**（2） | `datayes_basic.db` | 通联免费接口 | **精确退市日**无替代（例外 4） |
| | `consensus.db`（历史段） | 同花顺（历史） | GO* 无历史（例外 1） |
| **D. 归档/演示（不参与运行）**（3） | `bars_legacy_backup_20261016.db` | — | 唯一回滚点（2.7GB），保留 |
| | `data/demo/bars.db`、`data/demo/demo_bars.db` | 合成数据 | 开源包必需（AGENTS.md 铁律②） |
| | `data/demo/bars_incr.db` | — | 随 `bars_incr` 一起废弃 |
| **E. 废弃/可删**（3） | `bars_incr.db` | — | 主库已可写，路由机制失效 |
| | `minute.db` | → parquet（现状） | 文件不存在，9 文件死引用 |
| | `bars_tdx_test.db`（63MB） | — | 导入测试用，可删 |
| **F. 死引用清理**（21 个库名 ~90 处） | `unified.db`/`finance_ts.db`/`macro.db`/`epu.db`/`gdhs_full.db`/`lhb_full.db`/`rzrq_full.db`/`consensus_snap.db`/`factor_pool.db`/`factor_pitch_perf.db`/`paper.db`/`pools.db`/`subj_quant.db`/`shebao.db`/`stock_dividend.db`/`lhb2.db`/`minute_test.db`/`paper_test.db`/`pools_test.db`/`datayes_sample.db` | **均不存在** | 删引用或补建（DS-11） |

#### 架构建议：另类数据统一到一个入口

既然 A 类里 4 个另类库（lhb/rzrq/limitup/consensus）都改从通达信拉，就让 **`data/run_daily_update.ps1` 增加"另类数据刷新"一步**（现在是 2 步 → 变成 3 步），实现：
- **每日一个入口**（行情 + 元数据 + 另类）→ 少一个依赖
- 另类库的**写入端**换成 TDX，**表结构与文件名不变** → 20+ 处读代码零改动（符合"收口"策略）
- 在 `config/data_sources.yaml` 登记每个库的「逻辑名 → 物理文件 → 数据源 → 更新通道 → 取代关系」

### 9.14 最终执行清单（2026-10-17 用户确认 · 按优先级推进）

**已确认的决策**：D-13 = A（迁移窗口内临时禁用 4 个周任务）｜D-12 = 按 9.13 决策表执行｜T1a 复权引擎 = 要做｜另类数据 = **双轨**（历史留旧库 + 未来 TDX 追加）｜D-10 = 双窗口（主口径暂 2020-06，待 DS-17 重评后再定 + 稳健性窗口）｜D-11 北交所 = 暂记为已知边界。

#### T0 止血（✅ 2026-10-17 12:25 完成）

| ID | 任务 | 文件 | 状态 | 验收证据 |
|---|---|---|---|---|
| DS-01 | 增量补 `turn`（=volume/(Ltgb×10000)）、`is_st`（取 `stock_info_tdx.IsSTGP`）、`preclose/pct_chg`（批首日改用库内前值）+ **缺失率自检告警** | `data/tdx_daily_update.py` | ✅ | 语法通过；`turn` 口径与历史段一致（茅台 0.002927） |
| DS-01b | 回填 2026-10-12~16 增量行 | 新脚本 `data/fix_increment_fields.py` | ✅ | `bars.db`：turn 空 **27,860 → 48**、is_st=1 **0 → 1,005（201 只×5 天）**、preclose 空 5,610 → 38、pct_chg 空 → 50；`bars_tdx`：turn 空 27,905 → 79、并交叉补 preclose 4,953 |
| DS-05 | **改判**：16 行 `source=baostock` 不是残留，而是 **`SH.000300` 沪深300指数序列**（2026-09-17~10-16，`fetch_index_daily.py` 每日维护）→ **不删**，改为"待 T3 切通达信"（实测 `000300.SH` 取值 4460.16/4507.39 与库内完全一致；但代码格式是 `SH.000300` 前缀式，需统一） | `data/fix_increment_fields.py::check_index_rows` | ✅ 已登记 | 见 `logs\_t0_backfill.txt` |
| 9.12-1 | `daily_pipeline.py` 日线增量改用通达信链路（先看 bars.db 最新日，落后才补跑 `tdx_daily_update.py` + `fix_bars_increment.py`，幂等） | `data/daily_pipeline.py` | ✅ | 原 tushare 步骤（token 占位符必失败）已移除 |
| 9.12-2 | 代码格式断言 `sh.%/sz.%` → 新增 `%.SH/%.SZ/%.BJ` 完整性门槛（≥4000） | `data/daily_pipeline.py` | ✅ | — |

**T0 验收结果**：`[4c] tdx_api` turn 缺 **48/27,860（0.17%）**（其中 46 行是 API 返回全 NULL 的停牌/无数据行，非计算问题）；`[4d]` 近 5 日 turn 缺 **8~12/5,573**（原 5,572）；`run_daily_update.ps1` 重跑**两步退出码均 0、全部成功**（12:20 日志）。

#### T1a 复权引擎 + 底座导入（并行轨道 · 2026-10-17 架构升级）

> **架构变更（重大）**：`全A日K` 的 27 个年度 zip（73,739 个股票-年 CSV）**26 列**里已经自带
> `turnover(换手率) / pe / pe_ttm / pb / ps / ps_ttm / dv_yield / dv_ttm / total_share / float_share / free_share / total_mv / circ_mv`，
> 实测单位（与 bars.db 交叉验证，倍数精确）：**volume 手×100=股、amount 千元×1000=元、turnover=%、share=万股、mv=万元**。
> → **T1b（API 抓股本）取消**（已 kill 后台任务，省约 68 分钟 + 积分）；`hist_mv` / `valuation` 均可**直接从本地文件重建**（含茅台）。

| ID | 任务 | 状态 |
|---|---|---|
| DS-03a | 查清 `qfq_factor` 负值来源：**不是解析 bug**——`复权因子_前复权.zip` 原始导出就是负值；`复权因子_后复权.zip` 正常（从 1.0 单调增长，末值=最新日） | ✅ |
| DS-03b | 定出正确换算：**qfq(t) = raw(t) × h(t)/h(最新)**（h=后复权因子） | ✅ |
| **新 T1a-1** | 导入器 `data/import_kday_base.py` → **`data/cache/tdx_base.db`**（26 列全字段 + 单位归一 + PK(code,date)） | ✅ 试点 3 年通过，全量导入中 |
| **新 T1a-2** | 用 `tdx_base` 交叉验证 bars.db 现有 qfq（重叠段偏差应 ≈0） | 🔵 待做 |
| DS-03c | 产出**全历史未复权价 + 正确 qfq 因子** → 供 T2（北交所也一并解决） | 🔵 待做（依赖 T1a-1） |
| DS-02 | 北交所 247 只：文件里是否含 `920xxx/4xxxxx` 待查；若含且有股本 → 一并补进主库 | 🔵 待做（依赖 T1a-1） |

#### ~~T1b 股本引擎~~（✅ 已取消：文件自带 total_share/float_share/free_share，无需 API）

#### T3 代码对齐（并行轨道，与 T1/T2 解耦）

| ID | 任务 | 状态 |
|---|---|---|
| DS-06 | 清 `bars_incr.db` 死路由 + `_wprobe` 逻辑 + `live_api._bars_version()` glob | ✅ **已完成（写路由部分）**：`data/cache.py` 改为**单库模式**（`inc_path = None`）→ 主库被锁时**直接报错（fail fast）**，不再静默改道到 `bars_incr.db`。实测 `_inc_paths()=[]`、`latest_trade_date()` 仍返回 2026-10-16。空的 `bars_incr.db`（24KB，0 行）**归档受阻**（被运行中的进程占用）→ 待服务重启后清理。<br>⚠️ 15 个文件里的 `bars_incr_*.db` glob 均为**恒空的兼容逻辑**（无匹配文件），暂不动（属 DS-11 范畴） |
| **DS-08** | 基础信息适配器（`stock_basic.db`→`tdx_meta`+`datayes_basic`） | ✅ **已完成**：`data/rebuild_stock_basic.py` → `stock_basic_new.db` **5,918 只**（旧 5,561；新增 358 含 920xxx 北交所，仅缺 1 只 300114.SZ）；退市 338 只带**精确退市日**；⚠️ 行业口径变了（旧「J66货币金融服务」→ 新「全国性银行」） |
| DS-07+15+10 | 财务适配器（`finance.db`→CSMAR）+ 单季差分 + quality/valuation 收口 | 🟡 **候选库已建成（待切换决策）**：`data/rebuild_finance.py` → `finance_new.db` **325,903 行 / 5,978 只 / 1990-2026-03-31**。<br>口径：`net_profit`=归母累计、`revenue`=**total_revenue** 累计（茅台 1505.60 亿与旧库**完全一致**）、`sq_*`=同财年差分、`eps/roe`=**期末摊薄**（`eps/roe ≡ BVPS` 自证 **0.000%**）。<br>验收：`net_profit` 与旧库 **r=0.9927**；茅台 2024Q3 单季 191.32 亿/同比 13.23% **三方一致**；营收年报期 **95.8%** 差异 ≤5%。<br>⚠️ 已知：`sq_net_yoy` 与旧库 r=0.69（个案一致，差异疑为旧源 akshare 噪声；已排除期次错位——k=1/2/3 相关性更低）；**CSMAR 数据止于 2026-03-31，2026 中报缺失**。<br>⚠️ 旧库 `roe` 确认为**半年报错位**（茅台 2023-12-31 旧 16.75% ≈ 新 2023-06-30 的 18.22%）→ 旧 BP 因子失真 |
| DS-18 | 另类库替代实测（lhb 龙虎榜字段真调验证 + 历史深度） | ✅ **已完成，结论见 9.16**：龙虎榜只能替代 **2024+**、两融 **2020+**、涨停仅统计类、一致预期**不可替代** |
| DS-19 | 库→数据源审计精确化（更新通道列） | 🟡 初版已完成 |

**DS-07 的正确做法（待你确认）**：重建 `finance_report` 时显式定义口径并自证——
1. `sq_net_profit` = 单季归母净利 = CSMAR 季度累计差分（Q1=累计；Q2=H1−Q1；Q3=9M−H1；Q4=FY−9M）
2. `eps` = 单季归母净利 / 总股本（总股本取自 tdx_base.total_share），`roe` = 单季归母净利 / 净资产（CSMAR equity）
3. **自证**：`eps/roe` 应 ≈ 每股净资产；用 CSMAR `equity/total_share` 反算真实 BVPS 对比，偏差 < 5% 才算通过

#### T2 派生层（依赖 T1a+T1b · 进行中）

| ID | 任务 | 状态 |
|---|---|---|
| DS-09 | `hist_mv` 重建到 2000（Ltgb × 未复权 close），修茅台 0 行 | ✅ **已完成**：`hist_mv_new.db` **826,697 行 / 5,842 只 / 319 个月 / 2000-04~2026-10**；**茅台 0 行 → 302 个月**；单位=百万元（= 源 万元/100，与旧库重叠点差 0.08%~1.1%） |
| DS-16 | 估值自算 PE/PB/PS（总市值 ÷ CSMAR 财务） | 🟡 **改为直接取源**：`tdx_base` 自带 `pe/pe_ttm/pb/ps/ps_ttm/dv_yield/dv_ttm`，无需自算 → `data/build_valuation_from_base.py` 生成 `valuation_new.db`（进行中） |
| DS-14 | turn 复算校验（决定铁律③能否解除） | ✅ **已完成**：`risk/verify_turn_consistency.py` → `output\TURN_CONSISTENCY_20261017.md`。<br>**61/61 抽样点一致、0 异常**；全市场每年 500 只：中位偏差 **0.0005%~0.002%**、P90<0.01%；与旧库重叠日偏差 **0.00%**。<br>→ 换手率全历史同口径（成交量/流通股本），**铁律③ 修订建议已备好，待批准** |

#### T4 收口（依赖全部）

| ID | 任务 | 状态 |
|---|---|---|
| DS-04 | `stock_info_snapshot.IsSTGP` 修复（1 只 → 201 只） | ✅ **已完成**（列序错位根因已修，快照重建） |
| DS-11 | 断链清理（21 库名 ~90 处，**必须在替代源接上之后**） | 🔵 待做 |
| DS-17 | **数据可信起点重评估**（6 项指标 → 年份×可信度热力表 → 定窗口） | 🔵 待做 |
| DS-13 | 窗口下延（按 DS-17 结论） | 🔵 待做 |
| — | 重跑因子验证链 + 组合层 T+1；恢复 4 个周任务（D-13 解除） | 🔵 待做 |

#### 不变项

- 保留：`datayes_basic.db`（退市日无替代）、`consensus.db` 历史段、`bars_legacy_backup_20261016.db`、`data/demo/*`
- 废弃：`bars_incr.db`、`minute.db`、`datayes_factors.db`、`bars_tdx_test.db`

#### 进度汇报日志（每约 1 小时一条，最新在上）

| 时间 | 批次 | 完成 | 验收 | 下一步 |
|---|---|---|---|---|
| 2026-10-17 19:40 | **DS-11 断链盘点** | 全库扫描 `*.py` 里引用的 `.db` 名 vs `data/cache` 实际文件 | 被引用库名 63 个 / 实际存在 35 个 / **真实断链 50 处**，分 4 类：<br>**A 迁移产物名（7 个，9 处）**：`tdx_qfq.db`/`hist_mv_new.db`/`bars_events.db`/`valuation_new.db`/`finance_quality_new.db`/`stock_basic_new.db`/`finance_tdx_new.db` —— 已改为正式库名，**引用它们的分析脚本（`risk/assess_trust_window.py`、`risk/report_main_switch.py`）现在会失败**，需改指向正式库<br>**B 从未构建的功能库（5 个，15 处）**：`finance_ts.db`(5)/`epu.db`(4)/`macro.db`(3)/`unified.db`(2)/`paper.db`(2)<br>**C 已废弃旧名（8 个，10 处）**：`minute.db`/`lhb_full.db`/`rzrq_full.db`/`gdhs_full.db`/`lhb2.db`/`shebao.db`/`stock_dividend.db`/`factor_pitch_perf.db`<br>**D 测试/演示名（4 个，6 处）**：`demo_bars.db`/`minute_test.db`/`datayes_sample.db`/`pools_test.db` | 执行（按 A→C→B→D 顺序，A 类优先因会直接报错） |
| 2026-10-17 19:05 | **分年度 holdout（决定性检验）** | `risk/holdout_by_year.py`：用档案里的逐日收益算三段（2010-2015/2016-2020/2021-2026）年化，检验"是否真稳健" | **36 个因子里三段全正仅 6 个**：`bp_value`(**21.4%**/0.86：33.5/9.0/21.0)、`turn_mid_prox`(11.5%/0.72)、`turnover_low`(同上，实为同一因子)、`turn_std20`(11.0%/0.68)、`lowvol_60`(8.1%/0.55)、**`accel_factor`(10.2%/0.49，档案判"观察"却被低估)**。<br>⚠️ 档案判"有效"的 `sue` 实际 **2/3**（2016-2020 为 **-0.9%**）→ 不够稳健。<br>共性：**多数因子在 2016-2020 段为负**（该段小盘/反转失效，价值/大盘占优） | B1 资金因子验证（运行中）→ 去重 → 组合层 |
| 2026-10-17 18:55 | **回测档案清理 + 组合层终止** | ① 218 个档案中 **182 个是切换前（10-12~10-16）用旧脏数据跑的** → 归档到 `output/backtest_archive/_legacy_pre_switch/`，页面现只显示 36 条新结果；② 终止跑了 50 分钟的多因子合并组合（价值不高，单因子组合层结果已在档案） | 页面 `/backtest` 只剩 36 条（全 `start=2010-01-01`）；抽查确认 JSON 里 `params.start=2010-01-01`、`note` 明示"简化组合层" | — |
| 2026-10-17 18:45 | **A1 论文配方清点 / B1 资金因子** | ① 定位论文配方库：`output\FACTOR_VERIFICATION_BACKLOG_20261015.md` **18 个可自算逆波兰公式**（q-factor/价值复活/不确定性/关注度/彩票/非参数 六族）+ 32 个需另类数据；② 确认**求值引擎已存在**：`factors\formula_miner.py` 有 StackVM + 15 个特征叶子（ret/ret5/ret20/vol_chg/v_ret/trend/turn/volat/amihud/limup/sue/bp/ep/rev_yoy/accel）；③ **B1 完成**：`factors\funding_factors.py` 实现 3 个资金族因子 | B1 自检通过：**流通市值自算 1.6576 万亿**（茅台实际 1.66 万亿 ✅）、`margin_ratio_20`=1.04%、`short_ratio`=0.016%；`rzrq.db` 覆盖 2010-03~2026-10（619 万行 / 3,854 只）→ **可补上资金族 2010-2018 的空白** | 把 18 个公式喂进 formula_miner 做 ICIR 初筛（A3） |
| 2026-10-17 18:35 | **T4 因子链首轮（36 因子）** | `factors/validate_all_factors.py --out logs/t4_all36_2010.json`（窗口 2010-01-01~2026-10-16，面板 14.17M 行 × 9 列，耗时约 45 分钟） | **有效 6 / 观察 22 / 无效 8**。有效清单：`bp_value`（净超额 **+13.9%** 夏普 0.84）、`turn_mid_prox`（+4.4%/0.70）、`turnover_low`（+4.4%/0.70）、`sue`（+4.8%/0.53）、`turn_std20`（+3.8%/0.67）、`lowvol_60`（+1.0%/0.54）。<br>⚠️ **假覆盖陷阱**：`lhb_jg_cnt_20` 名义覆盖率 100%，但 2012/2015/2018 截面 **std=0、nunique=1（恒为 0）**，真实信号仅 2019+（nunique 36）→ 其"观察"结论只代表 2019+ | ① 把"截面退化"检查加入验证链 ② 8 强因子新旧对照 ③ 组合层 T+1 |
| 2026-10-17 18:00 | **窗口定版 + 文档** | ① `config/backtest_window.yaml` 定为 `2010-01-01 ~ 2026-10-16`、预热 `2008-12-01`；② 生产链 14 处写死常量统一（三批补丁）；③ **误改已修复**（`rebuild_is_st.CUTOFF` 被误改为 2010 → 已恢复 2020-06）；④ **补回 SH.000300 指数**（5,289 行 / 2005-2026 / `source=tdx`，2026-10-16 收盘 4170.61 与旧值一致）；⑤ **窗口写进项目文档**：`AGENTS.md` 数据边界章节重写 + 新建 `docs\回测窗口与数据边界.md`；⑥ `validate_all_factors.py` 加**覆盖率告警**（cov<50% 标"结论不代表全窗口"） | 所有窗口常量已核无残留；文档六节（结论/为什么 2010/九项验证/8 条限制/配置入口/变更历史） | T4 36 因子运行中（7/36，预计 45 分钟） |
| 2026-10-17 17:50 | **窗口配置化** | 按铁律「全部模块动态化」把窗口收敛到配置：`config/backtest_window.yaml` + `.example` + `factors/window_config.py`；改造 `portfolio_builder.py`、`combo_validate.py`（含 `load_panel` 起点） | **默认值仍为 2020-06-01（行为零变化）**；改 YAML 一处 → 两模块常量同步变（已演示 2010-01 生效后还原）；语法通过 | 待用户定窗口值 → 一并改其余 7 处（bt_engine/bt_runner 等）→ 开 T4 |
| 2026-10-17 17:35 | **V3 停牌缺口** | `risk/verify_suspension_gaps.py`：交易日历 4,074 天（2010+）+ 逐股票覆盖率 + 长停牌段 + 前瞻收益跨停牌比例 | **覆盖率<90% 的 234 只（4.0%）主要是北交所**（无成交日不落行）；长停牌段 **3,910 段 / 2,034 只**；**5 日窗跨停牌 0.34%、20 日窗 1.34%** → 因子计算需剔除跨停牌样本 | T4（待用户定窗口/范围） |
| 2026-10-17 17:15 | **DS-22 ST 重建** | 抓 5,581 只简称变更序列（并发提速 36 倍）+ 四级规则重建 + 应用 560,863 行 | **误判 7.8%→2.1%**（一致率 92.2%→97.9%）、影响量级 **0.88pp→0.14pp/年**；当前 201 只 ST 全部有名称记录（0 只无记录）；备份表可回滚 | **T4 验证链**（下游冒烟 → 因子链重跑） |
| 2026-10-17 16:25 | **V5 is_st 敏感性** | 比对 `bars.db.is_st`（旧推断）vs `is_st_inferred`（指标法推断）在 2010-2019 的一致性 + 分组收益 | **一致性仅 92.2%，且重叠极少**（两者都标 ST 仅 **113** 个股票-半年；bars.db 标 ST 2,998 vs 推断 1,218）；**ST 组日均收益比非 ST 低 0.0351pp → 年化 -8.8pp**；误判 7.8% → 影响约 **0.9pp/年** | 见 DS-22 |
| 2026-10-17 16:10 | **V1+V2 补强验证** | ① 估值全市场重算；② 除权事件反查 + 可疑行标记 | **V1：PE_TTM 94.1% 偏差<1%（中位 0.00%）、PB 92.5%（中位 0.05%）**；**V2：跳空 1,299 行中 589(45.3%) 有除权事件已正确复权，剩余 710 行 = 真实异动 551 + 疑似漏报送转 159（占全库 0.0043%）**，已落 `qfq_suspect` 表供因子研究剔除 | V5 is_st 敏感性 → T4 |
| 2026-10-17 15:55 | **DS-20 修复** | 除权明细全量抓取 + 事件法 qfq 重建 + 切换 + A/B 验证 | **涨跌幅异常 46,558 → 1,299 行（-97.2%）**；茅台 2005 年 qfq 9.29→6.85（-26%，旧值虚高）；无负价/重复；门户 HTTP 200 | 补强②估值重算 + 追加验证 |
| 2026-10-17 15:20 | **9.18 C-6** | `SC` 字段定位（与 `bars.db` 自算全市场聚合交叉验证） | **`SC31` = [上涨家数, 下跌家数] 精确确认**（10-09：3,296/2,145 与自算**完全一致**；10-08 1,698/3,747 vs 1,699/3,747）；`SC24` 疑似涨停/跌停家数；其余待与 `rzrq.db`/指数库定位 | T4 下游回归冒烟 |
| 2026-10-17 15:10 | **9.18 C-4/C-5** | 全市场交叉验证 + 成本盘点 | **`Ltsz` vs 自算流通市值：98.6% 偏差<1%、中位 0.013%**；**`Zsz` 99.2%、中位 0.010%**；`fHSL` vs `turn` 99.3%（<5%）→ **证明新主库价格与通达信服务端口径一致**。C-5 结论：SDK 无积分接口，只能给调用量清单（每日快照 11,162 次/天为最大来源，可降为周频） | C-6 迁移映射表收口 |
| 2026-10-17 14:55 | **9.18 C-2** | `data/fetch_tdx_more_info.py` 全市场落库 → `data/cache/tdx_snapshot.db`；并并入每日任务**步骤 3** | **more_info 5,581 行 × 94 列（关键字段非空率 100%）**；**relation 84,056 行 / 887 板块**（概念 47,030 / 风格 21,098 / 行业 10,347 / 地区 5,581）；风格标签含「连续亏损 1,105」「破净资产 435」「破发行价 483」「微小盘股 600」等现成因子 | C-3 深度矩阵 / C-5 成本 / C-6 迁移表 |
| 2026-10-17 14:25 | **9.18 C-1** | `data/probe_tdx_capability.py` 逐个真实调用 **41 个接口** → `output\TDX_CAPABILITY_MATRIX.md` | 23 可用 / 6 未实现 / 12 修正参数后可用；新发现 `get_tick_data`(逐笔)、`get_call_auction`(集合竞价)、`get_zzgz_stocklist`(**指数成分股 300 只**)、`get_trackzs_etf_info`(跟踪 ETF 30 只)、`get_domain_sorthq`(板块排序)、`get_more_info`(**92 字段**)、`get_relation`(**19 条关联**) | C-2 字段字典反推（GP/GO/SC/BK + 92 字段） |
| 2026-10-17 14:22 | **财务库切换** | **`finance.db` 已切到通达信源**（`data/rebuild_finance_tdx.py` → `finance_tdx_new.db` → 就位）：**297,118 行 / 5,577 只 / 1999-06-30~2026-09-30**，**新增第 12 列 `publish_date`（披露日，覆盖率 100%）**；旧库归档 `finance_before_switch_20261017.db` | 与 CSMAR 全量对账：**EPS 99.6%**、**归母净利 99.17%**、**营业收入 97.69%** 偏差<0.5%（EPS 其余差异为两位小数舍入）；与旧库 net_profit 仅 **82.8%** 一致 → **旧库约 17% 的净利润是错的**；茅台 2026-06-30 净利 445.17 亿 / 披露日 2026-08-15 | ① `fetch_finance.py` 需退役或改写（旧 11 列写入会报错）② 启动 C-1/C-2 通达信全能力盘点 |
| 2026-10-17 14:15 | **切换完成** | **主库等 4 个库已切换**：`bars.db`←`tdx_qfq.db`、`hist_mv.db`←`hist_mv_new.db`、`valuation.db`←`valuation_new.db`、`stock_basic.db`←`stock_basic_new.db`；旧库全部改名归档（`*_before_switch_20261017.db` / `bars_before_qfq_switch_20261017.db`）；脚本 `data\switch_main_db.ps1`（支持 `-Rollback` / `-WhatIfOnly`） | 结构自检通过：**16,373,178 行 / 5,842 只 / 2000-04-03~2026-10-16**、adjust 仅 qfq、source=tdx_front_mul+tdx_api；`DailyCache.latest_trade_date()=2026-10-16`；hist_mv 826,697/319 月；valuation 16,345,318；stock_basic 5,918；**门户 8787 重启后 HTTP 200** | 持续数据对照 → 确认无误后进 T4 验证链 |
| 2026-10-17 14:10 | **T3 / 财务通道** | `data/fetch_tdx_finance.py`：通达信财务全量抓取（FN001/004/006/040/074/095/096 + 披露日）→ `tdx_finance.db` | 5,573 只 / **~29.5 万行** / 披露日覆盖 **100%** / 0.11 秒每只 | 与 CSMAR 全量对账（`risk/verify_tdx_finance.py`） |
| 2026-10-17 14:40 | **T3 / 财务库** | `data/rebuild_finance.py` → `finance_new.db`（325,903 行 / 5,978 只）；`risk/verify_finance_rebuild.py` 验收 | `net_profit` r=**0.9927**；茅台 2024Q3 三方一致；`eps/roe≡BVPS` **0.000%**；营收 95.8% 差异≤5% | 待你决定是否切财务库；**CSMAR 止于 2026-03-31** 需补中报 |
| 2026-10-17 14:05 | **T4 / DS-14** | 换手率口径抽验：`risk/verify_turn_consistency.py` → `output\TURN_CONSISTENCY_20261017.md` | **61/61 抽样一致、0 异常**；全市场每年 500 只中位偏差 **0.0005%~0.002%**、P90<0.01%、最大 0.053%；旧库重叠日偏差 **0.00%** | 铁律③ 修订建议已写入报告 §4，**待用户批准**后改 `AGENTS.md` |
| 2026-10-17 13:50 | **T4 / DS-17** | 用新库重评「数据可信起点」：`risk/assess_trust_window.py` → `output\TRUST_WINDOW_20261017.md`。**关键发现：turn 缺失率 2000-2026 每年均 0.00%**（铁律③前提消失）；建议主回测起点 **2010-01**（价量）/ **2021+**（需 PIT 的财务因子） | 逐年 6 指标表：close 缺 0%、pb 缺 ≤2.6%、市值 12 个月全覆盖（除 2000/2026）；PIT 2014-2020 仅 72-78%；退市覆盖 2010 起 ≥90.5%、2000 仅 82.1% | 待确认后改 `DEFAULT_START`（2020-06 → 2010-01）；DS-14 抽验后修订铁律③ |
| 2026-10-17 13:47 | **T3 / DS-06** | `data/cache.py` 改**单库模式**（`inc_path=None`）：主库被锁时**报错而非静默改道** `bars_incr.db`（脑裂风险） | `_inc_paths()=[]`、`latest_trade_date()=2026-10-16` 正常；空 `bars_incr.db` 归档受阻（进程占用） | — |
| 2026-10-17 13:40 | **T3 / DS-18** | 另类库替代能力定案（见 9.16）：龙虎榜仅 2024+、两融 2020+、涨停仅统计类、一致预期不可替代 | 用真实上榜股逐年份实测，数值与老库**完全一致** | `rzrq.db` 可退役，其余保留 |
| 2026-10-17 13:30 | **T3 / DS-08** | `data/rebuild_stock_basic.py` → `stock_basic_new.db` **5,918 只**（旧 5,561） | 新增 358 含 920xxx 北交所；退市 338 带精确退市日；仅缺 300114.SZ | 待切换（与主库一起） |
| 2026-10-17 13:25 | **T1a-4 / T2** | ① qfq 全量重建完成（**16,373,178 行 / 5,842 只 / 2000-04-03~2026-10-16**，含并入 10-12~16 增量）；② **负价清零**（原 32,728 行 → 0）；65 只"因子含负值"股票记入 `qfq_negative_factor` 表；③ **`hist_mv_new.db` 建成**：826,697 行 / 319 个月 / 茅台 302 个月；④ `valuation_new.db` 生成中 | 茅台 2015-06-01 新库=**211.17**（bars.db 缺失）；格力 2015-04-27 新=**16.15**（旧=0.21 垃圾值）；无重复行、close≤0=0 | 估值库完成 → 出「新旧主库对照报告」+ 切换方案 |
| 2026-10-17 12:45 | **T1a-3** | ① 证实文件 h 与 API `back` 只差常数 **320.26**（2010/2020/2026 三点 320.08/320.25/320.26）→ 乘法口径自洽；② 写 `data/build_qfq_from_base.py`（qfq=raw×h/h_last，因子按日期前向填充，无因子的股票 qfq=raw）；③ 试点 6 只通过：**茅台 2015-06-01 = 211.17**（=271.46×0.7779 精确）；④ 全量重建 `tdx_qfq.db` 启动中 | **发现 bars.db 现有 qfq 有垃圾值：103,134 行 / 558 只**（如格力 2015-04-27 存 **0.21**，真实 raw **51.26**，差 77 倍；2001 年就有 10,165 行这类） | 全量完成后做偏差分档 + 抽样核对 → 提主库切换方案 |
| 2026-10-17 12:35 | **T1a** | ① 发现 `全A日K` 27 个 zip 是 **26 列**（含 turnover/pe/pb/ps/dv/share/mv）→ 一个本地包覆盖价格+估值+股本+市值；② 导入器 `data/import_kday_base.py` 完成 → **`tdx_base.db` 16,345,318 行 / 5,842 只 / 2000-04-03~2026-10-09 / 4.68 GiB（含北交所 593 只）**；③ 单位实测精确（volume 手×100、amount 千元×1000、turnover=%、share 万股、mv 万元）；④ **T1b 取消**（文件自带股本，省 68 分钟+积分）；⑤ 复权语义定清（见 9.15） | 单位倍数 100/1000/1 精确；2000 年行数 131,473 与旧测试库一致；茅台 2015-06-01 缺口行已在 base 里（raw 271.46 / pe_ttm 19.36 / circ_mv 3,100 亿） | 用后复权因子派生乘法口径 qfq → 写**新库**对照，确认后再切主库 |
| 2026-10-17 12:25 | **T0** | DS-01 增量字段修复（turn/is_st/preclose/pct_chg + 自检）；DS-01b 回填 27,860 行；9.12-1 日线增量改通达信；9.12-2 代码格式断言；DS-05 改判为"指数数据待切" | turn 空 27,860→48（46 行为 API 全空）；is_st 0→1,005；两步 exit 0 | T1a 复权引擎 + T1b 股本引擎（并行） |

### 9.15 复权口径定案（2026-10-17 实测，DS-03 的结论）

| 结论 | 证据 |
|---|---|
| `复权因子_前复权.zip` 的值 **就是 bars.db 的隐含因子**（qfq/raw） | 000001.SZ 各年：文件 0.132948 / 0.603774 / 0.785285 / 1.0 ↔ bars.db 隐含因子 **完全相等** |
| 但该文件**早期是负值**（茅台 2001-08-27 = **-8.79**、平安 2000-06-01 = -0.0039） | → 用 `raw × 负因子` 会得到**负价格**；当年 `qfq_factor > 0` 的过滤是**对通达信烂数据的规避，不是解析 bug** |
| 通达信 API 的 `dividend_type='front'` 同样给负价 | 茅台 2015-06-01 → Close **-55.0/-59.4/-62.88**（成交量 6,581,670 与库内一致，确认是同一天）→ **通达信的前复权是减法式，累计分红超过原价即转负** |
| `dividend_type` 有效取值 | `'front'`/`'1'` = 前复权；`'back'`/`'2'` = 后复权；`'none'`/None = 原始价（`'qfq'`/`'hfq'`/中文 均报 Invalid server response） |
| `复权因子_后复权.zip` **干净可用** | 从 1.0 单调增长到末值（平安 165.197、茅台 6.296），5,949 只（含 393 只北交所） |
| **定案：自建乘法口径** | **qfq(t) = raw(t) × h(t) / h(最新)**（h=后复权因子）；**无 h 因子的股票**（如 430047.BJ / 830832.BJ）经 `get_divid_factors` 验证**无除权事件 → qfq = raw** |
| 影响面 | 与现 bars.db 相比偏差 **3%~50%**（早期更大）→ 历史回测结果会整体平移，**必须在 T4 重跑验证链** |
| 退市股仍无解 | `tdx_base` 里 337 只退市 A 股只覆盖 25 只（7.4%），与 bars.db 相同 → **幸存者偏差不能靠价格数据修复**（DS-17 要如实披露） |

**下一步（T1a-3）**：把 qfq 计算成**新库/新表**（不覆盖 bars.db），与现 bars.db 做全量对照 → 确认无异常后再切换主库。

### 9.16 另类库通达信替代能力定案（2026-10-17 实测 · DS-18）

> 方法：**从老库挑「确实有数据」的股票与日期**再调 API（避免用不上榜的股票误判"无数据"）。
> 教训：**文档里有字段 ≠ 账号能取到数据**——此前 9.11 只查了文档，判断过于乐观。

| 旧库 | 通达信字段 | 近期数据 | **历史可回溯到** | 数值一致性 | 结论 |
|---|---|---|---|---|---|
| `lhb.db` 龙虎榜（老库 2019 起 13.9 万行） | `GP2` 买卖总额 / `GP17` 营业部 | ✅ 有 | **2024 年**（2019 None / 2020 返回 1000+ 条 `Date='0'` 垃圾 / 2022 None / 2024 ✅ / 2025 ✅） | ✅ **完全一致**（2024-01-02：7,938.73/4,104.59；2025-01-02：15,087.42/9,161.76） | ❌ **不能整体替代**：2024+ 可切，**2019-2023 必须留旧库** |
| `rzrq.db` 两融（老库 619 万行） | `GP3` 融资余额/融券余量、`GP11` 买入偿还、`GP13` 净买入 | ✅ 有 | **2020 年**（2020/2022/2024/2025/2026 每年都有值） | 接近（GP3 43.4 亿 vs 老库 44.1 亿，差 1.6%） | ✅ **可替代 2020+** |
| `limitup.db` 涨停/炸板池 | `GP14`/`GP24` ❌ **恒空**；`GP38-40` ✅ 有（近1年涨停次数/首板封板率/连板率） | 部分 | 未知 | — | ⚠️ **仅统计类可替代**；"当日涨停池名单"仍须自建逐日快照 |
| `consensus.db` 一致预期 | `GO3/GO5/GO8/GO23` | ❌ **茅台/五粮液均返回 '0.00'** | — | — | ❌ **不可替代**（当前账号无此数据） |

**最终处置**：
- `rzrq.db`：可退役（2020+ 由通达信供数）
- `lhb.db`：**保留**（2024 前历史）、2024+ 可双轨
- `limitup.db`：保留池名单；统计字段可选通达信
- `consensus.db`：**必须保留**（唯一来源）

### 9.17 通达信财务接口打通（2026-10-17 新发现 · 解决"CSMAR 停更"）

> `tqs.get_financial_data(stock_list, field_list=[FN001...FN584], start, end)` —— **之前完全没用过**。
> 返回 DataFrame，每行一个报告期，自带 `tag_time`（报告期）与 **`announce_time`（披露日 → PIT！）**。

**字段字典（官方文档缺失，用 CSMAR 值交叉验证反推，3 只股票验证）**

| FN 码 | 含义 | 验证（茅台/平安/格力 FY2025 vs CSMAR） |
|---|---|---|
| `FN001` | 基本每股收益（累计） | **0.0000% / 0.0000% / 0.0000%** ✅ |
| `FN004` | 每股净资产 | 195.36 / 23.25 / 26.05（数值合理，CSMAR 无直接字段） |
| `FN006` | 净资产收益率 ROE（%） | 33.65 vs 33.59、7.74 vs 7.73、19.88 vs 19.27（0.07%~3.2%，加权口径差） |
| `FN040` | 总资产 | **0.0000% / 0.0000% / 0.0000%** ✅ |
| `FN074` | 营业收入 | **0.0000% / 0.0000%** ✅ |
| `FN095` | 净利润（含少数股东） | 茅台 853.1 亿 ✅ |
| `FN096` | **归母净利润** | **0.0000% / 0.0000% / 0.0000%** ✅ |
| ~~`FN017`~~ | ~~经营现金流~~ | ❌ **不是**（格力差 39%）→ 弃用 |

**能力结论**：
1. **能取到 2026-06-30**（CSMAR 数据包止于 2026-03-31）→ **财务数据缺口可补**
2. **自带披露日** → 财务类因子的 PIT 问题**根治**（不必再用"报告期+60日延迟"近似）
3. 每次调用返回最近 6 期 → 可做**每日增量更新**，不再依赖人工更新 CSV 包
4. 缺：经营现金流对应字段未定位（`finance_quality` 需要）；净资产需由 `BPS × 股本` 或 `ROE` 反推

**下一步**：写 `data/fetch_tdx_finance.py`（FN001/FN004/FN006/FN040/FN074/FN095/FN096 + 披露日）→ 落 `tdx_finance.db` → 与 CSMAR 对照 → 作为财务库的**唯一增量通道**。

### 9.18 【新任务 · 用户 2026-10-17 指令】通达信全能力盘点与"尽量全用通达信"迁移

> **定位**：**通达信（tqs）是未来唯一主数据源**。此前多次判断失误，根源是**只查文档没实测**、
> 且**从未系统盘点过 41 个接口的字段/深度/口径**。本任务要求把这件事一次做透。

**目标**：形成《通达信能力矩阵》——对 41 个接口的**每一个字段**给出：
能否取到 / 历史深度 / 单位 / 与现有库的口径一致性 / 积分成本 / 建议用途。

**分阶段计划**

| 阶段 | 内容 | 交付物 | 状态 |
|---|---|---|---|
| **C-1 接口清点** | 41 个接口的签名、必填参数、返回结构（股/板块外层代码 vs 市场级无外层） | `output\TDX_CAPABILITY_MATRIX.md` | ✅ **2026-10-17 完成**：41 个逐个**真实调用**——**23 个可用有数据 / 6 个 SDK 未实现 / 12 个修正参数后可用**（已全部修正验证）。新发现：`get_tick_data` 逐笔、`get_call_auction` 集合竞价、`get_zzgz_stocklist` **指数成分股**、`get_trackzs_etf_info` 跟踪 ETF、`get_domain_sorthq` 板块排序、`get_more_info` **92 字段**、`get_relation` **19 条关联关系** |
| **C-2 字段字典反推** | 官方只给字段码不给含义（`GP1-46`/`GO1-47`/`SC1-42`/`FN1-584`/`BK…`）→ 用**数值交叉验证**反推：拿已知库的同名指标去匹配取值（本日已在 `FN` 上验证此法有效，误差 0.0000%） | 字段码 → 中文含义 → 验证依据 | 🟡 **2026-10-17 重大进展**：<br>· `FN`：7 个核心字段确认（0.0000%）<br>· **`get_more_info` 92 字段**全部盘完（含 `ZAFPre5/10/20/60` **多周期动量**、`Ltsz/Zsz` 市值亿元、`DynaPE/PB_MRQ/DYRatio`、`Zjl` 主力净流入、`FreeLtgb` 自由流通股本、`ZTPrice/DTPrice` 涨跌停价）<br>· **`get_relation` 19 板块**（地区/概念/**风格**/行业；风格含「高分红股/基金重仓/北向重仓/MSCI/行业龙头」→ **现成风格因子**）<br>· `SC` 34/42 有值（市场级，待与已知库定位）<br>· `GP` 11 个确认有值（`GP3` 融资余额、`GP13` 融资净买入已与老库口径吻合）<br>· **三条工程约束**已记录（见矩阵 §3.5） | 
| **C-3 历史深度矩阵** | 每接口 × 每字段 × 年份 的"有值/空/垃圾"三态（本日已发现：GP2 龙虎榜仅 2024+，且 2020 会返回 1000+ 条 `Date='0'` 垃圾） | 深度热力表 | 🟡 已测 GP2/GP3/GP14/GP17/FN | 
| **C-4 单位与口径** | 与 `tdx_base`/`bars.db`/`hist_mv_new` 交叉核对（如 GP3 两融额 vs 老 rzrq 差 1.6%） | 每个字段的单位与换算系数 | 🟡 部分完成 |
| **C-5 成本估算** | 各接口按"只×年"的积分消耗，给出全量抓取预算 | 成本表 | 🔵 待做 |
| **C-6 迁移映射表** | 现有 22 个库 → 通达信哪个接口/字段 → 可退役 / 保留 / 双轨 | 与 9.13 决策表合并 | 🟡 9.16 已定 lhb/rzrq/limitup/consensus |

**已确认的关键能力（本日新增）**
- `get_financial_data`：全历史报告期（100+ 期）+ **披露日**（PIT）+ **含 2026-06-30**（补 CSMAR 缺口）→ **财务库可完全建在通达信上**
- `get_market_data`：`dividend_type` 支持 `front`/`back`（但**通达信前复权为减法式，早期会负价，不可用**，已定案自建乘法口径）
- `get_gb_info_by_date`：逐日股本（万股），一次调用全历史
- `get_gpjy_value`：GP2 龙虎榜（2024+，数值与老库完全一致）、GP3/GP11/GP13 两融（2020+）
- **`get_more_info`（92 字段）+ `get_relation`（19 板块）已全市场落库** → `data/cache/tdx_snapshot.db`：**more_info 5,581 行 × 94 列（关键字段非空率 100%）、relation 84,056 行 / 887 个板块**；已并入每日任务**步骤 3**（`data/run_daily_update.ps1`）从今天起积累历史
  - 现成风格标签 Top：专精特新 1,230 / **连续亏损 1,105** / 近期新低 645 / **微小盘股 600** / 股权转让 495 / 专项贷款 485 / **破发行价 483** / **破净资产 435** / 回购计划 428

**验收标准**：形成一张**可执行的映射表**——每个仍在用的数据库都能回答"通达信哪个接口哪个字段替代它、替代不了的部分怎么办"。

### 9.19 数据层验收总表（2026-10-17 收口）

| 验证项 | 方法 | 结果 | 判定 |
|---|---|---|---|
| V0 复权正确性 | 涨跌幅异常（超板块限幅即错） | h因子法 46,558 → 事件法 **1,299** 行（-97.2%） | ✅ |
| V1 估值重算 | 市值÷净利TTM、价格÷BPS | PE **94.1%**、PB **92.5%** 偏差<1% | ✅ |
| V2 除权反查 | 跳空行有无对应除权事件 | 589/1,299 有事件；剩余 710 = 真实异动 551 + 疑似漏报 **159（0.0043%）** 已落 `qfq_suspect` | ✅ |
| V3 停牌缺口 | 覆盖率 + 长停牌 + 跨停牌收益比 | 234 只覆盖<90%（多为北交所）；**5日窗 0.34% / 20日窗 1.34%** 跨停牌 | ⚠️ 需在因子计算剔除 |
| V4 财务勾稽 | 累计=Σ单季 | 中位偏差 **0.000000%** | ✅ |
| V5 ST 敏感性 | 两套标签对比 + 分组收益 | 重建后误判 **7.8%→2.1%**，影响 **0.88→0.14pp/年** | ✅ |
| V6 市值一致 | 通达信市值 vs 自算 | 中位 **0.013%**（5,558 只） | ✅ |
| V7 换手一致 | 手算 volume/流通股本 | 中位 **0.002%**（61/61 抽样） | ✅ |
| V8 PIT | 披露日滞后分布 | 100% 覆盖、中位 32 天、0 条异常 | ✅ |

**结论：数据层可定稿用于因子研究。** 三条使用约束：
1. 主窗口 **2010-01 起**（2000-2009 幸存者偏差 10-18%，不可用于长期持有类研究）
2. 剔除 `qfq_suspect`（710 行）与**跨停牌样本**（5日窗 0.34% / 20日窗 1.34%）
3. 北交所 593 只流动性低（234 只覆盖率<90%），建议单独处理或在截面中降权

---

*本表随进度更新；每次新决策/完成项都追加进「决策记录」/「已完成」。*
