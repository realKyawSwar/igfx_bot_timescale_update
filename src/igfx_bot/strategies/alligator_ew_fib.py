import numpy as np
import pandas as pd
from ..strategy_base import Strategy, Signal

def smoothed_ma(series: pd.Series, length: int, smooth: int) -> pd.Series:
    # Simple smoothed MA by repeated EMA
    ema = series.ewm(span=length, adjust=False).mean()
    for _ in range(max(0, smooth-1)):
        ema = ema.ewm(span=length, adjust=False).mean()
    return ema

def zigzag_pivots(prices: pd.Series, pct=2.0):
    pivots = [np.nan]*len(prices)
    if len(prices) < 3: return pd.Series(pivots, index=prices.index)
    last_pivot_idx = 0
    last_pivot_price = prices.iloc[0]
    last_dir = 0
    for i in range(1, len(prices)):
        change = (prices.iloc[i] - last_pivot_price) / last_pivot_price * 100.0
        if last_dir >= 0 and change >= pct:
            pivots[i] = prices.iloc[i]
            last_pivot_idx = i
            last_pivot_price = prices.iloc[i]
            last_dir = -1
        elif last_dir <= 0 and change <= -pct:
            pivots[i] = prices.iloc[i]
            last_pivot_idx = i
            last_pivot_price = prices.iloc[i]
            last_dir = 1
    return pd.Series(pivots, index=prices.index)

class AlligatorEWFib(Strategy):
    def __init__(self, jaw=13, teeth=8, lips=5, smooth=5, zigzag_pct=2.0, fib_levels=(0.382,0.5,0.618), fib_tol=0.0015):
        self.jaw = jaw; self.teeth = teeth; self.lips = lips; self.smooth = smooth
        self.zigzag_pct = zigzag_pct
        self.fib_levels = fib_levels
        self.fib_tol = fib_tol

    def generate(self, df: pd.DataFrame) -> Signal:
        if len(df) < max(self.jaw, self.teeth, self.lips) + 30:
            return Signal('FLAT')
        d = df.copy()
        d['jaw'] = smoothed_ma(d['close'], self.jaw, self.smooth)
        d['teeth'] = smoothed_ma(d['close'], self.teeth, self.smooth)
        d['lips'] = smoothed_ma(d['close'], self.lips, self.smooth)

        # Trend filter: lips > teeth > jaw uptrend; opposite for downtrend
        up = d['lips'].iloc[-1] > d['teeth'].iloc[-1] > d['jaw'].iloc[-1]
        down = d['lips'].iloc[-1] < d['teeth'].iloc[-1] < d['jaw'].iloc[-1]

        piv = zigzag_pivots(d['close'], pct=self.zigzag_pct).dropna()
        if len(piv) < 2:
            return Signal('FLAT')
        last = piv.index[-1]
        prev = piv.index[-2]
        swing_high = max(d['close'].iloc[prev:last+1])
        swing_low = min(d['close'].iloc[prev:last+1])
        # Build fib retracement levels for most recent swing
        if up and swing_high > swing_low:
            diff = swing_high - swing_low
            retr_levels = [swing_high - lvl*diff for lvl in self.fib_levels]
            price = d['close'].iloc[-1]
            if any(abs(price - rl)/price <= self.fib_tol for rl in retr_levels):
                return Signal('BUY')
        if down and swing_high > swing_low:
            diff = swing_high - swing_low
            retr_levels = [swing_low + lvl*diff for lvl in self.fib_levels]
            price = d['close'].iloc[-1]
            if any(abs(price - rl)/price <= self.fib_tol for rl in retr_levels):
                return Signal('SELL')
        return Signal('FLAT')
