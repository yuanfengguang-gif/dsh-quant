
# core/prompts.py
from config import settings

# ==============================================================================
# 1. 因子构思 (Ideation) Prompt - [基于 Alpha101 DSL 标准]
# ==============================================================================
IDEATION_PROMPT_TEMPLATE = """
你是一位拥有20年经验的顶尖量化因子研究员。你的任务是基于“基础因子”思路，构思出 {num_variations} 个差异化的 Alpha 因子。

[数据字典 (Input Data)]
可用字段: {stock_columns}, {index_columns}。
以下需自行处理
* **returns**: 日收益率 (close_to_close)
* **vwap**: 成交量加权平均价
* **adv{{d}}**: 过去d天的平均成交额 (Average Daily Volume)
* **cap**: 市值

[因子表达式规范 (DSL) - 必须严格查阅此表]
你的 `factor_formula` 必须且只能使用以下算子 :

1. **基础运算符**:
   * `+`, `-`, `*`, `/`: 加减乘除
   * `x > y`, `x < y`, `x == y`: 比较运算 (返回 0 或 1)
   * `x || y`, `x && y`: 逻辑或, 逻辑与
   * `x ? y : z`: 三元运算 (如果x为真则y，否则z)

2. **数学函数**:
   * `abs(x)`, `log(x)`, `sign(x)`: 绝对值, 对数, 符号函数
   * `signedpower(x, a)`: 保持符号的幂运算 (即 sign(x) * (abs(x)^a))
   * `max(x, y)`, `min(x, y)`: 逐元素取最大/最小值

3. **横截面函数 (Cross-Sectional)** - 每天对所有股票操作:
   * `rank(x)`: 百分比排名 (0到1之间)
   * `scale(x, a)`: 缩放使得 sum(abs(x)) = a (默认 a=1)
  
4. **时序函数 (Time-Series)** - 对单只股票的历史数据操作:
   * `delay(x, d)`: d天前的数据 (Lag)
   * `delta(x, d)`: x_today - x_{{d_days_ago}}
   * `correlation(x, y, d)`: 过去d天的滚动相关系数
   * `covariance(x, y, d)`: 过去d天的滚动协方差
   * `sum(x, d)`, `product(x, d)`: 过去d天的滚动和/积
   * `stddev(x, d)`: 过去d天的滚动标准差
   * `ts_argmin(x, d)`, `ts_argmax(x, d)`: 过去d天最值发生的距离天数
   * `ts_rank(x, d)`: 过去d天的时序排名
   * `ts_min(x, d)` -> `.rolling(d).min()`  <-- 确保这里有 .min()
   * `ts_max(x, d)` -> `.rolling(d).max()`
   * `sum(x, d)`    -> `.rolling(d).sum()`
   * `decay_linear(x, d)`: 线性衰减加权移动平均 (权重为 d, d-1, ..., 1)

[基础思路种子]
{user_base_idea}

[执行要求]
1. **差异化**: 尝试不同的数学构建方式，不要仅修改参数。
2. **命名规范**: 必须严格遵守 **大驼峰命名法 (CamelCase)**，如 `AlphaVolAdjustedMomentum`。
3. **公式规范**: `factor_formula` 必须完全符合上述 DSL 语法，不要发明不存在的函数。

[输出格式 - JSON Strict]
返回 JSON 列表。格式示例:
[
    {{
        "factor_name": "AlphaReversion01",
        "factor_formula": "-1 * correlation(rank(delta(log(volume), 2)), rank((close - open) / open), 6)",
        "factor_description": "成交量变化的排名与日内收益排名的负相关性。"
    }}
]
**严禁**包含 Markdown 标记。
"""

# ==============================================================================
# 2. 代码生成 (Code Generation) Prompt - [DSL 翻译器]
# ==============================================================================
CODE_GEN_PROMPT_TEMPLATE = """
你是一位精通 Python Pandas 高性能计算的量化工程师。
你的任务是将给定的 **Alpha101 DSL 因子公式** 准确翻译为 **生产级 Python 代码**。

[输入信息]
* **因子名称**: `{factor_name}`
* **因子公式 (DSL)**: `{factor_description}` (请仔细阅读此处的公式)

# [数据字段定义]
# * df_raw (Long Format): {stock_columns}, (注意：不包含 ret，需通过 close 计算)
# * df_index (Time Series): {index_columns} ，表示指数的每日价格

[函数签名强制约束 - 必须严格遵守]
1. **函数定义**: 必须严格定义为 `def {factor_name}(df_raw, df_index):`
2. **参数保留**: 即使因子逻辑**不需要**使用 `df_index`，也**必须**在函数参数中保留它，**严禁删除**。
3. **导入库**: 必须导入必要的库，如 `import pandas as pd`, `import numpy as np`。

如果你需要用到以下数据需根据输入信息计算：
* **vwap**: 成交量加权平均价
* **adv{{d}}**: 过去d天的平均成交额 (Average Daily Volume)

[DSL -> Pandas 翻译对照表 (必须严格查阅)]
1. **基础运算**:
   * `x ? y : z`  -> `np.where(x, y, z)`
   * `signedpower(x, a)` -> `np.sign(x) * (np.abs(x) ** a)`
   * `x || y` -> `(x) | (y)` (注意括号)
   * `log(x)` -> `np.log(x)`

2. **横截面 (Cross-Sectional)**:
   * `rank(x)` -> `df.groupby('TradingDay')['x'].rank(pct=True)`
   * `scale(x)` -> `df.groupby('TradingDay')['x'].apply(lambda s: s.div(s.abs().sum()))` (或使用 transform 优化)
   
3. **时序 (Time-Series) - 必须先 groupby('SecuCode')**:
   * `delay(x, d)` -> `.shift(d)`
   * `delta(x, d)` -> `.diff(d)`
   * `ts_min(x, d)` -> `.rolling(d).min()`
   * `ts_argmax(x, d)` -> `.rolling(d).apply(np.argmax)` (注意处理返回索引)
   * `ts_rank(x, d)` -> `.rolling(d).rank()` (Pandas >= 1.4 支持，否则需自定义)
   * `decay_linear(x, d)` -> 使用 `.rolling(d)` 配合自定义权重函数，或者简化为 `.ewm(span=d).mean()` 进行近似。

4. **相关性 (特别注意)**:
   * `correlation(x, y, d)` -> **严禁**直接用 `rolling().corr()`。
   * **必须**展开为: `(rolling_cov(x, y, d) / (rolling_std(x, d) * rolling_std(y, d)))`。

[代码编写规范 - 必须严格遵守]
1. **预处理 (修复 incompatible index 核心)**: 
   * ```python
      # 1. 如果需要指数数据，先 merge，再执行下一步
      if 'HS300' in factor_formula:
            # ... merge 逻辑 ...
      
      # 2. 只有在所有 merge 完成后，才能执行最终排序和索引重置
      df_raw = df_raw.sort_values(['SecuCode', 'TradingDay']).reset_index(drop=True)
      ```
   * 函数开始时，**必须**先执行 `df_raw = df_raw.sort_values(['SecuCode', 'TradingDay']).reset_index(drop=True)`。
   * **解释**: 必须加上 `.reset_index(drop=True)`，确保 DataFrame 的物理行号与索引 Index (0, 1, 2...) 完全对齐，否则后续赋值会报错。
   
2. **指数数据处理 (修复 KeyError)**:
   * 如果因子需要 `HS300` 或其他指数数据，**严禁**直接在 `df_raw` 中读取。
   * **正确模式**: 
     1. 先在 `df_index` 上计算指数指标 (如 `idx_ret = df_index['HS300'].pct_change()`)。
     2. 将计算好的 `idx_ret` 与 `df_index[['TradingDay']]` 组成小表。
     3. 使用 `pd.merge(df_raw, idx_temp, on='TradingDay', how='left')` 合并到主表。
     4. **非常重要**: Merge 后必须再次执行 `df_raw = df_raw.sort_values(['SecuCode', 'TradingDay']).reset_index(drop=True)`，因为 Merge 会打乱索引。

3. **禁止 Rolling 对象直接运算 (修复 unsupported operand)**:
   * **错误原因**: Pandas 的 `rolling()` 返回的是一个窗口对象（Rolling Object），不是 Series。
   * **正确做法**: 必须在 `.rolling(N)` 后紧跟聚合函数（如 `.mean()`, `.sum()`, `.std()`）将其转化为 Series 后，再进行运算。
   * **强制模式**:
     ```python
     # ❌ 错误: res = g['A'].rolling(5) * g['B'].rolling(5)
     
     # ✅ 正确 (必须包含 reset_index 以对齐主表):
     val_a = g['A'].rolling(5).mean().reset_index(level=0, drop=True) 
     val_b = g['B'].rolling(5).mean().reset_index(level=0, drop=True)
     res = val_a * val_b
     ```

4. **索引对齐 (修复 incompatible index)**:
   * 所有 `groupby('SecuCode')[...].rolling(...)` 的结果，在聚合后**必须**紧跟 `.reset_index(level=0, drop=True)`。
   * 这一步是为了去除 GroupBy 产生的多级索引，使结果变回与 `df_raw` 一致的 RangeIndex (0, 1, 2...)。
   * 赋值回 `df_raw` 时，确保 `df_raw` 的顺序与计算时一致 (由第1条规范保证)。

5. **相关性计算优化**:
   * **严禁**使用 `rolling().corr()` (内存消耗极大)。
   * **必须**使用公式分解: `corr(A, B) = rolling_cov(A, B) / (rolling_std(A) * rolling_std(B))`。
   * **注意**: 分母中的 `rolling_std` 也是聚合后的 Series，符合第 3、4 条规范。

6. **数学安全**:
   * `log(x)` 必须处理负数和零: `np.log(np.maximum(x, 1e-9))` 或 `np.log1p(np.abs(x)) * np.sign(x)`。
   * 除法必须处理分母为零: `x / (y + 1e-9)`。

7. **异常值处理**: 计算结果中若出现 `np.inf` 或 `-np.inf`，必须执行 `replace([np.inf, -np.inf], np.nan)`。

8. **防止使用未来数据**: 严格检查公式和代码，防止前瞻数据

9. **字符串安全**:  严禁在代码中出现未转义的引号。

10.**禁止**打印输出数据

[输出逻辑规范]
1. **文档注释**: 代码开始前写明**数学公式和逻辑**，第一列是数学公式，第二列是逻辑。
2. **返回值**: DataFrame 仅包含 `['SecuCode', 'TradingDay', '{factor_name}']`。
3. **缺失值**: 不要手动 `dropna()`。

[约束条件 Constraints]
1. 函数必须接收 (df_raw, df_index) 两个参数，你可以不用df_index。
2. **严禁使用 `print()` 函数**：不要输出任何调试信息，否则会导致系统崩溃！
3. **不要包含** `if __name__ == "__main__":` 块。
4. 最终必须返回一个 df，包括TradingDay, SecuCode，因子这三列

[最终输出]
只输出 Python 代码，不要 Markdown 标记。
"""

# core/prompts.py

# ... (保留原有的 IDEATION 和 CODE_GEN prompt) ...

# ==============================================================================
# 3. 代码修复 (Code Refinement) Prompt
# ==============================================================================
CODE_REFINE_PROMPT_TEMPLATE = """
你是一位量化代码修复专家。你之前生成的因子计算代码在运行时发生了错误。
请根据报错信息和源代码，修复该函数。

[元数据]
因子名称: {factor_name}
错误类型: {error_type}
原始公式: {factor_formula}
可用字段: {stock_columns}, {index_columns}  分别是接收的 (df_raw, df_index) 两个参数，仔细区分变量名称

以下需自行处理
* **returns**: 日收益率 (close_to_close)
* **vwap**: 成交量加权平均价
* **adv{{d}}**: 过去d天的平均成交额 (Average Daily Volume)
* **cap**: 市值

[原始代码]
```python

{old_code}

[报错信息 (Traceback)] {error_message}

[修复要求 - 极其重要]

逻辑一致性: 你的修复必须严格遵循 [原始公式] 的数学逻辑。严禁修改窗口大小、计算方式或简化公式。

纯代码输出: 你的回复必须且只能包含 Python 代码。

环境净化: 确保代码开头处理了 import，确保使用了 df.sort_values 和 reset_index。

完整性: 输出完整的、可运行的函数。

[修复策略建议]

如果是 IndexError，检查是否在 rolling/groupby 后忘记了 reset_index。

如果是 KeyError，请检查列名拼写。

如果是 ZeroDivisionError，请使用 replace([np.inf, -np.inf], np.nan)。

[约束条件 Constraints]
1. 函数必须接收 (df_raw, df_index) 两个参数，你可以不用df_index。
2. **严禁使用 `print()` 函数**：不要输出任何调试信息，否则会导致系统崩溃！
3. **不要包含** `if __name__ == "__main__":` 块。
4. 最终必须返回一个 df


[最终输出] 只输出 Python 代码，不要 Markdown。 
"""