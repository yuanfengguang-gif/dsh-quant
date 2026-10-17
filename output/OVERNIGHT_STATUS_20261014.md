# 通宵任务状态报告（2026-10-14 早）

> 两项任务：(1) 7 项目因子挖掘模型选型；(2) 补完本机量化管线。

---

## 任务一：7 项目因子挖掘模型选型 ✅ 完成

**结论报告**：`C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant\output\factor_mining_model_comparison_20261014.md`

### 一句话结论
**没有唯一完美模型，最优是组合**。推荐：
- **生成层**：alpha-foundry 的「强类型 CFG + SemKind forbid 表」（从源头杜绝 35% 非法公式 + 同构因子）
- **搜索层**：gplearn 的「Warm Start GP」（0% 非法公式 + 从已验证因子起变异）
- **去重/入池**：alpha-foundry 的「行为正交池」+ money-agent 的「正交化边际 IC」
- **验证链**：保留我们的组合层 T+1 五步（这是我们的优势，7 个项目里多数都缺）

### 关键诚实发现
1. **我们已领先原版 AlphaGPT**：imbue-bit/AlphaGPT 主流程是 Solana meme（非 A 股），A 股只有单文件 times.py（单 ETF 时序，无截面），且原版无 benchmark、无去重、无组合层验证。我们的「截面化 + 去重 + 验证链」是自研扩展。
2. **License 红线**：只有 MIT/BSD 能抄（alpha-foundry、Qlib、RD-Agent、gplearn、alpha-mining-system）；alphaminingv2、money-agent 无 license 只能借鉴思路。
3. **最值钱的可抄模块**（按价值）：alpha-foundry 强类型 CFG + 行为正交池 + 4 道验证门；gplearn Warm Start GP 四招；RD-Agent 因子库累积闭环。

---

## 任务二：本机量化管线补完

### ✅ 已完成
1. **深验证（验收链后三步）**：`output\deep_validation_conclusion_20261014.md`
   - 真 alpha（双中性后 ICIR 改善）：amihud、f_score、bp_value、turn_mid_prox
   - 伪 alpha（截面靠行业/市值暴露）：sue（双中性后 ICIR +0.093→+0.004）
   - 方向性 alpha（截面弱组合层强）：mom_120、ma200_trend、near_high_250
   - Brinson 归因：7/8 因子 alpha 来自「行业内选股」而非「行业配置」
2. **验收工具拆分**：`validation\quality_exposure_check.py` + `quality_brinson_industry.py` + `quality_decay_check.py`（对齐主系统命名）
3. **因子池资产归档**：`output\factor_pool_report_20261013.md`（36 因子→15 有效）
4. **公式矿机**：`factors\formula_miner.py`（公式语言+StackVM+去重+组合层），去重闸门 bug 已修

### ✅ LLM 第 2 轮（已完成）
**31 候选 → 10 过海选 ICIR → 2 过组合层**（转化率 6.5%，符合 8% 标定）：
- `DECAY(NEG(DIV(RET5,VOLAT)))` 净超额 +1.18% 夏普 0.63
- `DECAY(NEG(DIV(RET20,VOLAT)))` 净超额 +1.87% 夏普 0.65
（都是「波动率调整的反转」同族，偏弱，需查与 reversal 相关性；远不如 amihud +20.59%）

### ⚠️ 未完成（诚实标注）

**1. 数据补拉 —— 大部分已推进（2/3 已在后台拉取）**
- ⚠️ **2010-2018 历史 K 线**：`data\fetch_bars_history_tencent.py`（腾讯 K 线）已在后台拉（pwsh-76，断点续传）。**实测发现三个数据口径问题（重要）**：① volume 单位 = 手（腾讯）vs 股（akshare 2019+）→ 差 100 倍，量价因子（vol_ratio/amihud）会断崖；② 腾讯 qfq 是「等差」口径、akshare 是「比例」口径 → close 在 2019-01 边界有 ~13% 跳变（000001.SZ 实测 6.152→6.99）；③ 无成交额。**结论：该数据只能用于「2010-2018 独立回测」，不能与 2019+ 无缝拼接**；要无缝拼接需改用「不复权 + 新浪比例复权因子」两步（§1.6）或等 baostock 冷却。
- ✅ **融资融券**：`data\fetch_rzrq_em.py`（东财 datacenter `RPTA_WEB_RZRQ_GGMX`，从搜索结果重建 API，绕开了 raw.githubusercontent 不可达）已建好并在后台拉 5561 只（pwsh-77，1s 限流，断点续传）。
- ❌ **一致预期（同花顺）**：是「当前快照」非历史序列，回测价值低，暂缓。

**2. 决策链接线（L0 红绿灯 + L2 Pitch + L1 因子池 + 执行）—— 代码完整，已提供一键运行**

✅ 结论：决策链代码**完整**（无需从零搭建），三层都在：
- **L0 择时**：`data/traffic_light.py` → output/dynamic_regime.json（仓位档）
- **L1 机会池**：`factors/opportunities/scan.py --pitch` → logs/opp_pool_*.json
- **L2 Pitch**：`factors/opportunities/pitch_v2.py` → logs/pitch_deck_*.json
- **L1 信号**：`factors/combo_daily_signal.py --topn 20` → output/daily_signal.json
- **展示**：deck_server.py serves 这些 JSON 到前端

✅ 新增：`scripts/run_decision_chain.py` —— 把 L0→L1→L2→信号 串成一条命令（`python scripts/run_decision_chain.py`）。

⚠️ 剩余缺口是**操作性的、非代码**：① 数据（正在补拉）；② Windows 计划任务（主系统 LWQuant-* 5 个，需在计划任务里设置，我无法代劳）。

---

## 建议下一步（需用户决策）
1. 数据补拉：先 re-fetch 完整 a-stock-data SKILL.md 拿两融代码 + 等 baostock 冷却后拉 2010-2018。或放弃（价值评估：两融高价值、一致预期低价值、历史 K 线高价值但被限流）。
2. 决策链：需要明确「接线」的目标形态（是否要完整复刻主系统 L0→L2→L1→执行，还是先做一个最小可用的「L1 因子池 → 机会池 → 今日买入指令」链路）。
3. 因子挖掘升级：按对比报告的 Phase 1（抄 alpha-foundry 强类型 CFG）开始升级 formula_miner。
