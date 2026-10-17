# reports/ —— 两机结果交换区（进 Git，用于跨机器传递运行结果）

## 为什么有这个目录

`logs/` 和 `output/` 被 `.gitignore` 排除（里面是大体积运行产物），
但**两台机器之间需要交换"小体积的结果文件"**（JSON 指标 / 回测日志 / 验收输出）。
这个目录就是为此准备：**只有几十 KB 的文本/JSON，可以放心进 Git**。

## 用法（在跑任务的那台机器上）

```powershell
# 1) 把结果文件拷进这里
cd "D:\Programs\DSH Projects\DSH Quant"
Copy-Item logs\pb_*.json reports\ -Force
Copy-Item logs\_combo2.txt reports\ -Force

# 2) 提交并推送
git add reports
git commit -m "reports: 组合层对照实验 P0/P1 结果"
git push
```

然后在另一台机器上 `git pull` 即可拿到。

## 不要放什么

| 内容 | 原因 |
|---|---|
| `*.db` / `*.parquet` / `*.csv` 大文件 | 体积大，走移动硬盘 |
| `data/`、`logs/` 整目录 | 运行产物，且已被忽略 |
| 含 API 密钥的配置 | 安全 |

## 结果文件命名建议

```
pb_bp_only.json          # 单因子基线：仅 bp_value
pb_turn_only.json        # 单因子基线：仅 turn_mid_prox
pb_noneutral.json        # 关中性化
pb_noregime.json         # 关择时
pb_nofilter.json         # 关过滤
pb_top20.json            # TopN=20
pb_rb120.json            # 调仓 120 日
pb_ex2014.json           # 剔除 2014-2015（start=2016-01-01）
```
