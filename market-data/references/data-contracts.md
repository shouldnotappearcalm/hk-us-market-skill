# 港美数据口径与使用边界

从技能根目录运行以下示例。各入口完整参数见 [API参考](api-reference.md)。

## 行情口径

历史入口新增 `--adjust raw|qfq|split_adjusted|total_return`，默认 raw。

| 口径 | 可用适配器 | 含义 |
|---|---|---|
| raw | 腾讯、新浪 | 供应商原始价端点，不做应用层复权；仍需参考供应商对拆股/成交量的定义 |
| qfq | 腾讯 | 前复权；港股使用 hkfqkline 专用端点，必须实际返回 qfq 节点 |
| split_adjusted | yfinance、Yahooquery、Yahoo chart | Yahoo 的拆股调整 OHLC，不冒充历史名义原始价 |
| total_return | yfinance、Yahooquery | Yahoo 的拆股、分红调整价格；不与腾讯前复权混用 |

不支持所请求口径的源会明确拒绝，不访问其数据端点。只有相同口径才可以降级。Yahoo-only 场景请显式选择 split_adjusted/total_return。

```bash
python3 scripts/fetch_history_hkus.py --symbol 09988.HK --adjust qfq --count 10 --json
python3 scripts/fetch_history_hkus.py --symbol BRK.B --adjust raw --count 10 --json
python3 scripts/fetch_history_hkus.py --symbol AAPL --adjust split_adjusted --count 10 --no-cache --json
python3 scripts/inspect_sources_hkus.py --symbol 09988.HK --source tencent_history --adjust qfq --json
python3 scripts/search_symbols_hkus.py 阿里巴巴 --json
```

BRK.B/BRK-B 保留同一证券身份，分别映射为 Yahoo BRK-B、腾讯 usBRK.B。交易所前缀只是请求提示，`exchange_verified=false`；未知前缀不被冒充为 NASDAQ。新浪港美价格/昨收/开盘字段按真实原始响应修复。

日线返回 ISO8601 带时区时间及 `trade_date`；分钟线保留交易所时区。日期过滤按交易所日期包含 end 当天全部分钟。交易日历使用 exchange_calendars；`updated_at` 是抓取时间，`data_time` 才是数据日期。供应商报价时间另保留 `quote_time_raw` 与 `quote_time_basis`，不声称它一定是最后成交时间。

腾讯/新浪分钟适配器只接受原生1m，不再把1m静默当成5m/60m。其他分钟周期由支持该周期的源提供。历史先检查OHLC有效性、尝试新鲜来源；所有新鲜源失败时可保留最新有效旧数据，但明确 `stale=true` 及诊断。

## 行业分类和真实成员

```bash
python3 scripts/fetch_industry_hkus.py --action directory --sector technology --json
python3 scripts/fetch_industry_hkus.py --action members --industry semiconductors --market US --pages 4 --json
python3 scripts/fetch_industry_hkus.py --action members --industry semiconductors --market HK --pages 4 --json
python3 scripts/fetch_industry_hkus.py --action profile --industry semiconductors --market US --json
```

Yahoo 分类不冒充 GICS/申万；目录注明 SDK 版本，成员使用显式行业、市场条件分页。原始公司记录位于 `data[].raw`；total/coverage_limited 标识覆盖，供应商分类及数量可能变化。profile 的头部公司与成员列表区分。当前成员不等于历史成员，effective_at 未知时保留 null。原行业ETF代理入口继续独立保留，ETF不是成员列表。

## 公司官方披露、RSS和原始附件

```bash
python3 scripts/fetch_disclosures_hkus.py --symbol 09988.HK --days 30 --json
python3 scripts/fetch_disclosures_hkus.py --symbol 2899.HK --days 30 --language ZH --json
python3 scripts/fetch_disclosures_hkus.py --cik 1577552 --days 30 --json
python3 scripts/fetch_disclosures_hkus.py --rss-url https://nvidianews.nvidia.com/releases.xml --days 30 --json
python3 scripts/fetch_disclosures_hkus.py --document-url '<公告中的原始附件URL>' --output /tmp/filing.pdf --json
```

港交所先按真实股票代码查 stockId，保留原始公告字段、附件链接和覆盖总数，不硬编码公司身份。SEC 保留原始申报记录，可明确选择 forms，默认保留所有类型；较老分卷未自动抓取时标覆盖受限。正文/附件只按显式URL获取，PDF保存原始字节并记录SHA256，不自动摘要。RSS保留原始feed与解析条目；时间未知条目不静默丢弃。

SEC最近一次在线验证（2026-10-11）返回403，包括显式CIK路径；不能仅凭已有适配代码声称在线已跑通。可配置 `SEC_USER_AGENT="项目名 联系邮箱"` 后再验证，不保证配置本身一定解除上游限制。身份映射失败不解释成公司没有公告。此适配器通过离线协议测试，港交所和官方RSS已在线实测。

原有 fetch_news_hkus 继续保留供应商原始记录，无语义筛选、分类、情绪、去重或摘要。

## 财务数据

```bash
python3 scripts/fetch_statements_hkus.py --symbol 09988.HK --kind income --period annual --json
python3 scripts/fetch_statements_hkus.py --symbol AAPL --kind cashflow --period quarterly --json
python3 scripts/fetch_statements_hkus.py --source sec --cik 320193 --as-of 2026-01-01 --start 2025-01-01 --json
```

Yahoo三表保留原始行项目，不凭空填币种，不能证明历史可见时间，遇到 --as-of 会拒绝。SEC companyfacts 保留 taxonomy/concept/unit/原始事实和版本，按 filed 日期过滤；这是日粒度，不是日内可见性保证，也不是财务报表重新分类器。自定义XBRL/未标注数据可能不在官方聚合接口内。SEC在线可用性限制同上。

## 缓存与取数

- 历史行情默认缓存300秒；分钟15秒；批量报价3秒；行业目录/成员和财报按各入口元信息TTL缓存。
- 支持该参数的入口用`--no-cache`跳过本次结果缓存；HKUS_NO_CACHE=1控制通用缓存，HKUS_CACHE_DIR可配置目录，默认在本技能cache/。单票实时和媒体新闻当前没有新增结果缓存；SEC身份映射等辅助缓存不一定由入口的--no-cache一并清除。缓存返回原始 fetched_at、cache_hit 和TTL，过期缓存不会在上游失败时假装新数据。
- 同参数并发请求只在同一进程内合并；多个CLI进程仍可能重复请求。原始价日线过期后补近期重叠区间，同源合并，跨源重新取完整区间；调整价完整刷新。供应商对更老数据的修订需要定期完整刷新，--no-cache会完整拉取。
- 外部请求使用固定12个后台工作线程与48个排队位置；超时停止等待并取消未开始任务。库内部正在执行的请求不能强杀，但不会无限新建线程。
- 三次连续源失败后在当前进程短暂熔断30秒，按能力/口径隔离。批量报价先使用供应商批量接口，只对缺失代码单票补取。
- 交易日历缓存单独标识SDK版本并每日更新，避免每次启动重复构造日历。

缓存实现为本地JSON文件，过期不等于自动删除；当前没有容量上限、自动清理或跨进程请求合并，SQLite也尚未实现。缓存、并发和源适配在scripts中提供，正常取数无需部署额外缓存服务。只读安装位置可能无法保存缓存，取数仍可执行。


| 数据 | 当前结果缓存TTL |
|---|---:|
| 历史日/周/月线 | 300秒 |
| 历史分钟线 | 15秒 |
| 批量报价 | 3秒；部分失败的批次不缓存 |
| 行业成员/profile、Yahoo财报、SEC事实 | 1小时 |
| 行业目录 | 来自SDK分类目录，不新增结果磁盘缓存 |
| 港交所/SEC披露、公司RSS | 120秒 |
| SEC ticker→CIK身份映射 | 7天 |
| 交易日历 | 1天，缓存键包含日历SDK版本 |

缓存命中仍保留原始fetched_at，正常查询结果中的cache_hit、TTL和来源诊断都应保留。API失败/异常不作为成功结果缓存；合法空结果在部分入口会按相同TTL缓存。缓存目录只包含运行数据，不应提交Git。
