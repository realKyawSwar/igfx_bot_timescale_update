import time
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

class Executor:
    def __init__(self, ig_service):
        self.ig = ig_service

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def place_market(self, epic: str, direction: str, size: float, sl: float = None, tp: float = None):
        deal_ref = f"IGFX-{int(time.time())}"
        try:
            resp = self.ig.create_open_position(epic=epic, direction=direction, size=size, order_type='MARKET', guaranteed_stop=False, stop_level=sl, limit_level=tp, deal_reference=deal_ref, currency_code=None, expiry=None, force_open=True, level=None, quote_id=None)
            logger.info(f"Market order submitted {direction} {size} {epic} ref={deal_ref}")
            return resp
        except Exception as e:
            logger.error(f"Order error: {e}")
            raise

    def close_position(self, deal_id: str):
        try:
            return self.ig.close_open_position(deal_id=deal_id)
        except Exception as e:
            logger.error(f"Close error: {e}")
            return None
