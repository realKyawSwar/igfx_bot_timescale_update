import os
from typing import Optional, Iterable
from loguru import logger
from dataclasses import dataclass
import psycopg2
import psycopg2.extras
import pandas as pd

@dataclass
class PgConfig:
    dsn: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = 5432
    user: Optional[str] = None
    password: Optional[str] = None
    dbname: Optional[str] = None

class PgSink:
    def __init__(self, cfg: PgConfig):
        self.cfg = cfg
        self.conn = None

    def connect(self):
        if self.conn:
            return self.conn
        if self.cfg.dsn:
            self.conn = psycopg2.connect(self.cfg.dsn)
        else:
            self.conn = psycopg2.connect(
                host=self.cfg.host,
                port=self.cfg.port,
                user=self.cfg.user,
                password=self.cfg.password,
                dbname=self.cfg.dbname,
            )
        self.conn.autocommit = True
        return self.conn

    def init_schema(self):
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute("""                CREATE EXTENSION IF NOT EXISTS timescaledb;
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
            """)
            logger.info("TimescaleDB schema ensured (candles, trades)." )

    def write_candles(self, symbol: str, df: pd.DataFrame):
        if df is None or df.empty:
            return 0
        conn = self.connect()
        rows = list(zip([symbol]*len(df), df['time'], df['open'], df['high'], df['low'], df['close'], df['volume']))
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """INSERT INTO candles(symbol,time,open,high,low,close,volume)
                    VALUES %s
                    ON CONFLICT (symbol, time) DO UPDATE
                    SET open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                        close=EXCLUDED.close, volume=EXCLUDED.volume
                """,
                rows,
                page_size=1000
            )
        return len(rows)

    def log_trade(self, *, epic:str, symbol:str, side:str, size:float, entry:float=None, sl:float=None, tp:float=None, deal_ref:str=None, raw:dict=None):
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO trades(epic, symbol, side, size, entry, sl, tp, deal_ref, raw)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (epic, symbol, side, size, entry, sl, tp, deal_ref, psycopg2.extras.Json(raw) if raw else None)
            )
            rid = cur.fetchone()[0]
        return rid
