"""Live trading loop and scheduler callbacks.

This module defines routines that can be scheduled to run at regular
intervals in order to perform live trading.  The main entry point
``run_live_cycle`` is intended to be run frequently (e.g. every
minute) via the APScheduler.  It loads the configuration, reads
price data, computes strategy signals, and places orders through
the :class:`~moex_bot.core.broker.Trader`.  In this simplified
implementation historical CSV files are used to simulate the most
recent price.  When integrated with a real broker API the
``DataProvider`` can be extended to fetch streaming quotes.
"""

from __future__ import annotations

import logging
from typing import Dict, Any, Optional, Iterable

import pandas as pd

from .config import load_config
from .backtester import load_strategies_from_config
from .data_provider import DataProvider
from .tinkoff_stream_provider import TinkoffStreamProvider
from .broker import Trader
from ..reporting.report_builder import send_telegram_message
from .risk import RiskManager
from .portfolio_manager import PortfolioManager
from .telegram_bot import TelegramBot

logger = logging.getLogger(__name__)

RUNNING: bool = False
TRADE_MODE: str = "sandbox"

# -----------------------------------------------------------------------------
# Helpers
#
def _to_bool(value: object, default: bool = False) -> bool:
    """Normalise configuration values to booleans.

    Accepts booleans, strings and numbers.  Strings such as "1",
    "true", "yes" and "on" evaluate to True.  Any other values
    evaluate to False unless ``default`` is provided.

    Args:
        value: Value to convert (may be None).
        default: Fallback when value is None.

    Returns:
        A boolean representing the truthiness of ``value``.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    try:
        if isinstance(value, (int, float)):
            return bool(value)
        s = str(value).strip().lower()
        return s in {"1", "true", "yes", "on"}
    except Exception:
        return default

def start_trading():
    global RUNNING
    RUNNING = True

def stop_trading():
    global RUNNING
    RUNNING = False

def toggle_mode():
    global TRADE_MODE
    TRADE_MODE = "real" if TRADE_MODE == "sandbox" else "sandbox"
    return TRADE_MODE


# Global dictionary to hold latest streamed prices.  Keys are uppercase
# ticker symbols; values are float prices.  This state is shared across
# calls to ``run_live_cycle`` when streaming is enabled.
LAST_PRICES: Dict[str, float] = {}
# Flag to ensure streaming subscription is started only once
STREAM_STARTED: bool = False

# Flag to ensure the Telegram bot is started only once.  Since run_live_cycle
# may be invoked repeatedly by a scheduler, we avoid spawning multiple
# polling loops by using this module-level sentinel.  It is set to True
# after the first successful bot start.
BOT_STARTED = False


def run_live_cycle(cfg: Dict[str, Any] | None = None) -> None:
    global RUNNING, TRADE_MODE
    if not RUNNING:
        logger.info('⏸ Торговый цикл приостановлен')
        return
    if cfg is None:
        cfg = load_config()
    cfg['trade_mode'] = TRADE_MODE

    """Execute one iteration of the live trading cycle.

    This function performs the following steps:

    1. Load the configuration (if not provided).
    2. Instantiate a :class:`DataProvider` using the configured
       ``data_path``.
    3. Instantiate all strategies defined in the configuration.
    4. Create a :class:`Trader` using the Tinkoff credentials from
       the configuration.
    5. For each strategy and each symbol specified for that strategy,
       load the most recent price history, compute the latest signal
       and place a buy or sell order if the signal dictates.

    In this stub implementation the symbol itself is used as the
    identifier passed to the broker.  In production the FIGI should
    be used instead.  All orders default to a single lot.

    Args:
        cfg: Optional pre‑loaded configuration.  If ``None``, the
            configuration will be loaded from the default YAML file.
    """
    # Step 1: load config if not provided
    if cfg is None:
        cfg = load_config()
    # Step 2: choose data provider.  If a valid Tinkoff token is configured
    # and the streaming SDK is available, use TinkoffStreamProvider to
    # obtain live quotes; otherwise fall back to the base DataProvider.
    data_dir = cfg.get('data_path', 'data')
    tinkoff_cfg = cfg.get('tinkoff', {}) or {}
    tinkoff_token = tinkoff_cfg.get('token')
    # Convert sandbox flag to a proper boolean (e.g. "false" should map to False)
    tinkoff_sandbox = _to_bool(tinkoff_cfg.get('sandbox'), default=True)
    # Instantiate provider accordingly
    if tinkoff_token:
        try:
            dp = TinkoffStreamProvider(
                token=tinkoff_token,
                account_id=tinkoff_cfg.get('account_id'),
                sandbox=tinkoff_sandbox,
                data_dir=data_dir,
            )
        except Exception:
            # Fallback to basic provider on failure
            dp = DataProvider(data_dir)
    else:
        dp = DataProvider(data_dir)
    # Step 3: load strategies
    strategies = load_strategies_from_config(cfg)
    # Step 4: create trader
    # reload tinkoff configuration (as dp may have consumed values)
    trade_mode = cfg.get('trade_mode') or 'sandbox'
    # Extract Telegram credentials if present for trade notifications
    telegram_cfg = cfg.get('telegram', {}) or {}
    # Pull Telegram configuration once so it can be reused for notifications
    token: Optional[str] = telegram_cfg.get('token')  # type: ignore[var-annotated]
    chat_id: Optional[str] = telegram_cfg.get('chat_id')  # type: ignore[var-annotated]

    trader = Trader(
        token=tinkoff_token,
        account_id=tinkoff_cfg.get('account_id'),
        # Normalise sandbox flag; default to True when unspecified
        sandbox=_to_bool(tinkoff_cfg.get('sandbox'), default=True),
        trade_mode=trade_mode,
        telegram_token=telegram_cfg.get('token'),
        telegram_chat_id=telegram_cfg.get('chat_id'),
        sandbox_token=tinkoff_cfg.get('sandbox_token'),
        sandbox_account_id=tinkoff_cfg.get('account_id_sandbox'),
        max_leverage=float(trading_cfg.get('leverage', 1.0)) if 'leverage' in trading_cfg else 1.0,
        allow_short=_to_bool(trading_cfg.get('allow_short'), default=True),
    )
    # Step 5: instantiate risk manager with initial capital
    # Prefer 'capital' key from configuration, fall back to 'start_capital'
    initial_capital = cfg.get('capital') or cfg.get('start_capital') or 1_000_000
    try:
        initial_capital_float = float(initial_capital)
    except Exception:
        initial_capital_float = 1_000_000.0
    # Extract risk parameters from configuration; unknown keys will be ignored
    trading_cfg = cfg.get('trading', {}) or {}
    risk_cfg = dict(cfg.get('risk') or {})
    if 'allow_short' not in risk_cfg and 'allow_short' in trading_cfg:
        risk_cfg['allow_short'] = _to_bool(trading_cfg.get('allow_short'), default=True)
    if 'max_leverage' not in risk_cfg and 'leverage' in trading_cfg:
        try:
            lev = float(trading_cfg.get('leverage', 1.0))
            risk_cfg.setdefault('max_leverage', lev)
            risk_cfg.setdefault('max_portfolio_exposure_pct', lev)
        except Exception:
            pass
    try:
        risk_manager = RiskManager(initial_capital=initial_capital_float, **risk_cfg)
    except TypeError:
        # If unexpected keys are provided, fall back to defaults
        risk_manager = RiskManager(initial_capital=initial_capital_float)

    # Optional portfolio manager setup
    portfolio_cfg = cfg.get('portfolio', {}) or {}
    target_allocations = portfolio_cfg.get('target_allocations', {}) or {}
    portfolio_manager: Optional[PortfolioManager] = None  # type: ignore[var-annotated]
    if target_allocations:
        try:
            portfolio_manager = PortfolioManager(target_allocations=target_allocations, risk_manager=risk_manager)
        except Exception:
            portfolio_manager = None

    # --- Streaming setup ----------------------------------------------------
    # If using TinkoffStreamProvider and streaming has not yet been started,
    # start a background thread to subscribe to price updates.  The callback
    # populates the global LAST_PRICES dict.  This ensures that subsequent
    # calls can fetch real-time prices without polling CSV files.  Only
    # unique symbols across all strategies are subscribed.
    global STREAM_STARTED  # type: ignore[global-statement]
    if isinstance(dp, TinkoffStreamProvider) and dp.enabled and not STREAM_STARTED:
        # Collect unique symbols from strategy configuration
        unique_symbols: set[str] = set()
        for strat_name, strat_callable in strategies.items():
            spec = cfg.get('strategies', {}).get(strat_name, {}) or {}
            syms = spec.get('symbols', []) or []
            for s in syms:
                unique_symbols.add(str(s).upper())
        if unique_symbols:
            def _on_price(symbol: str, price: float) -> None:
                # Update global price dict; ignore case by normalising symbol
                LAST_PRICES[symbol.upper()] = price
            import threading
            # Start streaming in a daemon thread; subscribe_prices blocks
            t = threading.Thread(target=dp.subscribe_prices, args=(list(unique_symbols), _on_price), kwargs={'interval': 1.0}, daemon=True)
            t.start()
            STREAM_STARTED = True
    # Step 6: iterate strategies and symbols
    for strat_name, strat_callable in strategies.items():
        spec = cfg.get('strategies', {}).get(strat_name, {}) or {}
        symbols = spec.get('symbols', []) or []
        if not symbols:
            # If no symbols specified we cannot trade anything; skip
            continue
        for symbol in symbols:
            try:
                # Load at least the last 90 days of hourly data.  A
                # different interval could be configured per strategy in
                # the future.
                df = dp.load_history(symbol, interval='hour', days=90)
            except Exception as e:
                logger.warning(f"Could not load data for {symbol}: {e}")
                continue
            if df.empty:
                continue
            # Determine the latest price.  Prefer real‑time prices from the
            # streaming provider if available; otherwise fall back to the
            # closing price from the DataFrame.  Normalise symbol case for
            # lookup.  If no price can be determined, skip this symbol.
            price: Optional[float] = None
            sym_uc = str(symbol).upper()
            # Use streamed price if available
            if isinstance(dp, TinkoffStreamProvider) and sym_uc in LAST_PRICES:
                price = LAST_PRICES.get(sym_uc)
            if price is None:
                # Fallback: compute from DataFrame
                try:
                    price = float(df['close'].astype(float).iloc[-1])
                except Exception:
                    price = None
            if price is None:
                continue
            # Risk management: check if we should exit an existing position
            if symbol in risk_manager.positions:
                # Update trailing stop and check for exit
                if risk_manager.check_exit(symbol, price):
                    lots_to_sell = int(risk_manager.positions[symbol].get('quantity', 0))
                    if lots_to_sell > 0:
                        logger.info(f"[{strat_name}] RiskManager exiting {symbol} with {lots_to_sell} lots")
                        trader.sell(figi=symbol, lots=lots_to_sell)
                    # Determine reason for exit (stop loss or take profit) and notify
                    # Construct a message describing the exit event
                    try:
                        if token and chat_id:
                            exit_reason = "stop or take profit"
                            msg = f"Closed {symbol} position due to {exit_reason} at {price:.2f}"
                            send_telegram_message(msg, [], token, chat_id)
                    except Exception:
                        pass
                    risk_manager.exit_position(symbol)
                    # Skip further processing of this symbol in this cycle
                    continue
            # Compute signals
            try:
                signals: pd.Series = strat_callable(df)
            except Exception as e:
                logger.error(f"Error computing signals for {strat_name}/{symbol}: {e}")
                continue
            if signals.empty:
                continue
            last_signal = signals.iloc[-1]
            # Determine how many lots we can trade based on risk management
            allowed_lots = risk_manager.allowed_position_size(price)
            if last_signal > 0:
                # Positive signal: aim to be long
                if symbol not in risk_manager.positions:
                    # Open long position
                    if allowed_lots > 0:
                        logger.info(f"[{strat_name}] BUY signal for {symbol} → buying {allowed_lots} lots")
                        trader.buy(figi=symbol, lots=allowed_lots)
                        risk_manager.register_entry(symbol, price, allowed_lots)
                        if portfolio_manager:
                            try:
                                portfolio_manager.update_position(symbol, allowed_lots, price, strat_name)
                            except Exception:
                                pass
                else:
                    # If currently short, close short
                    pos_qty = risk_manager.positions[symbol].get('quantity', 0)
                    if pos_qty < 0:
                        # Cover short by buying back
                        lots_to_buy = int(abs(pos_qty))
                        if lots_to_buy > 0:
                            logger.info(f"[{strat_name}] COVER short for {symbol} → buying {lots_to_buy} lots")
                            trader.buy(figi=symbol, lots=lots_to_buy)
                        risk_manager.exit_position(symbol)
                        if portfolio_manager:
                            try:
                                portfolio_manager.remove_position(symbol)
                            except Exception:
                                pass
                        # After covering, optionally open long if allowed_lots > 0
                        if allowed_lots > 0:
                            logger.info(f"[{strat_name}] Opening long for {symbol} → buying {allowed_lots} lots")
                            trader.buy(figi=symbol, lots=allowed_lots)
                            risk_manager.register_entry(symbol, price, allowed_lots)
                            if portfolio_manager:
                                try:
                                    portfolio_manager.update_position(symbol, allowed_lots, price, strat_name)
                                except Exception:
                                    pass
            elif last_signal < 0:
                # Negative signal: aim to be short if allowed
                if symbol in risk_manager.positions:
                    pos_qty = risk_manager.positions[symbol].get('quantity', 0)
                    if pos_qty > 0:
                        # Close long position
                        lots_to_sell = int(pos_qty)
                        if lots_to_sell > 0:
                            logger.info(f"[{strat_name}] SELL signal for {symbol} → selling {lots_to_sell} lots")
                            trader.sell(figi=symbol, lots=lots_to_sell)
                        risk_manager.exit_position(symbol)
                        if portfolio_manager:
                            try:
                                portfolio_manager.remove_position(symbol)
                            except Exception:
                                pass
                        # After closing long, fall through to opening short (below)
                        # Note: allowed_lots computed previously may be stale but acceptable
                    elif pos_qty < 0:
                        # Already short; no action needed here as trailing stop will manage exit
                        logger.debug(f"[{strat_name}] Maintaining short on {symbol}")
                        continue
                # If we are not in position after above and shorting is allowed, open short
                if risk_manager.allow_short:
                    if allowed_lots > 0:
                        logger.info(f"[{strat_name}] SHORT signal for {symbol} → selling {allowed_lots} lots")
                        trader.sell(figi=symbol, lots=allowed_lots)
                        risk_manager.register_entry(symbol, price, -allowed_lots)
                        if portfolio_manager:
                            try:
                                portfolio_manager.update_position(symbol, -allowed_lots, price, strat_name)
                            except Exception:
                                pass
            else:
                logger.debug(f"[{strat_name}] No action for {symbol} (signal=0)")

    # After iterating through all strategies and symbols, optionally start the
    # Telegram bot for interactive control.  We only start the bot on the
    # first invocation of this function to avoid spawning multiple polling
    # loops.  The bot uses the same trader and risk manager instances so that
    # user commands (/buy, /sell, /status, /stop) operate on the live state.
    global BOT_STARTED  # type: ignore[global-statement]
    # Start bot if it has not been started yet and Telegram is configured
    if not BOT_STARTED:
        telegram_cfg = cfg.get('telegram', {}) or {}
        token = telegram_cfg.get('token')
        allowed_users = telegram_cfg.get('allowed_users', []) or []
        # Only start if token and allowed users are provided
        if token and allowed_users:
            try:
                from pathlib import Path as _Path
                # Determine the path to persist equity so that /status can
                # report current portfolio value.  Mirror logic from below.
                equity_file = cfg.get('equity_file')
                if not equity_file:
                    res_dir = cfg.get('results_path') or cfg.get('results_dir') or 'results'
                    equity_file = str((_Path(res_dir) / 'portfolio_equity.txt').resolve())
                bot = TelegramBot(token, allowed_users, trader, risk_manager, portfolio_manager, equity_file=equity_file)
                # Only start the bot if it initialised correctly
                if getattr(bot, 'app', None):
                    import threading
                    t = threading.Thread(target=bot.run, daemon=True)
                    t.start()
                    BOT_STARTED = True
                    logger.info("Telegram bot polling loop started.")
            except Exception as bot_exc:
                logger.error(f"Failed to start Telegram bot: {bot_exc}")

    # After processing all symbols, update the portfolio equity based on open positions.
    # This simple mark-to-market calculation adds the unrealised P&L of each
    # open position to the initial capital.  It can be extended to
    # incorporate cash balances, commissions and multiple positions per
    # symbol.  The updated equity is passed to the risk manager which will
    # track peak equity and drawdowns.
    try:
        equity = initial_capital_float
        for sym, pos in risk_manager.positions.items():
            # Fetch latest price; use DataProvider directly to ensure up‑to‑date
            try:
                latest_price = dp.latest_price(sym)
            except Exception:
                latest_price = None
            if latest_price is None:
                continue
            entry_price = pos.get('entry_price')
            quantity = pos.get('quantity', 0)
            try:
                pnl = (float(latest_price) - float(entry_price)) * float(quantity)
            except Exception:
                pnl = 0.0
            equity += pnl
        # Update risk manager's equity to track drawdown and peak
        risk_manager.update_equity(equity)
    except Exception:
        # Ignore any errors in equity calculation to avoid disrupting the loop
        pass

    # Perform portfolio rebalancing if configured
    if portfolio_manager:
        try:
            portfolio_manager.rebalance(dp, trader, risk_manager)
        except Exception:
            # Ignore errors to avoid disrupting the trading cycle
            pass

    # --- Send a summary notification with current portfolio equity ---
    # Send a simple message at the end of each live cycle summarising the
    # current portfolio equity (mark‑to‑market value).  The message will
    # only be sent if Telegram credentials are configured.  This acts as
    # a basic report of live trading progress and can be extended to
    # include P&L or other metrics.
    try:
        telegram_cfg = cfg.get('telegram', {}) or {}
        token = telegram_cfg.get('token')
        chat_id = telegram_cfg.get('chat_id')
        if token and chat_id:
            # Use risk_manager's portfolio_equity, which is updated above
            equity_value = risk_manager.portfolio_equity
            # Calculate percentage P&L relative to initial capital
            try:
                pnl_pct = (equity_value - initial_capital_float) / max(initial_capital_float, 1e-9)
            except Exception:
                pnl_pct = 0.0
            msg = f"Current portfolio equity: {equity_value:.2f} (P&L: {pnl_pct * 100:.2f}%)"
            # Send message with no attachments
            send_telegram_message(msg, [], token, chat_id)
        # Persist equity to file for status queries
        # Determine file path from config or default to results/portfolio_equity.txt
        try:
            equity_file = cfg.get('equity_file')
            if not equity_file:
                # Use results path from config
                res_dir = cfg.get('results_path') or cfg.get('results_dir') or 'results'
                equity_file = str((Path(res_dir) / 'portfolio_equity.txt').resolve())
            from pathlib import Path as _P
            ef_path = _P(equity_file)
            ef_path.parent.mkdir(parents=True, exist_ok=True)
            with open(ef_path, 'w') as ef:
                ef.write(f"{risk_manager.portfolio_equity:.2f}\n")
        except Exception:
            pass
    except Exception:
        pass


__all__ = ['run_live_cycle', 'send_daily_summary']


def send_daily_summary() -> None:
    """Send a daily summary of portfolio equity and P&L via Telegram.

    This helper function can be scheduled via APScheduler (e.g. once per day)
    to report the end‑of‑day equity and percentage P&L.  It reads the
    configuration, loads the current equity from the equity file if
    available, computes the P&L relative to the starting capital and sends
    a message using ``send_telegram_message``.
    """
    try:
        cfg = load_config()
    except Exception:
        return
    telegram_cfg = cfg.get('telegram', {}) or {}
    token = telegram_cfg.get('token')
    chat_id = telegram_cfg.get('chat_id')
    if not (token and chat_id):
        return
    # Determine equity file path
    equity_file = cfg.get('equity_file')
    if not equity_file:
        from pathlib import Path as _Path
        res_dir = cfg.get('results_path') or cfg.get('results_dir') or 'results'
        equity_file = str((_Path(res_dir) / 'portfolio_equity.txt').resolve())
    # Read equity value
    equity = None
    try:
        with open(equity_file, 'r') as ef:
            val = ef.readline().strip()
            if val:
                equity = float(val)
    except Exception:
        pass
    # Determine starting capital
    try:
        initial_capital = float(cfg.get('capital') or cfg.get('start_capital') or 1_000_000)
    except Exception:
        initial_capital = 1_000_000.0
    if equity is None:
        equity = initial_capital
    try:
        pnl_pct = (equity - initial_capital) / max(initial_capital, 1e-9)
    except Exception:
        pnl_pct = 0.0
    msg = f"Daily summary:\nEquity: {equity:.2f}\nP&L: {pnl_pct * 100:.2f}%"
    try:
        send_telegram_message(msg, [], token, chat_id)
    except Exception:
        pass
