# IGFX-Bot — Automated Forex Trading System for IG Markets

**Python 3.10+ | Open‑source only | Modular | Backtesting + Risk Mgmt + Streamlit Dashboard**

This project provides a production‑ready, modular trading bot that connects to **IG Markets** (demo or live) using the open‑source
[`trading-ig`](https://github.com/ig-python/trading-ig) library. It includes data fetching (REST/Lightstreamer), a strategy layer
(SMA/EMA crossover, RSI, and an advanced **Alligator + Elliott Wave + Fibonacci** combo), risk management, execution, backtesting
with **backtrader**, scheduling, logging, and a **Streamlit** monitoring dashboard.

> ⚠️ **You need an IG account and API key.** Setup cannot be automated. Create an API key here: https://labs.ig.com/

---

## Features

- IG REST + Streaming (Lightstreamer) via `trading-ig`
- Configurable instruments (EUR/USD, GBP/USD, USD/JPY by default)
- Strategies:
  - `sma_ema_crossover`: SMA(50) vs EMA(200)
  - `rsi_reversal`: RSI(14) overbought/oversold
  - `alligator_ew_fib`: Trend‑pullback entries using **Alligator MAs**, swing detection (ZigZag) for **Elliott‑like waves**, and **Fibonacci** confluence
- Risk management: percent‑risk sizing, SL/TP, daily loss/trade caps, equity curve & drawdown tracking
- Execution: market/limit orders, error handling, retries, graceful shutdown
- Backtesting: `backtrader` with metrics (Sharpe, win rate, max drawdown)
- Streamlit dashboard: positions, PnL, equity curve, logs
- Tests with `pytest`
- Scheduler with `APScheduler`

---

## Quick Start

1. **Install dependencies** (consider a virtualenv):
   ```bash
   pip install -r requirements.txt
   ```

   > **TA‑Lib**: This project *prefers* TA‑Lib. If installation fails, the code falls back to `pandas_ta` automatically.
   > Windows users may use prebuilt wheels (see: https://www.lfd.uci.edu/~gohlke/pythonlibs/#ta-lib) or conda (`conda install -c conda-forge ta-lib`).

2. **Set environment variables** (or create a `.env`):
   ```bash
   IG_API_KEY=your_api_key
   IG_USERNAME=your_ig_username
   IG_PASSWORD=your_ig_password
   IG_ACCOUNT_TYPE=DEMO   # or LIVE
   IG_ACCOUNT_ID=ABC1234  # optional; will auto-select default if omitted
   ```

3. **Configure instruments and params** in `config/config.yaml`. Example provided for EURUSD/GBPUSD/USDJPY.

4. **Run a backtest** (uses `yfinance` data as a fallback when IG history is unavailable):
   ```bash
   python -m src.igfx_bot.backtest --config config/config.yaml --strategy sma_ema_crossover --symbol EURUSD --timeframe 5min --from 2024-01-01 --to 2024-06-30
   ```

5. **Start the live bot (demo)**:
   ```bash
   python -m src.igfx_bot.runner --config config/config.yaml --mode demo
   ```

6. **Dashboard**:
   ```bash
   streamlit run dashboard/app.py
   ```

---

## Project Structure

```text
igfx_bot/
├── config/
│   └── config.yaml
├── dashboard/
│   └── app.py
├── samples/
│   ├── sample_backtest_report.json
│   └── live_trade_simulation.log
├── src/igfx_bot/
│   ├── __init__.py
│   ├── utils.py
│   ├── auth.py
│   ├── data.py
│   ├── risk.py
│   ├── execution.py
│   ├── strategy_base.py
│   ├── strategies/
│   │   ├── __init__.py
│   │   ├── sma_ema_crossover.py
│   │   ├── rsi_reversal.py
│   │   └── alligator_ew_fib.py
│   ├── backtest.py
│   └── runner.py
├── tests/
│   ├── test_position_sizing.py
│   └── test_strategy_signals.py
└── requirements.txt
```

---

## Assumptions & Extensions to Upstream Repos

- **`trading-ig`** is the canonical IG API wrapper; we wrap it for auth, REST calls, and streaming subscriptions.
- We *reference* ideas from community repos (e.g., `g-make-it/IG_Trading_Algo_Scripts_Python`) but re‑implement a unified, modular architecture that isolates:
  data fetch, strategy, risk, and execution for maintainability.
- For **Alligator/Elliott/Fibonacci**: we implement a pragmatic version suitable for automation:
  Alligator = three smoothed MAs; Elliott‑like waves using a ZigZag swing detector; Fibonacci retracement confluence with trend filter.
- Backtesting uses **backtrader** with a thin adapter for our strategy interface.
- We respect IG rate limits (target << 30 req/sec), batch pulls, and cache metadata.

---

## Notes / Compliance

- This bot is **not** HFT. Default schedule evaluates once per bar (e.g., every 1–5 minutes).
- IG weekend/holiday handling: the scheduler skips closed markets via `trading-ig` market status and calendar checks.
- Leverage/size: default aligns with ESMA retail (e.g., 1:30 FX majors). Adjust in config; risk module enforces max loss caps.

---

## Support

- IG API Docs: https://labs.ig.com/
- IG Python Wrapper: https://github.com/ig-python/trading-ig
- Optional helper: https://github.com/lewisbarber/ig-markets-rest-api-python-library



---

## Postgres/TimescaleDB Sink

This project can persist **OHLCV candles** and **trades** to TimescaleDB.

**Dependencies**: `psycopg2-binary`

**Enable & Configure** in `config/config.yaml`:
```yaml
database:
  enabled: true
  dsn_env: PG_DSN      # optional DSN, takes precedence if set
  host_env: PGHOST
  port_env: PGPORT
  user_env: PGUSER
  password_env: PGPASSWORD
  dbname_env: PGDATABASE
```

**Environment** examples:
```bash
export PGHOST=localhost
export PGPORT=5432
export PGUSER=postgres
export PGPASSWORD=postgres
export PGDATABASE=igfx
# or provide a single DSN
# export PG_DSN='postgresql://postgres:postgres@localhost:5432/igfx'
```

**Initialize schema** (optional; runner will also attempt this):
```bash
psql "$PG_DSN" -f scripts/init_timescale.sql
```

Tables:
- `candles(symbol, time, open, high, low, close, volume)` — hypertable
- `trades(id, ts, epic, symbol, side, size, entry, sl, tp, deal_ref, raw)`

The runner writes candles every cycle and appends a row on each submitted order.
