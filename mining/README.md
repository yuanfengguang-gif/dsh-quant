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
