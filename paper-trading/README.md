# paper-trading

独立的港股+美股模拟仓 skill，和 `market-data` 解耦，负责：

- 多账户模拟交易
- 限价单、市价单、撤单
- 持仓、订单、成交、账户净值
- US/HK 回测
- 本地独立缓存与独立 SQLite

## 默认运行目录

- macOS: `~/Library/Application Support/hk-us-market-paper-trading/`
- Linux: `${XDG_DATA_HOME:-~/.local/share}/hk-us-market-paper-trading/`

默认数据库：

- `~/Library/Application Support/hk-us-market-paper-trading/paper_trading.db`

默认缓存：

- `~/Library/Application Support/hk-us-market-paper-trading/cache/quote_cache.json`

可通过环境变量 `HK_US_PAPER_TRADING_HOME` 覆盖运行目录。

## 启动服务

```bash
python3 /Users/yanyun/dev/git_repo/ai-stock/ai-stock-data-v2/hk-us-market-skill/paper-trading/scripts/paper_trading_service.py --host 127.0.0.1 --port 18766
```

## 控制脚本

```bash
python3 /Users/yanyun/dev/git_repo/ai-stock/ai-stock-data-v2/hk-us-market-skill/paper-trading/scripts/paper_trading_ctl.py start
python3 /Users/yanyun/dev/git_repo/ai-stock/ai-stock-data-v2/hk-us-market-skill/paper-trading/scripts/paper_trading_ctl.py status
python3 /Users/yanyun/dev/git_repo/ai-stock/ai-stock-data-v2/hk-us-market-skill/paper-trading/scripts/paper_trading_ctl.py stop
```

## CLI 示例

```bash
python3 /Users/yanyun/dev/git_repo/ai-stock/ai-stock-data-v2/hk-us-market-skill/paper-trading/scripts/paper_trade_cli.py create-account alpha --cash 500000
python3 /Users/yanyun/dev/git_repo/ai-stock/ai-stock-data-v2/hk-us-market-skill/paper-trading/scripts/paper_trade_cli.py buy alpha AAPL 10 --market
python3 /Users/yanyun/dev/git_repo/ai-stock/ai-stock-data-v2/hk-us-market-skill/paper-trading/scripts/paper_trade_cli.py buy alpha 0700.HK 100 --price 320
python3 /Users/yanyun/dev/git_repo/ai-stock/ai-stock-data-v2/hk-us-market-skill/paper-trading/scripts/paper_trade_cli.py positions alpha
python3 /Users/yanyun/dev/git_repo/ai-stock/ai-stock-data-v2/hk-us-market-skill/paper-trading/scripts/paper_trade_cli.py backtest AAPL --strategy sma_cross --start 2025-01-01 --end 2026-03-31 --cash 200000
```

## 测试

```bash
python3 /Users/yanyun/dev/git_repo/ai-stock/ai-stock-data-v2/hk-us-market-skill/paper-trading/scripts/full_function_smoke_check.py
python3 /Users/yanyun/dev/git_repo/ai-stock/ai-stock-data-v2/hk-us-market-skill/paper-trading/scripts/batch_backtest_hkus.py --market all --min-success 500 --start 2025-01-01 --output /Users/yanyun/dev/git_repo/ai-stock/ai-stock-data-v2/hk-us-market-skill/paper-trading/reports/backtest_500_all.json
```
