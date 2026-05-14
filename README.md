# hk-us-market-skill

面向港股与美股的 Agent 技能集合：用纯 Python 拉取行情与基本面、在独立模拟仓里完成港美下单与回测，并配套一组美股动量轮动策略脚本。各目录可单独拷贝到全局 skills 目录使用，互不依赖 A 股技能树。

## 本仓库解决什么问题

- 需要稳定、可脚本化的港美数据，且主数据源失败时能自动切换备用源
- 需要在不动实盘资金的前提下，验证港美交易流程、费用模型与批量回测
- 需要可复现的美股轮动信号：固定参数、T+1 执行口径、结构化 JSON 便于对接模拟仓

## 目录结构

```bash
hk-us-market-skill/
  market-data/                         # 港美市场数据 Skill
  paper-trading/                       # 港美模拟仓与回测 Skill
  us-strategy-us-momo-swing-fast/      # 美股动量轮动（默认持仓 6）
  us-strategy-us-momo-swing-slow/      # 美股动量轮动（默认持仓 6，参数更慢）
  us-strategy-us-momo-swing-balance/   # 美股动量轮动（默认持仓 7）
  us-strategy-us-momo-swing-broad/     # 美股动量轮动（默认持仓 8）
  us-strategy-us-momo-swing-wide/      # 美股动量轮动（默认持仓 9）
  us-strategy-lab/                     # 策略搜索与校验脚本（非独立 Skill）
  README.md
```

约定：每个 Skill 目录内为 `SKILL.md` + `scripts/`（及按需的 `references/`），与上游 Agent Skills 习惯一致。

---

## `market-data`（港美数据 Skill）

**定位**：为策略与回测提供统一字段的港美股数据拉取能力，不依赖 MCP，默认免密可跑。

**适合场景**

- 单票或批量实时报价、日/周/月历史 K 线
- 技术指标、估值与基本面、行业与 ETF 视角
- 美国宏观序列（利率、就业、增长等）
- 全市场股票清单与市场级实时扫描（配合 `universe-limit` 与 `top` 控制规模）

**能力要点**

- 单票与批量实时行情
- 历史 K 线（含批量与多 worker）
- 技术指标计算脚本
- 基本面与行业相关脚本
- 美国宏观数据脚本
- 全市场 universe 与市场级实时扫描
- 渠道健康检查脚本

**可靠性**

- 多渠道 fallback，结果中带 `source_primary`、`source_actual`、`fallback_used`、`fallback_chain`
- US 与 HK 各自定义主备链路（详见该目录 `SKILL.md`）

**符号规范**

- US：`EXCHANGE:TICKER`，例如 `NASDAQ:AAPL`
- HK：`NNNN.HK`，例如 `0700.HK`

**入口脚本（节选）**

- `scripts/fetch_realtime_hkus.py`
- `scripts/fetch_history_hkus.py`
- `scripts/fetch_technical_hkus.py`
- `scripts/fetch_fundamental_hkus.py`
- `scripts/fetch_sector_hkus.py`
- `scripts/fetch_macro_us.py`
- `scripts/fetch_universe_hkus.py`
- `scripts/fetch_market_realtime_hkus.py`
- `scripts/healthcheck_sources.py`

---

## `paper-trading`（港美模拟仓 Skill）

**定位**：独立的港股与美股模拟交易环境，与 A 股模拟仓数据目录隔离，可常驻 HTTP 服务或通过 CLI 驱动。

**适合场景**

- 启动或检查模拟盘服务，多账户管理（创建、重置、默认账户、加减资金）
- 限价单与市价单、撤单、查询订单与成交、持仓与账户估值
- 单票策略回测与全市场批量回测（可设最小成功样本数）
- 验证缓存路径与 A 股模拟仓互不干扰

**能力要点**

- 多账户、long-only、正整数股数
- US 默认最小价位 `0.01`，HK 默认 `0.001`
- 限价与市价统一撮合引擎，费用模型按市场区分
- 净值快照与批量港美扫描回测流程

**常驻服务**

- `scripts/paper_trading_service.py` 提供 HTTP 接口
- `scripts/paper_trading_ctl.py` 支持 start、status、stop，macOS 可选 launchd 安装

**CLI 入口**

- `scripts/paper_trade_cli.py`（开户、买卖、查询、撤单、回测等）

**验证**

- `scripts/full_function_smoke_check.py` 覆盖引擎、服务与 CLI 联动及缓存隔离
- `scripts/batch_backtest_hkus.py` 用于大样本扫描回测

---

## 美股动量轮动策略 Skill（`us-strategy-us-momo-swing-*`）

**共同定位**：同一套「自动 universe + 动量与均线规则 + 固定持仓数」的美股日线轮动框架的多个参数变体。每个变体是独立目录，自带 `daily_decisions.py` 与 `backtest_validate.py`，输出结构化 JSON，便于下游（如 `paper-trading`）消费。

**共同能力**

- 按 `t-1` 日收盘后可见数据生成信号，`t` 日执行（回测按 `t` 计入收益），严格避免未来函数
- 候选池来自多路自动榜单并集，不按主观板块手工挑票
- 产出次日候选买入列表（只数由 `top_k` 决定）
- `backtest_validate.py`：汇总 3m、6m、1y 区间的收益与最大回撤，并与内置门槛对照

**变体对照（固定参数；其余字段各目录 `SKILL.md` 一致）**

| 目录 | 默认持仓数 `top_k` | `ma_fast` | `ma_slow` | `mom_lb` |
|------|-------------------|-----------|------------|----------|
| `us-strategy-us-momo-swing-fast` | 6 | 15 | 120 | 80 |
| `us-strategy-us-momo-swing-slow` | 6 | 20 | 100 | 40 |
| `us-strategy-us-momo-swing-balance` | 7 | 20 | 100 | 40 |
| `us-strategy-us-momo-swing-broad` | 8 | 15 | 120 | 80 |
| `us-strategy-us-momo-swing-wide` | 9 | 15 | 120 | 80 |

各变体在 `ma_fast`、`ma_slow`、`mom_lb` 与 `top_k` 上不同，用于在「反应速度」与「换手宽度」之间做离线对照；`stop_loss`、`exposure`、`universe_keep` 等其余固定项以各目录 `SKILL.md` 为准。

**每个策略目录内推荐命令**

```bash
python3 us-strategy-us-momo-swing-<variant>/scripts/backtest_validate.py --asof YYYY-MM-DD --json
python3 us-strategy-us-momo-swing-<variant>/scripts/daily_decisions.py --asof YYYY-MM-DD --json
```

将 `<variant>` 替换为 `fast`、`slow`、`balance`、`broad` 或 `wide`。

---

## `us-strategy-lab`（辅助脚本，非发布用 Skill）

**定位**：与正式 Skill 并列的开发与实验目录，用于参数搜索、批量校验与结果落盘，不参与 Agent 侧「按目录名即 Skill」的约定。

**内容说明**

- `scripts/us_momo_runtime.py`：与策略侧共享的运行时逻辑入口（供搜索与校验复用）
- `scripts/us_strategy_search.py`：在 universe 与历史数据上做策略空间搜索，产出 JSON 结果
- `scripts/us_strategy_validate.py`：对候选参数或结果做校验与汇总
- 目录下的 `result_*.json`、`validate_result.json`、`search_result_small.json` 等为运行产物示例，可按需 gitignore 或本地保留

---

## 推荐组合方式

1. 用 `market-data` 拉行情、universe 或宏观上下文，保证符号与字段一致  
2. 用任一 `us-strategy-us-momo-swing-*` 生成次日候选或回测门槛结果  
3. 用 `paper-trading` 服务或 CLI 执行模拟下单、持仓跟踪与净值复盘  

---

## 依赖安装（数据 Skill）

在 `market-data` 目录下：

```bash
pip3 install yfinance pandas numpy requests pandas_datareader yahooquery pytest
```

`paper-trading` 与策略脚本以各自 `SKILL.md` 与脚本头部 import 为准；若缺依赖按报错补装即可。

---

## 快速开始

以下命令默认在**本仓库根目录**（即 `hk-us-market-skill/`）执行。

### 数据

```bash
cd market-data
python3 scripts/fetch_realtime_hkus.py --symbol AAPL --json
python3 scripts/fetch_history_hkus.py --symbol 0700.HK --days 180 --interval 1d --json
python3 scripts/fetch_universe_hkus.py --market all --json
python3 scripts/fetch_market_realtime_hkus.py --market all --universe-limit 800 --top 200 --json
cd ..
```

### 模拟仓

```bash
cd paper-trading
python3 scripts/paper_trading_service.py --host 127.0.0.1 --port 18766
```

另开终端：

```bash
cd paper-trading
python3 scripts/paper_trade_cli.py create-account alpha --cash 500000
python3 scripts/paper_trade_cli.py buy alpha AAPL 10 --market
python3 scripts/paper_trade_cli.py buy alpha 0700.HK 100 --price 320
python3 scripts/paper_trade_cli.py positions alpha
cd ..
```

### 美股策略（示例）

```bash
python3 us-strategy-us-momo-swing-fast/scripts/backtest_validate.py --asof 2026-05-10 --json
python3 us-strategy-us-momo-swing-fast/scripts/daily_decisions.py --asof 2026-05-10 --json
```

---

## 回测与验证

### 模拟仓烟测

```bash
python3 paper-trading/scripts/full_function_smoke_check.py
```

### 全市场批量回测

```bash
python3 paper-trading/scripts/batch_backtest_hkus.py \
  --market all \
  --min-success 500 \
  --start 2025-01-01 \
  --output paper-trading/reports/backtest_500_all.json
```

批量回测会先扫描全市场池，在达到 `--min-success` 指定样本数后停止；提高阈值可扩大样本规模，耗时相应增加。

---

## 运行目录与缓存（`paper-trading`）

默认数据目录：

- macOS：`~/Library/Application Support/hk-us-market-paper-trading/`
- Linux：`${XDG_DATA_HOME:-~/.local/share}/hk-us-market-paper-trading/`

默认文件：

- SQLite：`paper_trading.db`
- 行情缓存：`cache/quote_cache.json`

通过环境变量 `HK_US_PAPER_TRADING_HOME` 可覆盖根目录。

---

## 开发约定

- 新增脚本优先保持 JSON 字段与现有输出一致，避免下游解析分叉  
- 对外部数据源保持可回退链路，降低单点失效  
- 策略侧修改参数时同步更新对应目录的 `SKILL.md` 与本 README 中的对照表  
