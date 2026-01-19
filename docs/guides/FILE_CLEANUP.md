# 文件清理说明

## 清理日期
2026-01-05

## 清理内容

### 已移至 `archive_old/` 的旧文件

#### 旧版Python脚本 (8个)
- `dashboard.py` - 旧版仪表板
- `macd2.8.py` - 旧版MACD策略
- `macd_refactor.py` - MACD重构版本
- `realtime_simulator.py` - 旧版实时模拟器
- `web_monitor.py` - 旧版Web监控
- `compute_1m_macd_smooth_ma.py` - MACD计算工具
- `update_config_from_json.py` - 配置更新工具
- `test_replay_simple.py` - 旧版回测测试

#### 旧版文档 (29个)
- `ANALYSIS_JAN2_SIGNAL.md` - 1月2日信号分析
- `ARCHITECTURE_REFACTOR.md` - 架构重构说明
- `BACKTEST_COMPLETE.md` - 回测完成文档
- `BACKTEST_FLOW_GUIDE.md` - 回测流程指南
- `CHOOSE_CORRECT_MODE.md` - 模式选择说明
- `DATA_CONSISTENCY_ANALYSIS.md` - 数据一致性分析
- `FIX_DB_MODE_ISSUE.md` - 数据库模式问题修复
- `FIX_MISSING_HIST1D_PARAMS.md` - 1天参数修复
- `FIX_VERIFICATION.md` - 验证修复
- `MACD_CALCULATION_VERIFICATION.md` - MACD计算验证
- `MIGRATION_GUIDE.md` - 迁移指南
- `MODULE_STRUCTURE.md` - 模块结构说明
- `NEW_ARCHITECTURE.md` - 新架构文档
- `ORDER_SYSTEM_COMPLETE.md` - 订单系统完成
- `ORDER_SYSTEM_GUIDE.md` - 订单系统指南
- `PORT_AUTO_SWITCH.md` - 端口自动切换
- `PROJECT_STRUCTURE.md` - 项目结构
- `QUICKSTART.md` - 快速开始
- `QUICK_START.md` - 快速开始(重复)
- `README_NEW_ARCHITECTURE.md` - 新架构README
- `USAGE_GUIDE.md` - 使用指南
- `V5_ALGORITHM_VERIFICATION_COMPLETE.md` - V5算法验证
- `V5_CONSISTENCY_ANALYSIS.md` - V5一致性分析
- `V5_PARAMS_ALIGNMENT_COMPLETE.md` - V5参数对齐
- `V5_UPDATE_SUMMARY.md` - V5更新总结
- `WEB_MONITOR_README.md` - Web监控文档
- `WEB_USAGE.md` - Web使用说明

#### 旧版脚本 (4个)
- `start_simulator.sh` - 启动模拟器
- `start_web.sh` - 启动Web服务
- `test_backtest.sh` - 测试回测
- `verify_v5_params.sh` - 验证V5参数

#### 日志文件 (2个)
- `dashboard.log` - 仪表板日志
- `simulation.log` - 模拟日志

## 保留的新版文件

### 核心Python脚本 (3个)
- **[main.py](main.py)** - 新版主程序入口
- **[simple_replay.py](simple_replay.py)** - 简单回测测试脚本
- **[verify_replay.py](verify_replay.py)** - 回测数据验证脚本

### 新版文档 (5个)
- **[BACKTEST_LOGIC.md](BACKTEST_LOGIC.md)** - 回测逻辑详解
- **[COMPLETION_SUMMARY.md](COMPLETION_SUMMARY.md)** - 完成总结
- **[REPLAY_COMPLETE.md](REPLAY_COMPLETE.md)** - 回测完成文档
- **[WARMUP_UPDATE.md](WARMUP_UPDATE.md)** - 预热天数更新说明
- **[README.md](README.md)** - 项目主文档

### 配置和部署脚本 (3个)
- **[simulator_config.json](simulator_config.json)** - 模拟器配置
- **[IMPLEMENT_ALL_MODULES.sh](IMPLEMENT_ALL_MODULES.sh)** - 实现所有模块
- **[IMPLEMENT_REMAINING_MODULES.sh](IMPLEMENT_REMAINING_MODULES.sh)** - 实现剩余模块

## 新版项目结构

```
monipan/
├── core/                      # 核心模块
│   ├── config.py             # 配置管理
│   ├── database.py           # 数据库管理
│   └── logger.py             # 日志模块
│
├── data_module/              # 数据模块
│   ├── kline_fetcher.py      # K线获取
│   ├── indicator_calculator.py # 指标计算
│   ├── data_writer.py        # 数据写入
│   ├── data_notifier.py      # 数据通知
│   └── replay_engine.py      # 回测引擎 ⭐
│
├── signal_module/            # 信号模块
│   ├── signal_calculator.py  # 信号计算
│   ├── position_manager.py   # 持仓管理
│   ├── tp_manager.py         # 止盈管理
│   └── sl_manager.py         # 止损管理
│
├── trade_module/             # 交易模块
│   ├── local_order.py        # 本地订单
│   ├── account_tracker.py    # 账户追踪
│   └── order_executor.py     # 订单执行
│
├── interaction_module/       # 交互模块
│   ├── web_interface.py      # Web接口
│   └── feishu_bot.py         # 飞书机器人
│
├── data/                     # 数据目录
│   └── klines.db            # 历史K线数据库 (3.6GB)
│
├── archive/                  # 归档目录(已有)
│   └── ...                  # 旧版代码
│
├── archive_old/             # 新归档目录 ⭐
│   └── ...                  # 2025年的旧文件
│
├── main.py                   # 新版主程序 ⭐
├── simple_replay.py         # 回测测试 ⭐
├── verify_replay.py         # 数据验证 ⭐
└── *.md                     # 新版文档 ⭐
```

## 清理效果

### 清理前
- Python文件: 11个
- Markdown文档: 32个
- Shell脚本: 8个
- **总计: 51个文件**

### 清理后
- Python文件: 3个 (核心文件)
- Markdown文档: 5个 (核心文档)
- Shell脚本: 2个 (部署脚本)
- **总计: 10个文件**

### 减少文件数量
**41个旧文件已归档**,减少约80%的文件 clutter

## 如何访问旧文件

所有旧文件都已移至 `archive_old/` 目录,如需访问:

```bash
cd archive_old/
ls -la
```

## 注意事项

1. **archive_old/** 目录中的文件仅供参考,不建议使用
2. 新版代码采用模块化架构,功能更强大
3. 旧版的单文件脚本已被新模块系统替代
4. 如需查看旧实现逻辑,可参考 archive_old/ 中的文件

## 下一步建议

1. 定期清理 archive_old/ 目录中的过期文件
2. 更新 README.md 以反映新的项目结构
3. 添加更多新模块的使用示例
4. 考虑删除 archive_old/ 中超过1年的文件
