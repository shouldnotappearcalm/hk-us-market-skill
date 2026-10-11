# 港美数据与新闻体检（2026-10-11）

仓库已克隆至父目录 `hk-us-market-skill`。只修改/运行market-data数据部分，未运行策略、回测或模拟交易。证据环境为独立Python3.12；依赖列于market-data/requirements.txt。

## 主要修复

- 腾讯港股最新价/昨收/开盘字段错位修复。阿里原始报价分别为107、104.3、104.5；当前计算涨幅2.5887%。保留原报价时间，周末状态CLOSED。
- `09988.HK`规范为Yahoo的`9988.HK`、腾讯的`hk09988`；港交所Excel数值700.0不再变成7000。未知美股交易所使用US占位，不凭空标NASDAQ；可显式传NYSE:BABA。
- fallback改为按需调用：主源有数据就不请求备用源，禁用源完全跳过，异常/空结果/超时可继续下一源。默认单源等待6秒、整条链25秒，可用HKUS_SOURCE_TIMEOUT/HKUS_MAX_SECONDS调整；结果新增source_errors/source_elapsed_sec。
- 每线程复用HTTP连接；盘前补齐改为单只美股显式`--with-premarket`，默认保留主源字段，不额外查Yahoo。
- 港股基本面也可降级Yahooquery；机构持仓失败保留其他已取得字段；所有估值为空的结果不冒充成功。
- 行业ETF代理使用真实行情主备链并标真实来源；未知行业不再默认SPY，可用`--etf SOXX`显式指定。ETF代理不是行业成分股清单。个股行业字段为空会明确失败。
- FRED主源成功后不重复查CSV；健康检查独立探测各源并记录空/失败/耗时。全功能检查逐命令限时、检查JSON内容且失败非零退出，不再只看退出码0。
- 指标热身缺失值使用标准JSON null，未删除热身行。

## 港股与美股新闻

入口 `market-data/scripts/fetch_news_hkus.py`，默认输出JSON。

```bash
python3 market-data/scripts/fetch_news_hkus.py --symbol NYSE:BABA --days 7 --limit 100 --json
python3 market-data/scripts/fetch_news_hkus.py --symbol NASDAQ:NVDA --days 7 --json
python3 market-data/scripts/fetch_news_hkus.py --symbol 09988.HK --keyword 阿里巴巴 --days 7 --json
python3 market-data/scripts/fetch_news_hkus.py --symbol 2899.HK --keyword 紫金矿业 --days 7 --json
python3 market-data/scripts/fetch_news_hkus.py --keyword 半导体 --source eastmoney --days 7 --json
```

- Yahoo Search新闻按证券代码取；东方财富搜索按用户明确给出的公司名/行业关键词取。指定`--source yahoo/eastmoney/all`，不自动拼别名、不暗中把港股替换成ADR。
- 每条在`data[].raw`中保留未改写的上游字段，`source`标来源。不按业务相关性/情绪筛选、不合并去重、不生成摘要。日期窗口与每源limit/pages仍生效，覆盖截断与未知时间会标明。
- 原始content可能只是检索片段，不保证完整正文或抓全全部新闻。
- 本轮BABA：Yahoo原始49条候选，近7天25条；NVDA：近7天49条。阿里港股东财100条，紫金港股东财76条；这两个港股代码在Yahoo返回空并如实保留诊断。
- yfinance ticker-stream本轮返回空，故使用实测可用的Search路径。Yahoo空结果不证明公司没有新闻，亦不宣称全球媒体全覆盖。

## 测试与性能

- 21项离线回归通过；原16个代表数据入口完成在线复测；原有21项正式命令与强制降级检查21/21通过。退出码/JSON通过不等于所有数据字段都正确，因此价格与缺失值另有回归。
- 17个独立源探测：16个有返回，新浪美股历史返回空。主路径可用不代表每个备用源都可用。
- 与Git原始快照交替3轮，计时含进程启动及完整JSON，未使用新增数据缓存：港股报价中位数4.614→0.380秒；美股历史3.405→0.624秒，两版均10根。当前网络样本，不是SLA；新闻新入口无旧版同口径基准。
- 港交所与NASDAQ全证券清单、批量市场扫描也在数据检查范围；未验证策略侧收益或订单执行。

机器证据：[JSON](data-health-2026-10-11.json)。完整原始输出保留在 `reports/raw/data-health-2026-10-11/`（gitignore），新闻文件以hk-/us-命名。

## 边界与后续

港股行业信息仍依赖Yahoo部分字段；真正行业成分和申万等分类需另接适用市场数据。港股Yahoo新闻可能空，东财需要明确关键词。FRED数据与机构持仓各有发布延迟，查询时间不是业务数据时间。原有技术信号字段未扩展为新策略。

行业能力可参考CNEquity的版本化数据层、adata的多源行业与成分接口；产业链图谱参考ChainKnowledgeGraph的数据模型。本轮只是调研，没有安装或宣称第三方项目接口已跑通。
