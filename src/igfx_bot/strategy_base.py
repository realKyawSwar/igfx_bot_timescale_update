from dataclasses import dataclass
from abc import ABC, abstractmethod
import pandas as pd

@dataclass
class Signal:
    side: str   # 'BUY' or 'SELL' or 'FLAT'
    sl: float = None
    tp: float = None
    size: float = 0.0

class Strategy(ABC):
    @abstractmethod
    def generate(self, df: pd.DataFrame) -> Signal:
        ...
