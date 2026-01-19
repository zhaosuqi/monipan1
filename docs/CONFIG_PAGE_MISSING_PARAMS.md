# 配置页面缺少参数说明

## 日期
2026-01-07

## 问题

配置页面 (`web/templates/config.html`) 缺少 `TP_RATIO_PER_LEVEL` 参数的显示和编辑功能。

---

## 当前状态

### 后端API - ✅ 已支持

**文件**: [web_app.py:1040](web_app.py#L1040)

```python
def get_config_dict():
    """获取配置字典"""
    return {
        # ... 其他参数 ...

        # 止损止盈
        'STOP_LOSS_POINTS': config.STOP_LOSS_POINTS,
        'TP_LEVELS': config.TP_LEVELS,
        'TP_RATIO_PER_LEVEL': config.TP_RATIO_PER_LEVEL,  # ✅ 已包含
        'DRAWDOWN_POINTS': config.DRAWDOWN_POINTS,
        'CLOSE_TIME_MINUTES': config.CLOSE_TIME_MINUTES,
        'CLOSE_DECAY_POINTS': config.CLOSE_DECAY_POINTS,

        # ... 其他参数 ...
    }
```

**API端点**: `GET /api/config`

**验证**:
```bash
curl http://localhost:8076/api/config | grep TP_RATIO_PER_LEVEL
```

应该返回：
```json
"TP_RATIO_PER_LEVEL": 0.0
```

### 前端配置页面 - ⚠️ 功能不完整

**文件**: [web/templates/config.html](web/templates/config.html)

**当前显示的参数**:
- 模式选择（实盘/模拟盘/回测）
- Binance API配置
- 数据库基本信息

**缺少的参数**:
- ❌ 止损止盈参数（`STOP_LOSS_POINTS`, `TP_LEVELS`, `TP_RATIO_PER_LEVEL`）
- ❌ V5 T0参数
- ❌ V5均值参数
- ❌ 价格变化参数
- ❌ 其他所有V5.0参数

---

## 原因分析

配置页面目前是一个**简化版本**，只提供了最基础的配置功能：
- 运行模式切换
- API密钥配置
- 基本信息查看

完整的V5.0参数配置（100+个参数）尚未在前端实现。

---

## 解决方案

### 方案1: 使用API直接配置（推荐）

由于前端页面不完整，建议通过API或配置文件直接修改参数：

**方法1**: 修改环境变量
```bash
export TP_RATIO_PER_LEVEL=0.5
python web_app.py
```

**方法2**: 修改配置文件 `core/config.py`
```python
# core/config.py:243
self.TP_RATIO_PER_LEVEL = float(os.getenv('TP_RATIO_PER_LEVEL', '0.5'))
```

**方法3**: 使用配置JSON文件
```bash
# 创建 config.json
cat > config.json << EOF
{
  "TP_RATIO_PER_LEVEL": 0.5
}
EOF
```

### 方案2: 扩展前端配置页面（需要开发工作）

如果要添加完整的前端配置界面，需要：

1. **添加参数编辑表单** (config.html)
   - 止损止盈配置卡片
   - V5 T0参数配置卡片
   - V5均值参数配置卡片
   - 其他参数配置卡片

2. **添加保存API** (web_app.py)
   - 实现 `/api/config/update` 的完整功能
   - 支持所有V5.0参数的动态更新

3. **前端JavaScript**
   - 表单提交处理
   - 参数验证
   - 成功/失败提示

**工作量估计**: 中等到大（需要2-4小时）

---

## 当前可用的配置方法

### 1. 修改代码默认值（推荐）

直接修改 `core/config.py` 中的默认值：

```python
# core/config.py
self.TP_RATIO_PER_LEVEL = float(os.getenv('TP_RATIO_PER_LEVEL', '0.5'))  # 修改默认值
```

### 2. 使用环境变量

```bash
# 临时设置
TP_RATIO_PER_LEVEL=0.5 python web_app.py

# 或永久设置
export TP_RATIO_PER_LEVEL=0.5
```

### 3. 通过API查看当前值

```bash
# 查看所有配置
curl http://localhost:8076/api/config

# 使用Python
import requests
response = requests.get('http://localhost:8076/api/config')
config = response.json()['data']
print(f"TP_RATIO_PER_LEVEL: {config['TP_RATIO_PER_LEVEL']}")
```

---

## 参数说明

### TP_RATIO_PER_LEVEL

**配置**: [core/config.py:243](core/config.py#L243)
```python
self.TP_RATIO_PER_LEVEL = float(os.getenv('TP_RATIO_PER_LEVEL', '0.0'))
```

**含义**: 每个止盈级别的仓位平仓比例

**取值范围**:
- `0.0` - 不使用比例分仓（使用其他逻辑）
- `0.0 < x < 1.0` - 每个级别平仓x%的仓位
- `1.0` - 每个级别平仓全部仓位（一次性平仓）

**示例**:
```python
# 假设有5个止盈级别: [1.0065, 1.012, 1.018, 1.024, 1.03]
TP_LEVELS = [1.0065, 1.012, 1.018, 1.024, 1.03]
TP_RATIO_PER_LEVEL = 0.2  # 每个级别平仓20%

# 当价格达到第一个TP(1.0065)时，平仓20%
# 当价格达到第二个TP(1.012)时，再平仓20%
# 以此类推...
```

**相关参数**:
- `TP_LEVELS` - 止盈价格级别数组
- `STOP_LOSS_POINTS` - 止损点数
- `DRAWDOWN_POINTS` - 回撤点数

---

## 相关文件

- **配置文件**: [core/config.py:243](core/config.py#L243)
- **API返回**: [web_app.py:1040](web_app.py#L1040)
- **前端页面**: [web/templates/config.html](web/templates/config.html)
- **相关API**: `GET /api/config`, `POST /api/config/update`

---

## 总结

### 问题确认

✅ **后端已支持** - `TP_RATIO_PER_LEVEL` 在API中正确返回
❌ **前端未显示** - 配置页面没有包含此参数的编辑界面

### 临时解决方案

由于前端配置页面不完整，建议：
1. **通过代码修改** - 直接修改 `core/config.py` 默认值
2. **使用环境变量** - 运行时设置参数
3. **创建配置文件** - 使用 `config.json`

### 长期解决方案

扩展前端配置页面，添加完整的参数编辑功能（需要开发工作）。

---

**结论**: 参数已存在于后端，只是前端页面未显示。可以通过修改代码默认值或环境变量来配置。
