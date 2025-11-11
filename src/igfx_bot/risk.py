from dataclasses import dataclass
from loguru import logger
import math

@dataclass
class RiskConfig:
    balance: float
    risk_per_trade_pct: float = 1.0
    rr_ratio: float = 2.0
    max_daily_loss_pct: float = 3.0
    max_daily_trades: int = 5
    slippage_pips: float = 0.5

class RiskManager:
    def __init__(self, cfg: RiskConfig):
        self.cfg = cfg
        self._daily_loss = 0.0
        self._daily_trades = 0

    def can_trade(self):
        if self._daily_trades >= self.cfg.max_daily_trades:
            logger.warning("Max daily trades reached.")
            return False
        if (self._daily_loss / self.cfg.balance) * 100.0 >= self.cfg.max_daily_loss_pct:
            logger.warning("Max daily loss reached.")
            return False
        return True

    def position_size(self, entry: float, stop: float, pip_size: float, lot_size: int):
        risk_amt = self.cfg.balance * (self.cfg.risk_per_trade_pct / 100.0)
        pip_risk = abs(entry - stop) / pip_size
        if pip_risk <= 0:
            return 0
        units = risk_amt / pip_risk / pip_size
        # Convert to nearest lot
        lots = max(1, int(units // lot_size))
        return lots * lot_size

    def register_trade(self, pnl: float):
        self._daily_trades += 1
        if pnl < 0:
            self._daily_loss += abs(pnl)

    def reset_day(self):
        self._daily_loss = 0.0
        self._daily_trades = 0
