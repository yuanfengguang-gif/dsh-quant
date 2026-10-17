# skills/ —— 项目相关技能（DSH 技能源）

这些技能原本在 DSH 家目录 `~/.dsh/skills/` 下，`git clone` 拿不到。
为了让新电脑能直接跑因子挖掘，把它们收进仓库（合计仅 ~267 KB）。

## 安装到新电脑

```powershell
# 在项目根目录执行，把技能拷进 DSH 家目录
Copy-Item -Path "skills\*" -Destination "$env:USERPROFILE\.dsh\skills\" -Recurse -Force
```

验证：
```powershell
Get-ChildItem "$env:USERPROFILE\.dsh\skills" -Directory | Where-Object Name -match 'factor|alpha|niu-san|qf-llm|backtest' | Select-Object Name
```

## 各技能作用

| 技能 | 作用 |
|---|---|
| `factor-mining-workflow` | **完整因子挖掘工作流**（定域→建词表→生成→校验→ICIR初筛→去重→组合层T+1→分年度holdout→正交性→容量→归档） |
| `alpha-gpt-factor-mining` | AlphaGPT 方法论：特征+算子公式语言、StackVM 求值、REINFORCE 迭代 |
| `alpha-gpt-researcher` | 研究员自我档案：方法论 + 资产地图 + 踩坑记录 |
| `qf-llm` | autoresearch 式自主闭环（AI 每轮改因子代码，固定评分标准） |
| `backtest-acceptance` | 回测验收标准（T+1/成本/数据边界/结论分级） |
| `github-maintainer` | 仓库维护 + 主系统上下文 |
| `niu-san-*`（7 个） | 牛散/游资手法蒸馏 → 可转因子假设来源 |

## 注意

- `tdx-aidata`（通达信 API，含 8 个 DLL / 14.5 MB）**不在这里**，体积大且有二进制，
  走移动硬盘的 `03_项目外依赖\.dsh_skills_tdx-aidata`。
- 其余的通用技能（视频/图像类）与本项目无关，不需要迁。
