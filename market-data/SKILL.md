---
name: market-data
description: 港股与美股数据能力。支持实时、历史K线、技术指标、估值与机构持仓、行业ETF与美国宏观，且具备多渠道兜底。
---

# HK+US 数据能力

## 目标

以 Python 脚本直接拉数，不依赖 MCP。默认免密可运行，并提供多渠道兜底策略。

## 目录

- `scripts/fetch_news_hkus.py`（港美证券新闻/行业关键词新闻，原始输出）
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
pip3 install -r requirements.txt
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

### US / HK（行情与K线）

- 实时：`tencent_quote -> sina_quote -> yahooquery_realtime -> yfinance -> yahoo_chart`
- 历史/技术：`tencent_history -> sina_history -> yfinance -> yahooquery_history -> yahoo_chart`

腾讯、新浪均区分港/美代码。实时用 `usAAPL` / `hk00700`；K 线用 `fqkline/get`，美股需带交易所后缀（如 `usAAPL.OQ`、`usJPM.N`、`usSPY.AM`，由 qt 行情自动解析）。分钟 K 港股走 `minute/query`；美股盘中仅返回当前分钟快照，历史分钟由 Yahoo 兜底。实时结果含 `market_state` 与 `premarket`；单票美股仅显式加 `--with-premarket` 时补查Yahoo；默认不增加额外请求。

### 其他

- 基本面（US）：`yfinance -> yahooquery`
- 宏观：`fred_reader -> fred_csv`

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


## 新闻与数据真实性

- 新闻优先 `fetch_news_hkus.py --symbol NYSE:BABA --days 7 --json`。港股可用 `--symbol 09988.HK --keyword 阿里巴巴` 同时查两源，行业可用 `--keyword 半导体 --source eastmoney`。每条`raw`保留上游字段，不做相关性/事件/情绪硬规则分类，提供原始结果供调用方分析。
- Yahoo空结果与源失败分开；原始content可能只是摘要。`days/limit/pages`控制窗口与覆盖，保留来源状态。新闻当前无新增磁盘结果缓存。
- 行情/历史/技术/基本面按需降级，禁用源不调用；异常/空结果继续下一源，source_errors与source_elapsed_sec记录诊断。HKUS_SOURCE_TIMEOUT默认6秒，HKUS_MAX_SECONDS默认25秒。
- 行业ETF映射是显式代理，不是行业分类/成分库；不认识的行业返回错误，可用`--etf SOXX`显式选代理。
- 原始报价时间`quote_time`与查询时间`updated_at`分开。未知美股交易所输出US占位，可显式指定NYSE:BABA；不要凭默认值推断真实上市地点。
- 正式数据验证命令：在仓库根目录 `python -m pytest market-data/tests -q`；`python market-data/scripts/full_function_smoke_check.py --json`。这两条不运行策略或模拟仓。
- 实测与限制：`../reports/data-health-2026-10-11.md`。
