---
name: market-data
description: 港股与美股数据能力。支持实时、历史K线、技术指标、估值与机构持仓、行业ETF与美国宏观，且具备多渠道兜底。
---

# HK+US 数据能力

## 目标

以 Python 脚本直接拉数，不依赖 MCP。默认免密可运行，并提供多渠道兜底策略。

## 目录

- `scripts/fetch_realtime_hkus.py`
- `scripts/fetch_history_hkus.py`
- `scripts/fetch_technical_hkus.py`
- `scripts/fetch_fundamental_hkus.py`
- `scripts/fetch_sector_hkus.py`
- `scripts/fetch_macro_us.py`
- `scripts/fetch_universe_hkus.py`
- `scripts/fetch_market_realtime_hkus.py`
- `scripts/healthcheck_sources.py`

## 安装依赖

```bash
pip3 install yfinance pandas numpy requests pandas_datareader yahooquery pytest
```

## 代码规范

- US 代码统一输出为 `EXCHANGE:TICKER`，如 `NASDAQ:AAPL`
- HK 代码统一输出为 `NNNN.HK`，如 `0700.HK`
- 结果统一包含：
  - `source_primary`
  - `source_actual`
  - `fallback_used`
  - `fallback_chain`

## 渠道优先级

### US

- 历史/实时/技术：`yfinance -> yahooquery_history -> yahoo_chart`
- 基本面：`yfinance -> yahooquery`
- 宏观：`fred_reader -> fred_csv`

### HK

- 历史/技术：`yfinance -> yahoo_chart`
- 实时：`yfinance -> yahoo_chart -> tencent_quote`

## 快速命令

```bash
# 实时
python3 scripts/fetch_realtime_hkus.py --symbol AAPL --json
python3 scripts/fetch_realtime_hkus.py --batch AAPL,TSLA,0700.HK --json

# 历史
python3 scripts/fetch_history_hkus.py --symbol AAPL --interval 1d --days 180 --json
python3 scripts/fetch_history_hkus.py --batch AAPL,MSFT,0700.HK --workers 8 --json

# 技术
python3 scripts/fetch_technical_hkus.py AAPL --days 180 --interval 1d --json

# 基本面
python3 scripts/fetch_fundamental_hkus.py --symbol AAPL --json

# 行业与ETF
python3 scripts/fetch_sector_hkus.py --sector-name 半导体 --days 60 --json
python3 scripts/fetch_sector_hkus.py --symbol 0700.HK --json

# 美国宏观
python3 scripts/fetch_macro_us.py --interest-rates --days 365 --json
python3 scripts/fetch_macro_us.py --inflation-employment --months 36 --json
python3 scripts/fetch_macro_us.py --economic-growth --quarters 24 --json

# 渠道健康检查
python3 scripts/healthcheck_sources.py --us-symbol AAPL --hk-symbol 0700.HK

# 拉全市场股票清单
python3 scripts/fetch_universe_hkus.py --market all --json
python3 scripts/fetch_universe_hkus.py --market us --json
python3 scripts/fetch_universe_hkus.py --market hk --json

# 拉市场当前交易数据（可全市场）
python3 scripts/fetch_market_realtime_hkus.py --market all --universe-limit 800 --top 200 --json
python3 scripts/fetch_market_realtime_hkus.py --market us --universe-limit 1000 --top 100 --sort volume_desc --json
python3 scripts/fetch_market_realtime_hkus.py --symbols NASDAQ:AAPL,NYSE:MSFT,0700.HK --json
```

## 输出规则

- 默认输出简版摘要
- 带 `--json` 时输出完整结构
- 若主备源都失败，返回错误标识 `source_unavailable`
