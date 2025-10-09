"""Unit tests for the RiskManager class."""

from moex_bot.core.monitoring import risk_limit_breaches_total
from moex_bot.core.risk import RiskManager


def test_daily_loss_limit_triggers_halt() -> None:
    """RiskManager should halt trading when daily loss exceeds threshold."""
    risk_limit_breaches_total._metrics.clear()
    rm = RiskManager(initial_capital=1000.0, max_daily_loss_pct=0.1)
    # Simulate a drop below the daily loss threshold (20% loss)
    rm.update_equity(800.0)
    assert rm.halt_trading is True
    breach = risk_limit_breaches_total.labels(type='max_daily_loss')._value.get()
    assert breach == 1.0


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
    # Update mark price to simulate divergence between instruments
    rm.positions['TEST']['last_price'] = 200.0
    # Allowed size for a second position should be reduced due to exposure
    size2 = rm.allowed_position_size(10.0)
    assert size2 == 0