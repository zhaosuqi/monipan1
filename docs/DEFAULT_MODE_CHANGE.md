# 程序默认模式修改为数据库回测

## 日期
2026-01-07

## 修改内容

将程序启动时的默认模式从实时交易模式改为数据库回测模式。

---

## 修改文件

**文件**: [core/config.py:69-70](core/config.py#L69-L70)

### 修改前

```python
# 模式
self.REPLAY_MODE = os.getenv('REPLAY_MODE', '0').lower() in ('1', 'true', 'yes')
self.DB_SIM_MODE = os.getenv('DB_SIM_MODE', '0').lower() in ('1', 'true', 'yes')
```

**默认行为**: 实时交易模式（连接交易所API）

### 修改后

```python
# 模式
self.REPLAY_MODE = os.getenv('REPLAY_MODE', '1').lower() in ('1', 'true', 'yes')  # 默认为回测模式
self.DB_SIM_MODE = os.getenv('DB_SIM_MODE', '1').lower() in ('1', 'true', 'yes')  # 默认为数据库模拟
```

**默认行为**: 数据库回测模式

---

## 影响说明

### 启动后的默认状态

| 配置项 | 修改前 | 修改后 | 说明 |
|--------|--------|--------|------|
| **REPLAY_MODE** | `False` (0) | `True` (1) | 启用回测模式 |
| **DB_SIM_MODE** | `False` (0) | `True` (1) | 从数据库读取历史数据 |

### 用户体验变化

**修改前**:
- 程序启动后默认尝试连接交易所API
- 需要手动配置环境变量或切换到回测模式
- 如果没有配置API密钥，会报错

**修改后**:
- 程序启动后默认使用数据库回测模式
- 可以直接运行回测，无需额外配置
- 更安全，避免意外触发真实交易

---

## 如何切换到实时交易模式

### 方法1: 设置环境变量

```bash
export REPLAY_MODE=0
export DB_SIM_MODE=0
python web_app.py
```

### 方法2: 在代码中临时修改

```python
# core/config.py
self.REPLAY_MODE = False  # 临时禁用回测模式
self.DB_SIM_MODE = False  # 临时禁用数据库模拟
```

### 方法3: 启动时传递环境变量

```bash
REPLAY_MODE=0 DB_SIM_MODE=0 python web_app.py
```

---

## 数据库回测模式配置

### 默认回测参数

程序启动时默认使用以下回测参数：

```python
# 回测时间范围
REPLAY_START = '2024-01-01 00:00:00'
REPLAY_END = '2024-01-10 23:59:59'

# 预热天数（用于计算MACD等指标）
REPLAY_WARM_DAYS = 200

# 每次处理的K线数量
REPLAY_CHUNK = 2000

# K线周期
KLINE_INTERVAL = '1m'

# 交易对
SYMBOL = 'BTCUSD_PERP'
```

### 修改回测参数

可以通过环境变量自定义回测参数：

```bash
# 修改回测时间范围
export REPLAY_START='2024-01-01'
export REPLAY_END='2024-01-31'

# 修改交易对
export SYMBOL='ETHUSD_PERP'

# 运行程序
python web_app.py
```

---

## 验证默认模式

### 检查方法

启动程序后，在配置页面查看当前模式：

```bash
python web_app.py
# 浏览器访问 http://localhost:8076/config
```

**预期显示**:
- 模式: 数据库回测
- REPLAY_MODE: `True`
- DB_SIM_MODE: `True`

### 查看日志

程序启动时会输出当前模式：

```log
================================================================================
交易引擎初始化完成
初始资金: 1.0 BTC
合约名义价值: $100
模式: 回测模式 (DB_SIM_MODE=True)
================================================================================
```

---

## 安全考虑

### ✅ 优点

1. **避免意外交易** - 默认回测模式不会执行真实交易
2. **快速验证** - 启动后可以立即运行回测验证策略
3. **安全开发** - 开发调试时无需担心真实资金风险
4. **降低门槛** - 新用户可以直接体验回测功能

### ⚠️ 注意事项

1. **生产环境** - 如果要用于实盘交易，必须手动切换模式
2. **明确提示** - 在Web界面清晰显示当前模式，避免混淆
3. **多重确认** - 切换到实时交易前应该有明确的警告提示

---

## 相关文件

- **修改文件**: [core/config.py:69-70](core/config.py#L69-L70)
- **环境变量**: `REPLAY_MODE`, `DB_SIM_MODE`
- **相关文档**:
  - [README.md](../README.md)
  - [docs/WEB_APP_GUIDE.md](WEB_APP_GUIDE.md)

---

## 总结

通过修改默认模式为数据库回测：

✅ **提高安全性** - 避免意外执行真实交易
✅ **改善体验** - 新用户可以直接体验回测功能
✅ **降低门槛** - 无需配置API即可使用
✅ **灵活切换** - 仍可通过环境变量轻松切换模式

现在程序启动后默认为安全的数据库回测模式！ 🎉
