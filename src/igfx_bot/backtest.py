import argparse
import pandas as pd
import yfinance as yf
import backtrader as bt
from loguru import logger
from .utils import load_config

class GenericStrategy(bt.Strategy):
    params = dict(name='sma_ema_crossover', fast=50, slow=200, rsi_len=14, rsi_ob=70, rsi_os=30)

    def __init__(self):
        self.dataclose = self.datas[0].close
        if self.p.name == 'sma_ema_crossover':
            self.sma = bt.ind.SMA(period=self.p.fast)
            self.ema = bt.ind.EMA(period=self.p.slow)
        elif self.p.name == 'rsi_reversal':
            self.rsi = bt.ind.RSI(period=self.p.rsi_len)

    def next(self):
        if self.p.name == 'sma_ema_crossover':
            if not self.position and self.sma[0] > self.ema[0] and self.sma[-1] <= self.ema[-1]:
                self.buy()
            elif self.position and self.sma[0] < self.ema[0] and self.sma[-1] >= self.ema[-1]:
                self.sell()
        elif self.p.name == 'rsi_reversal':
            if not self.position and self.rsi[0] < self.p.rsi_os:
                self.buy()
            elif self.position and self.rsi[0] > self.p.rsi_ob:
                self.sell()

def yf_symbol(symbol: str):
    mapping = {'EURUSD':'EURUSD=X', 'GBPUSD':'GBPUSD=X', 'USDJPY':'JPY=X'}
    return mapping.get(symbol, symbol)

def run_backtest(args):
    cfg = load_config(args.config)
    cerebro = bt.Cerebro()
    cerebro.broker.setcash(10000.0)
    cerebro.broker.setcommission(commission=0.0002)

    yfsym = yf_symbol(args.symbol)
    data = yf.download(yfsym, start=args.from_, end=args.to, interval='5m' if args.timeframe=='5min' else '1m')
    data.dropna(inplace=True)
    datafeed = bt.feeds.PandasData(dataname=data)
    cerebro.adddata(datafeed)
    cerebro.addstrategy(GenericStrategy, name=args.strategy, fast=cfg['strategy']['params']['fast'], slow=cfg['strategy']['params']['slow'], rsi_len=cfg['strategy']['params']['rsi_len'], rsi_ob=cfg['strategy']['params']['rsi_ob'], rsi_os=cfg['strategy']['params']['rsi_os'])
    res = cerebro.run()
    final_val = cerebro.broker.getvalue()
    logger.info(f"Final portfolio value: {final_val:.2f}")
    return final_val

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--config', required=True)
    p.add_argument('--strategy', default='sma_ema_crossover')
    p.add_argument('--symbol', default='EURUSD')
    p.add_argument('--timeframe', default='5min')
    p.add_argument('--from', dest='from_', required=True)
    p.add_argument('--to', required=True)
    args = p.parse_args()
    run_backtest(args)
