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
    """Allowed position size should respect portfolio exposure and leverage caps."""
    rm = RiskManager(
        initial_capital=10000.0,
        max_position_pct=0.5,
        max_portfolio_exposure_pct=0.5,
        max_leverage=1.0,
        stop_loss_pct=0.1,
    )
    price = 100.0
    size1 = rm.allowed_position_size(price)
    rm.register_entry('TEST', price, size1)
    size2 = rm.allowed_position_size(price)
    assert size2 <= size1


def test_leverage_allows_additional_capacity() -> None:
    """When leverage is enabled the manager should allow additional exposure."""
    rm = RiskManager(
        initial_capital=10000.0,
        max_position_pct=1.0,
        per_trade_risk_pct=0.1,
        stop_loss_pct=0.05,
        max_leverage=2.0,
    )
    price = 100.0
    size1 = rm.allowed_position_size(price)
    assert size1 > 0
    rm.register_entry('AAA', price, size1)
    # With leverage>1 we should still be able to open another position
    size2 = rm.allowed_position_size(price)
    assert size2 > 0
    rm.register_entry('BBB', price, size2)
    # Now exposure should be capped
    size3 = rm.allowed_position_size(price)
    assert size3 == 0


def test_updates_market_prices_for_exposure() -> None:
    """Position price updates must reduce capacity when exposure hits the cap."""
    rm = RiskManager(
        initial_capital=5000.0,
        max_position_pct=1.0,
        per_trade_risk_pct=0.5,
        stop_loss_pct=0.05,
        max_portfolio_exposure_pct=1.0,
    )
    rm.register_entry('XYZ', price=100.0, quantity=10)
    baseline = rm.allowed_position_size(100.0)
    assert baseline > 0
    # Simulate price rally which should consume the exposure budget
    rm.update_position_price('XYZ', 500.0)
    tightened = rm.allowed_position_size(100.0)
    assert tightened == 0


def test_trailing_stop_stores_last_price() -> None:
    """check_exit should persist the latest price for subsequent risk checks."""
    rm = RiskManager(initial_capital=1000.0, stop_loss_pct=0.1)
    rm.register_entry('AAA', price=100.0, quantity=1)
    # Move price upward to update trailing stop and last price
    rm.check_exit('AAA', 120.0)
    assert rm.positions['AAA']['last_price'] == 120.0
    # Price falls triggering exit; last price should update again before removal
    assert rm.check_exit('AAA', 90.0) is True
    assert rm.positions['AAA']['last_price'] == 90.0

