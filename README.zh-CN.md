# 港股与美股数据 Skills

[English](README.md) | **简体中文**

面向港股与美股数据查询的 Python Agent Skills，覆盖报价、历史行情、公司新闻、官方披露、财报、行业与宏观。

通过 Agent 或 Python CLI 查询数据，获取结构化 JSON，并按明确的数据源、日期与覆盖口径使用结果。从 `market-data/` 开始即可，无需启动 MCP 服务。

[快速开始](#快速开始) · [数据查询示例](#数据查询示例) · [数据契约](market-data/references/data-contracts.md) · [文档索引](#文档索引)

## 能力概览

| 类别 | 可以查询或运行什么 |
|---|---|
| 行情 | 单票与批量报价、分钟及日/周/月 K 线、显式复权选择、技术指标 |
| 新闻与披露 | 原始公司与关键词新闻、港交所/SEC 适配器、公司 RSS/Atom、原始正文和附件 |
| 财务 | 估值、机构持仓、利润表、资产负债表、现金流量表、SEC XBRL 事实 |
| 行业 | 行业目录、公司分类与当前成员；单独标明的行业 ETF 代理 |
| 宏观与证券发现 | 美国利率、通胀、就业与 GDP；证券搜索、证券清单和有规模上限的市场扫描 |
| 数据源诊断 | 主备来源信息、逐源错误、历史行情源探测、本地 JSON 缓存信息 |

不同入口的数据源可用性与覆盖范围不同。日期、复权、部分结果和当前限制见[数据契约](market-data/references/data-contracts.md)。

## 快速开始

推荐 Python 3.12。以下安装示例使用 POSIX shell：

```bash
git clone https://github.com/shouldnotappearcalm/hk-us-market-skill.git
cd hk-us-market-skill
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r market-data/requirements.txt

python market-data/scripts/fetch_realtime_hkus.py --symbol AAPL --json
```

后续示例均从仓库根目录执行，并保持上述环境已激活。

### 在 Agent 中使用

将完整 skill 目录（如 `market-data/`）复制到 Agent 配置的技能目录。保留其中的 `SKILL.md`、`scripts/`、`references/` 和依赖文件，各 skill 的说明中有具体安装要求。各目录可单独安装，无需同时安装 A 股仓库。

只查数据时，从 [market-data/SKILL.md](market-data/SKILL.md) 开始。模拟仓和策略目录作为可选扩展，放在本文末尾说明。

## 数据查询示例

### 报价、证券搜索与历史行情

```bash
python market-data/scripts/search_symbols_hkus.py Alibaba --json
python market-data/scripts/fetch_realtime_hkus.py --batch AAPL,BRK.B,09988.HK --json
python market-data/scripts/fetch_history_hkus.py --symbol 09988.HK --adjust qfq --count 10 --no-cache --json
```

美股支持 `AAPL`、`NYSE:BABA`、`BRK.B` 等写法。港股 `09988.HK` 与 `9988.HK` 指向同一证券。交易所前缀是请求提示，不能据此认证上市地点。

### 公司新闻与官方披露

```bash
python market-data/scripts/fetch_news_hkus.py --symbol NYSE:BABA --days 7 --json
python market-data/scripts/fetch_news_hkus.py --symbol 09988.HK --keyword 阿里巴巴 --days 7 --json
python market-data/scripts/fetch_disclosures_hkus.py --symbol 09988.HK --days 30 --json
```

新闻在 `data[].raw` 中保留供应商原始字段，不做语义筛选、去重、情绪判断或生成摘要。东财关键词查询需显式提供 `--keyword`。媒体新闻和官方披露使用独立入口，搜索片段不等于完整正文。RSS 与文档下载参数见 [API 参考](market-data/references/api-reference.md)。

### 财报、行业与宏观

```bash
python market-data/scripts/fetch_statements_hkus.py --symbol AAPL --kind cashflow --period quarterly --json
python market-data/scripts/fetch_industry_hkus.py --action members --industry semiconductors --market HK --pages 4 --json
python market-data/scripts/fetch_macro_us.py --interest-rates --days 30 --json
```

### 检查指定历史行情源

```bash
python market-data/scripts/inspect_sources_hkus.py --symbol 09988.HK --source tencent_history --adjust qfq --json
```

取数后检查来源状态、覆盖范围、数据日期与错误，不能把请求成功当作数据完整或最新。不同脚本的输出结构和缓存开关不同，以其 `--help` 和 API 参考为准。

## 数据口径与当前限制

- **原始数据与来源可见：** 保留供应商记录、来源错误和部分覆盖信息。空结果不能证明公司没有发生事件。
- **日期与复权明确：** 抓取时间与交易日、新闻发布时间、申报日期分开。`raw`、腾讯 `qfq` 与 Yahoo 复权模式是不同口径。
- **行业范围：** 当前成员不代表历史成员，ETF 代理不等于行业指数或成员名单。
- **财务可见性：** Yahoo 财报缺少可靠公告日期时拒绝 `as-of`。SEC 已有适配器，但 2026-10-11 的在线验证记录为 HTTP 403，需要在实际环境中核实可用性。
- **缓存与耗时：** 使用本地 JSON 缓存并限制数据源等待时间。TTL 和绕过参数按入口分别提供，没有统一的全市场批量超时保证，也不承诺供应商长期可用。

## 文档索引

| 文档 | 内容 |
|---|---|
| [数据 Skill 指南](market-data/SKILL.md) | 查询路由、安装与常用方式 |
| [数据 API 参考](market-data/references/api-reference.md) | 参数、结果位置、RSS、附件和诊断 |
| [数据契约](market-data/references/data-contracts.md) | 覆盖、单位、日期、复权、缓存与限制 |
| [模拟交易指南](paper-trading/SKILL.md) | 服务、账户、订单、存储与回测 |
| [数据健康报告](reports/data-health-2026-10-11.md) | 指定日期的数据源实测与原始输出位置 |
| [数据升级报告](reports/data-upgrade-2026-10-11.md) | 新增数据能力的验证记录与已知失败 |

<details>
<summary>可选扩展：模拟交易与美股策略</summary>

这些配套工具可以使用市场数据，与数据 skill 独立，查询数据时无需安装。

### 可选技能

| 目录 | 用途 | 使用说明 |
|---|---|---|
| `paper-trading` | 港美模拟账户、订单撮合与回测 | [Skill 指南](paper-trading/SKILL.md) |
| `us-strategy-us-momo-swing-fast` | 动量轮动，默认 6 个持仓 | [Skill 指南](us-strategy-us-momo-swing-fast/SKILL.md) |
| `us-strategy-us-momo-swing-slow` | 较慢参数变体，默认 6 个持仓 | [Skill 指南](us-strategy-us-momo-swing-slow/SKILL.md) |
| `us-strategy-us-momo-swing-balance` | 平衡变体，默认 7 个持仓 | [Skill 指南](us-strategy-us-momo-swing-balance/SKILL.md) |
| `us-strategy-us-momo-swing-broad` | Broad 变体，默认 8 个持仓 | [Skill 指南](us-strategy-us-momo-swing-broad/SKILL.md) |
| `us-strategy-us-momo-swing-wide` | Wide 变体，默认 9 个持仓 | [Skill 指南](us-strategy-us-momo-swing-wide/SKILL.md) |

`us-strategy-lab/` 用于参数搜索与验证，不是独立 skill。策略参数与执行口径以对应 skill 的说明为准。

### 模拟交易

从仓库根目录启动本地服务：

```bash
python paper-trading/scripts/paper_trading_service.py --host 127.0.0.1 --port 18766
```

模拟仓使用只做多、整数股数和按市场区分的费用模型。SQLite 数据库与报价缓存独立于 A 股模拟仓。可以通过 `HK_US_PAPER_TRADING_HOME` 指定存储目录；账户与订单命令见模拟交易指南。

</details>

修改公开命令、能力或默认值时，同步更新中英文 README 和对应 skill 说明。
