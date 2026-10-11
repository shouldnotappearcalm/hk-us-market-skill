# 港美数据入口与参数

从技能根目录执行`python3 scripts/<入口> --help`查看实际解析器。以下列出功能、主要参数与结果位置；复权、行业、披露及缓存规则见 [数据契约](data-contracts.md)。

## 报价

`fetch_realtime_hkus.py`：单票`--symbol`，批量`--batch AAPL,MSFT,0700.HK`，`--workers`，`--json`。

- 批量先查询供应商批量接口，缺失项再逐票恢复；结果为meta及results[].ok/result/error。
- 单票美股可用`--with-premarket`显式补查盘前数据；默认不附加此请求。
- `--no-cache`绕过批量3秒结果缓存，单票目前没有该新增结果缓存。
- 价格在data.price/open/high/low/previous_close/change/change_pct/volume；报价时间和交易阶段字段按实际来源读取。

## 历史K线

`fetch_history_hkus.py`：`--symbol`或`--batch`，`--interval 1d|1wk|1mo|1m|5m|15m|30m|60m`，`--days`（180）、`--start/--end`、`--count`（180）、`--workers`（8）、`--json`。

- `--adjust raw|qfq|split_adjusted|total_return`默认raw，必须使用源支持的口径；`--no-cache`绕过该次数据缓存。
- 日期范围按交易所日期包含end当日全部分钟；data为OHLCV，含time和trade_date。
- 检查adjust_requested/adjust_actual、timezone、stale、data_time、coverage_start/coverage_end和cache。
- 批量meta提供requested/success/fail/success_rate，逐票状态在results。单次失败输出unavailable与原因。

## 技术指标

`fetch_technical_hkus.py`：symbol为位置参数；`--days`（180）、`--interval 1d|1wk|1mo`、`--adjust`（与历史相同）、`--no-cache`、`--json`。

返回data.series/latest/signals，含ma_5/20/60、macd_dif/dea/hist、rsi_14、boll_*、kdj_*。热身缺失值为null；现有signals是指标解释字段，不应解释为已经执行策略或交易。

## 估值与持仓

`fetch_fundamental_hkus.py --symbol SYMBOL --json`：返回估值、market_cap、beta、sector/industry与institutional_holders，主备源为yfinance/Yahooquery。某源没有字段时保留未知，报告发布时间与查询时间分开。

## 原始财报与SEC事实

`fetch_statements_hkus.py`：

| 参数 | 默认/功能 |
|---|---|
| `--symbol` | Yahoo财报必填，支持港美证券 |
| `--source yahoo/sec` | 默认yahoo（实际参数写`yahoo`或`sec`） |
| `--kind income/balance/cashflow` | Yahoo三表，默认income |
| `--period annual/quarterly` | Yahoo周期，默认annual |
| `--cik` | SEC明确发行人身份，避免依赖ticker映射 |
| `--as-of` | SEC filed日期截止，YYYY-MM-DD |
| `--start/--end` | SEC事实的period-end区间，不是公告日期 |
| `--no-cache/--json` | 绕过缓存/JSON输出 |

Yahoo返回data[].period_end/raw，行项目和数值为供应商原值，不推断币种；as-of/start/end仅用于SEC，Yahoo模式会拒绝。SEC返回taxonomy/concept/label/unit/raw，保留版本，日粒度可见性与在线403限制见 [财务数据](data-contracts.md#财务数据)。

## 行业目录与真实成员

`fetch_industry_hkus.py`：`--action directory|members|profile`（默认directory），`--market US|HK`（默认US），`--industry`，`--sector`，`--pages`（4，1..20），`--no-cache`、`--json`。

- directory提供sector/industry名称与key，注明SDK版本；这不保证每个市场都有该行业公司。
- members/profile要求一个明确industry名称或key，从directory取值。members按行业和市场分页，data[].raw保留公司记录，meta.count/total/coverage_limited说明覆盖。
- profile含overview和top_companies，不能把头部公司当完整成员。当前快照无法证明历史成员；effective_at未知保留null。

## 个股行业与ETF代理

`fetch_sector_hkus.py`：`--symbol`查询个股行业；`--sector-name`查询明确行业ETF代理；`--etf SOXX`可显式指定；`--days`默认30，支持`--json`。

ETF区间数据是代理，不是行业指数或真实成员。未知行业且未明确ETF时失败，不默认替换为SPY。

## 原始新闻

`fetch_news_hkus.py`：`--symbol`用于Yahoo证券新闻，`--keyword`用于东财公司/行业关键词，可同时给出；`--source all|yahoo|eastmoney`默认all。

- `--days`默认7（含今天的自然日），`--limit`默认100（每源，1..200），`--pages`默认2（东财，1..5），`--max-seconds`默认20（1..60），支持`--json`。
- 返回status/symbol/keyword/meta/data，每条为source/raw；默认不做语义分类、情绪判断、相关性过滤、去重或摘要。content可能是检索片段。
- Yahoo为空不证明没有新闻；coverage_limited表示候选集/分页覆盖受限。全部源失败时CLI非零退出。
- 当前没有新增磁盘结果缓存，也没有--no-cache参数；请勿把其他入口的缓存参数套用到此脚本。

## 官方披露、RSS与原始附件

`fetch_disclosures_hkus.py`：

| 用途 | 参数 |
|---|---|
| 港交所公告 | `--symbol 09988.HK`；`--language ZH/EN`默认ZH |
| SEC申报 | 美股`--symbol`或明确`--cik`；`--forms 6-K,20-F`可显式选类型，默认保留全部类型 |
| 公司RSS/Atom | `--rss-url URL`，仅使用明确给出的feed地址 |
| 原始正文/附件 | `--document-url URL`；PDF/二进制必须加`--output PATH`保存原始字节 |
| 时间与覆盖 | `--days`默认30（1..365），`--limit`默认100（1..1000） |
| 缓存与输出 | `--no-cache`、`--json` |

每次选择一种用途。公告data[].raw保持供应商字段，url提供原始附件；meta有发行人、覆盖及抓取时间。RSS返回raw条目与原始feed。文档下载输出字节数、content_type、SHA256和输出路径，上限5MiB。正文与PDF不会自动摘要。SEC身份映射、403与覆盖边界见 [官方披露](data-contracts.md#公司官方披露rss和原始附件)。

## 证券搜索

`search_symbols_hkus.py KEYWORD --json`：使用腾讯smartbox搜索港美候选，返回market/code/name/raw。中文名称按协议解码，class-share代码保留，raw保留原始记录；候选集有限，不能保证覆盖全部证券。此入口不自动为新闻拼接别名或替换ADR。

## 数据源诊断

- `inspect_sources_hkus.py`：无symbol只列capabilities；提供`--symbol`实测历史K线，可选`--source all|tencent_history|sina_history|yfinance|yahooquery_history|yahoo_chart`、`--adjust`（四种历史口径）、`--days`（30）、`--json`。结果看sources[].status/count/elapsed_sec/error/data；unsupported不当作源宕机。当前是历史K线诊断，不是所有能力的指定源开关。
- `healthcheck_sources.py --us-symbol AAPL --hk-symbol 0700.HK`：直接输出JSON，matrix给简版状态，diagnostics给每源ok/empty/failed、记录数、耗时及错误。它只测代表性行情、基本面与宏观源，不覆盖所有新增行业/公告接口。

## 美国宏观

`fetch_macro_us.py`：`--interest-rates --days N`取DGS2/DGS10/FEDFUNDS；`--inflation-employment --months N`取CPIAUCSL/UNRATE；`--economic-growth --quarters N`取GDPC1；支持`--json`。FRED reader失败可降级CSV，数据按各序列发布节奏更新。

## 证券清单与市场扫描

- `fetch_universe_hkus.py --market all|us|hk --limit N --json`：data含symbol/name/market/exchange/source，meta含total/returned/sources。未给limit时按脚本默认范围取数。
- `fetch_market_realtime_hkus.py`：`--market all|us|hk`，或用`--symbols NASDAQ:AAPL,NASDAQ:MSFT,0700.HK`明确列表；`--universe-limit`默认800（每市场），`--workers`默认12、`--top`默认100、`--sort change_pct_desc|change_pct_asc|volume_desc|price_desc`，支持`--json`。meta报告请求/成功/失败与源计数，data为显示结果，failed为失败列表；top显示限制不等于只请求top只股票。
