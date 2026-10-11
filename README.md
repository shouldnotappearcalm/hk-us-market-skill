# HK & US Market Data Skills

**English** | [简体中文](README.zh-CN.md)

Python agent skills for Hong Kong and US market data: quotes, price history, company news, filings, financials, industries, and macro.

Query data from an agent or Python CLI with structured JSON output and documented source, date and coverage rules. Start with `market-data/`; no MCP server is required.

[Quick start](#quick-start) · [Data examples](#data-examples) · [Data contracts](market-data/references/data-contracts.md) · [Documentation](#documentation)

## Capabilities

| Area | What you can query or run |
|---|---|
| Prices | Single and batch quotes, intraday and daily/weekly/monthly candles, explicit price-adjustment options, technical indicators |
| News and disclosures | Raw company and keyword news, HKEX/SEC adapters, company RSS/Atom feeds, original documents and attachments |
| Financials | Valuation, institutional holdings, income statements, balance sheets, cash-flow statements, SEC XBRL facts |
| Industries | Industry directories, company classifications and current constituents; separately labeled ETF proxies |
| Macro and discovery | US rates, inflation, employment and GDP; symbol search, stock universes and bounded market scans |
| Source diagnostics | Fallback metadata, source errors, history-source probes and local JSON cache information |

Source availability and coverage differ by entry point. See [data contracts](market-data/references/data-contracts.md) for dates, adjustment semantics, partial results and current limits.

## Quick start

Python 3.12 is recommended. From a POSIX shell:

```bash
git clone https://github.com/shouldnotappearcalm/hk-us-market-skill.git
cd hk-us-market-skill
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r market-data/requirements.txt

python market-data/scripts/fetch_realtime_hkus.py --symbol AAPL --json
```

The following examples run from the repository root with that environment active.

### Use with an agent

Copy a complete skill directory, such as `market-data/`, into your agent's configured skills directory. Keep its `SKILL.md`, `scripts/`, `references/` and dependency files together; each skill's instructions describe its setup. Individual skills can be installed separately without the A-share repository.

Start with [market-data/SKILL.md](market-data/SKILL.md) for data queries. Optional simulator and strategy folders are described at the end of this page.

## Data examples

### Quotes, search and history

```bash
python market-data/scripts/search_symbols_hkus.py Alibaba --json
python market-data/scripts/fetch_realtime_hkus.py --batch AAPL,BRK.B,09988.HK --json
python market-data/scripts/fetch_history_hkus.py --symbol 09988.HK --adjust qfq --count 10 --no-cache --json
```

US symbols support forms such as `AAPL`, `NYSE:BABA` and `BRK.B`. HK codes such as `09988.HK` and `9988.HK` identify the same security. An exchange prefix is a request hint, not verified listing evidence.

### Company news and official disclosures

```bash
python market-data/scripts/fetch_news_hkus.py --symbol NYSE:BABA --days 7 --json
python market-data/scripts/fetch_news_hkus.py --symbol 09988.HK --keyword 阿里巴巴 --days 7 --json
python market-data/scripts/fetch_disclosures_hkus.py --symbol 09988.HK --days 30 --json
```

News records preserve provider fields in `data[].raw`, without semantic filtering, deduplication, sentiment scoring or generated summaries. Supply `--keyword` explicitly for Eastmoney keyword search. Media news and official disclosures use separate entry points; a search snippet is not a full article. RSS feeds and document downloads are documented in the [API reference](market-data/references/api-reference.md).

### Financials, industries and macro

```bash
python market-data/scripts/fetch_statements_hkus.py --symbol AAPL --kind cashflow --period quarterly --json
python market-data/scripts/fetch_industry_hkus.py --action members --industry semiconductors --market HK --pages 4 --json
python market-data/scripts/fetch_macro_us.py --interest-rates --days 30 --json
```

### Inspect a history source

```bash
python market-data/scripts/inspect_sources_hkus.py --symbol 09988.HK --source tencent_history --adjust qfq --json
```

Check source status, coverage, data dates and errors rather than treating any successful request as complete or current data. Output schemas and cache switches vary by script; use its `--help` and the API reference.

## Data behavior and current limits

- **Raw data and source visibility:** preserve provider records, source errors and partial coverage. An empty response does not prove there were no company events.
- **Explicit dates and adjustments:** fetch time is separate from trade, publication and filing dates. `raw`, Tencent `qfq` and Yahoo adjustment modes are distinct contracts.
- **Industry scope:** current constituents do not establish historical membership. An ETF proxy is not an industry index or a constituent list.
- **Financial visibility:** Yahoo statements without reliable filing dates reject `as-of` requests. SEC adapters exist, but the recorded 2026-10-11 online verification returned HTTP 403; availability must be checked in the target environment.
- **Cache and runtime:** local JSON caches and bounded source waits are implemented. TTLs and bypass flags vary by route; there is no universal batch deadline or guarantee of long-term provider availability.

## Documentation

| Document | Contents |
|---|---|
| [Data skill guide](market-data/SKILL.md) | Query routing, setup and everyday usage |
| [Data API reference](market-data/references/api-reference.md) | Parameters, output locations, RSS, attachments and diagnostics |
| [Data contracts](market-data/references/data-contracts.md) | Source coverage, units, dates, adjustments, caching and limitations |
| [Paper-trading guide](paper-trading/SKILL.md) | Service, accounts, orders, storage and backtests |
| [Data health report](reports/data-health-2026-10-11.md) | Dated provider checks and raw-output locations |
| [Data upgrade report](reports/data-upgrade-2026-10-11.md) | Verification of added data capabilities and known failures |

<details>
<summary>Optional: paper trading and US strategy skills</summary>

These companion tools can consume market data. They are separate from the data skill and are not required for data queries.

### Optional skills

| Directory | Purpose | Instructions |
|---|---|---|
| `paper-trading` | HK/US paper accounts, order matching and backtests | [Skill guide](paper-trading/SKILL.md) |
| `us-strategy-us-momo-swing-fast` | Momentum rotation; 6 holdings by default | [Skill guide](us-strategy-us-momo-swing-fast/SKILL.md) |
| `us-strategy-us-momo-swing-slow` | Slower parameter variant; 6 holdings | [Skill guide](us-strategy-us-momo-swing-slow/SKILL.md) |
| `us-strategy-us-momo-swing-balance` | Balanced variant; 7 holdings | [Skill guide](us-strategy-us-momo-swing-balance/SKILL.md) |
| `us-strategy-us-momo-swing-broad` | Broad variant; 8 holdings | [Skill guide](us-strategy-us-momo-swing-broad/SKILL.md) |
| `us-strategy-us-momo-swing-wide` | Wide variant; 9 holdings | [Skill guide](us-strategy-us-momo-swing-wide/SKILL.md) |

`us-strategy-lab/` contains parameter-search and validation utilities; it is not a standalone skill. Strategy parameters and execution conventions live in the corresponding skill guides.

### Paper trading

Start the local service from the repository root:

```bash
python paper-trading/scripts/paper_trading_service.py --host 127.0.0.1 --port 18766
```

The simulator uses long-only positions, integer share quantities and market-specific fees. It stores its SQLite database and quote cache separately from the A-share simulator. Set `HK_US_PAPER_TRADING_HOME` to override its storage directory; account and order commands are in the paper-trading guide.

</details>

When changing public commands, capabilities or defaults, update both README translations and the relevant skill guide.
