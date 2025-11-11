import pandas as pd
from ..strategy_base import Strategy, Signal
try:
    import talib
    HAS_TALIB = True
except Exception:
    HAS_TALIB = False
    import pandas_ta as ta

class RSIReversal(Strategy):
    def __init__(self, length=14, ob=70, os=30):
        self.length = length
        self.ob = ob
        self.os = os

    def generate(self, df: pd.DataFrame) -> Signal:
        if len(df) < self.length + 2:
            return Signal('FLAT')
        close = df['close'].values
        if HAS_TALIB:
            rsi = talib.RSI(close, timeperiod=self.length)
        else:
            rsi = ta.rsi(df['close'], length=self.length).values
        val = rsi[-1]
        if val < self.os:
            return Signal('BUY')
        if val > self.ob:
            return Signal('SELL')
        return Signal('FLAT')
