# Web端口更新说明

## 更新时间
2026-01-06

## 变更内容

Web服务端口已从 **5000** 更改为 **8076**

## 更新的文件

### 1. 配置文件
- ✅ `core/config.py` - WEB_PORT默认值改为8076

### 2. 脚本文件
- ✅ `test_web_app.sh` - 访问地址更新
- ✅ `verify_web_install.sh` - 端口检查更新

### 3. 文档文件
- ✅ `README_WEB.md` - 所有端口引用更新

## 新的访问地址

### 主页面
```
http://localhost:8076
```

### 功能页面
```
配置页面: http://localhost:8076/config
监控页面: http://localhost:8076/monitor
参数页面: http://localhost:8076/parameters
```

### API接口
```
API基础地址: http://localhost:8076/api
```

## 启动方式

### 方式1: 使用测试脚本（推荐）

```bash
./test_web_app.sh
```

### 方式2: 直接启动

```bash
python web_app.py
```

### 方式3: 使用环境变量

```bash
# 临时设置端口
export WEB_PORT=8076
python web_app.py
```

## 端口检查

### 检查端口是否被占用

```bash
lsof -i :8076
```

### 如果端口被占用

**方案1: 停止占用进程**
```bash
# 查找占用进程
lsof -i :8076

# 停止进程
kill -9 <PID>
```

**方案2: 更换端口**
```bash
# 设置环境变量
export WEB_PORT=8077

# 或修改配置文件
vim core/config.py
# 修改 WEB_PORT = 8077
```

## 验证安装

```bash
# 运行验证脚本
./verify_web_install.sh

# 应该显示:
# ✓ 端口8076可用
```

## 配置文件详解

### core/config.py

```python
# Web服务配置
self.WEB_HOST = os.getenv('WEB_HOST', '0.0.0.0')    # 监听所有网卡
self.WEB_PORT = int(os.getenv('WEB_PORT', '8076')) # 新端口
self.WEB_ENABLED = os.getenv('WEB_ENABLED', '1').lower() in ('1', 'true', 'yes')
```

### 环境变量配置

**临时设置（当前会话）:**
```bash
export WEB_PORT=8076
python web_app.py
```

**永久设置（添加到~/.bashrc或~/.zshrc）:**
```bash
echo "export WEB_PORT=8076" >> ~/.bashrc
source ~/.bashrc
```

## 防火墙配置

如果需要远程访问，确保防火墙允许8076端口：

### macOS
```bash
# 查看防火墙状态
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate

# 如果需要，添加允许规则（系统偏好设置 -> 安全性与隐私 -> 防火墙）
```

### Linux
```bash
# UFW防火墙
sudo ufw allow 8076/tcp

# iptables
sudo iptables -A INPUT -p tcp --dport 8076 -j ACCEPT
```

## 生产环境建议

### 1. 使用反向代理（推荐）

使用Nginx作为反向代理：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8076;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

### 2. 使用HTTPS

配置SSL证书：

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:8076;
        # ... 其他配置
    }
}
```

### 3. 端口安全

- ✅ 不使用默认端口
- ✅ 限制访问来源
- ✅ 使用HTTPS
- ✅ 配置认证

## 常见问题

### Q: 为什么要更换端口？

A:
- 端口5000常被其他服务占用
- 使用非标准端口提高安全性
- 避免与系统服务冲突

### Q: 如何确认端口修改成功？

A:
```bash
# 启动服务后
python web_app.py

# 查看日志输出
# 应该显示: 访问地址: http://0.0.0.0:8076

# 或检查端口
lsof -i :8076
```

### Q: 其他程序需要访问怎么办？

A:
```python
# 更新API基础URL
BASE_URL = "http://localhost:8076/api"

# 使用配置
from core.config import config
url = f"http://localhost:{config.WEB_PORT}/api"
```

## 日志输出示例

启动成功后的日志：

```
2026-01-06 10:00:00 - web_app - INFO - ============================================================
2026-01-06 10:00:00 - web_app - INFO - 启动Web监控服务
2026-01-06 10:00:00 - web_app - INFO - ============================================================
2026-01-06 10:00:00 - web_app - INFO - 访问地址: http://0.0.0.0:8076
2026-01-06 10:00:00 - web_app - INFO - 配置页面: http://0.0.0.0:8076/config
2026-01-06 10:00:00 - web_app - INFO - 监控页面: http://0.0.0.0:8076/monitor
2026-01-06 10:00:00 - web_app - INFO - 参数页面: http://0.0.0.0:8076/parameters
2026-01-06 10:00:00 - web_app - INFO - ============================================================
 * Serving Flask app 'web_app'
 * Running on http://0.0.0.0:8076
```

## 相关文件

- `core/config.py` - 端口配置
- `web_app.py` - Web应用
- `test_web_app.sh` - 启动脚本
- `verify_web_install.sh` - 验证脚本
- `README_WEB.md` - 使用文档

## 总结

✅ 端口已成功更新为 **8076**
✅ 所有相关文件已更新
✅ 文档已同步更新
✅ 可以正常启动和访问

**现在可以使用新端口启动Web服务！**

```bash
./test_web_app.sh
```

然后访问: **http://localhost:8076** 🚀
