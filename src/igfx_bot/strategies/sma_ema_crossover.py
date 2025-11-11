import pandas as pd
from ..strategy_base import Strategy, Signal

class SMAEMACrossover(Strategy):
    def __init__(self, fast=50, slow=200):
        self.fast = fast
        self.slow = slow

    def generate(self, df: pd.DataFrame) -> Signal:
        if len(df) < max(self.fast, self.slow) + 2:
            return Signal('FLAT')
        df = df.copy()
        df['sma'] = df['close'].rolling(self.fast).mean()
        df['ema'] = df['close'].ewm(span=self.slow, adjust=False).mean()
        c1, p1 = df.iloc[-1], df.iloc[-2]
        # Crossovers
        buy = p1['sma'] < p1['ema'] and c1['sma'] > c1['ema']
        sell = p1['sma'] > p1['ema'] and c1['sma'] < c1['ema']
        if buy:
            return Signal('BUY')
        if sell:
            return Signal('SELL')
        return Signal('FLAT')
