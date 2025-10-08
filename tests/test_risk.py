"""Unit tests for the RiskManager class.

These tests verify that the risk manager correctly enforces daily loss
limits, position sizing rules and portfolio exposure constraints.
"""

from moex_bot.core.risk import RiskManager


def test_daily_loss_limit_triggers_halt() -> None:
    """RiskManager should halt trading when daily loss exceeds threshold."""
    rm = RiskManager(initial_capital=1000.0, max_daily_loss_pct=0.1)
    # Simulate a drop below the daily loss threshold (20% loss)
    rm.update_equity(800.0)
    assert rm.halt_trading is True


def test_allowed_position_size_respects_portfolio_exposure() -> None:
    """Allowed position size should not exceed portfolio exposure limit."""
    rm = RiskManager(
        initial_capital=10000.0,
        max_position_pct=0.5,
        max_portfolio_exposure_pct=0.5,
        stop_loss_pct=0.1,
    )
    price = 100.0
    size1 = rm.allowed_position_size(price)
    # Enter the first position
    rm.register_entry('TEST', price, size1)
    # Allowed size for a second position should be reduced due to exposure
    size2 = rm.allowed_position_size(price)
    assert size2 <= size1