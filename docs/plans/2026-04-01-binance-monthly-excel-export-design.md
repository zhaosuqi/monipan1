# 币安近一个月交易记录导出 Excel 设计

## 背景

当前仓库已经具备：

- 通过 [scripts/sync_trades_from_binance.py](/Users/zhaosuqi/work/monipan1/scripts/sync_trades_from_binance.py) 连接币安正式盘或测试盘
- 通过 [exchange_layer/binance_exchange.py](/Users/zhaosuqi/work/monipan1/exchange_layer/binance_exchange.py) 拉取用户成交明细
- 通过现有命令行参数执行历史同步

本次需求是在不改变现有同步主流程的前提下，新增一个可直接执行的脚本入口，用于连接币安正式盘，获取最近 30 天成交记录，并导出为 Excel。

## 目标

- 复用现有正式盘连接配置与交易拉取逻辑
- 提供一个命令行开关，直接导出近 30 天交易记录
- 生成一个 Excel 文件，包含原始明细和汇总两个 sheet
- 输出路径明确、命名稳定、失败时不产生误导性成功结果

## 非目标

- 不改造 Web 后台入口
- 不做复杂的财务报表或策略归因分析
- 不依赖先同步到本地数据库再导出
- 不新增额外的持久化表结构

## 方案选择

### 方案 A：扩展现有同步脚本

在 [scripts/sync_trades_from_binance.py](/Users/zhaosuqi/work/monipan1/scripts/sync_trades_from_binance.py) 中新增导出参数和 Excel 导出逻辑。

优点：

- 最大化复用现有币安连接、参数解析和交易拉取代码
- 对用户来说入口最少，执行方式简单
- 便于以后把同步与导出统一维护

缺点：

- 脚本职责会稍微增加

### 方案 B：新建独立导出脚本

单独创建一个导出脚本，仅做拉取和导出。

优点：

- 职责清晰

缺点：

- 与现有脚本有重复参数解析和连接逻辑
- 维护成本更高

### 决策

选择方案 A。直接扩展现有同步脚本，新增导出入口。

## 设计

### 命令行入口

在现有脚本中增加：

- `--export-monthly-excel`：导出最近 30 天交易到 Excel
- `--output <path>`：可选，自定义输出文件路径

默认要求显式使用正式盘，即通过 `--live` 或内部强制选择 `exchange_type='live'`。

### 数据获取

导出流程复用现有 `BinanceTradeSync` 与 `exchange.get_user_trades()`。

处理流程：

1. 连接币安正式盘
2. 计算时间范围：`now - 30 days` 到 `now`
3. 分页拉取成交明细
4. 过滤到时间窗口内
5. 将原始成交列表转换为 DataFrame

如果现有 `_fetch_trades_batch()` 分页只能基于最近若干条数据工作，则补强分页参数透传与终止条件，确保覆盖 30 天窗口。

### Excel 输出

生成目录：`data/exports/`

默认文件名格式：

`binance_trades_YYYYMMDD_YYYYMMDD.xlsx`

Sheet 设计：

1. `raw_trades`
   保留导出用关键字段，包括：
   - `trade_time`
   - `symbol`
   - `side`
   - `buyer`
   - `maker`
   - `price`
   - `qty`
   - `quoteQty`
   - `commission`
   - `commissionAsset`
   - `realizedPnl`
   - `orderId`
   - `id`
   - `positionSide`

2. `summary`
   按 `symbol + side` 聚合，输出：
   - 成交笔数
   - 总成交数量
   - 总成交额
   - 总手续费
   - 总已实现盈亏
   - 首笔成交时间
   - 末笔成交时间

### 格式化

使用 `pandas` 写入 Excel，使用 `openpyxl` 做轻量格式增强：

- 表头加粗
- 冻结首行
- 时间列格式化为易读文本
- 数值列统一小数位
- 自动调整列宽

### 错误处理

- 未配置正式盘 API Key/Secret：直接报错退出
- 连接失败：直接报错退出
- 拉取失败：直接报错退出
- 无交易记录：仍生成 Excel，但保留表头并在汇总中体现 0 条

## 测试策略

由于真实币安请求依赖网络和正式盘凭证，测试聚焦在可离线验证的纯逻辑：

- 原始交易列表到导出行的转换
- 汇总表聚合逻辑
- 默认输出文件路径生成逻辑

网络部分使用手动验证：

- 正式盘执行导出命令
- 检查终端输出路径
- 打开生成的 Excel 确认两个 sheet 和列结构

## 风险

### 币安接口分页不足

如果 `get_user_trades()` 不能稳定使用 `fromId` 分页，需要在交易所层补齐参数支持，否则 30 天数据在高频成交账户里可能不完整。

### 币本位计价字段口径

手续费和 `realizedPnl` 可能是 BTC 口径。汇总 sheet 初版保留原始字段求和，不在本次设计里做 USD 换算，避免错误口径。

### 依赖缺失

如果环境缺少 `openpyxl`，需要在运行时报出清晰提示，而不是生成损坏文件。
