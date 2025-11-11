import numpy as np
import pandas as pd
from ..strategy_base import Strategy, Signal

def zigzag_pivots(prices: pd.Series, pct=2.0):
    pivots = [np.nan]*len(prices)
    if len(prices) < 3: return pd.Series(pivots, index=prices.index)
    last_pivot_price = prices.iloc[0]
    last_dir = 0
    for i in range(1, len(prices)):
        change = (prices.iloc[i] - last_pivot_price) / last_pivot_price * 100.0
        if last_dir >= 0 and change >= pct:
            pivots[i] = prices.iloc[i]; last_pivot_price = prices.iloc[i]; last_dir = -1
        elif last_dir <= 0 and change <= -pct:
            pivots[i] = prices.iloc[i]; last_pivot_price = prices.iloc[i]; last_dir = 1
    return pd.Series(pivots, index=prices.index)

class FibElliott(Strategy):
    """Combined Fibonacci retracement + Elliott-like (ZigZag) swings.
    Long: in an upswing, enter near 38.2-61.8% retracement of the last swing.
    Short: symmetric for downswing.
    """
    def __init__(self, zigzag_pct=2.0, fib_levels=(0.382,0.5,0.618), tolerance=0.0015):
        self.zigzag_pct = zigzag_pct
        self.fib_levels = fib_levels
        self.tol = tolerance

    def generate(self, df: pd.DataFrame) -> Signal:
        if len(df) < 60:
            return Signal('FLAT')
        d = df.copy()
        piv = zigzag_pivots(d['close'], pct=self.zigzag_pct).dropna()
        if len(piv) < 2:
            return Signal('FLAT')
        last = piv.index[-1]
        prev = piv.index[-2]
        swing_high = max(d['close'].iloc[prev:last+1])
        swing_low = min(d['close'].iloc[prev:last+1])
        price = d['close'].iloc[-1]
        if swing_high <= swing_low:
            return Signal('FLAT')
        # Determine direction by last move
        up_move = d['close'].iloc[last] > d['close'].iloc[prev]
        diff = swing_high - swing_low
        if up_move:
            retr_levels = [swing_high - lvl*diff for lvl in self.fib_levels]
            if any(abs(price - rl)/price <= self.tol for rl in retr_levels):
                return Signal('BUY')
        else:
            retr_levels = [swing_low + lvl*diff for lvl in self.fib_levels]
            if any(abs(price - rl)/price <= self.tol for rl in retr_levels):
                return Signal('SELL')
        return Signal('FLAT')
