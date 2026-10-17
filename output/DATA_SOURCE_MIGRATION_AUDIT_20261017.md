# 数据源迁移审计报告（通达信 vs 程序引用）

> 生成：2026-10-17 10:00 · 审计源：`data_source_audit_20261017_095629.json` · 复现：`python risk\audit_data_sources.py`
> 目标：确认「程序里打开的库」是否都已经换成「为通达信新建的库」。

## 0. 一句话结论

**行情层切了，其它层没切。** 主行情 `bars.db` 已是通达信数据（含增量），但**财务/基础信息/市值/财务质量/估值**仍大量跑在旧免费源库上，而本轮新建的 `finance_csmar.db`、`tdx_meta.db` 几乎没被业务代码用起来。

| 状态 | 代码文件数 |
|---|---|
| ✅ 只用新库（已切换） | **98** |
| ⚠️ 新旧混用（半切换） | **56** |
| ❌ 只用旧库（完全未切换） | **31** |

## 1. 主库确认（第三次核实，含实测）

| 证据 | 结果 |
|---|---|
| 代码默认路径 | `data/cache.py:41` → `DEFAULT_DB = CACHE_DIR / "bars.db"` |
| 引用规模 | **304 处 / 140 个代码文件** |
| 内容标记 | `daily_bar` 15,700,238 行；`source` = tdx 15,672,362 + tdx_api 27,860 + **baostock 16（残留）** |
| 旧表归档 | `daily_bar_legacy`（切换前 13.42M 行）仍在库内 |
| 写权限实测 | `BEGIN IMMEDIATE` 成功取得写锁 → **主库当前可写** |
| 遗留机制 | `bars_incr.db` 仅 24 KB 空库 → 旧的「主库只读→写入路由」**已不生效** |

**结论**：主库 = `C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant\data\cache\bars.db`，内容已是通达信，且可写、可读、被 140 个代码文件引用。

待清理（很小的残留）：`daily_bar` 里 16 行 `source='baostock'`、`adjust='none'`。

## 2. 新库清单 × 实际使用度

| 新库 | 内容 | 代码引用 | 结论 |
|---|---|---|---|
| `bars.db` | 主行情库（已原地切换为通达信 qfq，2000-2026，1,570 万行） | 304 处 / 140 个文件 | ✅ 主力，已全面使用 |
| `bars_tdx.db` | 通达信源/中间库（qfq 15.67M + unadj 0.70M + adj_factor 1,848 万） | 34 处 / 18 个文件 | ✅ 增量链路在用 |
| `tdx_meta.db` | 通达信元数据（universe/stock_info_tdx/index_member/sector/每日快照/is_st_inferred） | 7 处 / 5 个文件 | ⚠️ 只有 5 个文件在用（元数据几乎闲置） |
| `finance_csmar.db` | CSMAR 财务（fin_core 年度 / fin_core_q 季度，含 publish_date） | 5 处 / 4 个文件 | ⚠️ 只有 4 个文件在用（CSMAR 财务几乎闲置） |
| `datayes_basic.db` | 通联基础清单（sec_listed / sec_delisted 退市股清单，免费接口） | 7 处 / 4 个文件 | ⚠️ 只有 4 个文件在用（退市清单未接入主链） |

## 3. 旧库清单 × 是否还能停

| 旧库 | 代码引用 | 通达信可替代？ | 替代方案 | 优先级 |
|---|---|---|---|---|
| `finance.db` | **64 处 / 39 个文件** | ✅ 可替代 | finance_csmar.db（fin_core/fin_core_q，含 publish_date，年度 95,435 / 季度 325,903） | P1 |
| `stock_basic.db` | **58 处 / 38 个文件** | ✅ 可替代 | tdx_meta.db → universe(5,581) / stock_info_tdx(63 列，含 IsSTGP/IsQuitGP/指数归属) | P1 |
| `hist_mv.db` | **36 处 / 24 个文件** | ⚠️ 需新建管道 | tdx_meta.ActiveCapital(万股) × 当日 close → 流通市值；月频聚合即可 | P2 |
| `finance_quality.db` | **19 处 / 14 个文件** | ⚠️ 需重算 | CSMAR 指标（ROE/ROA/毛利率等）在 fin_core 内已有，需重写 quality 表 | P2 |
| `valuation.db` | **18 处 / 9 个文件** | ⚠️ 部分可替代 | 通达信 get_more_info（Beta/PE/市值/股息率）；换手率已可从 ActiveCapital 算；isST 2020+ 短期仍需保留 | P2 |
| `industry.db` | **4 处 / 3 个文件** | ⚠️ 部分可替代 | 通达信 get_sector_list / get_zzgz_stocklist；申万 162 行体量小，可最后处理 | P3 |
| `lhb.db` | **11 处 / 5 个文件** | ❌ 通达信无 | 龙虎榜只在东财有 → **不能停**，保留并明确标注为外部补充源 | — |
| `limitup.db` | **7 处 / 3 个文件** | ❌ 通达信无 | 涨停/炸板池只在东财有 → **不能停** | — |
| `rzrq.db` | **2 处 / 2 个文件** | ❌ 通达信无 | 两融明细只在东财有 → **不能停** | — |
| `consensus.db` | **2 处 / 2 个文件** | ❌ 通达信无 | 一致预期只在同花顺有 → **不能停** | — |
| `minute.db` | **22 处 / 9 个文件** | ✅ 死引用 | 文件已不存在（改走 parquet），清掉引用即可 | P0 |
| `bars_incr.db` | **5 处 / 1 个文件** | ✅ 可废弃 | 主库现已可写，写入路由机制失效 → 移除 DailyCache 里的双库路由 | P0 |

> **不能停的旧库（通达信无对应）**：`lhb.db`、`limitup.db`、`rzrq.db`、`consensus.db`。这 4 个必须保留，并在文档/代码注释里明确标注为「外部补充源」，否则「全部切到通达信」这个目标会以断功能为代价。

## 4. 关键运行链路 → 数据库依赖

N=新库（通达信）、O=旧库（待停）、U=引用但文件不存在（断链）

| 链路 | 说明 | 新库 | 旧库 | 断链 | 判定 |
|---|---|---|---|---|---|
| `data/daily_pipeline.py` | 每日全链（18:30 计划任务） | bars.db | minute.db | — | ⚠️ 半切换 |
| `data/after_close_scan.py` | 盘后扫描（17:35 计划任务） | — | — | — | 无库引用 |
| `dev_auto.py` | 4h 巡检驱动 | — | — | unified.db | — |
| `deck/deck_server.py` | 门户服务端（8787） | bars.db | — | unified.db | ✅ 已切换 |
| `deck/live_api.py` | 门户 API 层 | bars.db | stock_basic.db | unified.db | ⚠️ 半切换 |
| `deck/system_live.py` | 门户健康面板 | bars.db | finance.db,finance_quality.db,hist_mv.db,minute.db | — | ⚠️ 半切换 |
| `factors/opportunities/scan.py` | 机会扫描（核心） | bars.db | finance.db,finance_quality.db,hist_mv.db,stock_basic.db | — | ⚠️ 半切换 |
| `factors/opportunities/tech_pitch.py` | 科技 Pitch | — | — | — | 无库引用 |
| `factors/import_qf_pool.py` | 因子池 → 面板加载 | bars.db | finance.db,hist_mv.db | — | ⚠️ 半切换 |
| `factors/portfolio_builder.py` | 组合构建（15 只） | bars.db | hist_mv.db,stock_basic.db | — | ⚠️ 半切换 |
| `factors/combo_portfolio.py` | 组合回测 | bars.db | — | — | ✅ 已切换 |
| `factors/formula_miner.py` | LLM 因子挖掘 | bars.db | finance.db | — | ⚠️ 半切换 |
| `factors/fscore.py` | F-Score 财务质量 | — | finance_quality.db | — | ❌ 未切换 |
| `factors/reproduce_factors.py` | 因子复现 | bars.db | finance.db,lhb.db,valuation.db | — | ⚠️ 半切换 |
| `risk/stop_monitor.py` | 止损监测 | bars.db | — | finance_ts.db | ✅ 已切换 |
| `risk/position_stop_check.py` | 持仓止损检查 | bars.db | — | finance_ts.db | ✅ 已切换 |
| `risk/take_profit_check.py` | 止盈检查 | bars.db | stock_basic.db | — | ⚠️ 半切换 |
| `backtest/bt_runner.py` | 回测引擎 | bars.db | hist_mv.db | finance_ts.db | ⚠️ 半切换 |
| `data/cache.py` | DailyCache（统一读写入口） | bars.db | bars_incr.db | — | ⚠️ 半切换 |
| `data/tdx_daily_update.py` | 通达信增量（新） | bars_tdx.db,tdx_meta.db | — | — | ✅ 已切换 |
| `data/fix_bars_increment.py` | unadj→qfq 合并（新） | bars.db,bars_tdx.db | — | — | ✅ 已切换 |

## 5. 完全未切换的代码文件（❌ 只用旧库）

- `data/batch_minute_7z.py` — 旧库：minute.db
- `data/build_unified_db.py` — 旧库：finance.db, finance_quality.db；断链：epu.db, factor_pitch_perf.db, finance_ts.db, gdhs_full.db, lhb_full.db, macro.db, rzrq_full.db, shebao.db, stock_dividend.db, unified.db
- `data/bulk_loader_akshare.py` — 旧库：stock_basic.db
- `data/daily_accumulate.py` — 旧库：lhb.db, limitup.db
- `data/fetch_consensus_ths.py` — 旧库：consensus.db, stock_basic.db
- `data/fetch_quality.py` — 旧库：finance_quality.db, stock_basic.db
- `data/fetch_quality_backup.py` — 旧库：finance_quality.db, stock_basic.db
- `data/fetch_quality_full.py` — 旧库：finance_quality.db, stock_basic.db
- `data/fetch_quality_tushare.py` — 旧库：finance_quality.db, stock_basic.db
- `data/fetch_rzrq_em.py` — 旧库：rzrq.db, stock_basic.db
- `data/fetch_stock_basic.py` — 旧库：stock_basic.db
- `data/ingest_minute.py` — 旧库：minute.db
- `data/inspect_schemas.py` — 旧库：finance.db, hist_mv.db；断链：finance_ts.db
- `data/minute_reader.py` — 旧库：minute.db
- `data/watch_minute_unlock.py` — 旧库：minute.db
- `deck/archive_old/dashboard_research_20260811_101312.html` — 旧库：finance.db
- `deck/archive_old/dashboard_research_20260811_101518.html` — 旧库：finance.db
- `deck/archive_old/dashboard_research_lib_20260811_101549.html` — 旧库：finance.db
- `deck/archive_old/dashboard_research_lib_20260811_102027.html` — 旧库：finance.db
- `deck/archive_old/dashboard_research_lib_20260811_104206.html` — 旧库：finance.db
- `deck/dashboard_research.html` — 旧库：finance.db
- `deck/dashboard_research_lib.html` — 旧库：finance.db
- `factors/_debug_st_filter.py` — 旧库：stock_basic.db
- `factors/_inspect_db.py` — 旧库：finance.db, hist_mv.db, stock_basic.db
- `factors/fscore.py` — 旧库：finance_quality.db
- `factors/fundamental.py` — 旧库：finance.db
- `risk/_check_mv_unit.py` — 旧库：hist_mv.db
- `risk/beneish.py` — 旧库：finance.db, finance_quality.db
- `risk/stock_risk.py` — 旧库：finance.db, finance_quality.db
- `scripts/bench_lp.py` — 旧库：stock_basic.db
- `validation/test_ewt_pt_backtest.py` — 旧库：hist_mv.db

## 6. 半切换的代码文件（⚠️ 新旧混用）

共 56 个。以下按「引用了哪些旧库」排序，优先处理引用旧库多的：

- `risk/_gap_check.py` — 新：bars_tdx.db｜**旧：consensus.db, finance.db, finance_quality.db, hist_mv.db, industry.db, lhb.db, limitup.db, rzrq.db, stock_basic.db, valuation.db**
- `data/audit_data_assets.py` — 新：bars.db｜**旧：finance.db, finance_quality.db, hist_mv.db, lhb.db, minute.db, stock_basic.db**
- `data/fetcher_advanced.py` — 新：bars.db｜**旧：industry.db, lhb.db, limitup.db, valuation.db**
- `deck/system_live.py` — 新：bars.db｜**旧：finance.db, finance_quality.db, hist_mv.db, minute.db**
- `factors/opportunities/scan.py` — 新：bars.db｜**旧：finance.db, finance_quality.db, hist_mv.db, stock_basic.db**
- `data/sector_research.py` — 新：bars.db｜**旧：finance.db, hist_mv.db, stock_basic.db**
- `data/subj_quant_stats.py` — 新：bars.db｜**旧：finance.db, hist_mv.db, stock_basic.db**
- `factors/opportunities/backtest_winrate.py` — 新：bars.db｜**旧：finance.db, finance_quality.db, stock_basic.db**
- `factors/reproduce_factors.py` — 新：bars.db｜**旧：finance.db, lhb.db, valuation.db**
- `risk/_dump_schema.py` — 新：bars.db｜**旧：finance.db, hist_mv.db, stock_basic.db**
- `risk/_inspect_schema.py` — 新：bars.db｜**旧：finance.db, hist_mv.db, stock_basic.db**
- `risk/data_diagnostic.py` — 新：bars.db｜**旧：finance.db, hist_mv.db, stock_basic.db**
- `data/build_stock_info.py` — 新：bars_tdx.db, datayes_basic.db｜**旧：industry.db, stock_basic.db**
- `factors/import_qf_pool.py` — 新：bars.db｜**旧：finance.db, hist_mv.db**
- `factors/opportunities/stock_check.py` — 新：bars.db｜**旧：finance_quality.db, stock_basic.db**
- `factors/portfolio_builder.py` — 新：bars.db｜**旧：hist_mv.db, stock_basic.db**
- `factors/validate_deep.py` — 新：bars.db｜**旧：hist_mv.db, stock_basic.db**
- `factors/verify_bp_consistency.py` — 新：bars.db｜**旧：finance.db, valuation.db**
- `risk/data_audit.py` — 新：bars.db｜**旧：finance.db, hist_mv.db**
- `strategy/base_pool.py` — 新：bars.db｜**旧：finance.db, stock_basic.db**
- `strategy/ranking_v2.py` — 新：bars.db｜**旧：finance.db, stock_basic.db**
- `ui_v2/pages/subj_quant.html` — 新：bars.db｜**旧：finance.db, stock_basic.db**
- `validation/diag_base_pool.py` — 新：bars.db｜**旧：finance.db, stock_basic.db**
- `validation/retail_crowd_recheck.py` — 新：bars.db｜**旧：hist_mv.db, stock_basic.db**
- `backtest/backtest_all_factors.py` — 新：bars.db｜**旧：hist_mv.db**
- `backtest/backtest_script1.py` — 新：bars.db｜**旧：hist_mv.db**
- `backtest/bt_runner.py` — 新：bars.db｜**旧：hist_mv.db**
- `data/build_hist_mv.py` — 新：bars.db｜**旧：hist_mv.db**
- `data/cache.py` — 新：bars.db｜**旧：bars_incr.db**
- `data/convert_7z_to_parquet.py` — 新：bars.db｜**旧：minute.db**
- `data/daily_pipeline.py` — 新：bars.db｜**旧：minute.db**
- `data/fetch_bars_history_baostock.py` — 新：bars.db｜**旧：stock_basic.db**
- `data/fetch_bars_history_tencent.py` — 新：bars.db｜**旧：stock_basic.db**
- `data/fetcher_finance.py` — 新：bars.db｜**旧：finance.db**
- `data/fetcher_hist_mv.py` — 新：bars.db｜**旧：hist_mv.db**
- `data/incremental_daily.py` — 新：bars.db｜**旧：stock_basic.db**
- `data/infer_hist_st.py` — 新：bars.db, tdx_meta.db｜**旧：valuation.db**
- `data/ingest_minute_7z.py` — 新：bars.db｜**旧：minute.db**
- `data/patch_is_st.py` — 新：bars_tdx.db｜**旧：valuation.db**
- `data/rank_live.py` — 新：bars.db｜**旧：stock_basic.db**
- `deck/live_api.py` — 新：bars.db｜**旧：stock_basic.db**
- `factors/formula_miner.py` — 新：bars.db｜**旧：finance.db**
- `factors/opportunities/pitch_replay.py` — 新：bars.db｜**旧：finance.db**
- `factors/opportunities/pitch_track.py` — 新：bars.db｜**旧：stock_basic.db**
- `factors/opportunities/tech_pitch_v3.py` — 新：bars.db｜**旧：finance.db**
- `factors/validate_all_factors.py` — 新：bars.db｜**旧：finance.db**
- `factors/walk_forward.py` — 新：bars.db｜**旧：stock_basic.db**
- `logs/_probe_incr_fields.py` — 新：bars.db, bars_tdx.db｜**旧：valuation.db**
- `logs/_probe_maindb_turn.py` — 新：bars.db, bars_tdx.db, tdx_meta.db｜**旧：valuation.db**
- `risk/_check_mv_unit2.py` — 新：bars.db｜**旧：hist_mv.db**
- `risk/_check_valuation.py` — 新：bars_tdx.db｜**旧：valuation.db**
- `risk/take_profit_check.py` — 新：bars.db｜**旧：stock_basic.db**
- `risk/verify_csmar.py` — 新：finance_csmar.db｜**旧：finance.db**
- `strategy/pitch.py` — 新：bars.db｜**旧：finance.db**
- `strategy/portfolio.py` — 新：bars.db｜**旧：stock_basic.db**
- `validation/test_factor_combo.py` — 新：bars.db｜**旧：finance.db**

## 7. 断链（代码引用了但文件不存在）

| 库名 | 代码处 | 代码文件 |
|---|---|---|
| `unified.db` | 28 | 7 |
| `finance_ts.db` | 19 | 12 |
| `macro.db` | 14 | 6 |
| `epu.db` | 8 | 5 |
| `factor_pitch_perf.db` | 5 | 2 |
| `gdhs_full.db` | 4 | 3 |
| `paper.db` | 4 | 2 |
| `subj_quant.db` | 3 | 2 |
| `consensus_snap.db` | 2 | 1 |
| `factor_pool.db` | 2 | 1 |
| `lhb_full.db` | 2 | 2 |
| `pools.db` | 2 | 1 |
| `rzrq_full.db` | 2 | 2 |
| `datayes_sample.db` | 1 | 1 |
| `lhb2.db` | 1 | 1 |
| `minute_test.db` | 1 | 1 |
| `paper_test.db` | 1 | 1 |
| `pools_test.db` | 1 | 1 |
| `shebao.db` | 1 | 1 |
| `stock_dividend.db` | 1 | 1 |

这些引用**不会报错但会静默降级**（大多包在 try/except 里），是「看起来跑通、实际没数据」的典型来源。

## 8. 建议的迁移顺序（按风险与收益）

| 阶段 | 内容 | 为什么先做这个 |
|---|---|---|
| **P0** | 清死引用：`minute.db`(9 文件)、`bars_incr.db` 路由（`data/cache.py`） | 零风险、纯减法；消除误导 |
| **P0** | 清 `bars.db` 里 16 行 baostock 残留 | 让「单一数据源」这句话成立 |
| **P1** | `finance.db`(39 文件) → `finance_csmar.db` | 旧库无披露日（PIT 不可用），CSMAR 有 publish_date，收益最大 |
| **P1** | `stock_basic.db`(38 文件) → `tdx_meta` | 基础信息是几乎所有脚本的横切依赖 |
| **P2** | `hist_mv.db`(24) → ActiveCapital×close 自算 | 组合构建/回测的市值中性化依赖它 |
| **P2** | `finance_quality.db`(14)、`valuation.db`(9) | 需重算/需新接口，工作量中等 |
| **P3** | `industry.db`(3) | 体量最小 |
| **例外** | `lhb.db`/`limitup.db`/`rzrq.db`/`consensus.db` **保留** | 通达信无对应，停了就断功能 |

> 建议做法：**不改 487 处调用点**，而是在 `data/cache.py` 这一层做「源适配器」——`finance.db` 的读取统一收口到一个函数，内部改成读 `finance_csmar.db` 并做字段映射（列名/代码格式/单位）。这样 P1 只需改 1-2 个文件，而不是 39 个。

## 9. 复现命令

```powershell
cd "C:\Users\Administrator\ DSH 量化交易系统\deepseek-harness-quant"
python risk\audit_data_sources.py      # 产出 logs/data_source_audit_<ts>.json
python risk\report_data_sources.py     # 生成本报告
```

*本报告由脚本生成，文件清单来自静态扫描，可直接核对每一处 file:line（见审计 JSON 的 sites 字段）。*