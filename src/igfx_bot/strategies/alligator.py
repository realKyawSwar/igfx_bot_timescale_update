import pandas as pd
from ..strategy_base import Strategy, Signal

def smoothed_ma(series: pd.Series, length: int, smooth: int) -> pd.Series:
    ema = series.ewm(span=length, adjust=False).mean()
    for _ in range(max(0, smooth-1)):
        ema = ema.ewm(span=length, adjust=False).mean()
    return ema

class Alligator(Strategy):
    """Standalone Alligator strategy.
    Entry when lips/teeth/jaw align (trend) and close breaks last N-bar high/low (momentum confirmation).
    """
    def __init__(self, jaw=13, teeth=8, lips=5, smooth=5, breakout_lookback=10):
        self.jaw = jaw; self.teeth = teeth; self.lips = lips; self.smooth = smooth
        self.lookback = breakout_lookback

    def generate(self, df: pd.DataFrame) -> Signal:
        if len(df) < max(self.jaw, self.teeth, self.lips) + self.lookback + 2:
            return Signal('FLAT')
        d = df.copy()
        d['jaw'] = smoothed_ma(d['close'], self.jaw, self.smooth)
        d['teeth'] = smoothed_ma(d['close'], self.teeth, self.smooth)
        d['lips'] = smoothed_ma(d['close'], self.lips, self.smooth)

        up = d['lips'].iloc[-1] > d['teeth'].iloc[-1] > d['jaw'].iloc[-1]
        down = d['lips'].iloc[-1] < d['teeth'].iloc[-1] < d['jaw'].iloc[-1]

        hi = d['high'].rolling(self.lookback).max().iloc[-2]  # prior bar
        lo = d['low'].rolling(self.lookback).min().iloc[-2]
        c = d['close'].iloc[-1]

        if up and c > hi:
            return Signal('BUY')
        if down and c < lo:
            return Signal('SELL')
        return Signal('FLAT')
