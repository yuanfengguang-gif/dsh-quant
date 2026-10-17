# 因子公式目录（Factor Formula Catalog）

> 生成：2026-10-13
> 来源：开源仓库 `deepseek-harness-quant` 代码快照 + `github-maintainer` 技能库（主系统信息库）
> 说明：**主系统（私有 DSHQuant）不在本机**（C:/D: 盘均已查证，仅开源快照 `deepseek-harness-quant`）。
>       本目录从开源代码快照 + 技能库中提取全部可得因子公式，并标注可验证性。
> 状态标记：✅ 精确公式（开源有代码）｜🔶 可反推近似（标准定义，非主系统原式）｜❌ 仅名字+ICIR 目标（主系统私有 factor_pool/core/，无开源公式）｜⛔ 需本机缺失数据

---

## 一、8 强因子（已反推 + 已三层验证，2026-10-13）

| 因子 | 精确公式 | 方向 | 三层验证结论 |
|---|---|---|---|
| limup_ex_5 | 非一字板涨停标记 5 日滚动次数；涨停=ret≥(ST 4.5%/创业板科创板 19.5%/主板 9.5%) 且 high≠low | + | ✅ 有效 +5.40%/夏普 0.78 |
| limup_ex_ret_20 | (涨停次日收益−次日市场均值)×涨停标记，20 日滚动和 | − | ❌ 无效 −23.90%（涨停次日超额族已证伪） |
| lhb_jg_cnt_20 | lhb_detail.jiedu 解析「N家机构买入−N家机构卖出」净买次数，20 日滚动和 | + | ❌ 无效 −18.39%（龙虎榜机构族组合层证伪） |
| bp_value | (eps/roe)/close（=1/PB，finance.db，60 日披露 lag） | + | ✅ 有效 +6.14%/1.21 |
| open_prem_20 | (open/prev_close−1) 20 日滚动和 | − | ❌ 无效 −20.97%（跳空高开→回落反转） |
| turn_mid_prox | −(20 日均换手 − 全市场中位数) | + | ✅ 有效 +3.03%/1.15 |
| sue | (当期单季净利−上年同期)/\|上年同期\|（60 日 PIT lag） | + | ✅ 有效 +4.43%/0.68 |
| f_score | roe 连续值代理（真 Piotroski 7/9 项需 finance_quality.db，见第七节） | + | ✅ 有效 +12.92%/0.98 |

> 结论：5 有效（limup_ex_5 / bp / sue / f_score / turn_mid_prox），3 无效（limup_ex_ret_20 / lhb_jg_cnt_20 / open_prem_20）。
> 主系统 ICIR120 目标值（strong_factor_table.py）：open_prem_20 1.857 / limup_ex_5 1.620 / lhb_jg_cnt_20 1.516 / limup_ex_ret_20 1.473。本机 2019+ 数据窗口下复现的截面 ICIR 与主系统不一致（数据边界差异，已接受）。

---

## 二、14 技术面因子（backtest_all_factors.py，✅ 精确公式）

| 因子 | 公式 |
|---|---|
| open_prem_20 | `(open/prev_close−1).rolling(20, min_periods=5).sum()` |
| o2c_sum_20 | `(−(close/open−1)).rolling(20, min_periods=5).sum()`（日内收益反转） |
| turn_std20 | `−turn.rolling(20).std()`（低换手波动） |
| amihud | `(\|ret\|/amount).rolling(20).mean()`（非流动性） |
| chip_concentration | `−(turn20.std()/turn20.median())`（换手波动比取负，横截面） |
| beta_60 | 滚动 60 日 beta vs 等权市场收益 |
| mom_120 | `close/close.shift(120)−1` |
| reversal_20 | `−(close/close.shift(20)−1)` |
| lowvol_60 | `−60 日收益波动率` |
| near_high_250 | `(close/250 日最高).clip(upper=1)` |
| vol_contract | `−(v20 − v20.shift(20))`，v20=20 日波动率（波动收缩） |
| rsi_14 | RSI(14) |
| vol_ratio | `volume/volume.rolling(20).mean()`（量比） |
| ma_trend_20 | `close/ma20 − 1` |

---

## 三、五强量价因子（backtest_pv_consensus.py，✅ 精确公式）

| 因子 | 公式 | 方向 |
|---|---|---|
| turnover | `−20 日均换手` | −（低换手） |
| lowvol | `−60 日年化波动率` | −（低波） |
| reversal20 | `−(close/close.shift(20)−1)` | +（超跌） |
| sentiment | `20 日均换手 / 60 日均换手`（换手异动） | + |
| turn_mid_prox | `−(20 日均换手 − 全市场中位数)` | −（接近中位） |

---

## 四、6 基本面因子（fundamental.py，✅ 精确公式）

| 因子 | 公式 |
|---|---|
| c_factor | 最新可用单季净利同比 `sq_net_yoy` |
| sue_factor | `(当期单季净利 − 上年同期)/\|上年同期\|` |
| accel_factor | 当期单季同比 − 上期单季同比（二阶加速） |
| a_factor | 近 3 年年度净利 CAGR |
| pead_factor | 同比加速 + 水平（本季>上季取全值，否则×0.5） |
| profit_ok | 单季净利 > 0（硬过滤） |

> 披露延迟（PIT）：一季报 4-30 / 中报 8-31 / 三季报 10-31 / 年报次年 4-30。

---

## 五、10 经典技术指标（classic_indicators.py，✅ 精确公式）

| 因子 | 公式 | 方向 |
|---|---|---|
| macd_hist | MACD 柱（DIF−DEA，12/26/9） | + |
| macd_golden | MACD 金叉新鲜度（金叉后衰减） | + |
| kdj_j | KDJ J 值（9 日） | −（超卖反转） |
| rsi14 | RSI(14) | − |
| boll_lower | 收盘/布林下轨 −1（20 日，2σ） | − |
| ma_bull | MA20/MA60 −1（多头排列） | + |
| roc12 | 12 日变动率 | −（A 股反转） |
| wr14 | W%R(14) | − |
| cci14 | CCI(14) | − |
| ma200_trend | close/MA200 −1 | + |

---

## 六、6 动量/低波/新高（factor_engine.py，✅ 精确公式）

| 因子 | 公式 | 方向 |
|---|---|---|
| lowvol_60 | 60 日收益波动率 | −（低波） |
| near_high_250 | `(close/250 日最高).clip(upper=1)` | + |
| mom_20 | `close/close.shift(20)−1` | −（短期反转） |
| mom_120 | `close/close.shift(120)−1` | −（小盘反转） |
| rps_120 | 120 日相对强度（=mom_120） | − |
| new_high_250 | 52 周新高（0/1） | 0（剔除） |

---

## 七、Piotroski F-Score（fscore.py，🔶 7/9 项）

| 项 | 判据 |
|---|---|
| P1 盈利 | roe_avg > 0 |
| P2 现金流 | cfo_to_or > 0 或 cfo_to_np 非空 |
| P3 盈利改善 | roe_avg 同比上升 |
| P4 应计 | cfo_to_np > 1（现金利润比） |
| P5 杠杆下降 | liability_to_asset 同比下降 |
| P6 流动性改善 | current_ratio 同比上升 |
| P7 无新股 | ⛔ 缺 totalShare（计 null 不参与） |
| P8 毛利率改善 | gp_margin 同比上升 |
| P9 资产周转率 | ⛔ 缺总资产（计 null 不参与） |

> 数据源：finance_quality.db（baostock profit/balance/cashflow 三接口）。本机原为空，2026-10-13 已启动 `data/fetch_quality_full.py` 补拉（2018Q1-2026Q2）。

---

## 八、27 强因子白名单（strong_factor_table.py，主系统 ICIR120 目标）

> 判定口径：有效 + ICIR120≥0.5 + t≥4 + IC 胜率≥60% + 拥挤代理<90 + n_days≥250 + 非 lowfreq。
> `EXPRESS_BANNED = {lhb_jg_cnt_20, limup_ex_5}`（截面强但组合层证伪）。

| 因子 | ICIR120 | 公式可得性 |
|---|---|---|
| open_prem_20 | 1.857 | ✅ |
| gap_ret_20 | 1.788 | ❌ 私有 |
| limup_ex_5 | 1.620 | ✅ |
| limit_up_cnt_5d | 1.574 | 🔶 5 日涨停次数 |
| chip_concentration | 1.562 | ✅ |
| lhb_jg_cnt_20 | 1.516 | ✅ |
| limup_ex_ret_20 | 1.473 | ✅ |
| shebao_chg_pct | 1.428 | ⛔ 需 shebao.db（主系统 D 盘） |
| shebao_chg | 1.389 | ⛔ 需 shebao.db |
| limit_up_turn | 1.368 | ❌ 私有（涨停换手） |
| alpha003 | 1.165 | ❌ 私有（WorldQuant 101） |
| alpha015 | 1.079 | ❌ 私有 |
| alpha006 | 1.068 | ❌ 私有 |
| consec_limit_up | 1.007 | 🔶 连续涨停天数 |
| limit_up_flag | 1.006 | 🔶 涨停标记（=reproduce `_limup_flag`） |
| alpha050 | 0.983 | ❌ 私有 |
| o2c_sum_20 | 0.881 | ✅ |
| consec_limit_down | 0.874 | 🔶 连续跌停天数 |
| limit_down_flag | 0.872 | 🔶 跌停标记 |
| turn_std20 | 0.798 | ✅ |
| vol_contract | 0.716 | ✅ |
| vol_curvature | 0.714 | ❌ 私有（波动曲率） |
| alpha044 | 0.677 | ❌ 私有 |
| open_gap | 0.600 | 🔶 开盘缺口（open/prev_close−1） |
| turnover | 0.578 | 🔶 换手率（turn 列） |
| sentiment | 0.565 | ✅（backtest_pv_consensus） |
| max_ret20 | 0.559 | 🔶 20 日最大单日收益 |

---

## 九、主系统私有因子（❌ 无开源公式，仅名字 + ICIR 目标）

> 这些因子的精确公式在主系统私有 `factor_pool/core/`（本机不可得），需从主系统取或按其名字反推近似：
> **gap_ret_20（缺口收益 20 日）、limit_up_turn（涨停换手）、vol_curvature（波动曲率）、
> alpha003 / alpha006 / alpha015 / alpha044 / alpha050（WorldQuant 101 alpha）、
> shebao_chg / shebao_chg_pct（社保持仓变动，需 shebao.db）**。

---

## 十、信号族词汇表（signal_family.py，约 100 因子名 → 9 族）

- **价值**：value / bp / pe / pb / pe_pct / pb_pct / div_yield / pcf
- **成长**：sue / growth / yoy_accel / sq_nyoy / pead / asset_growth / inst_surv / gross_margin_chg / o2c
- **质量**：quality / roe / roa / liability / cfo_health / accruals / f_score / gp_a / kline_hammer_cnt / kline_doji_cnt / kline_shooting_cnt
- **量价**：turnover / vol_ratio / vol_contract / turn_mid_prox / turn60 / turn_std20 / amihud / obv_break / near_high / near_high_250 / near_ma250 / ma_trend / ma50_up / ma200_up / below_ma120 / std20 / amp20 / intraday_range / am_pm_ratio / close30_ret / tail60_ret / pm_ret / head60_ret / first_half_ret / tail_vol_share / vshape / open30_ret / kline_5m_std / kline_ret_skew / kline_mom_ratio / kline_last_5m
- **情绪**：sentiment / limit_up_flag / limit_down_flag / consec_limit_up / consec_limit_down / limit_up_premium / limit_up_next_ret / limit_up_turn / limit_up_vol_ratio / limit_up_cnt_5d / open_limit_up_fail / limit_down_next_ret / ind_moneyflow / sector_break / open_prem_20 / limup_ex_ret_20 / open_gap / tail_vol_gain
- **反转动量**：reversal20 / reversal5 / max_ret20 / drawdown60 / drawdown_60d / rsi14 / skew20 / kurt20 / downside_vol / mom120 / mom60 / lowvol / o2c_sum_20 / ind_rs_20 / close_to_high / kline_bear_streak
- **资金**：shebao_hold / shebao_chg / shebao_chg_pct / inst_hold_chg / lhb_jg_cnt_20
- **政策**：epu / epu_level / epu_z12 / policy
- **其他**：size / alpha003 / alpha004 / alpha006 / alpha015 / alpha044 / alpha050 / alpha101 / res_alpha21 / rmax / non_st / inst_hold

> 别名映射（FACTOR_ALIAS）：sq_nyoy→sue；gross_margin_chg→sue；inst_surv→sue；inst_hold_chg→shebao_chg；pe_pct/pb_pct/div_yield→bp；roe/liability/cfo_health→f_score；drawdown_60d→drawdown60；near_high_250→near_high；ma50_up/ma200_up→ma_trend；ind_moneyflow→sentiment。
