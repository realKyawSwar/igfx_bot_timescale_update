import time
import signal
import sys
from datetime import datetime
import pandas as pd
from loguru import logger
from apscheduler.schedulers.background import BackgroundScheduler
from .utils import load_config, env, now_utc, within_session
from .auth import IGAuth
from .data import MarketData
from .risk import RiskConfig, RiskManager
from .execution import Executor
from .db import PgConfig, PgSink
from .strategies.sma_ema_crossover import SMAEMACrossover
from .strategies.rsi_reversal import RSIReversal
from .strategies.alligator import Alligator
from .strategies.fib_elliott import FibElliott

RUNNING = True

def handle_sig(sig, frame):
    global RUNNING
    logger.warning("Received shutdown signal; stopping scheduler...")
    RUNNING = False

def build_strategy(name: str, params: dict):
    if name == 'sma_ema_crossover':
        return SMAEMACrossover(fast=params.get('fast',50), slow=params.get('slow',200))
    if name == 'rsi_reversal':
        return RSIReversal(length=params.get('rsi_len',14), ob=params.get('rsi_ob',70), os=params.get('rsi_os',30))
    if name == 'alligator':
        ap = params.get('alligator',{})
        zp = params.get('zigzag',{})
        fp = params.get('fib',{})
        return Alligator(jaw=ap.get('jaw',13), teeth=ap.get('teeth',8), lips=ap.get('lips',5), smooth=ap.get('smooth',5), breakout_lookback=params.get('breakout_lookback',10))
    if name == 'fib_elliott':
        fp = params.get('fib',{})
        zp = params.get('zigzag',{})
        return FibElliott(zigzag_pct=zp.get('pct',2.0), fib_levels=tuple(fp.get('levels',[0.382,0.5,0.618])), tolerance=fp.get('tolerance',0.0015))
    raise ValueError(f"Unknown strategy {name}")

def job(cfg, ig, md, ex, rm):
    tz = cfg.get('timezone','UTC')
    sess = cfg['scheduler']['session']
    if not within_session(now_utc(), sess['start_hour'], sess['end_hour']):
        return
    for inst in cfg['instruments']:
        epic = inst['ig_epic']
        sym = inst['symbol']
        resolution = 'MINUTE_5' if inst.get('timeframe','5min')=='5min' else 'MINUTE'
        df = md.fetch_historical(epic, resolution=resolution, n=400)
            if sink:
                try:
                    sink.write_candles(sym, df)
                except Exception as e:
                    logger.warning(f"write_candles failed for {sym}: {e}")
        if df.empty:
            continue
        strat = build_strategy(cfg['strategy']['name'], cfg['strategy']['params'])
        sig = strat.generate(df)
        if sig.side == 'FLAT':
            continue
        last = df.iloc[-1]
        price = float(last['close'])
        pip = inst['pip_size']
        lot = inst['lot_size']
        # Simple SL/TP using RR from config
        rr = cfg['risk']['rr_ratio']
        # Example: 1 x ATR or fixed pip SL (use 10*pip as base)
        sl_distance = 10*pip
        if sig.side == 'BUY':
            sl = price - sl_distance
            tp = price + sl_distance*rr
        else:
            sl = price + sl_distance
            tp = price - sl_distance*rr
        rc = RiskConfig(balance=10000, risk_per_trade_pct=cfg['risk']['risk_per_trade_pct'], rr_ratio=rr, max_daily_loss_pct=cfg['risk']['max_daily_loss_pct'], max_daily_trades=cfg['risk']['max_daily_trades'], slippage_pips=cfg['risk']['slippage_pips'])
        if not rm.can_trade():
            continue
        size = rm.position_size(entry=price, stop=sl, pip_size=pip, lot_size=lot)
        if size <= 0:
            continue
        direction = 'BUY' if sig.side=='BUY' else 'SELL'
        try:
            resp = ex.place_market(epic=epic, direction=direction, size=size, sl=sl, tp=tp)
                if sink:
                    try:
                        deal_ref = None
                        try:
                            deal_ref = resp.get('dealReference') if isinstance(resp, dict) else None
                        except Exception:
                            pass
                        sink.log_trade(epic=epic, symbol=sym, side=direction, size=size, entry=price, sl=sl, tp=tp, deal_ref=deal_ref, raw=resp if isinstance(resp, dict) else None)
                    except Exception as e:
                        logger.warning(f"log_trade failed for {sym}: {e}")
        except Exception:
            continue

def main(config_path: str, mode: str = 'demo'):
    cfg = load_config(config_path)
    api_key = env(cfg['ig']['api_key_env'])
    username = env(cfg['ig']['username_env'])
    password = env(cfg['ig']['password_env'])
    account_type = env(cfg['ig']['account_type_env'], cfg.get('mode','DEMO'))
    account_id = env(cfg['ig'].get('account_id_env', ''), None)

    auth = IGAuth(api_key, username, password, account_type)
    ig = auth.login()
    if account_id:
        try:
            ig.switch_account(account_id, account_type)
        except Exception as e:
            logger.warning(f"Could not switch account: {e}")

    md = MarketData(ig_service=ig)
        # Optional TimescaleDB sink
sink = None
if cfg.get('database', {}).get('enabled', False):
    from .utils import env
    db = cfg['database']
    dsn = env(db.get('dsn_env','PG_DSN'))
    host = env(db.get('host_env','PGHOST'))
    port = env(db.get('port_env','PGPORT'), '5432')
    user = env(db.get('user_env','PGUSER'))
    password = env(db.get('password_env','PGPASSWORD'))
    dbname = env(db.get('dbname_env','PGDATABASE'))
    pgcfg = PgConfig(dsn=dsn, host=host, port=int(port) if port else 5432, user=user, password=password, dbname=dbname)
    sink = PgSink(pgcfg)
    try:
        sink.init_schema()
    except Exception as e:
        logger.warning(f"DB init failed: {e}")

    ex = Executor(ig_service=ig)
    rm = RiskManager(RiskConfig(balance=10000,
                                risk_per_trade_pct=cfg['risk']['risk_per_trade_pct'],
                                rr_ratio=cfg['risk']['rr_ratio'],
                                max_daily_loss_pct=cfg['risk']['max_daily_loss_pct'],
                                max_daily_trades=cfg['risk']['max_daily_trades'],
                                slippage_pips=cfg['risk']['slippage_pips']))

    scheduler = BackgroundScheduler()
    scheduler.add_job(job, 'interval', seconds=cfg['scheduler']['run_interval_seconds'], args=[cfg, ig, md, ex, rm], max_instances=1, coalesce=True)
    scheduler.start()

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)
    logger.info("IGFX-Bot runner started.")

    try:
        while True and RUNNING:
            time.sleep(1)
    finally:
        scheduler.shutdown(wait=False)
        auth.logout()
        logger.info("Runner stopped.")

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--config', required=True)
    p.add_argument('--mode', default='demo')
    args = p.parse_args()
    main(args.config, args.mode)
