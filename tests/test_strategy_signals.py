import pandas as pd
from src.igfx_bot.strategies.sma_ema_crossover import SMAEMACrossover

def test_sma_ema_signal_types():
    df = pd.DataFrame({"close": [i for i in range(1,300)]})
    s = SMAEMACrossover(fast=5, slow=10)
    sig = s.generate(df)
    assert sig.side in ('BUY','SELL','FLAT')
