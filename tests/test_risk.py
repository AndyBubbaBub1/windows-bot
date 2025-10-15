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


def test_update_position_price_marks_to_market_exposure() -> None:
    """Exposure calculations should react to mark-to-market price updates."""
    rm = RiskManager(
        initial_capital=1000.0,
        max_portfolio_exposure_pct=0.5,
        max_position_pct=1.0,
        stop_loss_pct=0.1,
    )
    price = 100.0
    size = rm.allowed_position_size(price)
    assert size > 0
    rm.register_entry('AAA', price, size)
    # Large price move should reduce remaining capacity to zero
    rm.update_position_price('AAA', 300.0)
    assert rm.allowed_position_size(price) == 0


def test_evaluate_portfolio_risk_reports_market_values() -> None:
    """Portfolio snapshot should use the latest observed prices."""
    rm = RiskManager(
        initial_capital=2000.0,
        max_portfolio_exposure_pct=0.5,
        max_position_pct=1.0,
        stop_loss_pct=0.1,
    )
    rm.register_entry('BBB', 100.0, 5)
    rm.update_position_price('BBB', 120.0)
    snapshot = rm.evaluate_portfolio_risk()
    assert abs(snapshot['gross_exposure'] - 600.0) < 1e-9
    assert abs(snapshot['allowed_exposure'] - 1000.0) < 1e-9
    assert abs(snapshot['remaining_capacity'] - 400.0) < 1e-9