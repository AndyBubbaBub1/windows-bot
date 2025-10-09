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


def test_short_position_allowed_when_enabled() -> None:
    """Risk manager should track short entries when allow_short is True."""
    rm = RiskManager(initial_capital=10000.0, allow_short=True)
    rm.register_entry('SHORT', price=50.0, quantity=-10)
    assert 'SHORT' in rm.positions
    assert rm.positions['SHORT']['quantity'] == -10


def test_short_position_blocked_when_disabled() -> None:
    """Short entries must be ignored when allow_short is False."""
    rm = RiskManager(initial_capital=10000.0, allow_short=False)
    rm.register_entry('SHORT', price=50.0, quantity=-5)
    assert 'SHORT' not in rm.positions


def test_leverage_cap_limits_total_exposure() -> None:
    """Total exposure should respect the configured leverage limit."""
    rm = RiskManager(
        initial_capital=10000.0,
        max_position_pct=1.0,
        per_trade_risk_pct=1.0,
        stop_loss_pct=0.1,
        max_leverage=2.0,
        max_portfolio_exposure_pct=2.0,
    )
    price = 100.0
    size1 = rm.allowed_position_size(price)
    rm.register_entry('LONG1', price, size1)
    size2 = rm.allowed_position_size(price)
    rm.register_entry('LONG2', price, size2)
    # With 2x leverage the gross exposure should not exceed 20k
    assert rm.current_gross_exposure() <= 20000.0 + 1e-6
    size3 = rm.allowed_position_size(price)
    assert size3 == 0