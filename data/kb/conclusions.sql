-- 红利低波养老方案 · 研究结论层（不含第三方行情数据）
-- 导出时间：2026-10-21 20:26:14
-- 来源：research_kb.db（本地全量库）
-- 重建行情层：python scripts/build_research_kb.py

-- ── meta ──
DROP TABLE IF EXISTS [meta];
CREATE TABLE meta(
  key TEXT PRIMARY KEY, value TEXT);
INSERT OR REPLACE INTO [meta] (key,value) VALUES('schema_version','1.0');
INSERT OR REPLACE INTO [meta] (key,value) VALUES('built_at','2026-10-21T20:26:13');
INSERT OR REPLACE INTO [meta] (key,value) VALUES('description','红利低波养老方案研究知识库（结论层 + 行情层）');
INSERT OR REPLACE INTO [meta] (key,value) VALUES('source_repo','deepseek-harness-quant');

-- ── round ──
DROP TABLE IF EXISTS [round];
CREATE TABLE round(
  rid TEXT PRIMARY KEY,            -- R6 / R14 / R33 ...
  title TEXT NOT NULL,
  rdate TEXT,                      -- YYYY-MM-DD
  topic TEXT,                      -- 分类：数据/策略/建仓/信号/风控/博主验证
  status TEXT,                     -- done / closed / superseded
  verdict TEXT,                    -- 一句话结论
  report_path TEXT);
INSERT OR REPLACE INTO [round] (rid,title,rdate,topic,status,verdict,report_path) VALUES('R5-0','红利 ETF 数据审计与覆盖','2026-10-17','数据','done','9 项数据验证通过；红利 ETF 分红覆盖率实测远低于预期','');
INSERT OR REPLACE INTO [round] (rid,title,rdate,topic,status,verdict,report_path) VALUES('R5-4','红利 ETF 分红覆盖率实测','2026-10-17','数据','done','512890 滚动 3 年分红覆盖 0%（ETF 不分红，靠净值复利）','');
INSERT OR REPLACE INTO [round] (rid,title,rdate,topic,status,verdict,report_path) VALUES('R6','博主策略复现（小马聊财经）','2026-10-18','博主验证','done','8 项完全复现、5 项接近、3 项部分、2 项自相矛盾；她的信号 20 年 6-7 次、胜率 100%','reports/R6_博主策略复现报告.md');
INSERT OR REPLACE INTO [round] (rid,title,rdate,topic,status,verdict,report_path) VALUES('R7','养老方案 v2（红利低波择时）','2026-10-18','策略','done','红利低波 20 年 15.05% 年化、MDD -66.2%；4% 提款生存率 98.6%','reports/R7_养老方案v2_红利低波择时.md');
INSERT OR REPLACE INTO [round] (rid,title,rdate,topic,status,verdict,report_path) VALUES('R8','择时卖出替代分红','2026-10-18','策略','done','分红取现 8.85% vs 再投资 12.50%（差 3.65pp）；生活费择时卖出把 P5 从 10.3% 提到 97.5%','reports/R8_择时卖出替代分红.md');
INSERT OR REPLACE INTO [round] (rid,title,rdate,topic,status,verdict,report_path) VALUES('R9','MA250 premium 校准','2026-10-18','信号','done','MA250×1.05 触发率 86%（6/7 年）','');
INSERT OR REPLACE INTO [round] (rid,title,rdate,topic,status,verdict,report_path) VALUES('R10','卫星仓波段（用户澄清版）','2026-10-18','策略','done','卫星仓 30% 降回撤 -66.9%→-52.5%，但中位收益下降','reports/R10_卫星仓波段_用户澄清版.md');
INSERT OR REPLACE INTO [round] (rid,title,rdate,topic,status,verdict,report_path) VALUES('R11','三种卫星仓驱动信号对比','2026-10-19','信号','done','股息率分位 13.15%/-52.5% > 博主规则 11.12%/-62.5%；博主信号低频不适配卫星仓','');
INSERT OR REPLACE INTO [round] (rid,title,rdate,topic,status,verdict,report_path) VALUES('R12','v2.0 最终方案块自助法','2026-10-19','策略','done','500 路径：生存率 99.2%、P5 22.8%、P50 651%','reports/r12_final_bootstrap.json');
INSERT OR REPLACE INTO [round] (rid,title,rdate,topic,status,verdict,report_path) VALUES('R14','建仓节奏（3 年递增）','2026-10-19','建仓','done','递增建仓 10 年均值 2.057，是最差；一次性 2.601','');
INSERT OR REPLACE INTO [round] (rid,title,rdate,topic,status,verdict,report_path) VALUES('R16','10 万建仓 + 等信号','2026-10-19','建仓','done','等 12 个月均值 2.279 vs 一次性 1.900（危机前提下 +20%）','');
INSERT OR REPLACE INTO [round] (rid,title,rdate,topic,status,verdict,report_path) VALUES('R18','信号阈值失效（绝对阈值漂移）','2026-10-19','信号','done','股息率≥5% 在 2006-2014 从未达到（0%），2020-2026 达 81% → 绝对阈值失效','');
INSERT OR REPLACE INTO [round] (rid,title,rdate,topic,status,verdict,report_path) VALUES('R19-R23','阶梯建仓回测','2026-10-19','建仓','closed','阶梯建仓在急跌中失效（一天跌穿所有档位）；均值低于一次性','');
INSERT OR REPLACE INTO [round] (rid,title,rdate,topic,status,verdict,report_path) VALUES('R24-R25','公平对比（修正费率 bug + 200 随机起点）','2026-10-19','建仓','done','一次性均值最高 2.531、最差 1.537；DCA 12 月最差 1.845（尾部最优）','');
INSERT OR REPLACE INTO [round] (rid,title,rdate,topic,status,verdict,report_path) VALUES('R26-R30','危机前提下的建仓','2026-10-19','建仓','done','纯等 12 个月最优（+20%）；加提前触发/DCA/阶梯都更差','reports/R42_P1工具_P2温和倾斜.md');
INSERT OR REPLACE INTO [round] (rid,title,rdate,topic,status,verdict,report_path) VALUES('R31','第三个视频验证（柒明东东）','2026-10-19','博主验证','done','5 条认知全对；核心指标股债收益比证伪；行业集中度标准有效','reports/R31_第三个视频验证_柒明东东.md');
INSERT OR REPLACE INTO [round] (rid,title,rdate,topic,status,verdict,report_path) VALUES('R33','四项验证（行业集中度等）','2026-10-19','风控','done','512890 前三大行业 58.3%、银行 52.5%；创业板信号/季节性/PE 分位均证伪','reports/R33_四项验证_行业集中度等.md');
INSERT OR REPLACE INTO [round] (rid,title,rdate,topic,status,verdict,report_path) VALUES('R35-R36','银行兜底强度分析','2026-10-19','风险','done','中国无全国性银行破产，但国有大行股价仍跌 60-74%；512890 国有大行仅 11.3%','');
INSERT OR REPLACE INTO [round] (rid,title,rdate,topic,status,verdict,report_path) VALUES('R37-R38','反向利用信号验证','2026-10-19','信号','done','仅 6 月效应可反向用（+2.6pp）；P2/股债比正反都不行','reports/R37_反向利用信号验证.md');
INSERT OR REPLACE INTO [round] (rid,title,rdate,topic,status,verdict,report_path) VALUES('R39-R41','5 个新择时信号','2026-10-19','信号','closed','全部证伪；发现「预测力≠可交易性」（ERP 相关 0.439 但不可交易）','reports/R39_新择时信号探索.md');
INSERT OR REPLACE INTO [round] (rid,title,rdate,topic,status,verdict,report_path) VALUES('R106-R110','8 个新视频分析与验证','2026-10-21','信号','done','ERP 极端阈值验证有效（+6.89pp）；按月分红是营销说法（实际1-3次/年）；现金流覆盖率仅106%','reports/R106_8个新视频分析_2026-10-21.md');
INSERT OR REPLACE INTO [round] (rid,title,rdate,topic,status,verdict,report_path) VALUES('R82-R99','卫星仓择时系统性验证（18 轮）','2026-10-20','信号','done','发现分红季锯齿、基准漂移、股息率数据污染三个缺陷；从 5 年分位改为绝对阈值 2.5%/4.0%，每月检查；应急条款证伪','reports/r93_threshold_grid.json');
INSERT OR REPLACE INTO [round] (rid,title,rdate,topic,status,verdict,report_path) VALUES('R73-R81','配比对比 + 银行业趋势','2026-10-20','策略','done','20 年全收益下 40/35/25 与 55/30/15 的 Calmar 相同（0.228），旧配比略优；515100 优势仅存在于 2014-2018；银行业 2025-2026 转强但属顺势','reports/r80_longcompare.json');
INSERT OR REPLACE INTO [round] (rid,title,rdate,topic,status,verdict,report_path) VALUES('R46-R55','6 个视频分析（4 位博主）','2026-10-20','博主验证','done','自由现金流 1:1 有样本内效果但样本仅 12.8 年；比价信号有预测力但不如股息率分位；价格网格灾难；穷诸葛 70/30 与我们一致','reports/R46_6个视频分析_2026-10-20.md');
INSERT OR REPLACE INTO [round] (rid,title,rdate,topic,status,verdict,report_path) VALUES('R42-R44','P1 监控工具 + P2 温和倾斜','2026-10-19','策略','done','ERP 温和倾斜也证伪；卫星仓全卖优于部分降仓（16.33%/-52.2%）；加过滤是负优化','reports/R42_P1工具_P2温和倾斜.md');

-- ── finding ──
DROP TABLE IF EXISTS [finding];
CREATE TABLE finding(
  fid TEXT PRIMARY KEY,            -- F001...
  category TEXT NOT NULL,          -- 估值/信号/建仓/风险/数据/认知
  statement TEXT NOT NULL,         -- 结论陈述
  evidence TEXT,                   -- 量化证据
  verdict TEXT NOT NULL,           -- CONFIRMED / FALSIFIED / PARTIAL / REFERENCE
  rid TEXT,                        -- 来源轮次
  data_pointer TEXT,               -- 指向 json/脚本/表的定位
  FOREIGN KEY(rid) REFERENCES round(rid));
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F001','收益','红利低波 20 年年化 15.05%（2006-07-31~2026-07-31，全收益）','H20269 全收益指数；红利低波100 14.80%；中证红利 12.09%；沪深300 6.53%','CONFIRMED','R7','idx_daily:H20269');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F002','收益','红利低波在每一个区间都跑赢中证红利','20年 +2.96pp、近10年 +0.84pp、近5年 +4.03pp、近3年 +1.63pp','CONFIRMED','R11','');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F003','风险','红利低波 20 年最大回撤 -66.2%（2008-11-04）','相对 250 日高点、全历史高点、全收益三个口径一致','CONFIRMED','R7','');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F004','认知','分红是净值扣减，真收益来自股价上涨 + 分红再投资复利','分红取现 8.85%/年 vs 再投资 12.50%/年，差 3.65pp；全收益 vs 价格差 3.85~5.13pp','CONFIRMED','R8','reports/R8_择时卖出替代分红.md');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F005','认知','红利是防御型资产，不是全天候资产','牛市跑输 13.28pp、熊市跑赢 16.56pp','CONFIRMED','R6','');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F006','信号','股息率 5 年分位是唯一通过验证的择时信号','卫星仓全卖/全买：16.33%/-52.2%/Calmar 0.313（纯持有 15.84%/-66.2%/0.239）','CONFIRMED','R44','logs/_r44_correct.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F007','信号','卫星仓要「全卖」，不要「部分降仓」','全卖 16.33%/-52.2%（0.313）> 降到30% 16.20%/-56.9%（0.285）> 降到半仓 16.11%/-59.7%（0.270）','CONFIRMED','R44','logs/_r44_correct.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F008','信号','给信号加「连续 N 个月同向」过滤是负优化','无过滤 16.61% → 连续2月 15.99% → 连续3月 14.21%；信号本身 20 年只翻转 10 次','CONFIRMED','R43','logs/_r43_flip.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F009','信号','股息率绝对阈值已失效（会随市场漂移）','股息率≥5%：2006-2014 满足 0% 天数、2015-2019 满足 2%、2020-2026 满足 81%','CONFIRMED','R18','');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F010','信号','股债收益比（股息率÷10Y国债）证伪','<1.5 分位未来1年 7.59% ≈ >3.0 的 8.61%（无单调性）；11 次跌破1.5，10 次后1年正收益','FALSIFIED','R31','');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F011','信号','ERP（1/PE−10Y）预测力最强但不可交易','相关系数 +0.439（全场最高），但策略 Calmar 0.312 < 满仓 0.428；温和倾斜也降年化，回撤完全不变','FALSIFIED','R41','logs/_r41_fix.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F012','信号','ERP 低点与回撤发生点不重合','ERP<30% 时段是 2018 初/2021 初；最大回撤发生在 2018-10/2022-10（那时 ERP 已高）','CONFIRMED','R42','reports/r42_erp_tilt.json');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F013','信号','创业板连 5 天跑赢红利 → 减仓红利，证伪','信号后 60日 +3.49% vs 全样本 +2.91%（反而更好）；胜率 69% vs 72%','FALSIFIED','R33','logs/_r34_p2.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F014','信号','5/11 月「分红前加仓窗口」证伪（实为反向）','5/11 月后续次月 0.21%/-0.30% vs 其他月 1.54%/1.88%（差 -1.33~-2.18pp）','FALSIFIED','R33','');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F015','信号','6 月季节性有效但只能轻度用','6 月均值 -3.57%（其他月 +1.56%）、正收益 8/21、t≈-2.3；但 2014-2020 完全失效','PARTIAL','R38','logs/_r38_june.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F016','信号','成交额拥挤度、波动率分位、PE 动量、股债利差 4 个信号均证伪','相关系数分别 -0.062/+0.016/-0.214/+0.227；策略 Calmar 均不优于满仓','FALSIFIED','R39','logs/_r40_out.txt');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F017','信号','13 个择时信号里只有 1 个可用（股息率分位）+ 1 个可轻用（6月）','其余 11 个证伪','CONFIRMED','R41','reports/R39_新择时信号探索.md');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F018','建仓','一次性投入的期望收益最高，但尾部最差','200 随机起点 10 年：一次性均值 2.531/最差 1.537；DCA12月 2.415/最差 1.845','CONFIRMED','R25','');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F019','建仓','在「1年内有危机」前提下，纯等 12 个月最优','6 个危机前起点：等12月 2.279 vs 一次性 1.900（+20%）；加提前触发 1.995/阶梯 2.071/DCA 1.931 都更差','CONFIRMED','R30','reports/r30_final_entry.json');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F020','建仓','递增建仓（15/30/55）是最差的建仓节奏','6 起点 10 年均值 2.057 vs 一次性 2.601；连 2007 大顶起点也落后 51%','FALSIFIED','R14','');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F021','建仓','阶梯建仓在单边急跌中失效','2008 全年多档位在同一天（兜底日）全部投完','FALSIFIED','R19','');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F022','风控','512890 红利低波ETF华泰柏瑞行业集中度超标','前三大行业 58.3%（地方性银行 30.1% + 全国性银行 22.3% + 公路铁路 4.6%），银行合计 52.5%','CONFIRMED','R33','reports/r33_four_tasks.json');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F023','风控','512890 的银行持仓 57.5% 是城商行+农商行（兜底最弱）','城商行 25.6% + 农商行 4.5% = 30.1%（占净值）；国有大行仅 11.3%（21.6% of banks）；前十大无一家国有大行','CONFIRMED','R35','logs/_r35_bank.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F024','风险','中国从未有全国性银行破产，但国有大行股价仍跌 60-74%','国有大行 MDD 中位 -60.1%（交行 -74.2%、建行 -67.0%、工行 -60.3%）；恒丰银行 2020 被重组','CONFIRMED','R36','logs/_r36b.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F025','风险','政府兜底的是储户，不是股东','包商银行 2019 二级资本债全额减记；恒丰 2020 中央汇金注资后股东权益大幅稀释','CONFIRMED','R36','');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F026','数据','红利 ETF 不代表分红（净值复利型）','512890 滚动 3 年分红覆盖 0%；红利低波指数分红贡献 4.16%','CONFIRMED','R5-4','');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F027','数据','bars_tdx.db 的 daily_bar 有脏数据','工商银行出现价格 0.010、招商银行 0.020，导致回撤算出 -99.8%（真实 -60.3%）；应使用 bars.db','CONFIRMED','R36','logs/_dbg_bank2.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F028','认知','预测力不等于可交易性','ERP 相关系数 0.439（最强）但策略 Calmar 最差；股息率相关系数仅 0.119~0.209 却是唯一可用信号','CONFIRMED','R41','');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F029','认知','博主策略复现：她的信号有效但低频，不适合管卫星仓','博主三条件 20 年 6-7 次、胜率 100%、平均 +45.6%；但用于卫星仓只有 11.12%（股息率分位 13.15%）','CONFIRMED','R11','');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F031','信号','信号检查频率会显著改变结果：按月检查 16.33%/-52.2%（11次调仓），按日检查 15.84%/-62.1%（84次调仓）','股息率分位在 30% 阈值附近日频抖动导致频繁翻转；方案规定按月检查，故以月频为准','CONFIRMED','R45','logs/_r45_s07fix.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F032','信号','自由现金流指数「10 年年化 20.31%」不可复现','932365 10年 10.89%、932368 12.07%、980092 13.01%；遍历 2015-2026 全部 9-11.5 年窗口最高仅 11.49%（起点 2016-02-19）','FALSIFIED','R46','logs/_r48_find2031.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F033','信号','自由现金流 1:1 组合在 2014-2026 样本内优于纯红利低波，但不可外推','50/50 半年再平衡 Calmar 0.230 vs 纯红利低波 0.167；但样本仅 12.8 年、指数 2014 前仅 2 行、与红利日相关 0.877/月 0.867','PARTIAL','R52','reports/r52_fcf_honest.json');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F034','信号','自由现金流组合中的再平衡无价值甚至有害','50/50 不再平衡 0.236 > 半年再平衡 0.230 = 年度再平衡 0.230（博主称「再平衡是必不可少的一环」，数据不支持）','FALSIFIED','R52','reports/r52_fcf_honest.json');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F035','信号','创业板/红利点数比价对红利未来 1 年收益有强预测力','原始比价相关系数 +0.394（分位化后 +0.311）；分档完美单调：<0.3 红利未来1年 -4.0%，>0.7 则 +16.6%；2026-06-30 比价 0.865 为历史最高','PARTIAL','R53','logs/_r53_ratio.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F036','信号','比价作卫星仓驱动不如股息率分位','比价单独用 Calmar 0.130 vs 股息率分位 0.142；两者组合 0.145（仅提升 2%，不值得复杂度）','FALSIFIED','R54','reports/r54_ratio_strategy.json');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F037','信号','价格网格（涨5%卖90%）灾难性失败','回测年化 -26.78%、回撤 -99.8%、155 次调仓；因长期上涨资产会把仓位卖光后永远踏空','FALSIFIED','R55','logs/_r55_v9.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F038','信号','股息率<3.5%空仓的漂亮回测是后视偏差','股息率<3% 在 2006-2014 是常态（8年均值 2.64%），策略几乎全程空仓恰好躲过 2008；Calmar 0.376 不可外推','FALSIFIED','R55','logs/_r55_v9.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F039','建仓','建仓节奏的排序取决于起点：开局上涨一次投入赢 78%，开局下跌分批赢 85%','穷诸葛 55 个「开局12月上涨」窗口中 43 个一次投入领先；26 个「开局12月下跌」窗口中 22 个分批领先（独立博主，与我们 R25 结论一致）','CONFIRMED','R55','logs/transcript_v5_穷诸葛_红利之道3_节奏的账.txt');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F040','建仓','「账户浮亏转正所需月数」是退休提款方案的关键指标','2015-06 高点进场：一次投入 89 个月 vs 分批 12 个月 14 个月（差 6 倍）；价格回到起点 62 vs 41 个月','CONFIRMED','R55','logs/transcript_v5_穷诸葛_红利之道3_节奏的账.txt');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F041','认知','两个独立博主对自由现金流给出相反结论，数据支持「暂不纳入」','睡前投资课主推 1:1 组合（称 10 年 20.31%）；光总有话说明确拒绝（称样本外从 2025 开始、历史检验不够）；我们的验证支持后者','CONFIRMED','R46','reports/R46_6个视频分析_2026-10-20.md');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F042','风控','512890 在三个独立来源中都被评为最差红利低波 ETF','光总：再平衡一年一次（vs 半年）、费率 0.85%（vs 0.72%）；我们：前三大行业 58.3%、银行 52.5%','CONFIRMED','R46','reports/R46_6个视频分析_2026-10-20.md');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F043','数据','东方红红利低波（012708/012709）是场外指数基金，非 ETF','成立 2021-12-30，规模 A 35.65亿 + C 28.36亿 ≈ 64亿；跟踪东方红定制指数；申赎 T+1/T+2，不适合每月择时操作','CONFIRMED','R56','logs/_dfh_info.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F044','风控','东方红红利低波收益不占优但回撤最小','同区间 2021-12-30~2026-10-19：东方红 8.65%/-11.8%(Calmar 0.733) vs 515100 6.25%/-12.9%(0.484) vs 515450 8.73%/-13.6%(0.642) vs 512890 9.79%/-14.0%(0.699)','CONFIRMED','R56','logs/_dfh_cmp.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F045','认知','光总「512890 跑输前两只」与我们数据相反','同区间 512890 年化 9.79% 是三只最高（东方红 8.65%、515450 8.73%、515100 6.25%）；可能他用了不同区间或混淆净值与二级市场价格','PARTIAL','R56','logs/_dfh_cmp.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F046','建仓','我们的建仓计划（10万分3月+第12月投140万）回本周数远优于一次投入','211 个历史起点：账户浮亏转正月数中位 12、P90 14、最坏 33（2.8年）；75.6% 的起点投完即转正；建仓期最深浮亏中位 -10.1%、P10 -39.8%','CONFIRMED','R56','reports/r56_entry_breakeven.json');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F047','策略','515100（红利低波100）的优势只存在于 2014-2018，2019 年后消失','滚动3年新方案（55/30/15）跑赢旧方案（40/35/25）的占比：2014-2018 为 80%，2019-2021 降至 14%，2022-2026 仅 16%','FALSIFIED','R80','reports/r80_longcompare.json');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F048','策略','20 年全收益下两个配比的 Calmar 完全相同（0.228），旧配比略优','旧 40/35/25：2478.1万/14.89%/-65.3%；新 55/30/15：2454.2万/14.83%/-65.0%；纯512890型 2517.2万/14.97%；纯515100型 2354.7万/14.60%','CONFIRMED','R80','reports/r80_longcompare.json');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F049','风险','银行业 2025-2026 转强，但此前连续 3 年落后','银行 vs 红利低波：2022 差 -21.9pp（银行赢 0%）、2023 差 -31.7pp（0%）、2024 差 -26.9pp（0%）、2025-2026 差 +10.0pp（赢 82%）；近3年 +6.42pp','CONFIRMED','R81','reports/r81_bank.json');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F050','风险','银行的波动与最大跌幅在缩小（成熟期特征）','波动：全期 19.59% → 近5年 16.66% → 近3年 16.20% → 近1年 14.67%；最大跌幅：-37.1% → -26.8% → -21.9% → -15.7%','CONFIRMED','R81','reports/r81_bank.json');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F051','认知','银行强弱是顺势指标，不是预测指标','2022-2024 连续 3 年落后 22-32pp 后于 2025 反转；追涨在转折点会滞后吃亏。用途是追踪理解，不是自动调仓依据','CONFIRMED','R81','logs/_r81_bank.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F052','信号','股息率有强季节效应：6 月平均跳升 +13.45%，7 月回落 −7.78%','20 年月度统计：6月 +13.45%、7月 −7.78%、8月 −4.35%，其它月约 0%；同期 6 月指数平均 −4.89%','CONFIRMED','R86','logs/_r86_seasonal.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F053','信号','股息率月度变化的 81.6% 来自分红数据更新，仅 19.1% 来自股价','全期相关：股息率变化 vs 分红变化 +0.706（贡献 81.6%）；vs 股价变化 −0.226（贡献 19.1%）；2025-05→07 股价 −0.18% 但股息率 −32.83%','CONFIRMED','R92','logs/_r92_yield_source.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F054','信号','5 年分位信号在 2025 年给出错误卖出（实为最便宜时）','2025-09 股息率 4.80%，5年分位 3%（极贵→卖），但 20 年历史位置 70%（便宜）；绝对值阈值判定为买回','FALSIFIED','R90','logs/_r90_two_problems.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F055','信号','5 年窗口的基准被 2021-2025 高股息期抬高（基准漂移）','5年窗口（2020-09~2025-09）股息率最低 4.50%、中位 5.46%，所以 4.80% 在此窗口算 3 分位，但 20 年均值仅 3.88%','CONFIRMED','R90','logs/_r90_two_problems.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F056','信号','20 年窗口分位会让策略在 2011 后永久满仓（近乎不择时）','20年窗口全部 6 次调仓发生在 2007-04~2011-06；2011-06 后 15 年零动作；卖出需股价涨 83%','CONFIRMED','R83','reports/r83_window20.json');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F057','策略','绝对阈值 2.5%/4.0% 优于 2.5%/4.5%（Calmar 0.250 vs 0.242）','2006-07~2026-10，每月检查：4.0% 版年化 13.06%/Calmar 0.250；4.5% 版 12.66%/0.242；4.0-4.2% 结果相同，4.5-4.8% 结果相同','CONFIRMED','R96','logs/_r96_recent_and_emergency.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F058','策略','判定频率对结果影响极小（每天/每月/每季/每年9月 Calmar 0.242~0.245）','R95 实测：所有频率调仓次数都是 2 次，因为 2.5%~4.0% 有 1.5pp 死区，天然防抖动；只有每半年较差（0.223，卖出延迟到 2008-01）','CONFIRMED','R95','logs/_r95_freq2.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F059','策略','应急条款（暴跌加仓）在本策略里不成立','R97 宽版 +0.004 Calmar 但多 8 次摩擦；R98 窄版（需股息率≥3%）从不触发；R99 回落版产生「买了又卖」冲突（Calmar 无改善）','FALSIFIED','R97-R99','logs/_r99_emergency_drawdown.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F060','策略','本策略只在「高分红年代」有效，2014 年前会长期空仓','2007-2013 股息率仅 1.5%~3.5%，永远够不到 4.0% 买回线；2008 年指数跌 66.2%，股息率只从 1.56% 涨到 2.15%，仍不满足买回 → 20年回测实质是「13年空仓+7年满仓」','CONFIRMED','R96','logs/_r96_recent_and_emergency.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F061','信号','8 位博主中只有 1 位（v1）用 20 年回测给出股息率阈值，其结论 4.5% 与我们的独立验证吻合','v1 实证：低于 4.5% 买入一年胜率 63.7%，高于 4.5% 胜率 95%；v1 明确反驳「3% 就卖」（3% 已 10 年未出现）；v2/v3 用 5%，v4 只提现状，v8 无数字，v9 用价格网格','CONFIRMED','R93','logs/transcript_v1_波段策略胜率.txt');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F062','风险','近期股息率区间：2020 年起 4.20%~7.85%（中位 5.28%）；2022 年起最低 4.50%；2026 年 4.65%~5.45%','2020 年后 100% 时间股息率 ≥4.0%；2026 年最低 4.65% → 绝对值阈值在当前环境下不会触发卖出','CONFIRMED','R96','logs/_r96_recent_and_emergency.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F063','策略','现行绝对值方案（2.5%/4.0%）在全期与分期间都优于永不动，但优势全部来自 2006-2013','分期间：2006-2013 信号 14.78% vs 永不动 13.58%（+1.20pp）、回撤 -52.2% vs -66.2%；2014-2019 与 2020-2026 差异均为 +0.00pp（因一直满仓未触发）','CONFIRMED','R101','logs/_r101_o09_fix.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F064','策略','阈值在 2.3-2.7% × 3.8-4.2% 区间内结果完全相同（极稳健）','9 个组合 Calmar 均为 0.250、年化 13.06%、调仓 2 次；因为 20 年只穿越阈值 2 次，区间内任何取值都捕捉到同两次','CONFIRMED','R101','logs/_r101_o09_fix.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F065','策略','换起始点后，只有含 2008 的窗口才有优势（2012 年后起算完全无用）','10 年窗口 Calmar 差异：2006 起 +8.3、2008 起 +5.7、2010 起 +1.1、2012 起 -0.1、2014 起 0.0、2016 起 0.0','CONFIRMED','R101','logs/_r101_o09_fix.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F066','信号','六类替代择时方案都不如现行绝对股息率方案（除 E 但 E 的优势是假象）','Calmar：A 现行 0.295 / E 双条件 0.300 / F MA250 0.268 / D 3年高点 0.254 / B 股债比 0.232 / C 回撤触发 0.221 / 永不动 0.226','CONFIRMED','R102','logs/_r102_o08_alternatives.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F067','信号','E（股息率+回撤双条件）的优势是「卖出晚一个月」的运气，不是机制改进','A 卖于 2007-07-31，E 卖于 2007-08-31，买回均为 2013-06-30；两者仅差一个月，Calmar 差 0.005 属样本内噪声','FALSIFIED','R104','logs/_r104_e_vs_a.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F068','信号','v1 博主提出的「回撤≥10% 就上车」在本策略里反而变差','回撤触发方案 Calmar 0.203-0.221，全部低于永不动的 0.226；原因是回撤不看估值，会在 2015 年高位回调时错误加仓','FALSIFIED','R102','logs/_r102_o08_alternatives.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F069','信号','ERP 极端阈值择时（>6% 满仓 / <3% 空仓）在沪深300上有效，但「年化20%」复现不了','2015-01~2026-10 沪深300：策略年化 8.05%/回撤 -24.8%/Calmar 0.325/调仓5次；持有年化 1.16%/回撤 -46.7%/Calmar 0.025；差异 +6.89pp。但阈值 6.5 就失效（年化1.40%、只触发1次）','CONFIRMED','R105','logs/_r105_erp_test.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F070','信号','ERP 择时只对沪深300有效，对中证红利完全无效（0 次触发）','中证红利 ERP 当前 9.55%、从未跌破 3%，所以 >6/<3 规则一次都不触发，等于什么都不做','CONFIRMED','R105','logs/_r105_erp_test.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F071','认知','「ERP 仅参考」的表述需要精确化：不适合连续倾斜，但适合极端阈值开关','R41/R42 测的是 ERP 分位→温和倾斜（无效，降年化）；R105 测的是 ERP 绝对值→>6满仓/<3空仓（+6.89pp）。两种用法结论相反，不矛盾','PARTIAL','R105','logs/_r105_erp_test.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F072','数据','「按月分红」是营销说法：三只 ETF 实际每年只分 1-3 次，且 512890 完全不发现金','真实记录：515100 分红2次(约每年1次,12月)、515450 分红9次(2024起每年2次,2026年3次)、512890 仅1次0元。512890 累计净值差额来自 2021-10-22 的 1:2 份额折算，不是分红','FALSIFIED','R108','logs/_r108_dividend_real.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F073','策略','当前配比 40/35/25 的现金分红覆盖率 67-78%，分红覆盖不了生活费，必须卖份额','四口径：全历史(含2023补发)99.8%、剔除补发77.6%、最近2年67.1%、2026单年15.3%。中性口径每月分红3,882元 vs 目标5,000元，缺1,118元；保守口径每月3,353元，缺1,647元。分红主要在7月/12月到账，全年8-10个月零到账','CONFIRMED','R110-R112','logs/_r112_coverage_fix.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F074','策略','即使完全去掉 512890，保守口径下分红覆盖率也只有 90%，靠调配比覆盖生活费走不通','保守口径(C)配比测试：40/35/25→2.68%(67%)；50/35/15→3.08%(77%)；55/40/5→3.49%(87%)；60/40/0→3.59%(90%)；35/25/40→2.11%(53%)。对照总收益：512890 13.38%、515100 11.28%、515450 9.79%','CONFIRMED','R110-R112','logs/_r112_coverage_fix.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F077','数据','515450 的分红在持续崩塌：2023 年 0.140 元/份 → 2026 年 0.025 元/份（-82%）','逐年：2021 0.060、2022 0.050(-17%)、2023 0.140(+180%)、2024 0.105(-25%)、2025 0.075(-29%)、2026 0.025(-67%)','CONFIRMED','R112','logs/_r112_coverage_fix.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F078','数据','515100 的 2023-12-21 分红 0.437 元/份是「3.5 年一次性补发」，不是常规年度分红','基金 2020-05 成立至 2023-12 一直未分红，一次性补发。用累计分红÷总年数会高估年度现金收益率（5.87% vs 剔除后 3.66%）','CONFIRMED','R111','logs/_r111_verify_div.py');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F075','策略','「一把梭 > 抄底 > 定投」在红利低波上成立，且博主推荐的「6-7成底仓+3-4成等跌」与我们70/30结构一致','v10 博主实测（20万，2019-03起7年）：一把梭41.4万(+107%,年化~11%) > 抄底30.5万(+52%) > 定投27.5万(+37%,年化~5%)。其结论「任何让你空仓等待的策略，都意味着你在这条坡上少爬了一段」','CONFIRMED','R106','logs/transcript_v10_睡前投资课_定投还是抄底.txt');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F076','认知','价值100 与自由现金流同样受「回测数据」问题困扰：2024-10 才正式运行，真实样本不足 2 年','博主主动披露：「过往这部分数据是拿着现在的规则用后视镜往回看的」「要等指数完整经历两个牛熊才能有更肯定答案」。编制规则：净利润>0 + 砍三刀(ROE水平/ROE稳定性/FCF率) + 三筛子(PE/股息率/FCF率算术平均)','CONFIRMED','R106','logs/transcript_v14_阿朗讲指数_价值100深度解析.txt');
INSERT OR REPLACE INTO [finding] (fid,category,statement,evidence,verdict,rid,data_pointer) VALUES('F030','认知','博主给的数据基本可信，但指标解释常出错','柒明东东：股息率 4.42%/10Y 1.76%/差 4.78pp 均核对一致；但股债比阈值、PE 分位 54.51% 无法复现','PARTIAL','R31','reports/R31_第三个视频验证_柒明东东.md');

-- ── signal ──
DROP TABLE IF EXISTS [signal];
CREATE TABLE signal(
  sid TEXT PRIMARY KEY,            -- S01...
  name TEXT NOT NULL,
  stype TEXT,                      -- 趋势/估值/情绪/日历/风格/价格/基本面
  rule TEXT,                       -- 规则描述
  sample_start TEXT, sample_end TEXT,
  corr_fwd1y REAL,                 -- 与未来1年收益相关系数
  ann REAL,                        -- 策略年化
  mdd REAL,                        -- 策略最大回撤
  calmar REAL,
  ann_base REAL,                   -- 满仓基准年化
  mdd_base REAL,
  verdict TEXT NOT NULL,           -- USABLE / LIGHT / TEMPERATURE / FALSIFIED
  note TEXT);
INSERT OR REPLACE INTO [signal] (sid,name,stype,rule,sample_start,sample_end,corr_fwd1y,ann,mdd,calmar,ann_base,mdd_base,verdict,note) VALUES('S01','MA200 趋势 + 破位保险','趋势','跌破 MA200 降仓','2005','2026',NULL,NULL,NULL,NULL,NULL,NULL,'FALSIFIED','保护代价 >> 收益，2009 -53~-65pp');
INSERT OR REPLACE INTO [signal] (sid,name,stype,rule,sample_start,sample_end,corr_fwd1y,ann,mdd,calmar,ann_base,mdd_base,verdict,note) VALUES('S02','与国债相关性 T5','相关性','相关性抬升 +0.05 降仓','2011','2026',NULL,NULL,NULL,NULL,NULL,NULL,'FALSIFIED','超额 71.7% 来自 2015+2018 两年；2008 无信号');
INSERT OR REPLACE INTO [signal] (sid,name,stype,rule,sample_start,sample_end,corr_fwd1y,ann,mdd,calmar,ann_base,mdd_base,verdict,note) VALUES('S03','股息率 5 年分位','估值','分位≤30% 卫星仓全卖 / ≥70% 全买','2006','2026',0.119,0.1633,-0.522,0.3128352490421456,0.1584,-0.662,'USABLE','唯一可用；按月检查，20年调仓11次（按日检查会抖成84次，年化降到15.84%/-62.1%）');
INSERT OR REPLACE INTO [signal] (sid,name,stype,rule,sample_start,sample_end,corr_fwd1y,ann,mdd,calmar,ann_base,mdd_base,verdict,note) VALUES('S04','股息率绝对阈值','估值','>4%持有 / 3.5-4%停止加仓 / <3.5%减仓','2006','2026',0.119,NULL,NULL,NULL,NULL,NULL,'TEMPERATURE','倒U型非单调；当前73%时间>4%');
INSERT OR REPLACE INTO [signal] (sid,name,stype,rule,sample_start,sample_end,corr_fwd1y,ann,mdd,calmar,ann_base,mdd_base,verdict,note) VALUES('S05','股债收益比','估值','股息率÷10Y国债；>2.5买 / <1.5卖','2018','2026',NULL,NULL,NULL,NULL,NULL,NULL,'FALSIFIED','<1.5(7.59%) ≈ >3.0(8.61%)；11次跌破10次正收益');
INSERT OR REPLACE INTO [signal] (sid,name,stype,rule,sample_start,sample_end,corr_fwd1y,ann,mdd,calmar,ann_base,mdd_base,verdict,note) VALUES('S06','创业板连5天跑赢','风格','创业板连5日跑赢红利 → 减仓红利','2010','2026',NULL,0.1142,-0.385,0.2966233766233766,0.1054,-0.425,'FALSIFIED','信号后红利反而更好(+0.57pp)，但组合层面降仓略优');
INSERT OR REPLACE INTO [signal] (sid,name,stype,rule,sample_start,sample_end,corr_fwd1y,ann,mdd,calmar,ann_base,mdd_base,verdict,note) VALUES('S07','6 月季节性','日历','6 月卫星仓全卖（7月买回）','2006','2026',NULL,0.1705,-0.629,0.27106518282988873,0.1584,-0.662,'LIGHT','统一70/30口径；6月均值-3.57%、t≈-2.3，但2014-2020失效；年化更高但Calmar(0.271)不及股息率分位(0.313)');
INSERT OR REPLACE INTO [signal] (sid,name,stype,rule,sample_start,sample_end,corr_fwd1y,ann,mdd,calmar,ann_base,mdd_base,verdict,note) VALUES('S08','成交额拥挤度','情绪','20日均额 3年分位≥0.7 降仓','2006','2026',-0.062,0.091,-0.538,0.1691449814126394,0.1584,-0.662,'FALSIFIED','Calmar 0.169 vs 满仓 0.239');
INSERT OR REPLACE INTO [signal] (sid,name,stype,rule,sample_start,sample_end,corr_fwd1y,ann,mdd,calmar,ann_base,mdd_base,verdict,note) VALUES('S09','波动率分位','风险','20日年化波动率 3年分位≥0.7 降仓','2006','2026',0.016,0.1102,-0.449,0.24543429844097997,0.1584,-0.662,'FALSIFIED','相关系数 0.016，无规律');
INSERT OR REPLACE INTO [signal] (sid,name,stype,rule,sample_start,sample_end,corr_fwd1y,ann,mdd,calmar,ann_base,mdd_base,verdict,note) VALUES('S10','ERP = 1/PE − 10Y','估值','ERP 分位<30% 降仓','2018','2026',0.439,0.0634,-0.203,0.31231527093596056,0.0843,-0.197,'TEMPERATURE','预测力最强但不可交易；Calmar 0.312 vs 0.428');
INSERT OR REPLACE INTO [signal] (sid,name,stype,rule,sample_start,sample_end,corr_fwd1y,ann,mdd,calmar,ann_base,mdd_base,verdict,note) VALUES('S11','股息率 − 10Y 绝对利差','估值','利差分位<30% 降仓','2018','2026',0.227,0.0859,-0.196,0.43826530612244896,0.0843,-0.197,'FALSIFIED','Calmar 0.440 ≈ 满仓 0.428');
INSERT OR REPLACE INTO [signal] (sid,name,stype,rule,sample_start,sample_end,corr_fwd1y,ann,mdd,calmar,ann_base,mdd_base,verdict,note) VALUES('S12','PE 6 个月动量','基本面','PE 6月涨幅分位≥0.7 降仓','2014','2026',-0.214,0.0545,-0.343,0.15889212827988336,0.1185,-0.425,'FALSIFIED','红利低波更差、中证红利略好，不一致');
INSERT OR REPLACE INTO [signal] (sid,name,stype,rule,sample_start,sample_end,corr_fwd1y,ann,mdd,calmar,ann_base,mdd_base,verdict,note) VALUES('S14','创业板/红利点数比价','风格','比价分位≥70% 卫星满 / ≤30% 空','2010','2026',0.394,0.0569,-0.436,0.1305045871559633,0.0604,-0.436,'FALSIFIED','预测力强(0.394)但作卫星驱动不如股息率分位(0.130 vs 0.142)；仅作监控，>0.7 是红利强买入信号');
INSERT OR REPLACE INTO [signal] (sid,name,stype,rule,sample_start,sample_end,corr_fwd1y,ann,mdd,calmar,ann_base,mdd_base,verdict,note) VALUES('S13','纯回撤阶梯','价格','15/25/35/50% 各投 25%','2006','2026',NULL,NULL,NULL,NULL,NULL,NULL,'FALSIFIED','10年均值 2.483 < 一次性 3.210；急跌时一天跌穿');

-- ── strategy ──
DROP TABLE IF EXISTS [strategy];
CREATE TABLE strategy(
  vid TEXT PRIMARY KEY,            -- v2.3
  sdate TEXT,
  params_json TEXT NOT NULL,       -- 全参数（可直接被程序读）
  backtest_json TEXT,              -- 回测结果
  note TEXT);
INSERT OR REPLACE INTO [strategy] (vid,sdate,params_json,backtest_json,note) VALUES('v2.3','2026-10-19','{"capital": 1500000, "withdrawal_rate": 0.04, "initial_annual": 60000, "layers": {"base": 0.7, "satellite": 0.3}, "assets": [{"code": "515100", "name": "红利低波100ETF景顺", "weight": 0.4, "top3_industry": 0.291, "bank_share": 0.199}, {"code": "515450", "name": "红利低波50ETF南方", "weight": 0.35, "top3_industry": 0.436, "bank_share": 0.301}, {"code": "512890", "name": "红利低波ETF华泰柏瑞", "weight": 0.25, "top3_industry": 0.583, "bank_share": 0.525}], "cash": {"code": "511990", "name": "货币ETF华宝添益", "target_months": 12}, "entry": {"mode": "immediate_plus_wait", "immediate_amount": 100000, "immediate_months": 3, "wait_amount": 1400000, "wait_deadline_months": 12, "trigger_conditions": "none"}, "signals": {"dividend_pct": {"index": "H30269", "window": 1250, "expensive": 0.3, "cheap": 0.7, "action": "satellite_full"}, "june_effect": {"month": 6, "reduced_position": 0.7, "status": "light"}, "erp_thermometer": {"index": "000922", "window": 750, "action": "display_only"}}}','{"satellite_full_switch": {"ann": 0.1633, "mdd": -0.522, "calmar": 0.313}, "buy_hold_70_30": {"ann": 0.1584, "mdd": -0.662, "calmar": 0.239}, "bootstrap_500_paths": {"survival": 0.992, "p5": 22.8, "p10": 68.2, "p50": 651.2}, "entry_crisis_premise": {"wait12m": 2.279, "lump_sum": 1.9}}','全卖优于部分降仓；不加连续N月过滤；ERP仅温度计不调仓');

-- ── data_source ──
DROP TABLE IF EXISTS [data_source];
CREATE TABLE data_source(
  did TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  kind TEXT,                       -- index / dividend / bond / etf_holding / stock / macro
  code TEXT,
  span TEXT,
  rows INTEGER,
  quality TEXT,
  location TEXT);
INSERT OR REPLACE INTO [data_source] (did,name,kind,code,span,rows,quality,location) VALUES('D01','红利低波指数（价格）','index','H30269','2006-07~2026-10',5049,'5,049 行全有效','research_kb.idx_daily');
INSERT OR REPLACE INTO [data_source] (did,name,kind,code,span,rows,quality,location) VALUES('D02','红利低波全收益指数','index','H20269','2006-07~2026-10',5049,'全有效','research_kb.idx_daily');
INSERT OR REPLACE INTO [data_source] (did,name,kind,code,span,rows,quality,location) VALUES('D03','红利低波100指数','index','930955','2006~2026',5049,'全有效','research_kb.idx_daily');
INSERT OR REPLACE INTO [data_source] (did,name,kind,code,span,rows,quality,location) VALUES('D04','红利低波100全收益','index','H20955','2006~2026',5049,'全有效','research_kb.idx_daily');
INSERT OR REPLACE INTO [data_source] (did,name,kind,code,span,rows,quality,location) VALUES('D05','中证红利（价格）','index','000922','2006~2026',5049,'全有效','research_kb.idx_daily');
INSERT OR REPLACE INTO [data_source] (did,name,kind,code,span,rows,quality,location) VALUES('D06','中证红利全收益','index','H00922','2006~2026',5049,'全有效','research_kb.idx_daily');
INSERT OR REPLACE INTO [data_source] (did,name,kind,code,span,rows,quality,location) VALUES('D07','沪深300','index','000300','2006~2026',5049,'全有效','research_kb.idx_daily');
INSERT OR REPLACE INTO [data_source] (did,name,kind,code,span,rows,quality,location) VALUES('D08','上证红利','index','000015','2006~2026',5049,'全有效','research_kb.idx_daily');
INSERT OR REPLACE INTO [data_source] (did,name,kind,code,span,rows,quality,location) VALUES('D09','股息率（TR/PR 推算）','dividend','H30269/000922/930955','2006~2026',14400,'推算值，2015 年段有误差','research_kb.div_yield');
INSERT OR REPLACE INTO [data_source] (did,name,kind,code,span,rows,quality,location) VALUES('D10','10Y 国债收益率','bond','cn10y','2018-01~2026-10',2194,'akshare bond_zh_us_rate','research_kb.macro');
INSERT OR REPLACE INTO [data_source] (did,name,kind,code,span,rows,quality,location) VALUES('D11','CPI 同比','macro','cpi_yoy','1986~2025',476,'历史序列','research_kb.macro');
INSERT OR REPLACE INTO [data_source] (did,name,kind,code,span,rows,quality,location) VALUES('D12','ETF 完整持仓','etf_holding','512890/515450/515100','2026Q2',246,'akshare fund_portfolio_hold_em','外部接口');
INSERT OR REPLACE INTO [data_source] (did,name,kind,code,span,rows,quality,location) VALUES('D13','创业板指','index','sz399006','2010-06~2026-10',3976,'sina stock_zh_index_daily','外部接口');

-- ── error_log ──
DROP TABLE IF EXISTS [error_log];
CREATE TABLE error_log(
  eid TEXT PRIMARY KEY,            -- E1..E17
  edate TEXT,
  what TEXT NOT NULL,              -- 错在哪
  impact TEXT,                     -- 后果
  fix TEXT);
INSERT OR REPLACE INTO [error_log] (eid,edate,what,impact,fix) VALUES('E1','2026-10-17','批量替换窗口时误改 rebuild_is_st.py 的 CUTOFF（2020-06→2010）','ST 重建逻辑会失效','当场恢复；此后改白名单替换');
INSERT OR REPLACE INTO [error_log] (eid,edate,what,impact,fix) VALUES('E2','2026-10-18','gate 定「夏普≥0.5」未参照资产夏普（HS300 只有 0.152）','把正常结果误判为失败','改为 ≥max(0.30, 资产夏普×2)');
INSERT OR REPLACE INTO [error_log] (eid,edate,what,impact,fix) VALUES('E3','2026-10-18','gate 定「候选池≥1500 只」未考虑 2010 年市场容量','物理上不可能满足','改为 ≥800 且 ≥当日可打分 40%');
INSERT OR REPLACE INTO [error_log] (eid,edate,what,impact,fix) VALUES('E4','2026-10-18','T5 用绝对相关阈值 0.80','实测 90.2% 天数触发，等于永久减仓','改相对抬升 +0.05');
INSERT OR REPLACE INTO [error_log] (eid,edate,what,impact,fix) VALUES('E5','2026-10-18','提交 62fe820 声称已推送，实际未推','对端拿不到任务书','此后所有推送走 push_verified.py');
INSERT OR REPLACE INTO [error_log] (eid,edate,what,impact,fix) VALUES('E6','2026-10-18','用「全期合并」结论掩盖分段趋势','把「近期在回暖」误述成「永久失效」','改为分段表述');
INSERT OR REPLACE INTO [error_log] (eid,edate,what,impact,fix) VALUES('E7','2026-10-18','G3 门禁数学上退化（Calmar 是仓位不变量）','12/12 组合全部「通过」','改为相同回撤下比较年化');
INSERT OR REPLACE INTO [error_log] (eid,edate,what,impact,fix) VALUES('E8','2026-10-18','用全期窗口评价只有部分历史的触发器','把 T5 的回撤改善错记为 0.0pp','改用共同窗口评价');
INSERT OR REPLACE INTO [error_log] (eid,edate,what,impact,fix) VALUES('E11','2026-10-18','擅自替换方案（用户问 A vs B，我直接改成采用 B）','方案选择权被 PM 越权','恢复三方案并列由用户决定');
INSERT OR REPLACE INTO [error_log] (eid,edate,what,impact,fix) VALUES('E12','2026-10-18','未验证的推断被表述为结论','无证据却当事实用于推荐','改写为「这是假设，未验证」');
INSERT OR REPLACE INTO [error_log] (eid,edate,what,impact,fix) VALUES('E13','2026-10-18','覆盖率算错（按单只 ETF 而非全部资金）','覆盖率 100% 实际只有 70%','以全部提款需求为分母');
INSERT OR REPLACE INTO [error_log] (eid,edate,what,impact,fix) VALUES('E14','2026-10-18','从覆盖率反推股息率高估 1.2-3.1pp','三层比例全部算错','股息率必须直接计算');
INSERT OR REPLACE INTO [error_log] (eid,edate,what,impact,fix) VALUES('E15','2026-10-19','对已是分位的序列又算一次分位（双重平滑）','把 S1 从 9.10%/-53.8% 误报成 13.58%/-36.4%','用单次分位重跑');
INSERT OR REPLACE INTO [error_log] (eid,edate,what,impact,fix) VALUES('E16','2026-10-19','未验证就往脚本加「连续2个月过滤」提示','若照做损失 0.6-2.4pp 年化','已删除并改为实测表述');
INSERT OR REPLACE INTO [error_log] (eid,edate,what,impact,fix) VALUES('E21','2026-10-21','现金流覆盖率算错：报 105.9%，实际 67-78%','三处错误：515450 年数用 5.80 年（实际 6.76）、515100 把 3.5 年补发当年度分红摊平、净值取值错误。后果：差点得出「分红能覆盖生活费」的错误结论','已修正为四口径披露（99.8%/77.6%/67.1%/15.3%），并加 R111 除息日净值交叉验证');
INSERT OR REPLACE INTO [error_log] (eid,edate,what,impact,fix) VALUES('E19','2026-10-20','把 5 年分位信号当作可靠工具用了多轮，未先检验股息率数据本身质量','股息率月度变化 81.6% 来自分红数据更新（非股价），5 年分位因此产生假信号：2025-09 在最便宜时判定卖出','改为绝对阈值 2.5%/4.0%；新增第九章「股息率历史位置」交叉验证');
INSERT OR REPLACE INTO [error_log] (eid,edate,what,impact,fix) VALUES('E18','2026-10-20','用窗口依赖的回测结论（R68 的 2014-2026 窗口）指导配比调整，把 515100 权重从 40% 提到 55%','515100 的优势只在 2014-2018；2019 年后消失。新配比在真实 ETF 数据（2020-2026）上少赚 4.9 万，20 年全收益也略差','退回 40/35/25；新增「银行强弱监测」只追踪不自动调仓');
INSERT OR REPLACE INTO [error_log] (eid,edate,what,impact,fix) VALUES('E17','2026-10-19','用「全仓 0/1」测信号，与「底仓永不动」结构不符','差点把 16.61%/-42.5% 当成本方案预期','用正确 70/30 结构重算');

-- ── defect_log ──
DROP TABLE IF EXISTS [defect_log];
CREATE TABLE defect_log(
  mid TEXT PRIMARY KEY,            -- M1..M11
  discovered TEXT,
  descr TEXT NOT NULL,
  severity TEXT,
  status TEXT,
  workaround TEXT);
INSERT OR REPLACE INTO [defect_log] (mid,discovered,descr,severity,status,workaround) VALUES('M8','2026-10-17','git ls-remote / fetch 超时被误判为失败','中','open','推送后独立核实远端 hash');
INSERT OR REPLACE INTO [defect_log] (mid,discovered,descr,severity,status,workaround) VALUES('M10','2026-10-17','check_delivery 的 CRLF 误报','低','fixed','换行归一化');
INSERT OR REPLACE INTO [defect_log] (mid,discovered,descr,severity,status,workaround) VALUES('M11','2026-10-19','bars_tdx.db 有脏数据（价格 0.010/0.020）','高','open','算个股回撤用 bars.db 或过滤 price<0.1');
INSERT OR REPLACE INTO [defect_log] (mid,discovered,descr,severity,status,workaround) VALUES('M12','2026-10-19','HuggingFace 直连不可用（WinError 10060）','中','fixed','用 HF_ENDPOINT=https://hf-mirror.com + HF_HUB_DISABLE_XET=1');
INSERT OR REPLACE INTO [defect_log] (mid,discovered,descr,severity,status,workaround) VALUES('M13','2026-10-19','东财 ETF 接口偶发 RemoteDisconnected','低','fixed','退化到新浪 fund_etf_category_sina 现价快照');
INSERT OR REPLACE INTO [defect_log] (mid,discovered,descr,severity,status,workaround) VALUES('M16','2026-10-20','股息率数据有「分红季」更新 artefact（6 月平均 +13.45%、7 月 -7.78%）','高','open','已规避：卫星仓改用绝对阈值，并在说明书与面板披露；数据源未修复');
INSERT OR REPLACE INTO [defect_log] (mid,discovered,descr,severity,status,workaround) VALUES('M17','2026-10-20','5 年分位窗口基准被高股息期抬高（2021-2025 把底抬到 4.50%）','高','open','已规避：改用绝对阈值，不再用相对排名');
INSERT OR REPLACE INTO [defect_log] (mid,discovered,descr,severity,status,workaround) VALUES('M18','2026-10-20','择时策略在低分红年代（2007-2013）实质失效（股息率仅 1.5%-3.5%，够不到 4.0% 买回线）','中','open','已披露：说明书与面板均标注「只在高分红年代有效」');

-- ── open_item ──
DROP TABLE IF EXISTS [open_item];
CREATE TABLE open_item(
  oid TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  priority TEXT,                   -- P1/P2/P3
  detail TEXT,
  status TEXT DEFAULT 'open');
INSERT OR REPLACE INTO [open_item] (oid,title,priority,detail,status) VALUES('O01','说明书更新到 v2.4','P1','已完成 2026-10-20：信号①整段重写为绝对阈值，含三条缺陷证据与重大局限披露','done');
INSERT OR REPLACE INTO [open_item] (oid,title,priority,detail,status) VALUES('O02','建仓启动时填 config/pension_plan.yaml 的 entry.start_date','P1','目前是 null，监控工具会显示「建仓未启动」','open');
INSERT OR REPLACE INTO [open_item] (oid,title,priority,detail,status) VALUES('O03','每季度复核行业集中度（512890 银行 52.5%）','P2','用 ak.fund_portfolio_hold_em 取最新季度','open');
INSERT OR REPLACE INTO [open_item] (oid,title,priority,detail,status) VALUES('O04','剩余 6 个视频的提炼与验证','P2','今天做了 1 个（新博主）；还有 6 个待处理','open');
INSERT OR REPLACE INTO [open_item] (oid,title,priority,detail,status) VALUES('O06','评估东方红红利低波（ROE+预期股息率，费率0.72%，半年再平衡）','P2','光总认为其编制因子优于现有三只；可选替代部分 512890','open');
INSERT OR REPLACE INTO [open_item] (oid,title,priority,detail,status) VALUES('O07','监控「账户浮亏转正所需月数」','P2','穷诸葛：一次投入 89 月 vs 分批 14 月；纳入监控工具输出','open');
INSERT OR REPLACE INTO [open_item] (oid,title,priority,detail,status) VALUES('O08','验证：股息率分位该用 5 年还是 20 年窗口','P1','已完成 2026-10-20：结论是不用分位（窗口无关），改用绝对阈值；另测六类替代方案均不如现行','done');
INSERT OR REPLACE INTO [open_item] (oid,title,priority,detail,status) VALUES('O09','阈值 2.5%/4.0% 更多数据复核','P2','已完成 2026-10-20（R101）：分期间 + 10 年滚动起点 + ±0.2pp 抖动，全部稳健；但确认优势仅来自 2006-2013，2012 年后起算无差异','done');
INSERT OR REPLACE INTO [open_item] (oid,title,priority,detail,status) VALUES('O10','配比再决策：现金流 vs 总收益','P1','现行40/35/25 现金分红覆盖仅106%(余量293元/月)，512890(25%)完全不发现金但总收益最高(13.38%)。若提到55/40/5 覆盖可到135%，但总收益下降。需用户权衡','open');
INSERT OR REPLACE INTO [open_item] (oid,title,priority,detail,status) VALUES('O11','把「按月分红是营销说法」写进说明书','P1','实测三只ETF每年只分1-3次，512890完全不分红；分红主要在7月/12月到账，必须保留现金池平滑','open');
INSERT OR REPLACE INTO [open_item] (oid,title,priority,detail,status) VALUES('O12','价值100（国证）列入观察项','P2','编制规则优秀(ROE+FCF+股息率)，但2024-10才正式运行，真实样本不足2年，与FCF同样问题','open');
INSERT OR REPLACE INTO [open_item] (oid,title,priority,detail,status) VALUES('O05','继续挖新择时信号（已不建议）','P3','13 个测完只 1 个可用，边际收益很低','paused');
