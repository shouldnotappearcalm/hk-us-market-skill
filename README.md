# hk-us-market-skill

**English** | [简体中文](README.zh-CN.md)

Agent skills for Hong Kong and US markets: fetch prices and fundamentals with Python, test orders and backtests in an isolated paper-trading account, and generate signals with US momentum rotation strategies. Each skill directory can be installed separately without depending on the A-share skill repository.

## What this repository provides

- Scriptable HK/US market data, with fallback sources where supported.
- Paper trading for testing order workflows, fees, and batch backtests.
- Reproducible US rotation signals with fixed parameters, next-session execution, and structured JSON output.

## Repository structure

```text
hk-us-market-skill/
  market-data/                       # HK/US market data skill
  paper-trading/                     # HK/US paper trading and backtesting skill
  us-strategy-us-momo-swing-fast/     # US momentum rotation; 6 holdings by default
  us-strategy-us-momo-swing-slow/     # Slower parameter variant; 6 holdings
  us-strategy-us-momo-swing-balance/  # Balanced variant; 7 holdings
  us-strategy-us-momo-swing-broad/    # Broad variant; 8 holdings
  us-strategy-us-momo-swing-wide/     # Wide variant; 9 holdings
  us-strategy-lab/                   # Research utilities, not a standalone skill
  README.md                         # English documentation (default)
  README.zh-CN.md                    # Simplified Chinese documentation
```

Each skill contains `SKILL.md`, `scripts/`, and optional `references/`. See each skill's instructions for its supported inputs and data contracts.

## `market-data`: HK/US market data

Fetch market data for analysis, strategies, and backtests without an MCP server. The default sources do not require API credentials; availability depends on the provider.

Supported workflows include:

- Single-symbol and batch quotes; daily, weekly, and monthly price history.
- Technical indicators, valuation and fundamentals, sectors, and ETF perspectives.
- US macroeconomic series, including rates, employment, and growth.
- Stock universes and market-wide quote scans, bounded by `universe-limit` and `top`.
- Company news, filings, RSS feeds, original attachments, and financial statements.
- Source diagnostics and transparent caching.

Fallback metadata includes `source_primary`, `source_actual`, `fallback_used`, and `fallback_chain` where provided. US and HK routes have separate source chains; consult [the data skill](market-data/SKILL.md) for current routing and limitations.

Symbol conventions:

- US: `EXCHANGE:TICKER`, for example `NASDAQ:AAPL`.
- HK: `NNNN.HK`, for example `0700.HK`.

Selected entry points, relative to `market-data/`:

- `scripts/fetch_realtime_hkus.py`
- `scripts/fetch_history_hkus.py`
- `scripts/fetch_technical_hkus.py`
- `scripts/fetch_fundamental_hkus.py`
- `scripts/fetch_sector_hkus.py`
- `scripts/fetch_macro_us.py`
- `scripts/fetch_universe_hkus.py`
- `scripts/fetch_market_realtime_hkus.py`
- `scripts/fetch_news_hkus.py`
- `scripts/healthcheck_sources.py`

See [data contracts](market-data/references/data-contracts.md) for source coverage, dates, cache behavior, and the distinction between actual sector constituents and ETF proxies.

## `paper-trading`: HK/US paper trading

An independent paper-trading environment with separate storage from the A-share simulator. It can run as an HTTP service or through the CLI.

Supported workflows include:

- Service startup and status checks; account creation, resets, default accounts, and cash adjustments.
- Limit and market orders, cancellations, order and fill queries, positions, and account valuation.
- Single-symbol and market-wide batch backtests with a configurable minimum number of successful samples.
- Cache and storage isolation checks.

The simulator supports multiple accounts, long-only positions, and positive integer share quantities. Default price ticks are `0.01` for US stocks and `0.001` for HK stocks. Limit and market orders share a matching engine, with market-specific fee models, equity snapshots, and batch scan/backtest workflows.

Entry points, relative to `paper-trading/`:

- `scripts/paper_trading_service.py`: HTTP service.
- `scripts/paper_trading_ctl.py`: start, status, and stop; optional macOS launchd installation.
- `scripts/paper_trade_cli.py`: accounts, orders, queries, cancellations, and backtests.
- `scripts/full_function_smoke_check.py`: engine, service, CLI, and cache-isolation checks.
- `scripts/batch_backtest_hkus.py`: larger batch backtests.

See [the paper-trading skill](paper-trading/SKILL.md) for details.

## US momentum rotation skills

The `us-strategy-us-momo-swing-*` directories are fixed-parameter variants of a daily US stock rotation framework using an automatic universe, momentum, moving averages, and a fixed holding count. Each is a standalone skill with `daily_decisions.py` and `backtest_validate.py`, producing structured JSON for downstream consumers such as `paper-trading`.

Shared behavior:

- Generate signals from information available after the `t-1` close and execute on day `t`; backtests attribute returns to day `t`.
- Build the candidate universe from the union of automatic rankings.
- Produce next-session candidate buys, with the count controlled by `top_k`.
- Validate 3-month, 6-month, and 1-year returns and maximum drawdowns against configured thresholds.

### Fixed parameter variants

| Directory | Default `top_k` | `ma_fast` | `ma_slow` | `mom_lb` |
|---|---|---|---|---|
| `us-strategy-us-momo-swing-fast` | 6 | 15 | 120 | 80 |
| `us-strategy-us-momo-swing-slow` | 6 | 20 | 100 | 40 |
| `us-strategy-us-momo-swing-balance` | 7 | 20 | 100 | 40 |
| `us-strategy-us-momo-swing-broad` | 8 | 15 | 120 | 80 |
| `us-strategy-us-momo-swing-wide` | 9 | 15 | 120 | 80 |

These variants differ in moving-average periods, momentum lookback, and holding count. Consult each directory's `SKILL.md` for the other fixed settings, including `stop_loss`, `exposure`, and `universe_keep`.

```bash
python3 us-strategy-us-momo-swing-<variant>/scripts/backtest_validate.py --asof YYYY-MM-DD --json
python3 us-strategy-us-momo-swing-<variant>/scripts/daily_decisions.py --asof YYYY-MM-DD --json
```

Replace `<variant>` with `fast`, `slow`, `balance`, `broad`, or `wide`.

## `us-strategy-lab`: research utilities

This development directory contains parameter searches, batch validation, and result files. It is not distributed as a standalone skill.

- `scripts/us_momo_runtime.py`: shared runtime for strategy search and validation.
- `scripts/us_strategy_search.py`: search strategy parameters using universe and historical data; output JSON results.
- `scripts/us_strategy_validate.py`: validate and summarize candidate parameters or results.
- Files such as `result_*.json`, `validate_result.json`, and `search_result_small.json` are runtime outputs that can be retained locally or ignored as appropriate.

## Suggested workflow

1. Fetch quotes, universe data, or macro context with `market-data`, preserving symbol and field conventions.
2. Use a `us-strategy-us-momo-swing-*` variant to generate next-session candidates or validate backtest thresholds.
3. Use the `paper-trading` service or CLI for simulated orders, position tracking, and equity review.

## Install data dependencies

From the repository root:

```bash
python3 -m pip install -r market-data/requirements.txt
```

For paper trading and strategies, consult their respective `SKILL.md` files and script dependencies.

## Quick start

Run these commands from the repository root unless a command explicitly changes directories.

### Market data

```bash
cd market-data
python3 scripts/fetch_realtime_hkus.py --symbol AAPL --json
python3 scripts/fetch_history_hkus.py --symbol 0700.HK --days 180 --interval 1d --json
python3 scripts/fetch_universe_hkus.py --market all --json
python3 scripts/fetch_market_realtime_hkus.py --market all --universe-limit 800 --top 200 --json
cd ..
```

### Paper trading

```bash
cd paper-trading
python3 scripts/paper_trading_service.py --host 127.0.0.1 --port 18766
```

In another terminal, starting from the repository root:

```bash
cd paper-trading
python3 scripts/paper_trade_cli.py create-account alpha --cash 500000
python3 scripts/paper_trade_cli.py buy alpha AAPL 10 --market
python3 scripts/paper_trade_cli.py buy alpha 0700.HK 100 --price 320
python3 scripts/paper_trade_cli.py positions alpha
cd ..
```

### US strategy example

```bash
python3 us-strategy-us-momo-swing-fast/scripts/backtest_validate.py --asof 2026-05-10 --json
python3 us-strategy-us-momo-swing-fast/scripts/daily_decisions.py --asof 2026-05-10 --json
```

## Backtesting and validation

### Paper-trading smoke check

```bash
python3 paper-trading/scripts/full_function_smoke_check.py
```

### Market-wide batch backtest

```bash
python3 paper-trading/scripts/batch_backtest_hkus.py \
  --market all \
  --min-success 500 \
  --start 2025-01-01 \
  --output paper-trading/reports/backtest_500_all.json
```

The batch backtest scans the market universe and stops after reaching `--min-success` successful samples. A larger target increases coverage and runtime.

## Paper-trading storage and cache

Default data directories:

- macOS: `~/Library/Application Support/hk-us-market-paper-trading/`
- Linux: `${XDG_DATA_HOME:-~/.local/share}/hk-us-market-paper-trading/`

Default files:

- SQLite database: `paper_trading.db`.
- Quote cache: `cache/quote_cache.json`.

Set `HK_US_PAPER_TRADING_HOME` to override the storage root.

## Development conventions

- Keep new script JSON fields compatible with existing consumers.
- Maintain fallback routes for external data sources where supported.
- When changing strategy parameters, update the relevant `SKILL.md` and the variant table in both README translations.

## Data and HK/US news updates (2026-10-11)

Install dependencies with `python3 -m pip install -r market-data/requirements.txt` from the repository root. Query company news with:

```bash
python3 market-data/scripts/fetch_news_hkus.py --symbol NYSE:BABA --days 7 --json
python3 market-data/scripts/fetch_news_hkus.py --symbol 09988.HK --keyword 阿里巴巴 --days 7 --json
```

Original records are available in `data[].raw`, preserving Yahoo and Eastmoney fields without business classification, sentiment scoring, or generated summaries. When Yahoo returns no HK news, an explicit Chinese keyword can query Eastmoney; the output retains both source statuses. Quote fallbacks run on demand with bounded waits. Sector ETF proxies are distinguished from actual sector constituents. See the [data health report](reports/data-health-2026-10-11.md) for verification details and raw-output locations.

Additional data capabilities include actual sector constituents, HKEX disclosures, company RSS feeds, original attachments, HK/US financial statements, per-source diagnostics, and transparent caching. See [data contracts](market-data/references/data-contracts.md) and the [data upgrade report](reports/data-upgrade-2026-10-11.md).
