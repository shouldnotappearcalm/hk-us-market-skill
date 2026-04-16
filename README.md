# hk-us-market-skill

面向港股与美股的量化技能集合，覆盖两类核心能力：

- `market-data`：多源容错市场数据（实时、历史、技术、基本面、行业、宏观、全市场扫描）
- `paper-trading`：港美模拟交易与回测（多账户、订单撮合、净值与批量回测）

## 目录结构与 Skill 列表

```bash
hk-us-market-skill/
  market-data/      # 港美市场数据技能
  paper-trading/    # 港美模拟仓与回测技能
  README.md
```

说明：本目录采用扁平化结构，每个 skill 目录内部保持 `SKILL.md + scripts/ (+ references/)` 的标准组织方式，便于单独复用和持续扩展。

## Skill 能力总览

- `market-data`：港股与美股数据能力  
  - **主要能力**：  
    - 单票/批量实时行情  
    - 日/周/月历史 K 线  
    - 常用技术指标计算  
    - 基本面数据与行业视角  
    - 美国宏观数据  
    - 全市场股票清单与市场级实时扫描  
  - **关键特性**：  
    - 纯 Python 拉取数据，不依赖 MCP  
    - 多渠道 fallback，支持主源失败自动切换  
    - 输出字段统一，便于下游策略和回测复用

- `paper-trading`：港美模拟仓能力  
  - **主要能力**：  
    - 多账户管理（创建、重置、默认账户、资金调整）  
    - 限价/市价单下单、撤单、成交与持仓查询  
    - 账户估值与净值快照  
    - 单票回测与全市场批量回测（支持最小成功样本控制）  
  - **关键特性**：  
    - 运行目录与缓存独立  
    - 交易和数据流程可脚本化验证  
    - 支持 `US/HK` 交替扫描的大样本回测流程

## 快速开始

以下命令在仓库根目录执行。

### 1) 数据能力

```bash
cd hk-us-market-skill/market-data
pip3 install yfinance pandas numpy requests pandas_datareader yahooquery pytest

python3 scripts/fetch_realtime_hkus.py --symbol AAPL --json
python3 scripts/fetch_history_hkus.py --symbol 0700.HK --days 180 --interval 1d --json
python3 scripts/fetch_universe_hkus.py --market all --json
python3 scripts/fetch_market_realtime_hkus.py --market all --universe-limit 800 --top 200 --json
```

### 2) 模拟仓能力

```bash
cd hk-us-market-skill/paper-trading
python3 scripts/paper_trading_service.py --host 127.0.0.1 --port 18766
```

另开终端调用 CLI：

```bash
cd hk-us-market-skill/paper-trading
python3 scripts/paper_trade_cli.py create-account alpha --cash 500000
python3 scripts/paper_trade_cli.py buy alpha AAPL 10 --market
python3 scripts/paper_trade_cli.py buy alpha 0700.HK 100 --price 320
python3 scripts/paper_trade_cli.py positions alpha
```

## 回测与验证

### 基础烟测

```bash
python3 hk-us-market-skill/paper-trading/scripts/full_function_smoke_check.py
```

### 全市场批量回测

```bash
python3 hk-us-market-skill/paper-trading/scripts/batch_backtest_hkus.py \
  --market all \
  --min-success 500 \
  --start 2025-01-01 \
  --output hk-us-market-skill/paper-trading/reports/backtest_500_all.json
```

说明：批量回测会先扫描全市场池，并在达到 `--min-success` 指定的可用样本后停止；可按需提高阈值以扩大样本规模。

## 运行目录与缓存

`paper-trading` 默认运行目录为：

- macOS: `~/Library/Application Support/hk-us-market-paper-trading/`
- Linux: `${XDG_DATA_HOME:-~/.local/share}/hk-us-market-paper-trading/`

默认文件：

- SQLite：`paper_trading.db`
- 行情缓存：`cache/quote_cache.json`

可通过环境变量 `HK_US_PAPER_TRADING_HOME` 覆盖运行目录。

## 开发约定

- 默认市场代码规范：  
  - US: `EXCHANGE:TICKER`，例如 `NASDAQ:AAPL`  
  - HK: `NNNN.HK`，例如 `0700.HK`
- 新增脚本优先保持与现有输出结构一致，避免下游解析分叉
- 对外部数据源调用默认走可回退链路，避免单点失效
