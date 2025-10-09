"""Risk management utilities for live trading.

This module defines a ``RiskManager`` class responsible for enforcing
position sizing rules, stop‑loss and take‑profit levels, and global
risk limits such as maximum drawdown.  It is designed to be used in
conjunction with the :class:`LiveTrader` to prevent overexposure and
to exit trades when risk thresholds are breached.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional
import datetime

import structlog

from .alerts import AlertDispatcher
from .monitoring import record_risk_limit_breach

logger = structlog.get_logger(__name__)

@dataclass
class RiskManager:
    initial_capital: float
    max_drawdown_pct: float = 0.2  # e.g. 20% maximum drawdown from peak equity
    max_daily_loss_pct: float = 0.1  # daily loss threshold before halting trading
    max_position_pct: float = 0.2  # maximum fraction of equity allowed in a single position
    per_trade_risk_pct: float = 0.02  # risk per trade as fraction of capital
    stop_loss_pct: float = 0.05  # 5% stop loss
    take_profit_pct: float = 0.1  # 10% take profit
    max_positions: int = 5  # maximum concurrent positions
    allow_short: bool = False  # whether short positions are permitted
    # Maximum total exposure relative to portfolio equity.  This caps the
    # combined market value of all open positions.  A value of 1.0
    # allows the entire portfolio to be deployed; lower values enforce
    # leverage constraints.
    max_portfolio_exposure_pct: float = 1.0
    # Flag indicating that trading should be halted for the remainder of the day.
    # Set to True when the daily loss threshold is exceeded.  When this flag
    # is active, no new positions will be opened and the manager will
    # immediately return zero size for all allowed_position_size calls.  It
    # resets at the start of a new day when a fresh instance is created.
    halt_trading: bool = field(default=False, init=False)
    # Track date when equity was last updated to detect a new trading day.
    last_equity_date: datetime.date = field(init=False)
    portfolio_equity: float = field(init=False)
    peak_equity: float = field(init=False)
    day_start_equity: float = field(init=False)
    positions: Dict[str, Dict[str, float]] = field(default_factory=dict)
    alert_dispatcher: AlertDispatcher | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self.portfolio_equity = self.initial_capital
        self.peak_equity = self.initial_capital
        # Track equity at the start of day for daily loss calculations
        self.day_start_equity = self.initial_capital
        # Set the last equity date to today when the manager is created
        self.last_equity_date = datetime.date.today()
        if self.alert_dispatcher is None:
            try:
                self.alert_dispatcher = AlertDispatcher()
            except Exception:
                self.alert_dispatcher = None

    def update_equity(self, new_equity: float) -> None:
        """Update internal equity tracking and check drawdown limit."""
        self.portfolio_equity = new_equity
        # If a new calendar day has started, reset day_start_equity and
        # clear the daily trading halt.  This ensures that daily loss limits
        # are evaluated independently for each trading day.
        today = datetime.date.today()
        if today != self.last_equity_date:
            self.day_start_equity = new_equity
            self.last_equity_date = today
            # Reset halt flag for new day
            self.halt_trading = False
        if new_equity > self.peak_equity:
            self.peak_equity = new_equity
        drawdown = 1 - new_equity / self.peak_equity
        if drawdown >= self.max_drawdown_pct:
            logger.error(
                f"Max drawdown exceeded: {drawdown:.2%} >= {self.max_drawdown_pct:.2%}. Trading should stop."
            )
            # send alert on drawdown breach
            self._send_alert(f"📉 Максимальная просадка превышена: {drawdown:.2%}. Торговля остановлена.")
            record_risk_limit_breach('max_drawdown')
            # In a real implementation this could trigger halting all trading.
        # Compute daily loss relative to the start of the day
        daily_loss = (self.day_start_equity - new_equity) / max(self.day_start_equity, 1e-9)
        if daily_loss >= self.max_daily_loss_pct:
            logger.error(
                f"Max daily loss exceeded: {daily_loss:.2%} >= {self.max_daily_loss_pct:.2%}. Halting trading for the day."
            )
            # Clear all positions to halt trading
            self.clear_positions()
            # Set flag to prevent further entries during this trading day
            self.halt_trading = True
            # notify via Telegram
            self._send_alert(
                f"⚠️ Дневной лимит потерь превышен: {daily_loss:.2%}. Торговля остановлена до конца дня."
            )
            record_risk_limit_breach('max_daily_loss')

    def allowed_position_size(self, price: float) -> int:
        """Compute the maximum number of shares/lots allowed per trade.

        Uses the per‑trade risk percentage to size the position such that a stop
        loss of ``stop_loss_pct`` will not lose more than ``per_trade_risk_pct`` of
        current equity.

        Args:
            price: Current price of the instrument.

        Returns:
            Maximum number of shares/lots to buy.
        """
        # Disallow any new trades if the risk manager has halted trading
        if self.halt_trading:
            return 0
        if price <= 0:
            return 0
        # Limit position size so that stop loss does not exceed per-trade risk
        risk_amount = self.portfolio_equity * self.per_trade_risk_pct
        stop_amount = price * self.stop_loss_pct
        base_size = risk_amount / max(stop_amount, 1e-9)
        # Additionally cap by max_position_pct of current equity
        max_size_by_equity = (self.portfolio_equity * self.max_position_pct) / price
        size = min(base_size, max_size_by_equity)
        # Enforce portfolio‑level exposure limit.  Sum the market value of existing
        # positions and ensure the new position does not push the total above
        # ``max_portfolio_exposure_pct`` of current equity.
        if self.max_portfolio_exposure_pct < 1.0:
            total_value = 0.0
            for sym, pos in self.positions.items():
                try:
                    mark = pos.get('last_price') or pos.get('entry_price') or price
                    total_value += abs(pos['quantity']) * float(mark)
                except Exception:
                    continue
            allowed_portfolio_value = max(
                0.0,
                (self.portfolio_equity * self.max_portfolio_exposure_pct) - total_value,
            )
            max_by_portfolio = allowed_portfolio_value / max(price, 1e-9)
            size = min(size, max_by_portfolio)
        return int(max(0, size))

    def register_entry(self, symbol: str, price: float, quantity: float) -> None:
        """Record a new position entry and initialise risk parameters.

        Supports both long (positive quantity) and short (negative quantity)
        positions.  For long positions the stop loss and trailing stop are
        placed below the entry price; for short positions the stop loss and
        trailing stop are above the entry price.  If the maximum number
        of concurrent positions has been reached the entry is rejected.

        Args:
            symbol: The instrument identifier.
            price: The entry price.
            quantity: Positive number for long positions, negative for short.
        """
        # Do not open new positions if trading has been halted due to daily loss
        if self.halt_trading:
            logger.warning("Trading halted due to daily loss limit. Cannot open new position.")
            return
        if len(self.positions) >= self.max_positions:
            logger.warning("Maximum number of positions reached. Cannot open new position.")
            return
        if quantity == 0:
            return
        is_short = quantity < 0
        if is_short and not self.allow_short:
            logger.warning(f"Short positions are not allowed. Skipping entry for {symbol}.")
            return
        # Determine stop and take‑profit levels based on direction
        if not is_short:
            # Long position
            stop_price = price * (1 - self.stop_loss_pct)
            take_profit = price * (1 + self.take_profit_pct)
            trailing_stop = stop_price
        else:
            # Short position: stop above entry, take profit below entry
            stop_price = price * (1 + self.stop_loss_pct)
            take_profit = price * (1 - self.take_profit_pct)
            trailing_stop = stop_price
        self.positions[symbol] = {
            'entry_price': price,
            'quantity': quantity,
            'stop_price': stop_price,
            'take_profit': take_profit,
            'trailing_stop': trailing_stop,
            'last_price': price,
        }
        direction = "short" if is_short else "long"
        logger.info(f"Entered {direction} position {symbol} at {price} x{abs(quantity)}")

    def check_exit(self, symbol: str, current_price: float) -> bool:
        """Check whether a position should be exited based on stop/take levels.

        Implements both fixed and trailing stop logic.  A trailing
        stop moves upwards as the price moves in favour of the
        position.  If the current price falls below the trailing
        stop or rises above the take profit level the position
        should be closed.

        Args:
            symbol: The symbol of the position.
            current_price: The latest market price.

        Returns:
            True if the position should be exited, otherwise False.
        """
        pos = self.positions.get(symbol)
        if not pos:
            return False
        quantity = pos['quantity']
        is_short = quantity < 0
        pos['last_price'] = current_price
        if not is_short:
            # Long position: update trailing stop upward if price increases
            new_trailing = current_price * (1 - self.stop_loss_pct)
            if new_trailing > pos['trailing_stop']:
                pos['trailing_stop'] = new_trailing
            # Exit if price falls below trailing stop (stop loss) or rises to take profit
            if current_price <= pos.get('trailing_stop', pos['stop_price']):
                logger.info(f"Stop loss or trailing stop hit for {symbol} at {current_price}. Exiting long position.")
                return True
            if current_price >= pos['take_profit']:
                logger.info(f"Take profit reached for {symbol} at {current_price}. Exiting long position.")
                return True
            return False
        else:
            # Short position: update trailing stop downward if price decreases
            new_trailing = current_price * (1 + self.stop_loss_pct)
            if new_trailing < pos['trailing_stop']:
                pos['trailing_stop'] = new_trailing
            # Exit if price rises above trailing stop (stop loss) or falls to take profit
            if current_price >= pos.get('trailing_stop', pos['stop_price']):
                logger.info(f"Stop loss or trailing stop hit for {symbol} at {current_price}. Exiting short position.")
                return True
            if current_price <= pos['take_profit']:
                logger.info(f"Take profit reached for {symbol} at {current_price}. Exiting short position.")
                return True
            return False

    def exit_position(self, symbol: str) -> None:
        """Remove a position after exit."""
        if symbol in self.positions:
            logger.info(f"Exited position {symbol}")
            del self.positions[symbol]

    def clear_positions(self) -> None:
        """Clear all open positions (used on drawdown breach or shutdown)."""
        for sym in list(self.positions.keys()):
            logger.info(f"Force closing position {sym}")
            del self.positions[sym]

    # ---------------------------------------------------------------------
    # Notification helpers
    # ---------------------------------------------------------------------
    def _send_alert(self, message: str) -> None:
        """Send a text alert via Telegram if a bot token and chat id are set.

        This helper attempts to send ``message`` to the chat configured
        in the environment variables ``TELEGRAM_TOKEN``/``TELEGRAM_BOT_TOKEN``
        and ``TELEGRAM_CHAT_ID``.  It silently ignores failures and logs
        any exceptions.  External dependencies (e.g. ``requests``) are
        imported within the function to avoid mandatory dependencies for
        users who do not require notifications.

        Args:
            message: Text of the notification to send.
        """
        if not message:
            return
        if self.alert_dispatcher:
            try:
                self.alert_dispatcher.send(message)
                return
            except Exception as exc:  # pragma: no cover - logging side effect
                logger.warning('failed to send alert', error=str(exc))
        logger.debug('alert dispatcher unavailable', message=message)


__all__ = ['RiskManager']