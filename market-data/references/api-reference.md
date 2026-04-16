# HK+US API Reference

## `fetch_realtime_hkus.py`

### 参数

- `--symbol <SYMBOL>`: 单标的
- `--batch <S1,S2,...>`: 批量标的
- `--workers <N>`: 批量并发数
- `--json`: JSON 输出

### 返回关键字段

- `symbol`
- `market`
- `source_primary`
- `source_actual`
- `fallback_used`
- `fallback_chain`
- `data.price/open/high/low/previous_close/change/change_pct/volume`

---

## `fetch_history_hkus.py`

### 参数

- `--symbol <SYMBOL>`
- `--batch <S1,S2,...>`
- `--interval <1d|1wk|1mo>`
- `--days <N>`
- `--start <YYYY-MM-DD>`
- `--end <YYYY-MM-DD>`
- `--count <N>`
- `--workers <N>`
- `--json`

### 返回关键字段

- 单标的同实时结构，`data` 为 OHLCV 序列
- 批量返回 `meta.requested/success/fail/success_rate` 和逐标的结果

---

## `fetch_technical_hkus.py`

### 参数

- `symbol` 位置参数
- `--days <N>`
- `--interval <1d|1wk|1mo>`
- `--json`

### 指标

- `ma_5/ma_20/ma_60`
- `macd_dif/macd_dea/macd_hist`
- `rsi_14`
- `boll_up/boll_mid/boll_low`
- `kdj_k/kdj_d/kdj_j`

### 返回关键字段

- `data.series`
- `data.latest`
- `data.signals`

---

## `fetch_fundamental_hkus.py`

### 参数

- `--symbol <SYMBOL>`
- `--json`

### 返回关键字段

- `pe_ttm/pe_forward/ps/pb/ev_ebitda/peg`
- `market_cap/beta/dividend_yield`
- `sector/industry`
- `institutional_holders`

---

## `fetch_sector_hkus.py`

### 参数

- `--sector-name <NAME>`: 使用行业名称映射 ETF 并输出区间分析
- `--symbol <SYMBOL>`: 查询标的行业归属
- `--days <N>`
- `--json`

---

## `fetch_macro_us.py`

### 参数

- `--interest-rates --days <N>`
- `--inflation-employment --months <N>`
- `--economic-growth --quarters <N>`
- `--json`

### 数据序列

- 利率：`DGS2/DGS10/FEDFUNDS`
- 通胀就业：`CPIAUCSL/UNRATE`
- 增长：`GDPC1`

---

## `healthcheck_sources.py`

### 参数

- `--us-symbol <TICKER>`
- `--hk-symbol <CODE.HK>`

### 输出

- `matrix.history`
- `matrix.realtime`
- `matrix.fundamental`
- `matrix.macro`

---

## `fetch_universe_hkus.py`

### 参数

- `--market <all|us|hk>`
- `--limit <N>`
- `--json`

### 输出

- `meta.total/returned/sources`
- `data[].symbol/name/market/exchange/source`

---

## `fetch_market_realtime_hkus.py`

### 参数

- `--market <all|us|hk>`
- `--symbols <S1,S2,...>`（可选，给了就按列表拉）
- `--universe-limit <N>`
- `--workers <N>`
- `--top <N>`
- `--sort <change_pct_desc|change_pct_asc|volume_desc|price_desc>`
- `--json`

### 输出

- `meta.requested/success/fail/success_rate/source_counts`
- `data[].symbol/price/change_pct/volume/source_actual`
- `failed[]`
