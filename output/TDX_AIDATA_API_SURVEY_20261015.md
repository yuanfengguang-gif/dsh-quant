# 通达信 TdxAiData API 能力盘点报告

> 环境：DSH 技能目录 `C:\Users\Administrator\.dsh\skills\tdx-aidata\`
> 引擎：tdxaidata **v1.2.2**（官方 7 件套）
> 日期：2026-10-15

---

## 一、环境就绪状态

| 体检项 | 结果 |
|---|---|
| 引擎 import | ✅ v1.2.2 |
| Token（ini） | ✅ 已写入 |
| DLL 4 件 | ✅ mfc100 / msvcp100 / msvcr100 / TdxAiData |
| 连通性 | ✅ 已通过 |

### ⚠️ 关键坑：ini 文件不能带 UTF-8 BOM

**现象**：一切配置正确，但所有接口返回 `[错误] Connection failed`
**根因**：`TdxAiData.ini` 带 UTF-8 BOM（`EF BB BF`）→ C++ DLL 把 BOM 当成第一个 section 名的一部分 → 读不到 `[TcHqHost]` → 连接失败
**修复**：用**无 BOM 的 UTF-8** 重写 ini
**验证**：`get_trading_dates('SH','20260101','20260110')` → `['20260105'...'20260109']` ✅

---

## 二、API 能力清单（实测 20+ 接口）

### 调用约定（踩坑记录）
| 项 | 正确写法 |
|---|---|
| 证券代码 | **带后缀**：`600519.SH` / `000001.SZ` |
| K 线周期 | **`1d`**（不是 `day`） |
| 股票列表 | `get_stock_list(market=0, list_type=0)` → 22,126 字符 |
| 行情 | `get_market_data(stock_list=[...], period="1d", count=N)` |

### ✅ 可用接口一览

| 类别 | 接口 | 实测返回 |
|---|---|---|
| **行情** | `get_market_data` | Open/High/Low/Close/Volume/Amount（日线） |
| | `get_minute_data` | 分钟时序（含 Average 均价） |
| | `get_call_auction` | **集合竞价逐笔**（105 行：LeaveQty/Price/Time/Volume） |
| | `get_tick_data` | 逐笔成交 |
| **财务** | `get_financial_data` | **按报告期 + `announce_time` 公告时间** ★ |
| | `get_stock_info` | **J_\* 财务快照**（净利/净资产/主营收入/每股净资产…） |
| **基础信息** | `get_stock_info` | **`IsSTGP` 是否ST / `IsQuitGP` 是否退市** ★ |
| | | `BelongHS300` 是否沪深300 / `BelongHSGT` / `BelongRZRQ` |
| | `get_gb_info` | 股本（Ltgb 流通 / Zgb 总） |
| | `get_more_info` | Beta / 股息率 / PE / **流通市值** / 历史高低 / 发行价 |
| **除权** | `get_divid_factors` | **完整除权除息明细**（分红/送股/配股，2002-2026） |
| **分类** | `get_sector_list` | 板块列表（880xxx.SH） |
| | `get_stock_list_in_sector` | 板块成分股 |
| | `get_zzgz_stocklist` | **指数成分股**（如 000300.SH 沪深300） |
| | `get_stock_list` | 全市场股票列表 |
| **其他** | `get_trading_dates` | 交易日历 |
| | `get_zdt_data` / `get_kzz_info` / `get_relation` / `get_pricevol` | 涨跌停 / 可转债 / 关联 / 量价 |

---

## 三、🎁 三大惊喜（对项目价值极高）

### 惊喜 1：`IsSTGP` + `IsQuitGP` —— **直接解决 is_st 缺陷**
```python
get_stock_info('600519.SH')
→ {'IsSTGP': '0',      # 是否 ST 股  ★
   'IsQuitGP': '0',    # 是否已退市 ★
   'BelongHS300': '1', # 沪深300 成分
   'BelongRZRQ': '1',  # 融资融券标的
   ...}
```
**意义**：项目此前 is_st 只能靠 `valuation.db`（2020+）+ 名称近似（2020前）。通达信**逐股实时标记**，且可批量（`get_stock_info_batch`）。

### 惊喜 2：`announce_time` —— **直接根治 F-5 前视偏差**
```python
get_financial_data('600519.SH', ...)
→  FN20240101  announce_time  tag_time
    ...        20260417       20251231   ← 公告日 ★
```
**意义**：本地 `finance.db` 没有披露日，只能用"60 天滞后代理"。通达信**直接给公告时间** → PIT 精确对齐。

### 惊喜 3：`get_divid_factors` + `get_zzgz_stocklist` + 集合竞价
- **除权除息明细**：分红/送股/配股全历史 → 可**自算复权因子**（与通达信日K文件交叉验证）
- **指数成分股**：`get_zzgz_stocklist('000300.SH')` → 沪深300 全部成分 → **基准构建 / 指数增强**
- **集合竞价逐笔**：09:15~09:25 完整时序 → **执行层优化**（挂单价位、成交概率）

---

## 四、单位注意（实测）

| 字段 | 单位 | 示例 |
|---|---|---|
| Volume | **股** | 3,155,604 |
| Amount | **万元** | 404,285.75（= 40.4 亿元） |
| 市值（Ltsz） | 亿元 | 16461.07 |

---

## 五、对项目数据需求的满足度

| 项目需求 | 通达信 API | 状态 |
|---|---|---|
| 日线行情 OHLCV | ✅ `get_market_data` | **满足** |
| 复权因子 | ✅ `get_divid_factors` 自算 | **满足** |
| **is_st** | ✅ `IsSTGP` | **满足**（优于现有） |
| **退市标记** | ✅ `IsQuitGP` | **满足**（优于现有） |
| **财务 + 披露日** | ✅ `get_financial_data` + `announce_time` | **满足**（PIT 精确） |
| 流通市值 | ✅ `get_more_info.Ltsz` | 满足 |
| 股本 | ✅ `get_gb_info` | 满足 |
| 行业/板块 | ✅ `get_sector_list` | 满足 |
| **指数成分** | ✅ `get_zzgz_stocklist` | **满足**（此前缺口） |
| 集合竞价/分钟/逐笔 | ✅ | **超出需求**（执行层可用） |
| 一致预期/分析师 | ❌ | 缺（需另找） |
| 股东户数 | ✅ `J_gdrs` | 满足 |

**结论**：通达信 API 能满足项目**除"另类数据（分析师/新闻）"外的全部数据需求**，且解决了 3 个长期缺陷（is_st、退市、披露日）。

---

## 六、性价比判断

| 项 | 通联 | 通达信 API |
|---|---|---|
| 计费 | 按行（11.16 万点/行） | **按积分**（用户 10,000 积分） |
| 行情全历史 | ~17 万元 | **积分制，成本极低** |
| 财务 + 披露日 | 按行计费 | ✅ 含 |
| ST/退市 | 需额外接口 | ✅ 含 |
| 指数成分 | 需额外接口 | ✅ 含 |

**结论**：**通达信 API 性价比显著优于通联**，建议作为项目主数据源。

---

## 七、落地文件

| 文件 | 路径 |
|---|---|
| 技能目录（7 件套） | `C:\Users\Administrator\.dsh\skills\tdx-aidata\` |
| 环境体检脚本 | `C:\Users\Administrator\.dsh\skills\tdx-aidata\env_check.py` |
| 连通性测试 | `C:\Users\Administrator\.dsh\skills\tdx-aidata\test_conn.py` |
| API 盘点脚本 | `C:\Users\Administrator\.dsh\skills\tdx-aidata\api_survey.py`（及 v2/v3） |
| 官方说明 | `C:\Users\Administrator\.dsh\skills\tdx-aidata\SKILL.md` |
| 使用文档 | `C:\Users\Administrator\.dsh\skills\tdx-aidata\docs\tdxaidata使用文档.md` |

*报告生成：本机 · 2026-10-15*
