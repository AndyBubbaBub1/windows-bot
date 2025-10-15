"""Portfolio Manager for MOEX bot.

This module defines a ``PortfolioManager`` class responsible for
managing allocations across multiple strategies in a live trading
environment.  It keeps track of current positions, computes target
exposures based on configurable allocations and collaborates with
``RiskManager`` and ``Trader`` to open or close positions in order
to maintain the desired portfolio structure.  The current
implementation is intentionally simple and should be extended with
more sophisticated logic for production use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class PortfolioManager:
    """Manage capital allocations across strategies.

    Args:
        target_allocations: Mapping of strategy names to target weights
            (fractions summing to 1.0).  For example, ``{'sma_strategy': 0.3}``.
        risk_manager: Instance of :class:`RiskManager` used to compute
            allowable position sizes.  May be ``None`` if not needed.
    """

    target_allocations: Dict[str, float]
    risk_manager: Optional[object] = None
    positions: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def update_position(self, symbol: str, quantity: float, price: float, strategy: str) -> None:
        """Record or update a position entry.

        Args:
            symbol: The traded instrument symbol.
            quantity: Number of lots held (positive for long).
            price: Entry price of the position.
            strategy: Name of the strategy owning the position.
        """
        self.positions[symbol] = {
            'quantity': quantity,
            'price': price,
            'strategy': strategy,
        }
        logger.debug(f"Portfolio: updated {symbol} position for {strategy}: qty={quantity}, price={price}")

    def remove_position(self, symbol: str) -> None:
        """Remove a position from the portfolio."""
        if symbol in self.positions:
            logger.debug(f"Portfolio: removed position {symbol}")
            del self.positions[symbol]

    def compute_exposure(self, symbol: str, price: float, quantity: float) -> float:
        """Return the monetary exposure of a position."""
        return price * quantity

    def rebalance(self, data_provider, trader, risk_manager) -> None:
        """Rebalance positions according to target allocations.

        This basic implementation calculates the current equity from
        ``risk_manager`` and compares actual exposures per strategy with
        desired exposures.  When under-allocated, it will attempt to
        open new positions up to the target weight.  When over-allocated,
        it will exit positions.  Only long positions are supported.

        Args:
            data_provider: Instance capable of fetching latest prices.
            trader: Instance capable of executing trades.
            risk_manager: Risk manager for sizing and risk checks.
        """
        # Compute total equity available
        equity = risk_manager.portfolio_equity if risk_manager else 0.0
        if equity <= 0:
            return
        # Compute current exposure per strategy
        exposure_by_strategy: Dict[str, float] = {name: 0.0 for name in self.target_allocations}
        for sym, pos in self.positions.items():
            price = data_provider.latest_price(sym) or 0.0
            exposure = self.compute_exposure(sym, price, pos['quantity'])
            strat = pos.get('strategy')
            if strat in exposure_by_strategy:
                exposure_by_strategy[strat] += exposure
        # Compute target exposure per strategy
        for strat, weight in self.target_allocations.items():
            target_exposure = equity * weight
            current_exposure = exposure_by_strategy.get(strat, 0.0)
            diff = target_exposure - current_exposure
            # Skip small differences
            if abs(diff) < 0.01 * equity:
                continue
            # Determine trading instrument from strategy name heuristically
            # (Strategies should specify their symbols in config for more accuracy.)
            symbols = [sym for sym, pos in self.positions.items() if pos.get('strategy') == strat]
            # If no existing position, derive symbol from strategy name (e.g. 'sma_strategy' -> 'SMA')
            if not symbols:
                base = strat.split('_')[0]
                symbols = [base.upper()]
            for sym in symbols:
                price = data_provider.latest_price(sym)
                if price is None or price <= 0:
                    continue
                lots = risk_manager.allowed_position_size(price, sym) if risk_manager else 0
                if lots <= 0:
                    continue
                if diff > 0:
                    # Buy to increase exposure
                    trader.buy(sym, lots)
                    risk_manager.register_entry(sym, price, lots)
                    self.update_position(sym, lots, price, strat)
                    diff -= price * lots
                else:
                    # Sell to decrease exposure
                    pos = self.positions.get(sym)
                    if pos:
                        trader.sell(sym, int(pos['quantity']))
                        risk_manager.exit_position(sym)
                        self.remove_position(sym)
                        diff += price * pos['quantity']


__all__ = ["PortfolioManager"]