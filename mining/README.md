# mining/ —— 因子挖掘子项目

本目录把外部因子挖掘工具并入主项目，统一版本管理。

## 目录

| 子目录 | 来源 | 说明 |
|---|---|---|
| `AI-Quant-Factor-Miner/` | https://github.com/IIcodehub/AI-Quant-Factor-Miner | LLM 驱动的因子公式生成 + 沙箱执行 + 回测打分 |

## ⚠️ 并入时的四个注意点（实测）

### 1. 上游没有 LICENSE
`IIcodehub/AI-Quant-Factor-Miner` 仓库内**未提供 LICENSE 文件**。
→ 仅作**本地私有使用**；若要对外开源本仓库，必须先联系上游取得授权，或把本目录移出。

### 2. 上游没有 requirements.txt
已由依赖扫描补齐（`pandas` / `python-dotenv` / `openai` / `google-generativeai`）。

### 3. 数据格式是 parquet，不是我们的 bars.db
上游 `data_loader/loader.py`：
```python
df_stock = pd.read_parquet(stock_path)
df_index = pd.read_parquet(index_path)
```
→ 需要先从 `data/cache/bars.db` 导出两份 parquet（股票面板 + 指数）。
**parquet 不进 Git**（`.gitignore` 已排除 `*.parquet`），新机要自己生成。

**导出命令**（在项目根目录执行，已验证可跑通，约 8 分钟 / 773 MB）：
```powershell
python scripts\migration\export_parquet_for_miner.py
```
输出的列名严格对齐上游 `config/settings.py` 的 `STOCK_COLUMNS_DESC` / `INDEX_COLUMNS_DESC`：

| 文件 | 行数（实测） | 列 |
|---|---|---|
| `mining\AI-Quant-Factor-Miner\data\data.parquet` | 13,798,233 | TradingDay, SecuCode, PrevClosePrice, OpenPrice, HighPrice, LowPrice, ClosePrice, TurnOverVolume, TurnOverValue, TurnOverRate, FloatMarketValue |
| `mining\AI-Quant-Factor-Miner\data\index.parquet` | 4,074 | TradingDay, HS300, ZZ500, ZZ1000, SZ |

口径说明：
- 价格 = **前复权（qfq）**，与主项目因子链一致
- `TurnOverRate` = **百分数**（0.83 表示 0.83%）；如需小数用 `--turn-unit ratio`
- `FloatMarketValue` = 元（取自 `tdx_base.daily.circ_mv` × 10000，原单位万元）
- 指数列：`HS300` 用本地 `bars.db` 的 `SH.000300`；`ZZ500/ZZ1000/SZ` 走通达信（需客户端运行，失败会自动留空）

### 4. 环境变量名与主项目不一致
上游读：`DEEPSEEK_API_KEY` / `KIMI_API_KEY` / `QWEN_API_KEY` / `ZHIPU_API_KEY`（见 `config/settings.py`）
主项目 `.env` 里是：`DSH_API_KEY` / `ARK_API_KEY` / `OPENAI_API_KEY` 等
→ 跑之前需在环境里补一份映射，例如：
```powershell
$env:DEEPSEEK_API_KEY = $env:DSH_API_KEY
```

## 未并入的内容

`_QF-LLM-assets/`（678.7 MB，puppeteer 的 node_modules + Chromium）**不并入 Git**。
如需要，在新机单独：
```powershell
mkdir _QF-LLM-assets; cd _QF-LLM-assets
npm init -y
npm install puppeteer-core
```
