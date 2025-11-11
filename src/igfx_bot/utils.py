import os
import time
import math
import pytz
import yaml
from dataclasses import dataclass
from dataclasses_json import dataclass_json
from loguru import logger
from datetime import datetime
from tzlocal import get_localzone

@dataclass_json
@dataclass
class Candle:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

def load_config(path: str) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    return cfg

def within_session(now_utc, start_hour, end_hour):
    hour = now_utc.hour
    if start_hour <= end_hour:
        return start_hour <= hour < end_hour
    else:
        return hour >= start_hour or hour < end_hour

def now_utc():
    return datetime.utcnow().replace(tzinfo=pytz.UTC)

def env(name: str, default: str = None):
    v = os.environ.get(name, default)
    if v is None:
        logger.warning(f"Environment variable {name} not set.")
    return v

def round_to_pip(price: float, pip_size: float):
    return round(price / pip_size) * pip_size
