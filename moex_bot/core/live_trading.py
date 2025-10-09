"""Live trading gateway (placeholder).

This module will integrate with broker APIs (e.g. Tinkoff Invest) to
execute trades in real time.  Currently it provides a stub class
`LiveTrader` that logs orders without sending them.  When real API
credentials and a suitable library become available, the methods
should be implemented to interact with the broker's REST or gRPC
interface.
"""

from __future__ import annotations

import structlog
from dataclasses import dataclass, field
from typing import Optional

from .risk import RiskManager

logger = structlog.get_logger(__name__)

@dataclass
class LiveTrader:
    account_id: Optional[str] = None
    sandbox: bool = True
    risk_manager: Optional[RiskManager] = None  # optional risk manager

    def __post_init__(self) -> None:
        # Initialise a default risk manager if none provided
        if self.risk_manager is None:
            # Default initial capital of 1m; will be updated via update_equity
            self.risk_manager = RiskManager(initial_capital=1_000_000)

    def buy(self, ticker: str, lots: int, limit_price: Optional[float] = None) -> None:
        """Place a buy order.

        Args:
            ticker: The ticker symbol.
            lots: Number of lots to purchase.
            limit_price: Optional limit price.  ``None`` means a market order.
        """
        logger.info(f"[LiveTrader] BUY {lots} {ticker} @ {limit_price or 'MARKET'} (sandbox={self.sandbox})")
        # Register position with risk manager
        if limit_price is not None and self.risk_manager is not None:
            self.risk_manager.register_entry(ticker, limit_price, lots)

    def sell(self, ticker: str, lots: int, limit_price: Optional[float] = None) -> None:
        """Place a sell order.

        Args:
            ticker: The ticker symbol.
            lots: Number of lots to sell.
            limit_price: Optional limit price.
        """
        logger.info(f"[LiveTrader] SELL {lots} {ticker} @ {limit_price or 'MARKET'} (sandbox={self.sandbox})")
        # Exiting position
        if self.risk_manager is not None:
            self.risk_manager.exit_position(ticker)

    def cancel_all(self) -> None:
        """Cancel all open orders.  Not yet implemented."""
        logger.warning("[LiveTrader] cancel_all called but not implemented.")

    def update_price(self, ticker: str, current_price: float) -> None:
        """Update risk manager with latest price and check for exits.

        In a real-time trading loop this method should be called for each
        tracked symbol to see if stop-loss or take-profit levels have been
        reached.  If so, a sell order should be placed.

        Args:
            ticker: Symbol to update.
            current_price: Latest market price.
        """
        if self.risk_manager is None:
            return
        if self.risk_manager.check_exit(ticker, current_price):
            # For simplicity we assume sell at market price
            self.sell(ticker, lots=int(self.risk_manager.positions.get(ticker, {}).get('quantity', 0)), limit_price=current_price)
        # Could update portfolio equity here if we track mark-to-market

    # Additional methods for risk management, portfolio status, etc. can be added here

__all__ = ['LiveTrader']