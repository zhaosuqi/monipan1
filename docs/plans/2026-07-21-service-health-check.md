# 服务健康检查实施记录

**日期**: 2026-07-21

**目标**: 为全部 systemd 托管服务增加统一的健康检查与飞书告警，覆盖服务存活、数据新鲜度与 Web 可达性。

## 背景

此前仅 `db_driven_trading` 有守护（systemd 重启 + 异常退出飞书告警，见
`docs/plans/2026-07-20-db-trading-service-guard.md`），存在两个盲区：

1. K线同步、指标计算、Web 三个进程没有守护与告警，挂掉后无人感知。
2. 进程存活不代表数据在更新——K线/指标表停止写入时没有任何告警。

## 方案

新增 `scripts/service_health_check.py`，由 `service-health-check.timer` 每分钟
触发一次，执行 4 项检查：

| 检查项 | 内容 | 异常判定 |
|--------|------|----------|
| 服务存活 | `systemctl is-active` 检查 4 个 unit | 非 `active`（inactive/activating/failed）；systemctl 不存在时跳过 |
| K线新鲜度 | `MAX(open_time)` of `klines_1m` | 滞后超过 `HEALTH_MAX_KLINE_AGE_SECONDS`（默认 180 秒）；表空/查询失败/解析失败也算异常 |
| 指标新鲜度 | `MAX(open_time)` of `klines_1m_macd_smooth_ma` | 同上 |
| Web 可达 | HTTP GET `http://127.0.0.1:{WEB_PORT}/` | 连接错误/超时；任意 HTTP 响应（含 302 登录跳转、4xx）视为存活 |

告警行为：

- **按检查项独立冷却**（默认 600 秒，`HEALTH_ALERT_COOLDOWN_SECONDS`），复用
  `scripts/notify_db_trading_failure.py` 的 `inspect_alert_state`/`record_alert`
  （三态冷却判断 + tempfile + os.replace 原子写）。
- 未处于冷却的异常项合并为**一条**中文飞书消息（含主机名、异常明细、东八区时间）；
  发送成功才记录冷却，失败/飞书未启用不记录、下轮重试。
- 某项从异常恢复时发送**一次**"已恢复"通知并删除该项状态文件；未告警过的项
  恢复时不通知。
- 全部正常时静默退出；`main()` 吞掉一切异常只记日志，**退出码恒为 0**，
  避免 timer 进入 failed 状态。
- 模块自带 stderr logger，不依赖 `core/logger`；bot、clock、systemctl runner、
  db 路径、http getter 全部可注入，便于测试。

冷却状态目录优先级：`HEALTH_STATE_DIR` 环境变量 > `/run/service-health-check`
（可写时）> 项目 `data/.health_state/`。

## 文件清单

本次新增/修改：

- `scripts/service_health_check.py` — 健康检查脚本（新增）
- `tests/test_service_health_check.py` — 测试 27 个用例（新增）
- `.env.example` — 追加 `HEALTH_MAX_KLINE_AGE_SECONDS` / `HEALTH_ALERT_COOLDOWN_SECONDS`；
  顺带修正 `WEB_PORT` 示例值 5000 → 8076 与代码默认值一致
- `AGENTS.md` — "启动流程"后新增"systemd 部署与健康检查"小节

由同事并行编写（本文档仅引用，不创建）：

- `deploy/systemd/realtime-kline-sync.service.in`
- `deploy/systemd/sync-macd-indicators.service.in`
- `deploy/systemd/kline-web.service.in`
- `deploy/systemd/service-health-check.service.in`
- `deploy/systemd/service-health-check.timer.in`
- `scripts/install_services.sh`

## 配置项

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `HEALTH_MAX_KLINE_AGE_SECONDS` | 180 | K线/指标数据最大允许滞后秒数 |
| `HEALTH_ALERT_COOLDOWN_SECONDS` | 600 | 同类告警冷却秒数 |
| `HEALTH_STATE_DIR` | 见上文优先级 | 冷却状态目录覆盖 |
| `DB_PATH` / `WEB_PORT` | 沿用 core/config | 数据库路径与 Web 端口 |

## 运维命令

```bash
# 安装/更新全部 service 与 timer
sudo bash scripts/install_services.sh

# 查看服务状态与日志
systemctl status db-driven-trading
journalctl -u db-driven-trading -n 100 --no-pager
journalctl -u service-health-check.service -n 50 --no-pager

# 手动触发一次健康检查（timer 之外）
systemctl start service-health-check.service

# 本地手动运行（调试用，退出码恒为 0）
python3 scripts/service_health_check.py
```

## 验证

- `python3 -m pytest tests/test_service_health_check.py -q` — 27 个用例全部通过
- `python3 scripts/service_health_check.py`（macOS 开发机）— systemctl 跳过、
  旧数据判定过期、飞书未启用不发送，退出码 0
- `python3 -m pytest tests/ -q` — 全量回归通过
