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
        initial_capital=10_000.0,
        max_position_pct=1.0,
        max_portfolio_exposure_pct=0.2,
        per_trade_risk_pct=1.0,
        stop_loss_pct=0.1,
    )
    first_price = 100.0
    first_size = rm.allowed_position_size(first_price)
    # Enter the first position and fully consume the exposure budget.
    rm.register_entry("FIRST", first_price, first_size)
    assert first_size > 0

    # Exposure is exhausted, so the second instrument should be rejected.
    second_price = 50.0
    second_size = rm.allowed_position_size(second_price)
    assert second_size == 0


def test_allowed_position_size_marks_to_market() -> None:
    """Exposure checks should use the latest price when it is provided."""
    rm = RiskManager(
        initial_capital=10_000.0,
        max_position_pct=1.0,
        max_portfolio_exposure_pct=0.2,
        per_trade_risk_pct=1.0,
        stop_loss_pct=0.1,
    )
    price = 100.0
    size = rm.allowed_position_size(price)
    rm.register_entry("FAST", price, size)
    assert size > 0

    # The position appreciates substantially; mark-to-market should
    # reduce any remaining exposure allowance.
    rm.update_position_price("FAST", 500.0)
    assert rm.allowed_position_size(100.0) == 0

