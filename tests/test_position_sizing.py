from src.igfx_bot.risk import RiskConfig, RiskManager

def test_position_sizing_basic():
    rm = RiskManager(RiskConfig(balance=10000, risk_per_trade_pct=1.0))
    size = rm.position_size(entry=1.1000, stop=1.0990, pip_size=0.0001, lot_size=10000)
    assert size > 0
