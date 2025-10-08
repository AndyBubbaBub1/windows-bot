"""Telegram bot interface for MOEX bot.

This module provides a wrapper around ``python-telegram-bot`` to
handle user commands and forward them to the trading engine.  It
defines a ``TelegramBot`` class which registers command handlers for
``/status``, ``/buy``, ``/sell``, ``/stop``, etc.  The bot only
processes commands from authorised users as specified in the
configuration.  When the ``python-telegram-bot`` library is not
installed, the class falls back to a dummy implementation which
logs that Telegram functionality is unavailable.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Any

try:
    from telegram import Update
    from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
except Exception:
    # Library is not available; define stubs
    Update = object  # type: ignore
    ApplicationBuilder = None  # type: ignore
    CommandHandler = None  # type: ignore
    ContextTypes = None  # type: ignore

logger = logging.getLogger(__name__)


class TelegramBot:
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = (
            "📖 Доступные команды:\n"
            "/status — показать текущий портфель и баланс\n"
            "/buy <TICKER> <QTY> — купить инструмент\n"
            "/sell <TICKER> <QTY> — продать инструмент\n"
            "/stop — закрыть позиции и остановить торговлю\n"
        )
        await update.message.reply_text(msg)
    
    def _validate_command(self, args):
        if len(args) < 2:
            return False, "⚠️ Используйте формат: /buy <TICKER> <QTY>"
        ticker, qty = args[0], args[1]
        if not qty.isdigit() or int(qty) <= 0:
            return False, "⚠️ Количество должно быть положительным числом"
        return True, (ticker, int(qty))
    
    """Manage a Telegram bot for interacting with the trading system."""

    def __init__(self, token: Optional[str], allowed_users: Optional[List[int]], trader, risk_manager, portfolio_manager, equity_file: Optional[str] = None) -> None:
        self.token = token or ''
        self.allowed_users = set(allowed_users or [])
        self.trader = trader
        self.risk_manager = risk_manager
        self.portfolio_manager = portfolio_manager
        # Path to a file where the live loop writes current equity.  If provided,
        # ``status`` will read this file instead of using the risk manager's state.
        self.equity_file = equity_file
        # Store pending trades awaiting confirmation.  Keys are user IDs; values
        # are dictionaries with keys: 'action', 'symbol', 'lots', 'price'.
        # Pending trades are cleared upon confirmation or cancellation.
        self.pending_trades: dict[int, dict[str, Any]] = {}
        self.app = None
        if ApplicationBuilder is None or not self.token:
            logger.info("Telegram bot functionality unavailable (missing library or token).")
            return
        try:
            self.app = ApplicationBuilder().token(self.token).build()
            # Register command handlers
            self.app.add_handler(CommandHandler("status", self.status))
            self.app.add_handler(CommandHandler("buy", self.buy))
            self.app.add_handler(CommandHandler("sell", self.sell))
            self.app.add_handler(CommandHandler("stop", self.stop))
            # Confirmation handlers
            self.app.add_handler(CommandHandler("confirm", self.confirm))
            self.app.add_handler(CommandHandler("cancel", self.cancel))
        except Exception as e:
            logger.error(f"Failed to initialise Telegram bot: {e}")
            self.app = None

    def check_user(self, update: Update) -> bool:
        """Check whether the message sender is authorised."""
        try:
            user_id = update.effective_user.id  # type: ignore[attr-defined]
        except Exception:
            return False
        if not self.allowed_users:
            # No users configured; deny all
            return False
        return user_id in self.allowed_users

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # type: ignore[type-arg]
        """Send current portfolio status to the user."""
        if not self.check_user(update):
            return
        # Prepare a status message.  If an external equity file is provided, use
        # it to report current portfolio equity; otherwise fall back to the
        # risk manager's in-memory state.
        lines = []
        equity_reported = False
        if self.equity_file:
            try:
                with open(self.equity_file, 'r') as ef:
                    val = ef.readline().strip()
                    if val:
                        lines.append(f"Equity: {val}")
                        equity_reported = True
            except Exception:
                pass
        # If equity was not reported from file, use risk manager
        if not equity_reported:
            if self.risk_manager:
                lines.append(f"Equity: {self.risk_manager.portfolio_equity:.2f}")
                lines.append(f"Positions: {len(self.risk_manager.positions)}")
            else:
                lines.append("Risk manager unavailable")
        # List positions from risk manager
        if self.risk_manager:
            for sym, pos in self.risk_manager.positions.items():
                lines.append(f"{sym}: qty={pos['quantity']}, entry={pos['entry_price']}")
        await context.bot.send_message(chat_id=update.effective_chat.id, text="\n".join(lines))  # type: ignore[attr-defined]

    async def buy(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # type: ignore[type-arg]
        """Handle /buy command: /buy SYMBOL LOTS

        This implementation fetches the latest price for the symbol using a
        data provider and respects the risk manager's maximum allowable
        position size.  If the requested quantity exceeds the allowed
        size, it will be reduced.  After placing the order the position
        is registered with the risk manager (if available).
        """
        if not self.check_user(update):
            return
        args = context.args  # type: ignore[attr-defined]
        if len(args) < 2:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Usage: /buy SYMBOL LOTS")  # type: ignore[attr-defined]
            return
        symbol = args[0].upper()
        try:
            requested_lots = int(args[1])
            if requested_lots <= 0:
                raise ValueError
        except Exception:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Invalid lot number.")  # type: ignore[attr-defined]
            return
        # Determine the latest price via DataProvider; fallback to None
        price: Optional[float] = None
        try:
            from .data_provider import DataProvider
            # Use default data_dir; could be extended to read from config
            dp = DataProvider('data')
            price = dp.latest_price(symbol)
        except Exception:
            price = None
        # Determine allowed lots via risk manager
        lots_to_trade = requested_lots
        if self.risk_manager and price is not None:
            try:
                max_lots = int(self.risk_manager.allowed_position_size(price))
                if max_lots <= 0:
                    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Cannot open position in {symbol}: risk limit reached.")  # type: ignore[attr-defined]
                    return
                if requested_lots > max_lots:
                    lots_to_trade = max_lots
            except Exception:
                pass
        # Store pending trade and ask for confirmation
        try:
            user_id = update.effective_user.id  # type: ignore[attr-defined]
        except Exception:
            user_id = None
        if user_id is not None:
            self.pending_trades[user_id] = {
                'action': 'buy',
                'symbol': symbol,
                'lots': lots_to_trade,
                'price': price,
            }
            price_info = f" at {price:.2f}" if price is not None else " at MARKET"
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Pending BUY {lots_to_trade} {symbol}{price_info}. Confirm with /confirm or cancel with /cancel."
            )  # type: ignore[attr-defined]
        else:
            # If user_id could not be determined, execute immediately
            self.trader.buy(symbol, lots=lots_to_trade, limit_price=price)
            if self.risk_manager and price is not None:
                try:
                    self.risk_manager.register_entry(symbol, price, lots_to_trade)
                except Exception:
                    pass
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Bought {lots_to_trade} {symbol}.")  # type: ignore[attr-defined]

    async def sell(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # type: ignore[type-arg]
        """Handle /sell command: /sell SYMBOL [LOTS]

        If ``LOTS`` is omitted, the entire position size (from the risk
        manager) will be sold.  Uses the latest price from the data
        provider to calculate P&L and update risk manager state.  If
        there is no open position, informs the user.
        """
        if not self.check_user(update):
            return
        args = context.args  # type: ignore[attr-defined]
        if not args:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Usage: /sell SYMBOL [LOTS]")  # type: ignore[attr-defined]
            return
        symbol = args[0].upper()
        # Determine quantity from arguments or risk manager
        lots: int = 0
        if len(args) > 1:
            try:
                lots = int(args[1])
                if lots <= 0:
                    raise ValueError
            except Exception:
                await context.bot.send_message(chat_id=update.effective_chat.id, text="Invalid lot number.")  # type: ignore[attr-defined]
                return
        # If lots not provided, derive from open position
        if lots == 0 and self.risk_manager and symbol in self.risk_manager.positions:
            try:
                lots = int(self.risk_manager.positions[symbol].get('quantity', 0))
            except Exception:
                lots = 0
        if lots <= 0:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"No position in {symbol}.")  # type: ignore[attr-defined]
            return
        # Fetch latest price
        price: Optional[float] = None
        try:
            from .data_provider import DataProvider
            dp = DataProvider('data')
            price = dp.latest_price(symbol)
        except Exception:
            price = None
        # Store pending trade and ask for confirmation
        try:
            user_id = update.effective_user.id  # type: ignore[attr-defined]
        except Exception:
            user_id = None
        if user_id is not None:
            self.pending_trades[user_id] = {
                'action': 'sell',
                'symbol': symbol,
                'lots': lots,
                'price': price,
            }
            price_info = f" at {price:.2f}" if price is not None else " at MARKET"
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Pending SELL {lots} {symbol}{price_info}. Confirm with /confirm or cancel with /cancel."
            )  # type: ignore[attr-defined]
        else:
            # If user_id could not be determined, execute immediately
            self.trader.sell(symbol, lots=lots, limit_price=price)
            if self.risk_manager:
                try:
                    self.risk_manager.exit_position(symbol)
                except Exception:
                    pass
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Sold {lots} {symbol}.")  # type: ignore[attr-defined]

    async def confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # type: ignore[type-arg]
        """Handle /confirm command: confirm pending trade for the user.

        If a pending trade exists for the user, execute it using the trader and
        update the risk manager.  If no pending trade is recorded, inform
        the user.  Pending trades are cleared on confirmation.
        """
        if not self.check_user(update):
            return
        try:
            user_id = update.effective_user.id  # type: ignore[attr-defined]
        except Exception:
            return
        trade = self.pending_trades.pop(user_id, None)
        if not trade:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="No pending trade to confirm.")  # type: ignore[attr-defined]
            return
        action = trade.get('action')
        symbol = trade.get('symbol')
        lots = trade.get('lots')
        price = trade.get('price')
        if not symbol or not lots or not action:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Invalid pending trade.")  # type: ignore[attr-defined]
            return
        if action == 'buy':
            self.trader.buy(symbol, lots=lots, limit_price=price)
            if self.risk_manager and price is not None:
                try:
                    self.risk_manager.register_entry(symbol, price, lots)
                except Exception:
                    pass
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Confirmed: bought {lots} {symbol}.")  # type: ignore[attr-defined]
        elif action == 'sell':
            self.trader.sell(symbol, lots=lots, limit_price=price)
            if self.risk_manager:
                try:
                    self.risk_manager.exit_position(symbol)
                except Exception:
                    pass
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Confirmed: sold {lots} {symbol}.")  # type: ignore[attr-defined]
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Unknown action for pending trade.")  # type: ignore[attr-defined]

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # type: ignore[type-arg]
        """Handle /cancel command: cancel pending trade for the user.

        Removes the pending trade for the user and informs them.  Does nothing
        if no pending trade is recorded.
        """
        if not self.check_user(update):
            return
        try:
            user_id = update.effective_user.id  # type: ignore[attr-defined]
        except Exception:
            return
        if self.pending_trades.pop(user_id, None):
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Pending trade cancelled.")  # type: ignore[attr-defined]
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="No pending trade to cancel.")  # type: ignore[attr-defined]

    async def stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # type: ignore[type-arg]
        """Handle /stop command: close all positions and halt trading."""
        if not self.check_user(update):
            return
        if self.risk_manager:
            symbols = list(self.risk_manager.positions.keys())
            for sym in symbols:
                qty = int(self.risk_manager.positions[sym].get('quantity', 0))
                if qty > 0:
                    self.trader.sell(sym, qty)
                    self.risk_manager.exit_position(sym)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="All positions closed. Trading halted.")  # type: ignore[attr-defined]

    def run(self) -> None:
        """Start the Telegram bot polling loop."""
        if not self.app:
            logger.info("Telegram bot not configured; skipping run.")
            return
        logger.info("Starting Telegram bot...")
        self.app.run_polling()


__all__ = ["TelegramBot"]