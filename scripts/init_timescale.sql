-- Enable TimescaleDB and create hypertable + trades table
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS candles (
    symbol TEXT NOT NULL,
    time   TIMESTAMPTZ NOT NULL,
    open   DOUBLE PRECISION NOT NULL,
    high   DOUBLE PRECISION NOT NULL,
    low    DOUBLE PRECISION NOT NULL,
    close  DOUBLE PRECISION NOT NULL,
    volume DOUBLE PRECISION NOT NULL,
    PRIMARY KEY(symbol, time)
);
SELECT create_hypertable('candles','time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_candles_symbol_time ON candles(symbol, time DESC);

CREATE TABLE IF NOT EXISTS trades (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    epic TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    size DOUBLE PRECISION NOT NULL,
    entry DOUBLE PRECISION,
    sl DOUBLE PRECISION,
    tp DOUBLE PRECISION,
    deal_ref TEXT,
    raw JSONB
);
