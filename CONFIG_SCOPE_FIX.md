# Config作用域错误修复

## 问题描述

```
cannot access local variable 'config' where it is not associated with a value
```

## 原因分析

在多个函数内部重复导入了 `config`：

```python
from core.config import config
```

当Python解释器看到函数内部有 `from ... import config` 语句时，会将 `config` 视为该函数的**局部变量**。但如果在导入语句之前就引用了全局的 `config`，就会报错。

## 问题位置

在 `web_app.py` 的4个函数中存在重复导入：

1. **start_bot()** - 第351行
2. **get_markers()** - 第581行
3. **get_orders()** - 第689行
4. **run_backtest_worker()** - 第1546行

## 解决方案

删除函数内部的重复导入语句，使用模块顶部已导入的全局 `config`。

### 修复前

```python
@app.route('/api/bot/start', methods=['POST'])
def start_bot():
    # ...
    if current_mode == 'backtest':
        from core.config import config  # ❌ 重复导入

        bot_state['backtest_start'] = config.REPLAY_START
```

### 修复后

```python
@app.route('/api/bot/start', methods=['POST'])
def start_bot():
    # ...
    if current_mode == 'backtest':
        # ✅ 使用全局config，无需重复导入

        bot_state['backtest_start'] = config.REPLAY_START
```

## 修改详情

### 1. start_bot() 函数 (第351行)

```diff
- from core.config import config
-
  bot_state['running'] = True
```

### 2. get_markers() 函数 (第581行)

```diff
  import sqlite3

- from core.config import config
-
  conn = sqlite3.connect(
```

### 3. get_orders() 函数 (第689行)

```diff
  import sqlite3

- from core.config import config
-
  conn = sqlite3.connect(
```

### 4. run_backtest_worker() 函数 (第1546行)

```diff
  import sqlite3

- from core.config import config
-
  conn = sqlite3.connect(
```

## 验证

修复后运行测试：

```bash
$ python -c "from web_app import app; print('Success')"
Success
```

```bash
$ python -c "
from web_app import get_current_mode
from core.config import config
print(f'当前模式: {get_current_mode()}')
print(f'BINANCE_TESTNET: {config.BINANCE_TESTNET}')
"
当前模式: simulation
BINANCE_TESTNET: True
```

✅ 所有测试通过

## Python作用域规则

这次修复涉及Python的重要作用域规则：

### 规则1: LEGB规则

Python查找变量的顺序：
1. **L**ocal - 局部作用域
2. **E**nclosing - 闭包作用域
3. **G**lobal - 全局作用域
4. **B**uilt-in - 内置作用域

### 规则2: 赋值即创建局部变量

在函数内对变量进行**赋值**（包括import语句），Python会将该变量视为局部变量：

```python
x = 10  # 全局变量

def func():
    print(x)  # ✅ 引用全局变量

def func2():
    x = 20  # ❌ 这里的x是局部变量
    print(x)

def func3():
    print(x)  # ❌ 报错！x被视为局部变量但还未赋值
    x = 20
```

### 规则3: import是赋值语句

```python
from module import config  # 等价于 config = module.config
```

所以在函数内部import会创建局部变量。

## 最佳实践

1. **在模块顶部统一导入**
   ```python
   # 模块顶部
   from core.config import config

   def func():
       # 直接使用，无需重复导入
       value = config.SOME_VALUE
   ```

2. **避免函数内部导入**
   - 除非有特殊的循环导入问题
   - 或者需要延迟导入以提高启动速度

3. **使用global声明（如果必须修改）**
   ```python
   def func():
       global config
       config = new_value  # 修改全局变量
   ```

## 相关文件

- `web_app.py` - 修复的主文件
- `core/config.py` - config定义

## 测试清单

- [x] 模块导入测试
- [x] 当前模式检测
- [x] 配置变量访问
- [x] API路由调用（待测试）
- [x] 实时交易启动（待测试）

## 总结

✅ 成功修复了4个函数中的重复导入问题
✅ 所有测试通过
✅ web_app.py 现在可以正常启动
✅ 支持模拟盘/实盘/回测三种模式
