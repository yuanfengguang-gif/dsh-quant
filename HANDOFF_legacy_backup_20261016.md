# 交接文档（HANDOFF）

> **给完全没有上下文的新会话读这里**：快速了解「我们在做什么、做到哪了、卡在哪、下一步、别踩哪些坑」。
> 详细决策/待办见 `CORE_ISSUE_TRACKER.md`；项目定位说明见 `PROJECT_BRIEF.md`。
> 最后更新：2026-10-14

---

## 一、我们在做什么项目

**个人低频量化交易系统**（开源快照 `deepseek-harness-quant`，本机）。

- 目标：**确定性盈利**（高胜率 + 低回撤 + 稳定复利）+ **执行自动化** + **预警复盘**。
- 定位：个人、低频（40 交易日调仓）、不追暴利追稳定。与私有主系统（DSHQuant，2010-2026 全量数据，**不在这台机器**）定位相似，但更强调执行自动化 + 预警。
- 关键口径（用户拍板）：持仓 15 只 / 因子子集 6-8 个 / 季度常规+事件触发调仓（人工确认）/ 择时硬控仓位 / 三级止损 / 目标 夏普>1·回撤<15%·年化 15-25%。

**系统架构（8 层）**：数据 → 因子 → 组合构建 → 风控 → 执行 → 回溯 → 前向模拟盘 → 监控预警。8 层骨架已全部建好。

---

## 二、数据现状（重要，先了解这个）

| 库 | 内容 | 关键缺陷 |
|---|---|---|
| bars.db | 13.4M 行 / 5487 只，2010-2026 | 2010-2018 是 tencent 源（**无 amount**，volume 单位异常），2019+ 是 akshare（完整）。**回测只用 2019+** |
| finance.db | 财报（akshare 摘要），319K 行 | sq_net_yoy 缺失 16.9%；**无披露日 ann_date**（用固定 60 日延迟近似） |
| hist_mv.db | 流通市值，2020 起月频 | 前向填充 |
| stock_basic.db | 基础信息 | **code 是 `600000.SH` 全码格式**（见坑①） |

**三个 P0 数据缺陷（未修，是当前最大隐患）**：
- **F-1**：is_st 字段全 0（276 只 ST 股 100% 漏标）→ ST 过滤失效，已用「name 含 ST」兜底
- **F-2**：退市股 148 只缺失 → 样本内幸存者偏差虚高
- **F-6**：qfq 前复权以「查询日」为基准 → 80% 行 pct_chg 与 close/preclose 偏差，回测不可精确复现

**数据审计**：`python risk/data_audit.py`（健康度 ~80/100，1 FAIL 8 WARN）。

---

## 三、已完成（截至 2026-10-14）

### 核心成果

| 模块 | 产出文件 | 状态 |
|---|---|---|
| 15 个有效因子 + 三层验证链 | `factors/import_qf_pool.py` + `combo_validate.py` + `factor_pool_writer.py` | ✅ |
| 因子矿机（AlphaGPT 式公式语言） | `factors/formula_miner.py` | ✅ |
| 短板族定向挖掘（价值 5 + 成长 6 新因子） | `logs/formula_miner_directed_{value,growth}.json` | ✅ |
| 因子子集选择（8 因子跨 6 族） | `factors/factor_subset.py` | ✅ |
| 组合构建 6 环节 | `factors/portfolio_builder.py` | ✅ |
| 前向模拟盘 + 分年度 holdout | `factors/walk_forward.py` + `holdout_split.py` | ✅ |
| **层4 风控**（三级止损 + 个股止损联动择时 + 压力测试） | `portfolio_builder.py` + `risk/stress_test.py` | ✅ |
| **层8 预警复盘**（5 类预警 + 微信推送 + 复盘报告） | `risk/alert_engine.py` + `scripts/run_review.py` | ✅ |
| 数据全面诊断 | `risk/data_audit.py` + `risk/data_diagnostic.py` | ✅ |
| 通联数据评估 | `output/DATAYES_DATA_ASSESSMENT_20261014.md` | ✅ |

### 当前组合配置（冻结于 config/portfolio.yaml）

8 因子：`bp_value(价值) / turn_mid_prox(量价) / kdj_j(反转) / amihud(量价) / f_score(质量) / pead_factor(成长) / a_factor(成长) / ma200_trend(量价)`，等权合成 + Top15 + 行业市值中性 + 硬过滤 + Regime 择时（MA200）+ 三级回撤（5%/10%/15%）+ 个股止损（只在择时空头启用）。

### 当前回测结果（最终版「止损择时联动」，基于 2019+ 脏数据，需打折）

| 窗口 | 净超额 | 夏普 | 回撤 |
|---|---|---|---|
| 全样本 2020-2025 | +6.95% | 1.42 | −15.31% |
| 前向 2026（样本外 184 天） | +8.01% | 0.30 | −14.64% |

- holdout 2022-2025 各窗全正；危机窗口抗跌（2022 超额 +18.7%、2024 微盘股 +28.5%）。
- 对比：无止损全样本 +20.97%/1.62/−19.41%；无条件止损全样本 −10.53%（牛市误杀）。

---

## 四、当前卡在哪里（阻塞点）

**通联数据（DataYes）账号问题** —— 用户账号有异常，人工客服已下班，**明天（2026-10-15）处理**。

拿到通联 token 后要做（脚本已写好）：
1. `python risk/verify_datayes.py`（4 项验证：退市股覆盖 / 复权因子 / 披露日 actDate / 424 因子清单）
2. 验证通过 → 用户决定是否上「个人版 1299/年」（已建议先 128 元/月试用）
3. 数据修复（F-1 is_st / F-2 退市股 / F-6 复权）→ 通联一个源可基本根治

---

## 五、下一步计划（按优先级，用户已确认顺序）

```
1. 【等通联】拿到 token → 4 项验证 → 修数据缺陷（A-08）
   └─ 通联字段级评估已做：覆盖 ~95% 需求（行情全字段+复权因子 accumAdjFactor+流通市值+披露日 actDate+退市状态），
      缺口 = ST 原生字段（可用 SecST 接口补）+ 因子库(424+精品，locked 需付费)+ 历史范围(免费版仅近一月)
2. 【等数据修好】A-09 优化择时信号：用更快信号（MA50/20日动量）gate 个股止损，减少 MA200 滞后
3. 【层2 因子】11 个新因子最终入池验证（A-06）：初步筛除已做完（10 个全过粗筛，但年际稳定性差，正年≈负年 3:3）
   → 矿机 SemKind 强类型升级（A-03）→ 每日自动挖掘+40因子目标（A-05）
4. 【层5 执行】决策链完整复刻 L0→L2→L1→执行（D-04）+ 券商接口（QMT/PTrade）
```

**11 新因子初步筛除结论**（`logs/new_factors_screening.json`）：全部「基本面(BP/EP/SUE/ACCEL) − 收益(RET/RET20)」主线；最强 4 个 = BP−RET(+8.20%) / BP−RET20(+5.53%) / SUE−RET20(+4.75%) / ACCEL−RET20(+4.21%)；但年际稳定性差，最终入池前必须等通联复验。

---

## 六、踩过的坑（绝对不要再踩）

1. **stock_basic.code 是 `600000.SH` 全码**，不是 6 位数字。`str.zfill(6)` 会 map 失败导致整层静默失效。正确：`.str.split(".").str[0].str.zfill(6)`。finance.db 的 code 才是 6 位。
2. **三级止损要「逐日」检查回撤**，不是只在调仓日查（否则周期内回撤抓不到，止损完全失效）。
3. **个股止损的权重归一化**：止损卖出后「现金留现金」不重新分配给剩余股。用 `sum(r*w)`，别除以 `wsum`（否则止损后满仓少数股、风险集中、回撤反而更大）。
4. **is_st 字段本身是坏的（F-1，全 0）**：ST 过滤必须用 `stock_basic.name 含 "ST"` 兜底，不能只信 bars.db 的 is_st。
5. **finance.db 基本面 PIT ffill**：`m.reindex(dates).ffill()` 会丢掉面板起点前的 eff_date → 全 NaN。正确：`m.reindex(m.index.union(dates)).sort_index().ffill().reindex(dates)`。
6. **矿机只对「池内锚点」去重**，不对同批候选互相去重 → 要加「批内互去重」，否则同一批出重复因子（如 ADD(EP,SUE) 出现两次）。
7. **矿机 forbid 要拦 NEG(NEG)=恒等**、去重要用「双保险」`max(cross_corr Spearman, pnl_corr 行为)`（否则漏「反方向同源」如 TURN vs turn_mid_prox）。
8. **yaml 会把 `2026-01-02` 解析成 date 对象**（不是字符串）→ 传给 pandas 比较会报错，用 `str(...)` 转回字符串。
9. **baostock 查询 ≥1 年会挂起**（无响应），只适合小批量；2010-2018 历史用 tencent 源但无 amount。
10. **PowerShell 里跑 `python -c "..."` 嵌套引号会炸**（`*` 会被 shell 解释、SQL 的引号被吞）→ 复杂逻辑写成 `.py` 文件跑。
11. **个股止损 + 三级回撤是 regime 依赖的**：熊市救命、牛市误杀。必须「止损与择时联动」（择时空头才启用个股止损），无条件止损会把全样本收益从 +20.97% 打到 −10.53%。

---

## 七、关键决策（D-01 ~ D-08）

| ID | 决策 |
|---|---|
| D-01 | 社保 tushare token 暂缓 |
| D-02 | 15 因子等长历史验证后入池 |
| D-03 | 矿机直接上完整版 alpha-foundry SemKind |
| D-04 | 决策链完整复刻 L0→L2→L1→执行 |
| D-05 | 主系统私有因子公式放弃，纯靠矿机挖 |
| D-06 | 每天自动挖 → 40 有效因子后改每周 |
| D-07 | 因子组合前向模拟盘验证（已完成 walk_forward + holdout） |
| D-08 | 数据源升级通联（评估完成，待用户拍板付费） |
| — | **三级止损用主系统 5%/10%/15%（第15课），不是 10%/15%/20%** |

---

## 八、关键文件索引

- `HANDOFF.md`（本文件）· `CORE_ISSUE_TRACKER.md`（决策/待办 A-01~A-09）· `PROJECT_BRIEF.md`（项目说明）
- 配置：`config/portfolio.yaml`（组合冻结配置）· `config/alerts.yaml`（预警/通知，**Server酱 SendKey 已配**）· `config/params.yaml`（全局参数，含主系统三层回撤 5/10/15）
- 组合：`factors/portfolio_builder.py`（6环节+三级止损+个股止损联动择时）· `factor_subset.py` · `walk_forward.py` · `holdout_split.py` · `validate_new_factors.py`
- 风控/预警：`risk/stop_rules.py`（个股 7 规则）· `risk/risk_agent.py`（主系统风控）· `risk/stress_test.py` · `risk/alert_engine.py` · `scripts/run_review.py` · `risk/data_audit.py` · `risk/data_diagnostic.py`
- 报告：`output/` 下 5 个报告（组合构建/数据诊断/通联评估/任务总结/因子选型）
- 结果 JSON：`logs/`（portfolio_builder / factor_subset / walk_forward / holdout_split / stress_test / new_factors_screening / formula_miner_directed_*）

---

## 九、待用户操作

1. **通联数据账号**（明天处理人工客服）→ 拿到 token 给我跑 4 项验证。
2. 通知通道：Server酱已配 ✅；企业微信/邮件待定（可选）。

---

*本文件随进度更新；新会话先读本文件 + `CORE_ISSUE_TRACKER.md`。*
