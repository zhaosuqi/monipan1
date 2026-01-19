# API调试指南

## 问题现象

调用`/api/bot/start`接口后:
- 没有任何输出
- 页面没有变化
- HTTP状态码显示为20(异常)

## 调试步骤

### 1. 检查Web服务是否正常运行

```bash
# 确认服务启动
ps aux | grep web_app.py

# 或检查端口
lsof -i :5000
```

### 2. 使用Python测试脚本

```bash
# 在项目目录下运行
python test_api.py
```

这个脚本会:
- ✅ 测试启动API
- ✅ 显示完整的请求和响应信息
- ✅ 显示HTTP状态码
- ✅ 显示响应头和响应体

### 3. 检查浏览器控制台

1. 打开浏览器访问: http://localhost:5000/monitor
2. 按F12打开开发者工具
3. 切换到"Console"标签
4. 点击"启动"按钮
5. 查看控制台输出:

**正常情况下应该看到:**
```
开始启动机器人...
收到响应, 状态码: 200
响应头: Headers {...}
解析响应数据: {success: true, message: "...", data: {...}}
```

**异常情况下会看到:**
```
开始启动机器人...
收到响应, 状态码: 20
HTTP错误! 状态码: 20
启动失败: HTTP错误! 状态码: 20
```

### 4. 检查服务器日志

查看web_app.py的输出日志:

```bash
# 如果看到这些日志表示API被调用了
收到启动机器人请求
当前模式: backtest
创建回测线程...
回测线程已启动
回测机器人已启动 - 模式: 数据库回测模式
已发送状态通知: {'running': True, ...}
返回响应: {...}
```

### 5. 使用curl测试

```bash
# 测试启动API
curl -X POST http://localhost:5000/api/bot/start \
  -H "Content-Type: application/json" \
  -v

# 测试状态API
curl http://localhost:5000/api/bot/state

# 测试停止API
curl -X POST http://localhost:5000/api/bot/stop \
  -H "Content-Type: application/json" \
  -v
```

### 6. 检查Flask/SocketIO版本

```bash
pip list | grep -E "(Flask|SocketIO)"
```

应该看到:
- Flask >= 2.0
- Flask-SocketIO >= 5.0
- python-socketio >= 5.0

## 常见问题

### 问题1: 状态码20

**原因**: 这不是正常的HTTP状态码,通常表示:
- 响应被截断
- SocketIO响应冲突
- WSGI服务器配置问题

**解决方法**:
1. 检查是否使用了SocketIO的异步模式
2. 尝试在生产模式下运行(无热重载)
3. 检查Flask和SocketIO版本兼容性

### 问题2: 前端JavaScript错误

**检查方法**:
- 打开浏览器控制台(F12)
- 查看是否有JavaScript错误
- 检查Network标签,看请求是否发送

**解决方法**:
- 清除浏览器缓存
- 刷新页面(Ctrl+F5)
- 尝试使用隐私模式

### 问题3: 后台线程未启动

**症状**: API返回成功,但没有回测日志

**检查方法**:
```bash
# 查看Python进程
ps aux | grep python
```

**解决方法**:
- 检查`daemon=True`参数
- 检查是否有异常捕获但未记录
- 添加更多调试日志

## 正常工作的日志示例

### 服务器端日志
```
2026-01-06 23:10:00 - __main__ - INFO - 收到启动机器人请求
2026-01-06 23:10:00 - __main__ - INFO - 当前模式: backtest
2026-01-06 23:10:00 - __main__ - INFO - 创建回测线程...
2026-01-06 23:10:00 - __main__ - INFO - 回测线程已启动
2026-01-06 23:10:00 - __main__ - INFO - 回测机器人已启动 - 模式: 数据库回测模式
2026-01-06 23:10:00 - __main__ - INFO - 已发送状态通知
2026-01-06 23:10:00 - __main__ - INFO - 返回响应: {...}
```

### 浏览器控制台
```
开始启动机器人...
收到响应, 状态码: 200
解析响应数据: {
  success: true,
  message: "机器人已启动 - 数据库回测模式",
  data: {
    running: true,
    mode: "backtest",
    ...
  }
}
```

### 回测线程日志
```
============================================================
开始数据库回测
============================================================
获取到 10000 条K线数据
开始回测 - 数据回放模式
已处理 100/10000 条K线 | 信号: 3多/2空 | 开仓: 2次 | 当前资金: 1.001234 BTC
...
```

## 调试技巧

### 1. 逐步测试

```bash
# 步骤1: 测试Flask基本功能
curl http://localhost:5000/

# 步骤2: 测试API状态
curl http://localhost:5000/api/bot/state

# 步骤3: 测试启动API
curl -X POST http://localhost:5000/api/bot/start
```

### 2. 启用详细日志

在`web_app.py`开头添加:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### 3. 使用Postman或类似工具

- 安装Postman
- 创建POST请求到`http://localhost:5000/api/bot/start`
- 查看完整响应

### 4. 检查WebSocket连接

在浏览器控制台:
```javascript
// 检查Socket连接
console.log('Socket状态:', socket);

// 手动发送事件
socket.emit('bot_state_changed');
```

## 相关文件

- `web_app.py` - Web应用主文件
- `test_api.py` - API测试脚本
- `web/templates/monitor.html` - 监控页面

## 获取帮助

如果问题依然存在:

1. 收集以下信息:
   - 完整的服务器日志
   - 浏览器控制台输出
   - `test_api.py`的输出
   - Flask和SocketIO版本

2. 运行测试脚本:
   ```bash
   python test_api.py > api_test.log 2>&1
   ```

3. 将日志提供给开发者
