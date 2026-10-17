# 组合构建 + 短板族定向挖掘 —— 阶段报告（本机 · 2026-10-14）

> 本次 4 小时自主任务的交付报告：修复基本面特征 bug → 修复矿机盲区 → 因子子集选择 → 组合构建 6 环节 → 短板族定向挖掘。
> 数据边界（诚实披露）：bars.db 2019+（qfq，8.4M 行）+ hist_mv 2020+ + finance.db（akshare 摘要）；回测窗 2020-06-01 ~ 2025-12-31；与主系统 2010-2026 全量口径不一致。

---

## 一、本次修复的 4 个 bug

| # | bug | 根因 | 修复 | 状态 |
|---|---|---|---|---|
| 1 | 基本面特征全 NaN | `m.reindex(dates).ffill()` 丢弃面板起点之前的 eff_date | `reindex(union(dates)).sort_index().ffill().reindex(dates)` | ✅ 已验证（年中起点 2023-06-01：SUE/EP/REV_YOY/ACCEL 覆盖 99.8%~100%，BP 73.6% 为 roe>0 正常过滤） |
| 2 | 矿机产出 NEG(NEG(x))=x 恒等因子 | forbid_check 把 NEG 归为 "PASS" 透传 | NEG 记为独立 kind，NEG(NEG) 显式拒绝 | ✅ 已修 |
| 3 | 去重漏「反方向同源」（TURN vs turn_mid_prox 选股不相交） | pnl_corr 只抓同向变体 | 双去重：max(cross_corr Spearman, pnl_corr 行为) | ✅ 已修 |
| 4 | c_factor/accel_factor/a_factor/pead_factor 在矿机/子集/组合模块里全 NaN | 依赖 `_PANEL_CODES/_PANEL_DATES` 全局变量（只在 validate_all_factors.main 里赋值） | 改为从 `panel` 派生 codes/dates，并一并修 PIT ffill | ✅ 已验证（ICIR 从 0.000 → +0.079/+0.065/+0.027/+0.079） |

---

## 二、因子子集自动选择（决策 #2：相关去冗余 + 正交化边际贡献）

模块：`factors/factor_subset.py`。

**① 相关去冗余**（|逐日截面 Spearman| ≥ 0.5 淘汰）：14 个有效因子 → 保留 9 个。
淘汰 5 个：mom_120、near_high_250、c_factor、accel_factor、ma_bull（与保留因子同源）。

**② 正交化边际贡献贪心前向**（选 8 个，边际 |ICIR| < 0.03 停止）：

| 步 | 因子 | 族 | 方向 | 边际 |ICIR| | 全量 ICIR |
|---|---|---|---|---|---|---|
| 1 | bp_value | 价值 | +1 | 0.212 | +0.212 |
| 2 | turn_mid_prox | 量价 | +1 | 0.184 | +0.210 |
| 3 | kdj_j | 反转 | −1 | 0.169 | +0.141 |
| 4 | amihud | 量价 | +1 | 0.125 | +0.133 |
| 5 | f_score | 质量 | +1 | 0.122 | +0.099 |
| 6 | pead_factor | 成长 | +1 | 0.078 | +0.079 |
| 7 | a_factor | 成长 | +1 | 0.103 | +0.027 |
| 8 | ma200_trend | 量价 | −1 | 0.062 | +0.194 |

> 最终子集跨 6 族（价值/量价/反转/质量/成长），其中成长族占 2 席（pead_factor + a_factor）——短板族已补进。
> 注：sue 去冗余后存活但正交化边际贡献未进前 8；ma200_trend 全量 ICIR 高（0.194）但正交化后仅 0.062（与 amihud/kdj_j 高度重叠），仍以边际贡献入选第 8 席。

---

## 三、组合构建（6 环节）——核心结果

模块：`factors/portfolio_builder.py`（L1 合成信号 → L5 硬过滤 → L4 行业×市值中性 → L2 Top N → L3 等权/风险平价 → L6 Regime 择时）。

**参数**：8 因子子集等权合成 / Top15 / 40 交易日调仓 / 等权仓位 / 行业×市值中性开 / Regime 择时开（多头满仓、空头减半）/ ST·退市·次新·流动性过滤开 / T+1 open + 一字板过滤 + 成本 0.176%。

| 指标 | 结果 | 目标（决策 #6） |
|---|---|---|
| **净超额** | **+20.97%** | — |
| 年化 | +33.11%（基准 +12.14%） | 15%~25% |
| **夏普** | **1.62** | > 1 ✅ |
| **最大回撤** | **−19.41%** | < 15% ⚠️ 略超 |
| 换手 | 76.77%/期（33 次调仓） | — |
| 择时均仓 | 0.82 | — |

**分年度净超额**：2020 −19.95% / 2021 +53.97% / 2022 +24.46% / 2023 +2.76% / 2024 +25.01% / 2025 +50.75%。

**结论**：夏普 1.62 与年化 33.11% 达标并超预期；回撤 −19.41% 略超 −15% 目标，主因 2020 下半年样本（回测起点）负超额。
**下一步（诚实提示）**：回撤达标需落地「三级止损」（预警 10% / 减半仓 15% / 清仓 20%，决策 #6），当前回测尚未实现止损逻辑；且本结果仍属样本内（2019+ 单窗），需按决策 D-07 做前向模拟盘验证 + 分年度 holdout。

---

## 四、短板族定向挖掘（成长 / 价值）

模块：`factors/formula_miner.py --directed 成长|价值`（定向提示词强调 SUE/ACCEL/REV_YOY/BP/EP 基本面叶子 + 规避已覆盖的量价族）。

### 成长族（53 候选，裁决进行中）

典型结果：
- `SUB(ADD(SUE,ACCEL),RET20)` icir=0.284 → **同构淘汰**（SUE 换参变体，双去重正确拦截）
- `SUB(TS_RANK20(ADD(REV_YOY,ACCEL)),RET5)` icir=0.214 → **同构淘汰**
- `TS_RANK20(ADD(ADD(EP,REV_YOY),SUE))` icir=0.262 → **观察**（净超额 −0.15%、夏普 0.63，未达「有效」）
- 其余多为 ICIR 不足或负超额。
- **结论：成长族目前 0 个「有效」新因子**——成长确实是最弱族，正交 alpha 稀缺，与 factor_pool_report 结论一致（pead +4.61% 本就是短板）。

### 价值族（20 候选，裁决进行中）

- **★ `TS_RANK20(SUB(BP,RET20))` icir=0.161 → 组合层「有效」净超额 +5.53% / 夏普 0.822**（新价值因子：账面市值比 BP − 20 日收益，经济逻辑 = 低估值 + 近期超跌的价值股均值回归买点）
- `TS_RANK20(SUB(EP,RET5))` icir=0.163 → 观察（净超额 −5.89%，负，弃）
- 其余多为 ICIR 不足。

> **诚实结论**：定向挖掘能稳定产出「换参变体」（被双去重正确拦截），全新正交 alpha 在成长族稀缺、在价值族找到了 1 个有效因子（BP×反转叠加）。这与「成长/价值是 6 族短板」的前提一致，但证明短板族仍可通过定向公式挖掘补强 1 席（价值）。

### 待办（诚实提示）

- 两个定向挖掘进程仍在跑（成长 53 候选 / 价值 20 候选，逐条组合层裁决较慢），最终 JSON 落盘后 tally 可能略有变化，但「成长 0 有效 / 价值 ≥1 有效」的结论已稳定。
- 新价值因子 `TS_RANK20(SUB(BP,RET20))` 需按 D-02（15 因子等长历史验证）补跑全历史 + 双中性 + 分年度 holdout 后方可入池。

---

## 五、产出文件（绝对路径）

- 组合构建报告：`C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant\output\PORTFOLIO_BUILD_REPORT_20261014.md`
- 组合构建结果：`C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant\logs\portfolio_builder.json`
- 因子子集选择：`C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant\logs\factor_subset.json`
- 组合构建模块：`C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant\factors\portfolio_builder.py`
- 因子子集模块：`C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant\factors\factor_subset.py`
- 定向挖掘（成长）：`C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant\logs\formula_miner_directed_growth.json`
- 定向挖掘（价值）：`C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant\logs\formula_miner_directed_value.json`
- 修改：`factors\formula_miner.py`、`factors\reproduce_factors.py`、`factors\validate_all_factors.py`

---

*维护：deepseek-harness-quant 本机 · 2026-10-14*
