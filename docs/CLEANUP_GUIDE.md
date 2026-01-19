# 文件清理和归档说明

## 概述

为了保持项目根目录的整洁，每次运行完成后应该执行清理脚本，将MD文档归档到docs目录，并清理临时文件。

## 快速使用

```bash
# 执行清理和归档
./cleanup_and_organize.sh
```

## 清理内容

### 1. 文档归档

**保留在根目录:**
- `README.md` - 项目主文档
- `README_WEB.md` - Web系统文档

**归档到docs/guides/ (使用指南):**
- DATA_MODULE_MODES.md
- DATA_SOURCE_ADAPTER.md
- QUICK_START_DATA_SOURCE.md
- SQLITE_QUICK_GUIDE.md
- WEB_QUICK_REFERENCE.md
- WEB_SYSTEM_GUIDE.md
- KLINE_FETCHER_COMPLETE.md
- KLINE_FETCHER_STANDALONE.md
- SQLITE_INTEGRATION_COMPLETE.md
- REPLAY_COMPLETE.md
- LOG_INTEGRATION.md
- FILE_CLEANUP.md
- WARMUP_UPDATE.md

**归档到docs/summaries/ (实现总结):**
- DATA_SOURCE_IMPLEMENTATION_SUMMARY.md
- WEB_SYSTEM_SUMMARY.md
- WEB_COMPLETION_REPORT.md
- COMPLETION_SUMMARY.md
- LOG_SYSTEM_SUMMARY.md
- LOG_QUICK_REFERENCE.md
- BACKTEST_LOGIC.md

### 2. 临时文件清理

- Python缓存 (`__pycache__`, `*.pyc`, `*.pyo`)
- 临时数据库 (`klines_sim.db`, `market_data.db`, `test_*.db`)
- 7天前的旧日志
- 30天前的临时文件

## 目录结构

清理后的目录结构：

```
monipan/
├── README.md                    # 主文档
├── README_WEB.md               # Web系统文档
│
├── *.py                        # Python应用文件
├── *.sh                        # Shell脚本
│
├── core/                       # 核心模块
├── data_module/                # 数据模块
├── signal_module/              # 信号模块
├── trade_module/               # 交易模块
├── interaction_module/         # 交互模块
├── web/                        # Web界面
│
├── docs/                       # 所有文档归档处
│   ├── README.md              # 文档索引
│   ├── guides/                # 使用指南 (13个文件)
│   ├── summaries/             # 实现总结 (7个文件)
│   └── api/                   # API文档
│
├── data/                       # 数据目录
│   ├── klines.db              # K线数据库
│   └── logs/                  # 日志目录
│
├── archive/                    # 归档目录
│   ├── old/                   # 旧版本文件
│   └── tmp/                   # 临时文件
│
└── cleanup_and_organize.sh    # 清理脚本
```

## 使用时机

### 建议在以下情况下运行清理脚本：

1. **完成功能开发后**
   - 新功能开发完成
   - 文档已编写完成

2. **提交代码前**
   - Git commit前
   - 确保根目录整洁

3. **定期维护**
   - 每周清理一次
   - 删除临时文件

4. **发布版本前**
   - 版本发布前
   - 确保项目结构清晰

## 脚本功能详解

### 1. 创建目录结构

```bash
mkdir -p docs/guides
mkdir -p docs/summaries
mkdir -p docs/api
mkdir -p archive/tmp
```

### 2. 文档分类归档

脚本会自动识别文档类型并归档：

- **guides/** - 使用指南和教程
- **summaries/** - 实现总结和报告
- **api/** - API文档（预留）

### 3. 清理临时文件

**Python缓存:**
```bash
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -type f -name "*.pyc" -delete
find . -type f -name "*.pyo" -delete
```

**临时数据库:**
```bash
rm -f klines_sim.db
rm -f market_data.db
rm -f test_*.db
rm -f tmp_*.db
```

**旧日志:**
```bash
find logs -name "*.log" -mtime +7 -delete
```

**临时文件:**
```bash
find archive/tmp -type f -mtime +30 -delete
```

### 4. 统计信息

脚本会显示：
- 根目录MD文件数量
- docs目录MD文件数量
- 核心Python文件数量
- Shell脚本数量

## 查看文档

所有文档已归档到`docs/`目录，可以通过以下方式查看：

### 查看文档索引

```bash
cat docs/README.md
```

### 查看特定文档

```bash
# 使用指南
ls docs/guides/

# 实现总结
ls docs/summaries/
```

## 自定义配置

如果需要添加新的文档分类，可以修改脚本：

```bash
# 编辑清理脚本
vim cleanup_and_organize.sh

# 添加新的文档分类
guides_files=(
    "YOUR_NEW_DOC.md"
    # ... 其他文档
)
```

## 注意事项

1. **README文档**
   - README.md 和 README_WEB.md 会保留在根目录
   - 其他MD文档都会被归档

2. **数据安全**
   - 脚本不会删除 `data/klines.db` 主数据库
   - 只删除临时数据库文件

3. **日志保留**
   - 保留最近7天的日志
   - 更早的日志会被自动清理

4. **可重复执行**
   - 脚本可以安全地重复执行
   - 不会重复移动已归档的文件

## 最佳实践

### 1. 开发流程

```bash
# 1. 开发新功能
vim your_module.py

# 2. 编写文档
vim docs/guides/NEW_FEATURE.md

# 3. 测试功能
python test_your_feature.py

# 4. 运行清理
./cleanup_and_organize.sh

# 5. 提交代码
git add .
git commit -m "Add new feature"
```

### 2. 发布流程

```bash
# 1. 完成所有开发
# 2. 运行清理
./cleanup_and_organize.sh

# 3. 检查文件结构
ls -la
ls docs/

# 4. 测试系统
python main.py

# 5. 发布版本
git tag v1.0.0
git push origin v1.0.0
```

## 故障排查

### 问题1: 脚本无法执行

```bash
# 添加执行权限
chmod +x cleanup_and_organize.sh
```

### 问题2: 文档未正确归档

检查文档是否在脚本的白名单中：
```bash
# 查看脚本内容
grep "guides_files=" cleanup_and_organize.sh
grep "summaries_files=" cleanup_and_organize.sh
```

### 问题3: 重要文件被删除

脚本不会删除以下文件：
- Python源码 (*.py)
- Shell脚本 (*.sh)
- README文档
- 主数据库 (data/klines.db)

## 更新日志

### v1.0.0 (2026-01-06)

- 初始版本
- 支持文档自动分类归档
- 支持临时文件清理
- 创建docs目录结构
- 生成文档索引

## 相关文件

- `cleanup_and_organize.sh` - 清理脚本
- `docs/README.md` - 文档索引
- `README.md` - 项目主文档

## 总结

通过使用清理脚本，可以：
- ✅ 保持根目录整洁
- ✅ 文档分类清晰
- ✅ 自动清理临时文件
- ✅ 提高项目可维护性

**建议每次运行后都执行清理！**
