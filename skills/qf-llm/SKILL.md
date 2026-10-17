---
name: qf-llm
description: 把 Karpathy autoresearch 的自主闭环复刻到量化因子挖掘。三件套——AI 不可改的固定评分标准（RankIC+ICIR+覆盖率+相关性加权）、AI 每轮可改的因子代码、人类可改的研究规程（program.md）——驱动 AI 因子研究员自主「生成候选→沙箱执行→打分→多样性门控入池/淘汰→写研究总结→下一轮站在上一轮肩膀上」。当用户要用 autoresearch 思路挖因子、搭 AI 因子研究员、无人值守自主迭代因子、或提到 QF-LLM/QFLAM 时使用。
whenToUse: 用户要求"用 autoresearch 思路挖因子 / 搭 AI 因子研究员 / 自主迭代因子挖掘 / QF-LLM / QFLAM"，或想让 AI 无人值守地生成→验证→入池因子。
metadata:
  source: 抖音视频《从autoresearch到AI因子挖掘》（作者小木之之；作者在视频中称该项目为 QFLAM，本 skill 按约定命名 QF-LLM）
  principle: karpathy/autoresearch —— modify → verify → keep/discard → repeat
  source_assets: 视频与转写见工作区 _QF-LLM-assets/（video.mp4 / transcript.txt）
  local_scripts: scripts/（orchestrator.py / scoring.py / sandbox.py）
---

# QF-LLM：autoresearch 式自主因子挖掘研究员

> 蒸馏自抖音视频《从autoresearch到AI因子挖掘》。一句话概括：**把 Karpathy autoresearch 的「三件套」搬进因子挖掘**——一个 AI 只能读不能改的**评分标准**、一份人类可改的**研究规程**、一段 AI 每轮可改的**因子代码**，让它在沙箱里自主「生成 → 验证 → 留/弃 → 总结 → 再来」。

## 零、autoresearch 原型（先懂它）

Karpathy 2023-06 的 [autoresearch](https://github.com/karpathy/autoresearch) 核心只有三个文件：

| 文件 | 作用 | AI 权限 |
|---|---|---|
| `prepare.py` | 准备数据 + 定义评分标准 | 只读，**不可改** |
| `train.py` | 完整训练代码（模型结构/超参） | **唯一可改** |
| `program.md` | 自然语言研究规程（研究什么、什么值得试、哪些别碰） | 只读不可改；**人类靠改它指挥 AI** |

闭环：AI 按 program.md 改 train.py → 跑 5 分钟训练 → 看验证分 → **变好 commit 保留 / 变差 revert 撤回**；每轮留档，错误永不摧毁已有成果。
实测：跑一晚 100+ 实验（loss 0.99→0.96）；跑两天 700+ 修改（20+ 有效）→ 迁移 GPT-2 提效 11%，只用 1 张 GPU。
**内核 = 给 AI 一个「可改对象 + 不可改评分 + 一份规程」，让它自主循环、越改越好。**

## 一、QF-LLM 三件套（复刻到因子挖掘）

| autoresearch | QF-LLM 因子版 | 本 skill 落地 |
|---|---|---|
| prepare.py（评分标准，AI 不可改） | 综合评分：RankIC + ICIR + 覆盖率 + 相关性 | `scripts/scoring.py` |
| train.py（AI 可改的代码） | 因子代码：输入全市场行情 → 输出每只股票得分 | AI 每轮生成（沙箱执行） |
| program.md（研究规程，人类可改） | 实验流程 + 已验证好因子 + 迭代方向 | `references/program.md.example` |

## 二、固定评分标准（scoring.py，AI 不可改）

综合分 = `w1·RankIC + w2·ICIR + w3·覆盖率 + w4·相关性惩罚`（默认 0.4 / 0.3 / 0.1 / -0.2，可调权重但**逻辑写死，AI 不能改**）。

- **RankIC**（排序准不准）：逐日截面 Spearman（= rank 后 Pearson）的均值。
- **ICIR**（排序稳不稳）：IC 均值 / IC 标准差。
- **覆盖率**（能不能覆盖足够多的股票）：非 NaN 占比。
- **相关性惩罚**：与池内每个已入池因子的截面相关绝对值最大值（越高越扣分）。

## 三、多样性门控（因子版独有，训练模型没有）

训练要「一个最强模型」，因子要「**很多彼此不同、各有用的信号**」。没有约束时 AI 会揪住一个有价值的方向反复钻，产出一堆高相关因子。

→ **硬门控（对齐工作区 factor-mining-workflow 去重闸门口径）**：每个因子入池前，与池内已有因子做截面相关性检查，三级判定——`>0.5` **淘汰**（同构，必杀）｜`0.3~0.5` **警示**（不入池，反馈「方向已覆盖」）｜`<0.3` **通过**入池。**即使 IC 很高，相关超线也丢弃**。

## 四、自研编排器（不用 IDE，直连 LLM API）

autoresearch 跑在 Cursor/Claude Code 里，对话历史会随轮数变长被冲淡、中断即丢失；而因子挖掘是**稀疏价值问题**，要试成千上万次。

→ QF-LLM **不用 IDE 管上下文**，自己写 `orchestrator.py` 直连 LLM API，每次调用独立：
- 每轮开头：把「研究规程 + 因子池 + 实验历史 + 研究记忆」拼成 prompt。
- 每轮结尾：AI 必须写一份**研究总结**（哪些有效/无效、下一步往哪走）。
- 下轮把总结读回来 → **每轮都站在上一轮肩膀上**。

## 五、沙箱（防数据泄漏 / 越权）

让 AI 自己写 Python 有风险（用未来函数、乱做 IO）。沙箱 `scripts/sandbox.py`：
- **禁止一切 IO**（open / 文件 / 网络 / 子进程；静态 AST 拦截 pandas/numpy 的 read_* / to_* 等）。
- **只允许白名单计算库**（numpy / pandas）+ 白名单内建函数。
- **超时杀进程**（默认 30s，subprocess 隔离，超时即 kill）。
- **跑完检查输出格式**（必须产出对齐行情索引的得分 Series）。

## 六、每轮完整流程（AI 因子研究员）

1. 读三样：**研究规程**（方向）→ **研究记忆**（做过啥/别踩坑）→ **因子池**（已有好因子）。
2. LLM 生成 N 个候选因子（Python 代码）。
3. 逐个进沙箱安全执行。
4. 打分：综合分不够 → 淘汰；够了 → 过**多样性门控**（与老因子太像也淘汰）。
5. 真正留下的进**因子池**。
6. AI 写**总结反馈**（这轮为何成/败，下轮少碰啥多做啥）。
7. 下轮读回这份总结 → 循环。

作者实测（视频自述）：**588 轮 → 236 个有效因子 → 50 个入池，淘汰率 >80%，DeepSeek API 成本 <1 元**。

## 七、落地对接本工作区

- **数据**：接 `factor-mining-workflow` 的 `research_engine.load_universe()`（parquet 面板，列 open/high/low/close/volume/amount/turn/pct_chg/is_st）；本 skill 脚本接受同样 schema 的 parquet/csv。
- **评分/裁决口径**：本 skill 的 `scoring.py` 是「海选段」快速评分；入池前仍需走 `factor-mining-workflow` P4-P6 与 `backtest-acceptance` 的组合层 T+1 裁决（ICIR 只是门票，组合层 T+1 才是裁决）。
- **生成器**：本 skill 用 LLM 直连；也可复用 `alpha-gpt-factor-mining` 的「特征+算子」公式语言作为候选表达。
- **API Key 唯一来源**：`C:\Users\Administrator\dsh-desktop\.env`（DeepSeek 等，见全局 AGENTS.md 规则）。

## 八、怎么跑

1. 写 `program.md`（研究规程 + 初始好因子 + 迭代方向），参考 `references/program.md.example`。
2. 确认 `.env` 里有 `DEEPSEEK_API_KEY`（唯一来源 `C:\Users\Administrator\dsh-desktop\.env`）。
3. 跑编排器：
   ```bash
   python scripts/orchestrator.py --data <行情面板.parquet> --program program.md --rounds 50 --per-round 10
   ```
4. 每轮产出落盘到 `runs/`：候选因子代码、评分、入池/淘汰记录、研究总结。

## 九、输出格式与变更记录

### 落盘字段（v2，2026-10-12 起）

- `pool.json`：入池因子数组，每项在评分字段（`rank_ic/ic_ir/ic_abs/ir_abs/direction/coverage/max_corr/total/pass_*`）之外，**新增 `code` 字段** = 该因子的完整 Python 代码（`def factor(panel)->pd.Series`）。
- `round_*.json`：`candidates` 每项同样**新增 `code` 字段**（含被淘汰的候选，便于后续复检/正交化）。
- 研究总结（`summary`）prompt **仍剥离 code**（只传评分），总结行为不变。

### 为什么新增 code

供下游决策系统（deepseek-harness-quant）的「因子池导入器」复用因子代码，在自有 bars.db 面板上重算 daily_scores（避免用快照信号导致数据不一致）。导入器属于下游系统，不在本 skill 内。

### 影响面（已评估，无破坏）

- `dashboard.py`：用 `.get()` 读取特定评分字段，自动忽略新增 `code`，看板不受影响。
- `scoring.py` / `sandbox.py`：未改动。
- 编排器 `build_gen_prompt`：只读 pool 的 `name/rank_ic/ic_ir`，不受影响。

### 变更记录 v3（2026-10-13）——前向标签改为 T+1 open-to-open

- `orchestrator.py` 的 `forward_returns()`：从「次日 close-to-close（`pct_chg.shift(-1)`，含收盘价前视）」改为「**t 信号 → t+1 开盘买入 → t+2 开盘卖出（open-to-open）+ 剔除 t+1 一字板涨停**」，与下游 deepseek-harness-quant 消费端 `factors/import_qf_pool.forward_returns` 完全同口径。
- 若面板缺 `open/high/low` 列，自动回退到旧口径（close-to-close），向后兼容。
- 动机：此前 qf-llm 自评 ICIR 系统虚高（r8_f0 自报 0.52，消费端 T+1 口径只剩 0.195），根源是标签含前视；改后 qf-llm 每轮自评即「可成交口径」，消除「生产者自嗨、消费者全毙」的目标函数错位。
- 影响面：`scoring.py` 只收 `forward_ret` 参数、不自己算标签，故无需改；`sandbox.py` 不涉及标签，无需改。
