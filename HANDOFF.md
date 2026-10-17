# 交接文档（HANDOFF）

> **给完全没有上下文的新会话读这里**：快速了解「我们在做什么、做到哪了、卡在哪、下一步、别踩哪些坑」。
> 详细决策/待办见 `CORE_ISSUE_TRACKER.md`；项目定位说明见 `PROJECT_BRIEF.md`。
> **最后更新：2026-10-16**（上一版已备份为 `HANDOFF_legacy_backup_20261016.md`）

---

## 〇、30 秒速览（本轮发生了什么）

| 项 | 内容 |
|---|---|
| **本轮任务** | 给项目换一套**可靠 + 便宜**的数据底座（原免费源有 5 个 P0 缺陷） |
| **评估结论** | **通联 → 否决**（全量 ≈ 17 万元）；**通达信 → 采纳**（全量 ≈ 16-22 元） |
| **核心动作** | **`bars.db` 原地切换为通达信数据**（1,570 万行，2000-2026）—— 让全项目 487 处引用**零代码改动**生效 |
| **当前状态** | 数据切换 ✅ 完成 + 下游 `load_panel` 已验证；每日增量自动化 ⚠️ 刚修完待最终验证 |
| **下一步** | 见第五节（P0-1 验证计划任务 → P0-2 下游回归 → P1 补字段/写质量报告） |

---

## 一、我们在做什么项目

**个人低频量化交易系统**（开源快照 `deepseek-harness-quant`，本机）。

- 目标：**确定性盈利**（高胜率 + 低回撤 + 稳定复利）+ **执行自动化** + **预警复盘**。
- 定位：个人、低频（40 交易日调仓）、不追暴利追稳定。与私有主系统（DSHQuant，**不在这台机器**）定位相似，但更强调执行自动化 + 预警。
- 关键口径（用户拍板）：持仓 15 只 / 因子子集 6-8 个 / 季度常规+事件触发调仓（人工确认）/ 择时硬控仓位 / 三级止损 / 目标 夏普>1·回撤<15%·年化 15-25%。
- **架构（8 层）**：数据 → 因子 → 组合构建 → 风控 → 执行 → 回溯 → 前向模拟盘 → 监控预警。骨架已全部建好。

### 铁律（不可违反，见 `AGENTS.md`）
1. **全部模块动态化**：禁止把数据/列表/配置硬编码进代码（用配置/数据文件 + API）。
2. **数据边界**：第三方行情**禁止再分发**；只开源代码 + 获取脚本 + 合成演示数据。
3. **换手率（turn）2019 年前缺失 → 2019 前换手类结论一律作废**。
4. **回测口径**：T+1 开盘执行、一字板过滤、成本模型 —— 见 skill `backtest-acceptance`。

---

## 二、数据现状（本轮已大改，先读这里）

### 2.1 主行情库：`data/cache/bars.db` —— **已切换为通达信数据**

| 项 | 切换前（旧） | **切换后（现在）** |
|---|---|---|
| `daily_bar` 行数 | 1,342 万 | **1,570 万** |
| 日期范围 | 2010-01-04 ~ 2026-10-15 | **2000-04-03 ~ 2026-10-16** |
| 年份数 | 17 | **27** |
| 复权口径 | 以爬取日为基准（**不可复现**，F-6） | 独立因子（**可复现**） |
| volume 单位 | 2010-2018 异常 | **统一（股）** |
| `is_st` | 2020+ 精确 / 2020前名称近似 | 同（另有通达信 `IsSTGP` 可用） |
| `bar_meta` | — | 5,608 行（已重建） |
| `is_st=1` | — | 658,812 行 |

**为什么用「原地切换」而不是新建库**：全项目有 **487 处**数据库引用（165 处走 `DailyCache` + **322 处硬编码 `sqlite3.connect("...bars.db")`**）。改配置只能覆盖 165 处；**原地替换 `bars.db` 才能让全部 487 处零改动生效**（= 零 BUG 风险）。

**回滚方式**（在新库执行）：
```sql
ALTER TABLE daily_bar RENAME TO daily_bar_tdx_bak;
ALTER TABLE daily_bar_legacy RENAME TO daily_bar;
ALTER TABLE bar_meta RENAME TO bar_meta_bak;
ALTER TABLE bar_meta_prev RENAME TO bar_meta;
```
备份文件：`data/cache/bars_legacy_backup_20261016.db`（2713 MB）

### 2.2 其他数据资产

| 库/表 | 内容 | 状态 |
|---|---|---|
| `data/cache/bars_tdx.db` | 通达信原始导入（unadj 1,638万 + `adj_factor` 1,848万 + `stock_info` 6,035） | ✅ |
| `data/cache/tdx_meta.db` | **通达信元数据**（见 3.4） | ✅ 本轮新增 |
| `data/cache/finance_csmar.db` | **CSMAR 财务**（`fin_core` 年度 95,435 / `fin_core_q` 季度 325,903） | ✅ 本轮新增 |
| `data/cache/datayes_basic.db` | 通联基础（`sec_delisted` 16,487 / `sec_listed` 30,164） | ✅ 本轮新增 |
| `data/cache/finance.db` | 老财报（akshare 摘要，319K 行，**无披露日**） | 仍在被部分脚本引用 |
| `data/cache/hist_mv.db` / `stock_basic.db` / `valuation.db` | 月频市值 / 基础信息 / 估值 | 仍在被引用 |

### 2.3 旧数据缺陷修复进度

| 编号 | 缺陷 | 现状 |
|---|---|---|
| F-1 | `is_st` 全 0 | 🟡 部分修（valuation.db 2020+ / 名称近似 2020前；通达信 `IsSTGP` 可补当前） |
| F-2 | 退市股缺失 | 🟡 已拿退市清单（374 只 A 股 + 退市日），但**无退市股行情** → 用清单过滤 + 报告披露 |
| F-5 | 无公告日 | ✅ **CSMAR `publish_date` + 通达信 `announce_time` 均可用** |
| F-6 | qfq 基准漂移 | ✅ **修复**（独立复权因子，可复现） |
| — | volume 单位异常 | ✅ **修复**（通达信统一单位） |

---

## 三、本轮已完成的工作

### 3.1 数据源评估：通联 vs 通达信

| 维度 | 通联 DataYes | 通达信 |
|---|---|---|
| 计费 | 按行（**11.16 万点/行**，100元=1000M点） | 积分制（**1 万积分 = 20 元**） |
| 全量行情 2010-2026 | **≈ 17 万元** | **≈ 9.2 元** |
| 全量（行情+财务+基础） | ≈ 17 万元 | **≈ 16-22 元** |
| 财务披露日 | 有 | 有（`announce_time`） |
| ST / 退市标记 | 需另购 | **自带**（`IsSTGP` / `IsQuitGP`） |
| 指数成分 | 需另购 | **自带** |
| 退市股行情 | 有（贵） | **没有** |
| 另类数据（分析师/舆情） | 有 | **没有** |

**结论：通达信性价比完胜（约 7,000-9,000 倍），采纳。**

### 3.2 ★ `bars.db` 原地切换（核心里程碑）

- 脚本：`data/switch_to_tdx_bars.py`（可重复执行，自带备份检查）
- 增量补齐：`data/fix_bars_increment.py`（unadj → ×复权因子 → qfq）
- **下游实测通过**：
```
load_panel('data/cache/bars.db', start='2026-10-01')
→ ✅ 38,975 行，列 = open/high/low/close/volume/amount/turn/pct_chg/is_st
→ 日期 2026-10-08 ~ 2026-10-16，耗时 4.6s
```

### 3.3 通达信 API（TdxAiData）接入

- **安装位置**：`C:\Users\Administrator\.dsh\skills\tdx-aidata\`（官方 7 件套）
- **环境体检 4 项全通过**：引擎 v1.2.2 ✅ / Token ✅ / DLL 4/4 ✅ / 连通 ✅
- **已配好的 Token**：写在 `TdxAiData.ini` 的 `[Token]` 节（技能目录 + `lib/` + site-packages **三处同步**）

### 3.4 ★ 通达信 API 能力（三大惊喜）

| 惊喜 | 接口 | 价值 |
|---|---|---|
| **1** | `get_stock_info` → **`IsSTGP`（是否ST）+ `IsQuitGP`（是否退市）** | 直接解决 F-1 |
| **2** | `get_financial_data` → **`announce_time`（公告日）** + FN 系列 500+ 字段（1999 起） | 根治 F-5 前视偏差 |
| **3** | `get_divid_factors`（除权明细）+ `get_zzgz_stocklist`（指数成分）+ `get_sector_list`（板块） | 补基准/分类缺口 |

**其他可用**：`get_market_data`（日线）、`get_minute_data`、`get_call_auction`（集合竞价）、`get_gb_info`（股本）、`get_more_info`（Beta/PE/市值/股息率）、`get_trading_dates`

### 3.5 已下载的元数据（`data/cache/tdx_meta.db`）

| 表 | 行数 | 内容 |
|---|---|---|
| `universe` | 5,581 | 全市场股票（沪+深+北）+ **名称** |
| `stock_info_tdx` | 5,581 × 63 列 | **IsSTGP / IsQuitGP** / 指数归属 / J_* 财务快照 |
| `index_member` | 2,000 | 上证50/沪深300/中证500/中证1000/创业板指/科创50 |
| `sector` / `sector_member` | 560 / 78,535 | 板块 + 成分股 |
| `stock_info_snapshot` | 每日追加 | **历史 ST 序列（从今天起积累）** |

**关键数据**：`IsSTGP=1` **201 只**、`BelongHS300` 300 只、`BelongRZRQ` 3,885 只

### 3.6 每日增量 + 断点追赶（已配计划任务）

- **脚本**：`data/tdx_daily_update.py`（幂等 + **漏跑自动补齐**）
  - 逻辑：读库 `MAX(date)` → 算缺口 `(MAX, 最新交易日]` → **一次补齐所有缺口**
  - 每次落 `stock_info_snapshot`（**积累历史 ST 序列**）；写 `update_log` 表（可审计）
  - 用法：`python data/tdx_daily_update.py` / `--dry-run` / `--init 2010-01-01`
- **计划任务**：`DSHQuant-TDX-DailyUpdate`（每天 **17:30**，`StartWhenAvailable`）
- **包装脚本**：`data/run_daily_update.ps1`（**两步串联**）
  ```
  步骤1  tdx_daily_update.py    → 拉增量（写 bars_tdx.db 的 unadj）
  步骤2  fix_bars_increment.py  → unadj 转 qfq → 合并进 bars.db
  ```
- 日志：`logs/tdx_daily_update_YYYYMMDD.log`（保留 60 天）

### 3.7 CSMAR（国泰安）财务数据

- **源**：`D:\BaiduNetdiskDownload\A股上市公司财务数据（1990-2026.3.31）`
  - `年度最终合并.csv`（608 MB，**949 列**）、`季度合并.csv`（1.95 GB，**835 列**）
- **已导入** `finance_csmar.db`：`fin_core`（年度 **95,435** × 41 列）、`fin_core_q`（季度 **325,903** × 37 列）
- **关键**：保留 **`publish_date`（年报公布日期）** → PIT 可用
- **验证结果**：
  - ✅ **公开数据点核对**：贵州茅台 / 平安银行 / 万科A 的 2023 归母净利/营收 **偏差 0.00%**
  - ✅ 资产负债表恒等式 **99.8%** 通过

### 3.8 退市股清单（免费）

- 来源：通联 `getSecID listStatusCD=DE`（**priceAmountCent=0，免费**）
- 共 **16,487 条**（含全球），其中**沪深A股 374 只**、北交所 5 只，含 **`delist_date`（退市日）**
- **结论：通达信不含退市股行情**（374 只里只有 25 只恰好有）

---

## 四、当前卡在哪里

### 🔴 卡点 1：每日任务链路「刚修完，未最终验证」
`run_daily_update.ps1` 先后踩了两个坑（第六节 #2/#3），**刚加 BOM 并通过语法校验，完整跑通验证还没做**。
**验证命令**：
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant\data\run_daily_update.ps1"
```
**期望**：步骤1「已是最新（缺口为空）」+ 步骤2「无增量，退出」，两步退出码均 0。

### 🟡 卡点 2：数据源切换的下游回归未做
487 处引用中**只验证了 `load_panel` 一个**。需跑关键下游脚本确认可用（见 P0-2）。

### 🟡 卡点 3：`source` 字段与单位归一函数
新库全部 `source='tdx'`，而 `data/cache.py` 的 `normalize_units()` **按 source 判断单位**（`tushare`→×1000/×100）。因通达信写入时**已换算成标准单位（元/股）**，所以不会被二次换算 ✅。**但若将来混入其他源，必须检查这个函数。**

### 🟡 卡点 4：复权因子有截止日
通达信复权因子文件只到 **2026-06**。增量日期（2026-07 之后）无因子，`fix_bars_increment.py` 用「**该股最新一日的因子**」兜底（前复权以最新日为 1.0，属合理近似）。**但遇除权事件会失真** —— 需留意。

### 🟡 卡点 5：CSMAR 949 列全字段未导入
只导入了 41 个核心字段。**论文因子（劳动力/另类类）需要更多字段**（如应付职工薪酬、股东户数、审计意见）。

### 🟡 卡点 6：`bars.db` 里有历史遗留表
`daily_bar_legacy`、`bar_meta_prev`、`_wprobe` 仍在库中（占用空间但无害）。确认稳定后可清理。

---

## 五、下一步计划（按优先级）

### P0-1 验证每日任务链路
跑 `run_daily_update.ps1`，确认两步都成功（见卡点 1）。

### P0-2 下游回归验证（**关键**）
随机抽 3-5 个关键下游脚本跑一遍，确认新旧数据**方向一致**（不要求数值完全相同，因复权基准不同）：
| 脚本 | 验证点 |
|---|---|
| `factors/import_qf_pool.py` → `load_panel` | ✅ 已通过 |
| `factors/combo_portfolio.py` | 组合回测能否跑通 |
| `factors/formula_miner.py` | 因子挖掘面板加载 |
| `factors/portfolio_builder.py` | 组合构建（读 stock_basic/hist_mv） |
| `risk/stop_monitor.py`、`risk/position_stop_check.py` | 实盘监控读最新价 |
| `deck/live_api.py` | Web 门户数据源版本 |
**特别检查**：`is_st` 过滤、`turn` 可用性、`adjust='qfq'` 过滤、单位一致性。

### P0-3 用通达信补 2020 年前的 is_st
`valuation.db` 的 `isST` 只覆盖 2020-06 之后；2020 年前用「名称含 ST」近似（**有前视偏差**）。
- 可选：通达信 API **从今天起逐日快照**（`stock_info_snapshot` 已在做）
- 历史段只能接受近似 + **在报告里明确披露**

### P1 导入 CSMAR 949 列全字段
用 parquet 存储（比 SQLite 高效），供未来因子挖掘。

### P1 写《数据底座质量报告》
整合已有验证结果，明确披露：
- 幸存者偏差幅度（2010 年 **~16.5%**、2025 年 ~0.9%）
- 2020 年前 is_st 近似偏差
- 复权因子截止日的近似处理
- volume 单位统一前后的影响

### P2 因子验证重启
- **论文因子**：`logs/paper_factors_generated.json`（18 个可计算公式 + 32 个另类）
- **通联因子公式**：`output/DATAYES_FACTOR_FORMULAS_20261015.md`
- **待验证总表**：`output/FACTOR_VERIFICATION_BACKLOG_20261015.md`（502 个）
- 验证链见 skill `factor-mining-workflow` / `alpha-gpt-factor-mining`
- **注意**：组合层 T+1 是**唯一仲裁者**

---

## 六、踩过的坑（**绝对不要再踩**）

### 坑 #1 ★★★ ini 文件绝不能带 UTF-8 BOM
- **现象**：TdxAiData 配置全对，但所有接口报 `[错误] Connection failed`
- **根因**：`TdxAiData.ini` 带 UTF-8 BOM（`EF BB BF`）→ C++ DLL 把 BOM 当 section 名的一部分 → 读不到 `[TcHqHost]`
- **修复**：用**无 BOM UTF-8** 重写 ini
- **检查**：`[System.IO.File]::ReadAllBytes($p)[0..2]` 是否为 `239,187,191`

### 坑 #2 ★★★ .ps1 文件必须有 BOM（Windows PowerShell 5.1）
- **现象**：PS1 里 Python 报 `can't open file '...\量化交易系统\...'`，日志全乱码
- **根因**：**PS 5.1 读取无 BOM 的 .ps1 时默认按 ANSI/GBK** → 中文路径乱码
- **修复**：存为 **UTF-8 with BOM**
```powershell
$enc = New-Object System.Text.UTF8Encoding($true)   # $true = 带 BOM
[System.IO.File]::WriteAllText($path, $txt, $enc)
```
- **环境事实**：本机 PowerShell 是 **5.1**（不是 pwsh 7）

### 坑 #3 ★★ PowerShell 脚本里不能写 Python docstring
- **现象**：`.ps1` 解析报 `Unexpected token`
- **根因**：开头写了 `"""..."""`（Python 风格）→ PS 不支持
- **修复**：全部用 `#` 注释

### 坑 #4 ★★ 通达信 API 调用约定（硬规则）
| 项 | 正确 | 错误 |
|---|---|---|
| 证券代码 | **带后缀** `600519.SH` | `600519` → `Invalid stock code` |
| K线周期 | **`1d`** | `day` → `period 必须是合法 K 线周期` |
| 全市场列表 | **`get_stock_list(5, 0)`** | `(0,0)` 只返回沪市 1,702 只 |
| 财务数据 | 必须传 **`field_list`** | 不传 → `field_list 不能为空` |

### 坑 #5 ★★ 切换 `bars.db` 时别只搬 qfq 行
- **现象**：切换后 `bars.db` 缺最新 5 天
- **根因**：只搬 `adjust='qfq'`，而每日增量写的是 `adjust='unadj'`
- **修复**：`data/fix_bars_increment.py` 补搬（unadj → ×因子 → qfq）

### 坑 #6 ★★ 复权因子有截止日，增量日期需兜底
- 因子文件到 2026-06；增量日期无因子 → **必须用「该股最新一日因子」兜底**
- **注意**：`ffill` 在「只有增量行」的批内**无效**（无历史值作源），必须从全量因子表取「每股最新值」

### 坑 #7 ★ 计费模型别靠小额流水猜
- 曾误判通达信为「1 积分/进程」（因为小额记录都是 1）
- **实测**：按**数据量**计费（1,000 只 × 1 年 = **64 积分**；全市场基础信息 = **349 积分**）
- **教训**：测计费要用**不同数量级**的批次

### 坑 #8 ★ 不要用「全量枚举」验证额度
- 曾用 `getSecID listStatusCD=L`（30,164 行）+ `getMktEqud tradeDate`（5,652 行）当"额度检查" → **烧掉刚充值的余额**
- **正确做法**：用**最小调用**（1 只股票 1 天）验证连通性

### 坑 #9 ★ PowerShell 嵌套引号
- `python -c "...含引号/SQL..."` 在 pwsh 里极易崩
- **正确做法**：写成 `.py` 文件再跑（本仓库惯例）

### 坑 #10 ★ 中文路径 + GBK 控制台 → 输出乱码但数据无误
- 看到 `閫氳揪淇` 这类乱码时，**先判断是显示问题还是数据问题**
- 脚本里统一 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`

### 坑 #11 ★ 通达信**取不到**的数据（别浪费时间）
| 数据 | 结论 |
|---|---|
| 退市股行情 | ❌ 测 5 只全部返回空 |
| 历史指数成分 | ❌ 接口无日期参数，只有当前 |
| 历史 ST 序列 | ❌ 只有当前状态（需逐日快照积累） |
| 另类数据（分析师/北向/舆情） | ❌ 完全没有 |

### 坑 #12 ★ 会话过长会导致 agent 反复「卡住不回复」
- **本轮实测**：会话极长后，agent 在「工具调用 → 生成回复」间反复中断
- **应对**：**开新会话**；每轮**先启动后台任务 → 立即回复正文**；单轮**只调 1 个工具**
- **不要**在未诊断的情况下断言「是 DSH 的问题」（版本 2.0.17，未确认根因）

---

## 七、关键文件与路径速查

### 数据
| 文件 | 说明 |
|---|---|
| `data/cache/bars.db` | **主行情库（已切换为通达信）**，1,570 万行，2000-2026 |
| `data/cache/bars.db` → `daily_bar_legacy` | 老数据表（**回滚用**） |
| `data/cache/bars_legacy_backup_20261016.db` | 老库完整备份（2713 MB） |
| `data/cache/bars_tdx.db` | 通达信原始库（unadj + adj_factor + stock_info） |
| `data/cache/tdx_meta.db` | 通达信元数据（ST/退市/指数/板块/每日快照） |
| `data/cache/finance_csmar.db` | CSMAR 财务（fin_core / fin_core_q） |
| `data/cache/datayes_basic.db` | 通联基础（退市/上市清单） |

### 脚本（本轮新增）
| 文件 | 作用 |
|---|---|
| `data/tdx_daily_update.py` | **每日增量（幂等 + 追赶）** |
| `data/fix_bars_increment.py` | unadj → qfq → 合并进 bars.db |
| `data/run_daily_update.ps1` | 计划任务包装（**必须带 BOM**） |
| `data/switch_to_tdx_bars.py` | bars.db 原地切换（可重复执行） |
| `data/import_tdx.py` | 通达信文件导入（probe/daily_zip/factor/apply_qfq） |
| `data/fetch_tdx_meta.py` | 元数据下载 |
| `data/import_csmar.py` | CSMAR 财务导入 |
| `data/build_stock_info.py` | 股票信息汇总（含退市日） |
| `data/patch_is_st.py` | is_st 补全 |
| `risk/impact_analysis.py` | 数据源切换影响面分析 |

### 报告
| 文件 | 内容 |
|---|---|
| `output/TDX_AIDATA_API_SURVEY_20261015.md` | 通达信 API 能力盘点 |
| `output/TDX_DATA_VERIFICATION_20261015.md` | 通达信数据验证 |
| `output/CSMAR_FINANCE_VERIFICATION_PLAN_20261015.md` | 财务数据五重验证方案 |
| `output/DATAYES_FACTOR_FORMULAS_20261015.md` | 通联因子公式 |
| `output/FACTOR_VERIFICATION_BACKLOG_20261015.md` | 待验证因子总表（502 个） |

### 技能
| 路径 | 说明 |
|---|---|
| `C:\Users\Administrator\.dsh\skills\tdx-aidata\` | 通达信 API（7 件套 + 体检/盘点脚本） |
| skill `backtest-acceptance` | 回测口径铁律 |
| skill `factor-mining-workflow` | 因子挖掘工作流 |
| skill `alpha-gpt-factor-mining` | AlphaGPT 公式挖掘 |

---

## 八、环境事实（避免重复踩坑）

| 项 | 值 |
|---|---|
| 工作目录 | `C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant` |
| Python | **3.13.15**（pandas 3.0.6 / numpy 2.5.4） |
| PowerShell | **5.1**（不是 pwsh 7 → **注意 BOM 问题**） |
| 控制台编码 | GBK（中文易乱码，属显示问题） |
| 计划任务 | `DSHQuant-TDX-DailyUpdate`（每天 17:30） |
| 通达信 Token | 已写入 `TdxAiData.ini` 的 `[Token]` 节（三处同步） |
| 路径含空格 | `C:\Users\Administrator\ DSH 量化交易系统\`（**注意引号**） |
| DSH 版本 | 2.0.17（`dsh-plugin-desktop`） |

---

## 九、给新会话的第一句话建议

> 读 `HANDOFF.md`，然后从「第五节 P0-1」开始：先跑一次 `data/run_daily_update.ps1` 验证每日任务链路，再做 P0-2 的下游回归验证。

**不要做的事**：
- ❌ 不要重新下载通达信全量行情（**已有**，1,570 万行）
- ❌ 不要重新评估通联（**已否决**，17 万元）
- ❌ 不要盲目批量改那 487 处数据库引用（**已通过原地切换 `bars.db` 解决**）
- ❌ 不要在未诊断的情况下断言「是 DSH 的问题」

---

*文档生成：2026-10-16 · 上一版已备份为 `HANDOFF_legacy_backup_20261016.md`*
