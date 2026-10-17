# 前沿经济学/金融学论文 → 股市因子挖掘（20 篇，2026-10-15）

> 说明：以国外（英文）顶刊/工作论文为主，2020–2025 年，聚焦「经济研究结论可转化为横截面收益预测因子」。
> 全部经联网核实作者/年份/期刊，无编造。分 4 个主题 × 5 篇。

---

## 主题 A：机器学习与 AI 资产定价（5 篇）

### A1. Empirical Asset Pricing via Machine Learning（基于机器学习的实证资产定价）
- **作者**：Shihao Gu、Bryan T. Kelly、Dacheng Xiu
- **时间**：2020，Review of Financial Studies 33(5): 2223–2273
- **内容**：系统比较线性与多种 ML 方法（正则化线性、树、神经网络）预测股票横截面收益，ML 在样本外 R²、夏普与组合收益上大幅优于线性基准，非线性与变量交互是主要增益。
- **可转因子**：用 94 个公司特征训练梯度提升树/神经网络，输出个股预期收益，按预测值多空分组，提取特征重要性与非线性交互复合信号。
- **链接**：https://academic.oup.com/rfs/article-abstract/33/5/2223/5758276

### A2. The Virtue of Complexity in Return Prediction（收益预测中复杂性的价值）
- **作者**：Bryan T. Kelly、Semyon Malamud、Kangying Zhou
- **时间**：2024，Journal of Finance 79(1): 459–503
- **内容**：证明在更复杂（多特征、非线性）预测空间里样本外预测力与组合表现更强，并提出控制复杂度的正则化方法避免过拟合。
- **可转因子**：在高维特征集上做带正则化的 ML 预测，取「预测收益分位数排序 + 复杂度控制后的残差 alpha」作多空信号。
- **链接**：https://onlinelibrary.wiley.com/doi/full/10.1111/jofi.13298

### A3. Deep Learning in Asset Pricing（深度学习资产定价）
- **作者**：Luyang Chen、Markus Pelger、Jason Zhu
- **时间**：2024，Management Science 70(2)（arXiv 初版 2019）
- **内容**：将无套利约束嵌入深度神经网络（GAN 学习 SDF），用特征+宏观变量联合估计随机贴现因子与条件预期收益，样本外显著优于传统因子模型。
- **可转因子**：用自编码器+GAN 学潜在定价因子，输出个股条件期望收益与隐性因子暴露(beta)，构建「高预期收益−低预期收益」或「高/低 SDF 暴露」因子。
- **链接**：https://pubsonline.informs.org/doi/abs/10.1287/mnsc.2023.4695

### A4. Can ChatGPT Forecast Stock Price Movements?（ChatGPT 能否预测股价走势）
- **作者**：Alejandro Lopez-Lira、Yuehua Tang
- **时间**：2023（NBER/SSRN 工作论文，arXiv:2304.07619；后发表于 Journal of Financial Economics）
- **内容**：未经金融训练的 GPT-4 能从新闻标题预测股票反应，情感/方向评分显著预测次日收益漂移（小盘股与负面新闻更强），能力随模型规模增强。
- **可转因子**：对个股新闻标题用 LLM 输出标准化情感/方向打分，按评分横截面多空分组作次日漂移信号，聚合为滚动新闻情绪均值、正负新闻不对称等指标。
- **链接**：https://arxiv.org/abs/2304.07619

### A5. (Re-)Imag(in)ing Price Trends（（重新）想象价格趋势）
- **作者**：Jingwen Jiang、Bryan T. Kelly、Dacheng Xiu
- **时间**：2023，Journal of Finance 78(6)
- **内容**：把 OHLC 价格序列编码为图像，用 CNN 从 K 线形状学习并预测未来收益趋势，样本外优于传统技术指标与线性动量/趋势变量。
- **可转因子**：将个股 OHLC 渲染为标准 K 线图，CNN 输出涨跌概率/趋势强度评分，作横截面多空信号，量化图表技术形态替代传统动量/反转因子。
- **链接**：https://onlinelibrary.wiley.com/doi/10.1111/jofi.13268

---

## 主题 B：宏观 / 生产函数资产定价 / 另类数据（5 篇）

### B1. Replicating Anomalies（异象的可复制性）
- **作者**：Kewei Hou、Chen Xue、Lu Zhang（张橹）
- **时间**：2020，Review of Financial Studies 33(5): 2019–2133
- **内容**：统一方法论复制 452 个已发表横截面异象，绝大多数在 q-factor 模型（市场、规模、投资、盈利）控制下不再显著，确立投资 CAPM/q-factor 为简洁经验基准。
- **可转因子**：直接构造投资因子 I/A（总资产增长）与盈利因子 ROE，计算 q 因子载荷或「异象存活度」评分，把数百异象按是否被 q-factor 解释做「净化」后合成。
- **链接**：https://academic.oup.com/rfs/article-abstract/33/5/2019/5236964

### B2. Production Networks and Stock Returns: The Role of Vertical Creative Destruction（生产网络与股票收益：纵向创造性破坏）
- **作者**：Michael Gofman、Gill Segal、Youchang Wu
- **时间**：2020，Review of Financial Studies 33(12): 5856–5905
- **内容**：用客户-供应商网络研究上下游创新冲击如何经创造性破坏传导，被客户/供应商创新冲击的程度系统影响企业增长与股票收益。
- **可转因子**：构建「供应链纵向创新暴露度」——用客户/供应商研发强度或专利活动度量上下游创造性破坏压力，沿网络聚合；另可构造供应链网络中心度、供应链动量。
- **链接**：https://academic.oup.com/rfs/article-abstract/33/12/5856/5807619

### B3. Untangling the Value Premium with Labor Shares（用劳动份额拆解价值溢价）
- **作者**：Andres Donangelo
- **时间**：2021，Review of Financial Studies 34(1): 451–508
- **内容**：证明价值溢价（HML）可被劳动份额驱动的经营杠杆解释：劳动份额越高，经营杠杆与预期收益越高，把生产函数中的劳动投入与横截面收益直接联系。
- **可转因子**：计算「劳动经营杠杆」= 劳动报酬/增加值（或 1+固定劳动成本比例），按劳动份额排序构造能部分吸收 HML 的独立因子。
- **链接**：https://academic.oup.com/rfs/article-abstract/34/1/451/5753963

### B4. Reports of Value's Death May Be Greatly Exaggerated（「价值已死」的报告可能被严重夸大）
- **作者**：Robert D. Arnott、Campbell R. Harvey、Vitali Kalesnik、Juhani T. Linnainmaa
- **时间**：2021，Financial Analysts Journal 77(1): 44–78（2020 在线发表）
- **内容**：指出传统账面市值比因费用化无形资产而低估账面价值，导致价值因子「失效」；资本化研发/SG&A 后价值溢价显著复活。
- **可转因子**：构造「无形资产调整后账面市值比」——把研发及部分 SG&A 资本化（按行业摊销率）计入账面权益后再排序，得到溢价更高、IC 更稳的改进版价值因子。
- **链接**：https://doi.org/10.1080/0015198X.2020.1842704

### B5. Uncertainty Shocks as Second-Moment News Shocks（作为二阶矩新闻冲击的不确定性冲击）
- **作者**：David Berger、Ian Dew-Becker、Stefano Giglio
- **时间**：2020，Review of Economic Studies 87(1): 40–76
- **内容**：用已实现/预期波动率识别不确定性冲击，证明其为「二阶矩新闻冲击」，压低资产价格并驱动波动率风险溢价。
- **可转因子**：构造企业「不确定性暴露(uncertainty beta)」——估计个股收益对不确定性冲击的敏感度，高暴露者预期收益更高；或用二阶矩冲击作宏观风险因子做横截面定价与择时。
- **链接**：https://academic.oup.com/restud/article-abstract/87/1/40/5364025

---

## 主题 C：行为金融与市场异象（5 篇）

### C1. Investor Attention and Stock Returns（投资者关注度与股票收益）
- **作者**：Jian Chen、Guohao Tang、Jiaquan Yao、Guofu Zhou
- **时间**：2022，Journal of Financial and Quantitative Analysis 57(2): 455–484
- **内容**：用 PLS 把多种关注代理合成为统一「投资者关注指数」，样本内外均显著预测股市风险溢价，预测力来自临时价格压力反转，对高波动股更强。
- **可转因子**：投资者关注综合指数/横截面异常关注——高关注伴随临时价格压力随后反转，做多低关注、做空高关注形成短期反转因子。
- **链接**：https://ideas.repec.org/a/cup/jfinqa/v57y2022i2p455-484_2.html

### C2. Attention-Induced Trading and Returns: Evidence from Robinhood Users（注意力驱动交易与收益：Robinhood 用户证据）
- **作者**：Brad M. Barber、Xing Huang、Terrance Odean、Christopher Schwarz
- **时间**：2022，Journal of Finance 77(6): 3141–3190
- **内容**：Robinhood 散户「注意力驱动」抱团买入后股票显著跑输，负向预测在注意力事件驱动的买入中尤强。
- **可转因子**：Robinhood 散户净订单流不平衡(ROIB)/持仓人数变动率——做空散户集中净买入、做多散户冷落股，结合注意力事件日放大做空端。
- **链接**：https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.13183

### C3. Tracking Retail Investor Activity（追踪散户交易活动）
- **作者**：Ekkehart Boehmer、Charles M. Jones、Xiaoyan Zhang
- **时间**：2021，Journal of Finance 76(5): 2249–2305
- **内容**：开发识别「可成交散户订单流」的方法，构建日频散户买卖不平衡指标；散户净买入推动当日价格上行但随后部分反转，并提高波动与联动。
- **可转因子**：散户订单流不平衡(ROIB)横截面因子——做空高散户净买入、做多低散户净买入，捕捉噪声交易导致的短期错误定价反转。
- **链接**：https://onlinelibrary.wiley.com/doi/10.1111/jofi.13033

### C4. Business News and Business Cycles（商业新闻与经济周期）
- **作者**：Leland Bybee、Bryan Kelly、Asaf Manela、Dacheng Xiu
- **时间**：2024，Journal of Finance 79(5)
- **内容**：对海量商业新闻建大规模主题模型，构造新闻主题关注度/新闻冲击指数；新闻通过现金流与贴现率渠道驱动股市，解释相当部分波动与可预测性。
- **可转因子**：个股层面新闻主题曝光度/关注度 + 新闻情绪因子——做多正面新闻/低关注反转、做空负面新闻/高关注过热。
- **链接**：https://onlinelibrary.wiley.com/doi/full/10.1111/jofi.13377

### C5. Time-dependent lottery preference and the cross-section of stock returns（时变彩票偏好与股票横截面收益）
- **作者**：Chaonan Lin、Hong-Yi Chen、Kuan-Cheng Ko、Nien-Tzu Yang
- **时间**：2021，Journal of Empirical Finance
- **内容**：彩票偏好随时间动态形成，构造「时变最大日收益(TMAX)」策略——买历史分布中近期 MAX 下十分位、卖上十分位，获得显著溢价且涵盖 Bali-Cakici-Whitelaw(2011) MAX 策略收益。
- **可转因子**：TMAX 因子——个股近期最大日收益在其自身历史分布中的分位数，做多低 TMAX 分位、做空高 TMAX 分位。
- **链接**：https://www.sciencedirect.com/science/article/abs/pii/S0927539821000815

---

## 主题 D：文本 NLP / ESG 气候 / 特征工程（5 篇）

### D1. Lazy Prices（「惰性价格」：年报/季报文本变动与未来收益）
- **作者**：Lauren Cohen、Christopher Malloy、Quoc Nguyen
- **时间**：2020，Journal of Finance 75(3): 1371–1415
- **内容**：度量 10-K/10-Q 文本逐期变动；文本越「惰性」的公司越被低估坏消息，未来收益越差。
- **可转因子**：文本惰性因子——两期披露文本相似度/改动占比排序，多「大改」空「惰性」，long-short 组合。
- **链接**：https://ideas.repec.org/a/bla/jfinan/v75y2020i3p1371-1415.html

### D2. Firm-level Climate Change Exposure（公司层面气候变化暴露）
- **作者**：Zacharias Sautner、Laurence van Lent、Grigory Vilkov、Ruishen Zhang
- **时间**：2023，Journal of Finance 78(3): 1449–1498
- **内容**：财报电话会议文本 + ML（关键词 Bigram→BERT）构建公司气候暴露（机会/物理/监管三维）。
- **可转因子**：气候暴露因子/气候 beta——CCExposure 得分排序「高−低暴露」组合，作横截面定价信号。
- **链接**：https://onlinelibrary.wiley.com/doi/full/10.1111/jofi.13219

### D3. Sustainable Investing in Equilibrium（均衡中的可持续投资）
- **作者**：Ľuboš Pástor、Robert F. Stambaugh、Lucian A. Taylor
- **时间**：2021，Journal of Financial Economics 142(2): 550–571
- **内容**：ESG 偏好定价理论+实证；绿色资产期望收益更低，但绿色偏好冲击时实现超额收益。
- **可转因子**：绿色−棕色因子 + ESG 关注度动量（评级排序 + 资金流/媒体关注变化）。
- **链接**：https://www.sciencedirect.com/journal/journal-of-financial-economics/vol/142/issue/2

### D4. Do Investors Care About Carbon Risk?（投资者是否在意碳风险？）
- **作者**：Patrick Bolton、Marcin Kacperczyk
- **时间**：2021，Journal of Financial Economics 142(2): 517–549
- **内容**：碳排放越高的公司股票收益越高（「碳溢价」），无法被常见因子解释，机构开始撤碳。
- **可转因子**：碳强度因子——Scope 1 排放/营收（或排放同比变化）排序，多高碳空低碳。
- **链接**：https://www.newyorkfed.org/research/staff_reports/sr977

### D5. Dissecting Characteristics Nonparametrically（非参数化拆解特征）
- **作者**：Joachim Freyberger、Andreas Neuhierl、Michael Weber
- **时间**：2020，Review of Financial Studies 33(5): 2326–2377
- **内容**：用自适应分组的非参数方法估计特征与收益的非线性关系，发现特征的非线性/阈值效应定价，少数几个特征贡献了大部分横截面解释力。
- **可转因子**：非参数特征工程——识别特征的非线性/阈值效应，构造自适应分组后的特征信号（比线性排序更精确的特征构造方法）。
- **链接**：https://academic.oup.com/rfs/article-abstract/33/5/2326/5758275

---

## 附：可转因子速查表（对接因子挖掘工作流）

| # | 因子信号 | 数据源 | 方向 | 论文 |
|---|---|---|---|---|
| 1 | ML 预期收益（GBDT/NN） | 94 特征 | 多空 | A1 |
| 2 | 复杂度管理 alpha | 高维特征 | 多空 | A2 |
| 3 | 深度学习隐含收益/SDF 暴露 | 特征+宏观 | 多空 | A3 |
| 4 | LLM 新闻情绪 | 新闻标题 | 多空 | A4 |
| 5 | CNN 技术形态趋势评分 | OHLC 图 | 多空 | A5 |
| 6 | 投资 I/A + 盈利 ROE | 财报 | 正向 | B1 |
| 7 | 供应链创新暴露/网络中心度 | 客户-供应商+研发 | 多空 | B2 |
| 8 | 劳动经营杠杆（劳动份额） | 财报 | 正向 | B3 |
| 9 | 无形资产调整 B/M | 财报+研发资本化 | 正向 | B4 |
| 10 | 不确定性暴露 beta | 波动率序列 | 正向 | B5 |
| 11 | 投资者关注综合指数 | 关注代理 | 反转 | C1 |
| 12 | 散户净买入不平衡 ROIB | 订单流 | 反转 | C2/C3 |
| 13 | 新闻主题关注+情绪 | 新闻文本 | 多空 | C4 |
| 14 | 时变最大日收益 TMAX | 日收益 | 反转 | C5 |
| 15 | 文本惰性（披露改动占比） | 年报/季报 | 反转 | D1 |
| 16 | 气候暴露 beta | 电话会议文本 | 多空 | D2 |
| 17 | 绿色−棕色 + ESG 关注动量 | ESG 评级+资金流 | 多空 | D3 |
| 18 | 碳强度（排放/营收） | 碳排放数据 | 多空 | D4 |
| 19 | 非参数特征（阈值/非线性） | 多特征 | 多空 | D5 |

---

## 附：信息核实说明

- 20 篇全部经 web_search/web_fetch 联网核实（期刊官网、DOI 页、RePEc、Wiley、NBER、纽约联储等），作者/年份/期刊/卷期准确，无编造。
- 一处重复处理：`Tracking Retail Investor Activity`（Boehmer–Jones–Zhang）在原「微观结构」与「行为金融」两个子代理均出现，此处仅保留于 C3，D 主题用已核实的 `Dissecting Characteristics Nonparametrically`（Freyberger–Neuhierl–Weber, 2020 RFS）补足。
- 精确卷期页码以 DOI 链接最终版为准。

*生成：本机 · 2026-10-15*
