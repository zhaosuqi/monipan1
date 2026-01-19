# Web监控系统使用指南

## 概述

MoniPan Web监控系统是一个完整的Web界面，用于配置、监控和管理量化交易系统。

### 主要功能

1. **配置管理** - 切换运行模式、配置Binance连接参数
2. **运行监控** - 实时K线图、订单监控、运行状态展示
3. **参数维护** - 查看和修改所有参数、支持JSON导入导出

## 安装依赖

### 方式1: 使用安装脚本（推荐）

```bash
./install_web_deps.sh
```

### 方式2: 手动安装

```bash
# 激活环境
conda activate bigtree

# 安装Flask-SocketIO
pip install flask-socketio
```

### 依赖包

- Flask >= 3.0
- Flask-SocketIO >= 5.0
- python-socketio >= 5.0
- eventlet (可选，用于性能优化)

## 快速启动

### 方式1: 使用测试脚本

```bash
./test_web_app.sh
```

### 方式2: 直接启动

```bash
# 激活环境
conda activate bigtree

# 启动Web服务器
python web_app.py
```

### 访问地址

启动后，在浏览器中访问:

- **首页**: http://localhost:5000/
- **配置页面**: http://localhost:5000/config
- **监控页面**: http://localhost:5000/monitor
- **参数页面**: http://localhost:5000/parameters

默认端口为5000，可在 `core/config.py` 中修改 `WEB_PORT` 配置。

## 功能详解

### 一、配置页面

#### 1.1 运行模式切换

系统支持三种运行模式:

**实盘模式**
- 连接到币安实盘
- 真实订单执行
- 需要API密钥
- ⚠️ 风险: 真实资金交易

**模拟盘模式**
- 连接到币安测试网
- 虚拟资金交易
- 需要测试网API密钥
- ✅ 无风险测试

**数据库回测模式**
- 从SQLite数据库读取历史数据
- 无需网络连接
- 用于验证计算准确性
- ✅ 本地运行

#### 1.2 Binance连接参数配置

在配置页面可以设置:

- **API Key** - 币安API密钥
- **API Secret** - 币安API密钥密码
- **交易对** - 例如: BTCUSD_PERP
- **测试网络** - 是否使用测试网

配置步骤:
1. 点击"实盘模式"或"模拟盘模式"
2. 填写API Key和API Secret
3. 选择交易对
4. 勾选/取消"测试网络"
5. 点击"保存配置"

#### 1.3 数据库配置

显示当前数据库配置:
- 数据库路径: `data/klines.db`
- 历史表名: `klines_1m`
- 回测时间范围

### 二、运行监控页面

#### 2.1 状态监控

顶部显示4个状态卡片:

- **运行状态** - 显示机器人是否运行中
- **运行模式** - 当前运行模式
- **运行时间** - 已运行时长
- **连接状态** - 数据源连接状态

#### 2.2 K线图表

- 实时显示K线数据
- 可选择显示50/100/200条K线
- 使用Chart.js绘制
- 支持缩放和拖拽

操作按钮:
- **50** - 显示最近50条K线
- **100** - 显示最近100条K线
- **200** - 显示最近200条K线

#### 2.3 订单监控

实时显示订单列表:

| 列 | 说明 |
|-----|------|
| 时间 | 订单创建时间 |
| 交易对 | 例如: BTCUSD_PERP |
| 方向 | 买入/卖出 (绿色/红色标签) |
| 价格 | 成交价格 |
| 数量 | 成交数量 |
| 状态 | 订单状态 |

#### 2.4 运行参数显示

显示当前运行参数:

**交易参数**
- 交易对
- 仓位BTC
- 合约名义价值

**指标参数**
- MACD快线周期
- MACD慢线周期
- MACD信号线周期

**止损止盈**
- 止损点数
- 止盈级别
- 回撤点数

#### 2.5 控制按钮

- **启动** - 启动交易机器人
- **停止** - 停止交易机器人
- **刷新** - 刷新所有数据

### 三、参数维护页面

#### 3.1 参数分组展示

所有参数按功能分组显示:

**模式配置**
- `DB_SIM_MODE` - 数据库模拟模式
- `REPLAY_MODE` - 回放模式
- `REPLAY_WARM_DAYS` - 预热天数

**Binance配置**
- `BINANCE_API_KEY` - API密钥
- `BINANCE_TESTNET` - 测试网络
- `SYMBOL` - 交易对

**交易配置**
- `POSITION_BTC` - 仓位BTC
- `CONTRACT_NOTIONAL` - 合约名义价值

**指标配置**
- `MACD_FAST` - MACD快线周期
- `MACD_SLOW` - MACD慢线周期
- `MACD_SIGNAL` - MACD信号线周期

**V5参数**
- `T0_HIST15_LIMIT` - 15周期柱体上限
- `T0_DIF15_LIMIT` - 15周期DIF上限
- `T0_J15M_LIMIT` - 15分钟J值上限

**止损止盈**
- `STOP_LOSS_POINTS` - 止损点数
- `TP_LEVELS` - 止盈级别
- `DRAWDOWN_POINTS` - 回撤点数
- `CLOSE_TIME_MINUTES` - 平仓时间

#### 3.2 导出JSON参数

点击"导出JSON"按钮，将当前所有参数导出为JSON文件。

文件名格式: `monipan-parameters-YYYY-MM-DD.json`

示例导出内容:
```json
{
  "MACD_FAST": 12,
  "MACD_SLOW": 26,
  "MACD_SIGNAL": 9,
  "STOP_LOSS_POINTS": 0.0165,
  "TP_LEVELS": [1.0065, 1.012, 1.018, 1.024, 1.03]
}
```

#### 3.3 导入JSON参数

步骤:
1. 点击"导入JSON"按钮
2. 在弹出的对话框中粘贴JSON格式参数
3. 点击"导入"按钮
4. 系统验证JSON格式
5. 更新参数并自动刷新页面

⚠️ **注意**: 参数导入仅在机器人停止状态下可用。

JSON格式示例:
```json
{
  "MACD_FAST": 12,
  "MACD_SLOW": 26,
  "MACD_SIGNAL": 9,
  "POSITION_BTC": 1.0,
  "STOP_LOSS_POINTS": 0.0165
}
```

## API接口

系统提供RESTful API接口:

### 配置相关

```
GET  /api/config              - 获取所有配置
GET  /api/config/mode         - 获取当前模式
POST /api/config/mode         - 设置运行模式
POST /api/config/binance      - 设置Binance配置
```

### 参数相关

```
GET  /api/parameters          - 获取所有参数
POST /api/parameters          - 更新单个参数
GET  /api/parameters/export   - 导出JSON参数
POST /api/parameters/import   - 导入JSON参数
```

### 机器人控制

```
GET  /api/bot/state           - 获取机器人状态
POST /api/bot/start           - 启动机器人
POST /api/bot/stop            - 停止机器人
```

### 数据相关

```
GET  /api/klines              - 获取K线数据
GET  /api/orders              - 获取订单列表
```

### WebSocket事件

```
connect                       - 客户端连接
disconnect                    - 客户端断开
subscribe_klines              - 订阅K线数据
bot_state_changed            - 机器人状态变化
kline_update                 - K线更新
```

## 使用场景

### 场景1: 首次配置

1. 启动Web服务器
2. 访问配置页面
3. 选择运行模式（建议先测试网）
4. 配置Binance API密钥
5. 保存配置
6. 切换到监控页面
7. 点击"启动"按钮

### 场景2: 参数优化

1. 在参数页面查看当前参数
2. 导出JSON参数备份
3. 修改需要调整的参数
4. 导入新的JSON参数
5. 切换到监控页面观察效果

### 场景3: 监控运行

1. 启动交易机器人
2. 实时查看K线图表
3. 监控订单执行情况
4. 观察运行状态
5. 必要时点击停止

### 场景4: 回测验证

1. 在配置页面切换到"数据库回测模式"
2. 设置回测时间范围
3. 启动机器人
4. 在监控页面查看回测结果
5. 检查订单列表和指标计算

## 安全建议

1. **API密钥保护**
   - 不要在公共场所访问Web界面
   - 使用强密码保护API密钥
   - 定期更换API密钥

2. **网络隔离**
   - 建议在内网运行
   - 如需外网访问，使用VPN
   - 配置防火墙规则

3. **测试优先**
   - 先在模拟盘测试
   - 验证参数配置
   - 确认无误后切换实盘

4. **权限控制**
   - 限制Web界面访问权限
   - 记录操作日志
   - 定期审计配置

## 故障排查

### 问题1: 无法启动Web服务器

**检查:**
```bash
# 检查端口是否被占用
lsof -i :5000

# 更换端口
# 修改 core/config.py 中的 WEB_PORT
```

### 问题2: 无法连接WebSocket

**检查:**
- 浏览器控制台是否有错误
- Flask-SocketIO是否正确安装
- 网络连接是否正常

### 问题3: K线图不显示

**检查:**
- 数据源是否正确配置
- 数据库是否有数据
- 浏览器控制台是否有JavaScript错误

### 问题4: 参数修改失败

**检查:**
- 机器人是否正在运行（需先停止）
- 参数名称是否正确
- JSON格式是否有效

## 性能优化

### WebSocket优化

安装eventlet以提高性能:
```bash
pip install eventlet
```

### 数据库优化

- 在`open_time`字段上创建索引
- 定期清理历史数据
- 使用分页查询

### 前端优化

- 使用浏览器缓存
- 启用gzip压缩
- 减少WebSocket数据传输频率

## 配置文件

### core/config.py 相关配置

```python
# Web服务配置
WEB_HOST = '0.0.0.0'  # 监听地址
WEB_PORT = 5000       # 监听端口
WEB_ENABLED = True    # 是否启用Web服务
```

## 文件结构

```
web/
├── templates/          # HTML模板
│   ├── base.html      # 基础模板
│   ├── index.html     # 首页
│   ├── config.html    # 配置页面
│   ├── monitor.html   # 监控页面
│   └── parameters.html # 参数页面
└── static/            # 静态资源 (CSS/JS/图片)

web_app.py             # Web应用主文件
```

## 更新日志

### v1.0.0 (2026-01-06)

- ✅ 实现配置页面 - 模式切换和连接参数维护
- ✅ 实现运行监控页面 - K线图和订单展示
- ✅ 实现参数维护页面 - 参数展示和JSON导入
- ✅ 集成WebSocket实时数据推送
- ✅ 提供RESTful API接口

## 技术栈

- **后端**: Flask + Flask-SocketIO
- **前端**: Bootstrap 5 + Chart.js + jQuery
- **通信**: WebSocket + REST API
- **数据库**: SQLite (已有)

## 相关文档

- [DATA_SOURCE_ADAPTER.md](DATA_SOURCE_ADAPTER.md) - 数据源适配器
- [DATA_MODULE_MODES.md](DATA_MODULE_MODES.md) - 数据模块模式
- [core/config.py](core/config.py) - 配置管理

## 支持

如有问题，请查看:
1. 浏览器控制台日志
2. Web服务器日志
3. 系统日志文件: `data/logs/`
