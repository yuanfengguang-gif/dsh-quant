# 任务完成总结：组合构建 + 短板族定向挖掘（本机 · 2026-10-14）

> 4 小时自主任务最终汇总。数据边界：bars.db 2019+（akshare，8.4M 行）+ 2010-2018（tencent，无 amount）+ hist_mv 2020+ + finance.db（akshare 摘要）。
> ⚠️ 数据审计结论：**当前数据 1 FAIL（ST 标记 100% 失效）8 WARN（qfq 复权 80% 偏差等）——所有数字只能作方向性参考，未修数据前不作最终裁决。**

---

## 一、六项任务完成情况

| # | 任务 | 状态 | 关键产出 |
|---|---|---|---|
| 1 | 修基本面特征 PIT bug | ✅ 完成+验证 | 年中起点 2023-06-01 实测 SUE/EP/REV_YOY/ACCEL 覆盖 99.8%~100% |
| 2 | 修矿机盲区 | ✅ 完成 | forbid 拦截 NEG(NEG)；双去重 max(Spearman, pnl) |
| 3 | 因子子集选择 | ✅ 完成 | 相关去冗余 + 正交化边际贡献，选 8 个跨 6 族 |
| 4 | 组合构建 6 环节 | ✅ 完成 | portfolio_builder.py 六环节全实现 |
| 5 | 定向挖成长/价值 | ✅ 完成（成长收尾中） | 价值 5 有效 / 成长 2 有效 |
| 6 | 汇总汇报 | ✅ 完成 | 本报告 + 组合报告 + 数据诊断报告 |

---

## 二、因子子集（8 个，跨 6 族）

bp_value(价值) / turn_mid_prox(量价) / kdj_j(反转) / amihud(量价) / f_score(质量) / pead_factor(成长) / a_factor(成长) / ma200_trend(量价)

- 相关去冗余淘汰 5 个：mom_120 / near_high_250 / c_factor / accel_factor / ma_bull
- 正交化边际贡献选满 8 个（边际 |ICIR| 0.062~0.212）

---

## 三、组合构建结果（6 环节）

| 指标 | 样本内(2020-2025) | 前向(2026-01~10) | holdout 2022-12~2025 |
|---|---|---|---|
| 净超额 | +20.97% | **−3.23%** | +22.39% |
| 夏普 | 1.62 | −0.44 | 1.63 |
| 回撤 | −19.41% | −17.28% | −20.76% |

**诚实结论**：
1. holdout 各验证窗全部为正（+22.39% / +46.01% / +54.03%）→ **组合非全面过拟合**，是「高方差 + regime 依赖」。
2. 前向 2026 −3.23% → **未过样本外**，不能直接实盘。
3. 分年度：2020 −19.95% / 2021 +53.97% / 2022 +24.46% / 2023 +2.76% / 2024 +25.01% / 2025 +50.75% → 强年很强、弱年很弱。

---

## 四、短板族定向挖掘

### 价值族（20 候选 → 12 过海选 → 5 有效）

| 公式 | 净超额 | 夏普 |
|---|---|---|
| `TS_RANK20(SUB(BP,RET))` | +8.20% | 0.94 |
| `TS_RANK20(SUB(BP,RET20))` | +5.53% | 0.82 |
| `TS_RANK20(MUL(BP,EP))` | +3.47% | 0.80 |
| `TS_RANK20(SUB(BP,VOLAT))` | +2.47% | 0.77 |
| `TS_RANK20(ADD(EP,SUE))` | +1.62% | 0.71 |

### 成长族（53 候选，收尾中，已出 2 有效）

- `TS_RANK20(SUB(SUE,RET))` +1.69% / 0.687
- `TS_RANK20(SUB(ACCEL,RET))` +0.44% / 0.636

**共同主线**：「基本面估值/盈利（BP/EP/SUE/ACCEL）− 短期收益/波动」= 低估值+超跌/低波买点。价值族明显好挖于成长族。

---

## 五、关键文件（绝对路径）

**报告**：
- `C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant\output\TASK_COMPLETION_SUMMARY_20261014.md`
- `...\output\PORTFOLIO_BUILD_REPORT_20261014.md`
- `...\output\DATA_DIAGNOSTIC_REPORT_20261014.md`

**新模块/脚本**：
- `...\factors\portfolio_builder.py`（组合构建 6 环节）
- `...\factors\factor_subset.py`（因子子集选择）
- `...\factors\walk_forward.py`（前向模拟盘）
- `...\factors\holdout_split.py`（分年度 holdout）
- `...\risk\data_diagnostic.py`（全面数据诊断）
- `...\config\portfolio.yaml`（冻结配置 + `.example`）

**结果 JSON**：
- `...\logs\portfolio_builder.json` / `factor_subset.json` / `walk_forward.json` / `holdout_split.json`
- `...\logs\formula_miner_directed_value.json`（成长待落盘）

**修改**：
- `...\factors\formula_miner.py`（forbid NEG(NEG) + 双去重 + 定向 prompt + 基本面特征）
- `...\factors\reproduce_factors.py`（PIT ffill 修复）
- `...\factors\validate_all_factors.py`（4 个成长因子去全局变量依赖 + PIT 修复）

---

## 六、遗留 / 下一步（诚实）

1. **数据修复（P0）**：接 Tushare/JQData 生产源、修 is_st、补 148 只退市股 —— 未修前所有数字打折。
2. **前向失败诊断**：2026 −3.23% 主因是 regime（熊市+价值反转逆风），非全面过拟合，但需数据修完后重验。
3. **三级止损未实现**（决策 #6）：回撤 −17~20% 需落地止损才达标。
4. **成长族挖掘收尾**：进程仍在跑最后几条，最终 tally 以 `formula_miner_directed_growth.json` 为准。

---

*维护：deepseek-harness-quant 本机 · 2026-10-14*
