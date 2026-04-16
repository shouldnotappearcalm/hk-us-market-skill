---
name: paper-trading
description: 港股+美股模拟仓技能。支持多账户、下单撮合、持仓资金查询、回测，并使用独立缓存目录。
---

# HK+US 模拟仓

独立的港美模拟盘 skill。交易服务、CLI、账户、撮合和行情适配都在本目录内，不依赖 A 股模拟仓脚本。

## 何时使用

- 启动或检查模拟盘服务
- 创建/重置账户
- 港股和美股下单、撤单
- 查询账户、持仓、订单、成交
- 跑 US/HK 回测
- 验证缓存隔离（与 `a-share-paper-trading` 分离）

## 启动

```bash
SKILL_DIR="/Users/yanyun/dev/git_repo/ai-stock/ai-stock-data-v2/hk-us-market-skill/paper-trading"
python3 "$SKILL_DIR/scripts/paper_trading_service.py" --host 127.0.0.1 --port 18766
```

更推荐用控制脚本常驻运行：

```bash
python3 "$SKILL_DIR/scripts/paper_trading_ctl.py" start
python3 "$SKILL_DIR/scripts/paper_trading_ctl.py" status
python3 "$SKILL_DIR/scripts/paper_trading_ctl.py" stop
```

在 macOS 上，如需持续自启动：

```bash
python3 "$SKILL_DIR/scripts/paper_trading_ctl.py" install-launchd
python3 "$SKILL_DIR/scripts/paper_trading_ctl.py" uninstall-launchd
```

默认监听 `http://127.0.0.1:18766`。

默认运行目录（独立 cache）：

- macOS: `~/Library/Application Support/hk-us-market-paper-trading/`
- Linux: `${XDG_DATA_HOME:-~/.local/share}/hk-us-market-paper-trading/`
- 缓存：`cache/quote_cache.json`

可通过 `HK_US_PAPER_TRADING_HOME` 覆盖路径。

## CLI

```bash
python3 "$SKILL_DIR/scripts/paper_trade_cli.py" create-account alpha --cash 500000
python3 "$SKILL_DIR/scripts/paper_trade_cli.py" list-accounts
python3 "$SKILL_DIR/scripts/paper_trade_cli.py" show-default-account
python3 "$SKILL_DIR/scripts/paper_trade_cli.py" set-default-account alpha
python3 "$SKILL_DIR/scripts/paper_trade_cli.py" reset-account alpha --cash 300000
python3 "$SKILL_DIR/scripts/paper_trade_cli.py" add-cash alpha 50000 --note deposit
python3 "$SKILL_DIR/scripts/paper_trade_cli.py" deduct-cash alpha 10000 --note withdraw
python3 "$SKILL_DIR/scripts/paper_trade_cli.py" buy alpha AAPL 10 --market
python3 "$SKILL_DIR/scripts/paper_trade_cli.py" buy alpha 0700.HK 100 --price 320
python3 "$SKILL_DIR/scripts/paper_trade_cli.py" sell alpha AAPL 10 --price 200
python3 "$SKILL_DIR/scripts/paper_trade_cli.py" orders alpha
python3 "$SKILL_DIR/scripts/paper_trade_cli.py" positions alpha
python3 "$SKILL_DIR/scripts/paper_trade_cli.py" show-account alpha
python3 "$SKILL_DIR/scripts/paper_trade_cli.py" trades alpha
python3 "$SKILL_DIR/scripts/paper_trade_cli.py" cancel <order_id>
python3 "$SKILL_DIR/scripts/paper_trade_cli.py" process-orders
python3 "$SKILL_DIR/scripts/paper_trade_cli.py" run-snapshots
python3 "$SKILL_DIR/scripts/paper_trade_cli.py" backtest AAPL --strategy sma_cross --start 2025-01-01 --end 2026-03-31 --cash 200000
```

## 规则摘要

- long-only
- 买卖数量均为正整数股数
- US 默认价格最小变动 `0.01`
- HK 默认价格最小变动 `0.001`
- 限价单价格需满足最小变动单位
- 市价单和限价单都走统一撮合引擎
- 费用模型按市场区分费率，税默认 0

## 测试

```bash
python3 "$SKILL_DIR/scripts/full_function_smoke_check.py"
python3 "$SKILL_DIR/scripts/batch_backtest_hkus.py" --market all --min-success 500 --start 2025-01-01 --output "$SKILL_DIR/reports/backtest_500_all.json"
```

该 smoke 脚本覆盖：

- 引擎基础流程（开户、买卖、持仓、快照、回测）
- 服务+CLI 联动
- cache 路径隔离检查

批量回测脚本 `batch_backtest_hkus.py` 用于全市场扫描与大样本回测，支持按 `--min-success` 至少完成指定数量的可用票回测。
