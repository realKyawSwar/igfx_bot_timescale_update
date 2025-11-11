import pandas as pd
import numpy as np
from loguru import logger
from datetime import datetime, timedelta
from .utils import Candle
try:
    import talib
    HAS_TALIB = True
except Exception:
    HAS_TALIB = False
    import pandas_ta as ta

class MarketData:
    def __init__(self, ig_service=None):
        self.ig = ig_service

    def fetch_historical(self, epic: str, resolution: str = "MINUTE_5", n: int = 500) -> pd.DataFrame:
        """Fetch historical OHLC from IG. If IG unavailable, returns empty df."""
        if self.ig is None:
            logger.warning("IG service not provided; returning empty DataFrame.")
            return pd.DataFrame()
        try:
            resp = self.ig.fetch_historical_prices_by_epic_and_num_points(epic, resolution, n)
            df = resp['prices']
            # Normalize columns
            df = df.rename(columns={
                'snapshotTime': 'time',
                'openPrice': 'openPrice',
                'closePrice': 'closePrice',
                'highPrice': 'highPrice',
                'lowPrice': 'lowPrice',
                'lastTradedVolume': 'lastTradedVolume',
            })
            # flatten dict columns
            for col in ['openPrice','closePrice','highPrice','lowPrice']:
                df[col] = df[col].apply(lambda d: float(d['bid']) if isinstance(d, dict) else float(d))
            df = df.rename(columns={
                'openPrice': 'open',
                'closePrice': 'close',
                'highPrice': 'high',
                'lowPrice': 'low',
                'lastTradedVolume': 'volume'
            })
            df['time'] = pd.to_datetime(df['time'])
            df = df[['time','open','high','low','close','volume']].sort_values('time')
            return df
        except Exception as e:
            logger.error(f"IG history error: {e}")
            return pd.DataFrame()

    def add_indicator(self, df: pd.DataFrame, name: str, **kwargs) -> pd.DataFrame:
        if df.empty:
            return df
        close = df['close'].values.astype(float)
        if name == 'sma':
            length = kwargs.get('length', 50)
            df[f'sma_{length}'] = pd.Series(close).rolling(length).mean().values
        elif name == 'ema':
            length = kwargs.get('length', 200)
            df[f'ema_{length}'] = pd.Series(close).ewm(span=length, adjust=False).mean().values
        elif name == 'rsi':
            length = kwargs.get('length', 14)
            if HAS_TALIB:
                df[f'rsi_{length}'] = talib.RSI(close, timeperiod=length)
            else:
                df[f'rsi_{length}'] = ta.rsi(pd.Series(close), length=length).values
        return df
