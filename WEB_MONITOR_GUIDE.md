# Web监控使用指南

## 概述

`web_app.py` 是一个统一的Web监控服务，支持三种模式：

1. **回测模式 (backtest)** - 从数据库读取历史数据进行回测
2. **模拟盘模式 (simulation)** - 连接币安测试网，实时交易
3. **实盘模式 (live)** - 连接币安实盘，实时交易

## 快速开始

### 1. 切换到模拟盘模式

```bash
./switch_to_testnet.sh
```

这会创建/更新 `.env` 文件，配置为模拟盘模式。

### 2. 配置API密钥

编辑 `.env` 文件，填入币安测试网的API密钥：

```bash
vim .env
```

修改以下内容：
```
BINANCE_API_KEY=你的测试网API密钥
BINANCE_API_SECRET=你的测试网API密钥
```

### 3. 启动Web监控

```bash
./start_web_monitor.sh
```

或者直接运行：

```bash
python web_app.py
```

### 4. 访问监控页面

在浏览器中打开：http://localhost:5000

- **配置页面**: http://localhost:5000/config
- **监控页面**: http://localhost:5000/monitor
- **参数页面**: http://localhost:5000/parameters

## 三种模式对比

| 特性 | 回测模式 | 模拟盘模式 | 实盘模式 |
|------|----------|------------|----------|
| 数据源 | 数据库 | 币安测试网API | 币安实盘API |
| 更新方式 | 手动触发 | 实时推送 | 实时推送 |
| 交易执行 | 模拟 | 真实（测试网） | 真实（实盘） |
| 风险 | 无 | 无资金风险 | 真实资金风险 |
| 用途 | 策略验证 | 模拟测试 | 实盘交易 |

## 模式切换

### 切换到模拟盘

```bash
./switch_to_testnet.sh
./start_web_monitor.sh
```

### 切换到回测模式

```bash
./switch_to_backtest.sh
./start_web_monitor.sh
```

### 通过Web界面切换

你也可以在Web界面上直接切换模式：

1. 访问配置页面: http://localhost:5000/config
2. 点击相应的模式按钮
3. 系统会自动更新配置并重启数据源

## 模拟盘模式使用说明

### 启动流程

1. **配置模式** - 确保 `.env` 中设置了：
   ```
   BINANCE_TESTNET=1
   REPLAY_MODE=0
   DB_SIM_MODE=0
   ```

2. **启动服务** - 运行 `./start_web_monitor.sh`

3. **访问监控页面** - 打开 http://localhost:5000/monitor

4. **启动交易** - 点击"启动机器人"按钮

### 后台工作流程

启动机器人后，系统会：

1. ✓ 连接到币安测试网
2. ✓ 创建交易引擎
3. ✓ 预加载1000条历史K线数据
4. ✓ 启动实时K线监控线程
5. ✓ 每60秒获取最新K线
6. ✓ 处理交易信号并执行交易
7. ✓ 推送新K线到前端

### WebSocket事件

模拟盘模式下，前端会收到以下事件：

- `historical_klines_loaded` - 历史K线加载完成
- `new_kline` - 新K线数据（每分钟）
- `bot_state_changed` - 机器人状态变化
- `trade_signal` - 交易信号（如有）

## API接口

### 获取K线数据

```bash
# 获取最新100条K线
curl http://localhost:5000/api/klines?limit=100

# 回测模式支持时间范围查询
curl "http://localhost:5000/api/klines?start_time=2024-01-01%2000:00:00&end_time=2024-01-02%2000:00:00"
```

### 获取机器人状态

```bash
curl http://localhost:5000/api/bot/state
```

### 启动/停止机器人

```bash
# 启动
curl -X POST http://localhost:5000/api/bot/start

# 停止
curl -X POST http://localhost:5000/api/bot/stop
```

### 切换模式

```bash
curl -X POST http://localhost:5000/api/config/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "simulation"}'
```

可选模式：`backtest`, `simulation`, `live`

## 故障排查

### 问题1: 无法连接到币安测试网

**检查：**
- API密钥是否正确配置
- 网络连接是否正常
- 测试网API是否可用

**解决：**
```bash
# 测试连接
python test_testnet_connection.py
```

### 问题2: 页面显示"机器人未运行"

**原因：** 机器人未启动

**解决：**
1. 访问配置页面确认模式
2. 点击"启动机器人"按钮
3. 查看后端日志确认状态

### 问题3: K线数据不更新

**检查：**
- 后端日志是否有错误
- WebSocket连接是否正常
- 交易所API是否正常

**解决：**
- 检查后端日志：`tail -f logs/web_app.log`
- 刷新浏览器页面
- 重新连接WebSocket

### 问题4: 模式切换后仍使用旧数据源

**原因：** 数据源单例未重置

**解决：**
```bash
# 重启服务
pkill -f web_app.py
./start_web_monitor.sh
```

## 配置参数

### Web服务配置

在 `.env` 文件中：

```bash
# Web服务端口
WEB_PORT=5000
WEB_HOST=0.0.0.0
WEB_ENABLED=1

# 开发模式（热重载）
# 启动时添加 --debug 参数
python web_app.py --debug
```

### 交易配置

```bash
# 交易对
SYMBOL=BTCUSD_PERP

# 仓位配置
POSITION_BTC=1.0
CONTRACT_NOTIONAL=100

# MACD参数
MACD_FAST=12
MACD_SLOW=26
MACD_SIGNAL=9
```

## 日志查看

### 实时日志

```bash
# 查看所有日志
tail -f logs/web_app.log

# 只看错误日志
tail -f logs/web_app.log | grep ERROR
```

### 日志级别

在 `core/config.py` 中修改日志级别：

```python
LOG_LEVEL = 'INFO'  # DEBUG, INFO, WARNING, ERROR
```

## 生产部署

### 使用Gunicorn

```bash
pip install gunicorn eventlet

gunicorn --worker-class eventlet -w 1 \
  --bind 0.0.0.0:5000 \
  --access-logfile logs/access.log \
  --error-logfile logs/error.log \
  web_app:app
```

### 使用Supervisor管理

创建 `/etc/supervisor/conf.d/monipan.conf`:

```ini
[program:monipan]
command=/path/to/venv/bin/python web_app.py
directory=/path/to/monipan
user=www-data
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/monipan.log
```

启动：

```bash
supervisorctl reread
supervisorctl update
supervisorctl start monipan
```

## 安全建议

1. **API密钥保护**
   - 不要在代码中硬编码API密钥
   - 使用 `.env` 文件管理敏感信息
   - 将 `.env` 添加到 `.gitignore`

2. **网络安全**
   - 生产环境使用HTTPS
   - 配置防火墙规则
   - 限制管理页面访问

3. **实盘交易**
   - 充分测试后再使用实盘模式
   - 从小额开始
   - 设置止损和监控告警

## 相关文件

- `web_app.py` - Web监控主程序
- `start_web_monitor.sh` - 启动脚本
- `switch_to_testnet.sh` - 切换到测试网
- `switch_to_backtest.sh` - 切换到回测
- `.env` - 环境变量配置
- `web/templates/` - HTML模板
- `web/static/` - 静态资源

## 技术支持

如有问题，请检查：
1. 后端日志输出
2. 浏览器开发者工具控制台
3. 系统日志文件
