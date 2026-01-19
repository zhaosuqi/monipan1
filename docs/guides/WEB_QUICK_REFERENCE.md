# Web监控系统快速参考

## 快速启动

```bash
# 1. 安装依赖（首次）
./install_web_deps.sh

# 2. 启动Web服务
./test_web_app.sh

# 3. 浏览器访问
# http://localhost:5000
```

## 三个核心页面

### 1. 配置页面 `/config`

**功能:**
- ✅ 切换运行模式（实盘/模拟盘/回测）
- ✅ 配置Binance API密钥
- ✅ 设置交易对和测试网

**操作:**
1. 点击选择模式卡片
2. 填写API Key和Secret
3. 保存配置

### 2. 监控页面 `/monitor`

**功能:**
- ✅ K线图表（50/100/200条）
- ✅ 订单监控列表
- ✅ 运行状态显示
- ✅ 启动/停止控制

**操作:**
1. 点击"启动"按钮
2. 实时查看K线图
3. 监控订单执行

### 3. 参数页面 `/parameters`

**功能:**
- ✅ 查看所有参数
- ✅ 导出JSON配置
- ✅ 导入JSON配置

**操作:**
1. 点击"导出JSON"备份
2. 修改参数
3. 点击"导入JSON"更新

## 三种运行模式

| 模式 | 说明 | 风险 | 网络 |
|------|------|------|------|
| **实盘** | 币安实盘 | ⚠️ 真实资金 | 需要 |
| **模拟** | 测试网 | ✅ 虚拟资金 | 需要 |
| **回测** | 数据库 | ✅ 无风险 | 不需要 |

## API快速参考

### 设置模式
```bash
POST /api/config/mode
{
  "mode": "live"  # live, simulation, backtest
}
```

### 启动机器人
```bash
POST /api/bot/start
```

### 停止机器人
```bash
POST /api/bot/stop
```

### 获取K线
```bash
GET /api/klines?limit=100
```

### 导出参数
```bash
GET /api/parameters/export
```

### 导入参数
```bash
POST /api/parameters/import
{
  "parameters": {
    "MACD_FAST": 12,
    "STOP_LOSS_POINTS": 0.0165
  }
}
```

## 配置文件位置

- **Web服务**: `web_app.py`
- **模板目录**: `web/templates/`
- **配置管理**: `core/config.py`
- **数据库**: `data/klines.db`

## 常用端口

- **Web服务**: 5000 (可在config.py修改)
- **WebSocket**: 同Web服务端口

## 依赖包

```bash
flask>=3.0
flask-socketio>=5.0
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `web_app.py` | Web应用主文件 |
| `install_web_deps.sh` | 依赖安装脚本 |
| `test_web_app.sh` | 启动测试脚本 |
| `WEB_SYSTEM_GUIDE.md` | 完整使用指南 |

## 故障排查

**无法启动?**
```bash
# 检查端口
lsof -i :5000

# 查看日志
tail -f data/logs/web_app_*.log
```

**WebSocket不工作?**
```bash
# 检查Flask-SocketIO
pip install flask-socketio
```

## 安全建议

1. ⚠️ 不要在生产环境使用默认端口
2. ⚠️ 保护好API密钥
3. ✅ 先在模拟盘测试
4. ✅ 定期备份参数配置

## 下一步

1. 阅读完整指南: [WEB_SYSTEM_GUIDE.md](WEB_SYSTEM_GUIDE.md)
2. 了解数据源: [DATA_SOURCE_ADAPTER.md](DATA_SOURCE_ADAPTER.md)
3. 查看配置说明: [core/config.py](core/config.py)
