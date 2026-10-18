# 测试报告（校验器自测）

| 项 | 值 |
|---|---|
| 策略夏普 | 0.3340 [src: b1_single_asset.json#index."2016+".strategy.sharpe] |
| 买入持有夏普 | 0.1520 [src: b1_single_asset.json#index."2016+".buy_hold.sharpe] |
| 策略回撤 | -35.78% [src: b1_single_asset.json#index."2016+".strategy.max_drawdown] |
| 故意写错的数 | 0.9999 [src: b1_single_asset.json#index."2016+".strategy.calmar] |
| 不存在的路径 | 1.0 [src: b1_single_asset.json#index."2016+".nonexistent.key] |
| 找不到的文件 | 1.0 [src: no_such_file.json#a.b] |
