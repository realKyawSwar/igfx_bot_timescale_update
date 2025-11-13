"""Main entrypoint for running live trading jobs."""

from __future__ import annotations

import signal
import time
from typing import Dict, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from loguru import logger

from .auth import IGAuth
from .data import MarketData
from .db import PgConfig, PgSink
from .execution import Executor
from .notifications import TelegramNotifier
from .risk import RiskConfig, RiskManager
from .strategies.alligator import Alligator
from .strategies.fib_elliott import FibElliott
from .strategies.rsi_reversal import RSIReversal
from .strategies.sma_ema_crossover import SMAEMACrossover
from .utils import env, load_config, now_utc, within_session


SUPPORTED_MODES = {"DEMO", "LIVE"}


def _normalise_mode(mode: Optional[str]) -> Optional[str]:
    if mode is None:
        return None
    value = str(mode).strip().upper()
    return value or None


def _resolve_mode(cli_mode: Optional[str], cfg_mode: Optional[str]) -> str:
    for candidate in (_normalise_mode(cli_mode), _normalise_mode(cfg_mode)):
        if candidate:
            if candidate in SUPPORTED_MODES:
                return candidate
            logger.warning("Unknown trading mode '{}'; falling back to DEMO", candidate)
    return "DEMO"


def _resolve_ig_env_names(ig_cfg: dict, mode: str) -> Dict[str, Optional[str]]:
    credentials_cfg = ig_cfg.get("credentials", {}) or {}

    mode_cfg: Dict[str, str] = {}
    for key, value in credentials_cfg.items():
        if isinstance(key, str) and key.strip().upper() == mode:
            if isinstance(value, dict):
                mode_cfg = value
            break

    def _pick(name: str, fallback: Optional[str] = None) -> Optional[str]:
        mode_key = f"{name}_env"
        if mode_key in mode_cfg and mode_cfg[mode_key]:
            return mode_cfg[mode_key]
        value = ig_cfg.get(mode_key)
        if value:
            return value
        return fallback

    return {
        "api_key_env": _pick("api_key"),
        "username_env": _pick("username"),
        "password_env": _pick("password"),
        "account_type_env": _pick("account_type"),
        "account_id_env": _pick("account_id"),
    }


def _read_env(name: Optional[str], default: Optional[str] = None) -> Optional[str]:
    if not name:
        return default
    return env(name, default)


RUNNING = True


def handle_sig(sig, frame):
    global RUNNING
    logger.warning("Received shutdown signal; stopping scheduler...")
    RUNNING = False


def build_strategy(name: str, params: dict):
    if name == "sma_ema_crossover":
        return SMAEMACrossover(fast=params.get("fast", 50), slow=params.get("slow", 200))
    if name == "rsi_reversal":
        return RSIReversal(
            length=params.get("rsi_len", 14),
            ob=params.get("rsi_ob", 70),
            os=params.get("rsi_os", 30),
        )
    if name == "alligator":
        ap = params.get("alligator", {})
        return Alligator(
            jaw=ap.get("jaw", 13),
            teeth=ap.get("teeth", 8),
            lips=ap.get("lips", 5),
            smooth=ap.get("smooth", 5),
            breakout_lookback=params.get("breakout_lookback", 10),
        )
    if name == "fib_elliott":
        fp = params.get("fib", {})
        zp = params.get("zigzag", {})
        return FibElliott(
            zigzag_pct=zp.get("pct", 2.0),
            fib_levels=tuple(fp.get("levels", [0.382, 0.5, 0.618])),
            tolerance=fp.get("tolerance", 0.0015),
        )
    raise ValueError(f"Unknown strategy {name}")


def _price_format(pip_size: float) -> str:
    if pip_size <= 0:
        return "{:.5f}"
    pip_str = f"{pip_size:.10f}".rstrip("0").rstrip(".")
    if "." in pip_str:
        decimals = len(pip_str.split(".")[1])
    else:
        decimals = 0
    precision = min(max(decimals, 1), 6)
    return "{:." + str(precision) + "f}"


def job(
    cfg: dict,
    md: MarketData,
    ex: Executor,
    rm: RiskManager,
    sink: Optional[PgSink] = None,
    notifier: Optional[TelegramNotifier] = None,
    strategies: Optional[Dict[str, object]] = None,
):
    scheduler_cfg = cfg.get("scheduler", {})
    session_cfg = scheduler_cfg.get("session", {})
    start_hour = session_cfg.get("start_hour", 0)
    end_hour = session_cfg.get("end_hour", 24)

    if not within_session(now_utc(), start_hour, end_hour):
        return

    strategy_cfg = cfg.get("strategy", {})
    strategy_name = strategy_cfg.get("name")
    strategy_params = strategy_cfg.get("params", {})
    history_points = cfg.get("data", {}).get("history_points", 400)

    for inst in cfg.get("instruments", []):
        symbol = inst["symbol"]
        epic = inst["ig_epic"]
        resolution = "MINUTE_5" if inst.get("timeframe", "5min") == "5min" else "MINUTE"

        strategy = None
        if strategies is not None:
            strategy = strategies.get(symbol)
        if strategy is None:
            if not strategy_name:
                logger.warning("No strategy configured; skipping instrument {}", symbol)
                continue
            strategy = build_strategy(strategy_name, strategy_params)
            if strategies is not None:
                strategies[symbol] = strategy

        df = md.fetch_historical(epic, resolution=resolution, n=history_points)
        if sink and not df.empty:
            try:
                sink.write_candles(symbol, df.tail(1))
            except Exception as exc:
                logger.warning(f"write_candles failed for {symbol}: {exc}")

        if df.empty:
            continue

        sig = strategy.generate(df)
        if sig.side == "FLAT":
            continue

        last = df.iloc[-1]
        price = float(last["close"])
        pip_size = float(inst["pip_size"])
        lot_size = int(inst["lot_size"])
        rr = rm.cfg.rr_ratio
        stop_distance_pips = max(inst.get("stop_distance_pips", 10), 1)
        sl_distance = stop_distance_pips * pip_size

        if sig.side == "BUY":
            sl = price - sl_distance
            tp = price + sl_distance * rr
        else:
            sl = price + sl_distance
            tp = price - sl_distance * rr

        if not rm.can_trade():
            continue

        size = rm.position_size(entry=price, stop=sl, pip_size=pip_size, lot_size=lot_size)
        if size <= 0:
            continue

        direction = "BUY" if sig.side == "BUY" else "SELL"
        price_format = _price_format(pip_size)

        if notifier:
            approved = notifier.handle_trade_alert(
                symbol=symbol,
                direction=direction,
                price=price,
                stop_loss=sl,
                take_profit=tp,
                size=size,
                price_format=price_format,
            )
            if not approved:
                continue

        try:
            resp = ex.place_market(epic=epic, direction=direction, size=size, sl=sl, tp=tp)
        except Exception as exc:
            logger.exception(f"Failed to execute trade for {symbol}: {exc}")
            continue

        deal_ref = resp.get("dealReference") if isinstance(resp, dict) else None

        if sink:
            try:
                sink.log_trade(
                    epic=epic,
                    symbol=symbol,
                    side=direction,
                    size=size,
                    entry=price,
                    sl=sl,
                    tp=tp,
                    deal_ref=deal_ref,
                    raw=resp if isinstance(resp, dict) else None,
                )
            except Exception as exc:
                logger.warning(f"log_trade failed for {symbol}: {exc}")

        if notifier:
            notifier.notify_execution(
                symbol=symbol,
                direction=direction,
                price=price,
                size=size,
                deal_reference=deal_ref,
                price_format=price_format,
            )

        rm.register_trade(0.0)


def main(config_path: str, mode: Optional[str] = None):
    cfg = load_config(config_path)

    trading_mode = _resolve_mode(mode, cfg.get("mode"))
    logger.info("Selected IG trading mode: {}", trading_mode)

    ig_cfg = cfg.get("ig", {})
    env_names = _resolve_ig_env_names(ig_cfg, trading_mode)

    api_key = _read_env(env_names.get("api_key_env"))
    username = _read_env(env_names.get("username_env"))
    password = _read_env(env_names.get("password_env"))
    account_type = _read_env(env_names.get("account_type_env"), trading_mode)
    if not account_type:
        account_type = trading_mode
    account_type = account_type.upper()
    account_id = _read_env(env_names.get("account_id_env"))

    auth = IGAuth(api_key, username, password, account_type)
    ig = auth.login()
    if account_id:
        try:
            ig.switch_account(account_id, account_type)
        except Exception as exc:
            logger.warning(f"Could not switch account: {exc}")

    md = MarketData(ig_service=ig)

    sink: Optional[PgSink] = None
    db_cfg = cfg.get("database", {})
    if db_cfg.get("enabled"):
        dsn = env(db_cfg.get("dsn_env", "PG_DSN"))
        host = env(db_cfg.get("host_env", "PGHOST"))
        port = env(db_cfg.get("port_env", "PGPORT"), "5432")
        user = env(db_cfg.get("user_env", "PGUSER"))
        password = env(db_cfg.get("password_env", "PGPASSWORD"))
        dbname = env(db_cfg.get("dbname_env", "PGDATABASE"))
        pgcfg = PgConfig(
            dsn=dsn,
            host=host,
            port=int(port) if port else 5432,
            user=user,
            password=password,
            dbname=dbname,
        )
        sink = PgSink(pgcfg)
        try:
            sink.init_schema()
        except Exception as exc:
            logger.warning(f"DB init failed: {exc}")

    ex = Executor(ig_service=ig)

    risk_cfg = cfg.get("risk", {})
    rm = RiskManager(
        RiskConfig(
            balance=risk_cfg.get("balance", 10000),
            risk_per_trade_pct=risk_cfg.get("risk_per_trade_pct", 1.0),
            rr_ratio=risk_cfg.get("rr_ratio", 2.0),
            max_daily_loss_pct=risk_cfg.get("max_daily_loss_pct", 3.0),
            max_daily_trades=risk_cfg.get("max_daily_trades", 5),
            slippage_pips=risk_cfg.get("slippage_pips", 0.5),
        )
    )

    notifier: Optional[TelegramNotifier] = None
    telegram_cfg = cfg.get("telegram", {})
    if telegram_cfg.get("enabled"):
        bot_token = env(telegram_cfg.get("bot_token_env", "TELEGRAM_BOT_TOKEN"))
        chat_id = env(telegram_cfg.get("chat_id_env", "TELEGRAM_CHAT_ID"))
        require_confirmation = telegram_cfg.get("require_trade_confirmation", True)
        confirmation_timeout = telegram_cfg.get("confirmation_timeout_seconds", 45)
        poll_interval = telegram_cfg.get("poll_interval_seconds", 2.0)
        if bot_token and chat_id:
            notifier = TelegramNotifier(
                bot_token=bot_token,
                chat_id=chat_id,
                require_confirmation=require_confirmation,
                confirmation_timeout=int(confirmation_timeout),
                poll_interval=float(poll_interval),
            )
        else:
            logger.warning("Telegram alerts enabled but bot token or chat id is missing.")

    strategies: Dict[str, object] = {}
    strategy_cfg = cfg.get("strategy", {})
    strategy_name = strategy_cfg.get("name")
    strategy_params = strategy_cfg.get("params", {})
    if strategy_name:
        for inst in cfg.get("instruments", []):
            symbol = inst["symbol"]
            strategies[symbol] = build_strategy(strategy_name, strategy_params)

    scheduler_cfg = cfg.get("scheduler", {})
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        job,
        "interval",
        seconds=scheduler_cfg.get("run_interval_seconds", 60),
        args=[cfg, md, ex, rm, sink, notifier, strategies],
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)
    logger.info("IGFX-Bot runner started.")

    try:
        while RUNNING:
            time.sleep(1)
    finally:
        scheduler.shutdown(wait=False)
        auth.logout()
        logger.info("Runner stopped.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument(
        "--mode",
        default=None,
        help="Trading mode to use (DEMO or LIVE). Overrides the `mode` value in the config when provided.",
    )
    args = parser.parse_args()
    main(args.config, args.mode)

