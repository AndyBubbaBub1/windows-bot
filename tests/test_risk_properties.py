"""Property-based tests for risk management."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from moex_bot.core.risk import RiskManager


@given(
    capital=st.floats(min_value=10_000, max_value=1_000_000),
    price=st.floats(min_value=10, max_value=1000),
    stop_loss=st.floats(min_value=0.01, max_value=0.2),
    exposure_limit=st.floats(min_value=0.1, max_value=1.0),
)
@settings(max_examples=25)
def test_portfolio_exposure_never_exceeds_limit(capital: float, price: float, stop_loss: float, exposure_limit: float) -> None:
    rm = RiskManager(
        initial_capital=capital,
        stop_loss_pct=stop_loss,
        max_portfolio_exposure_pct=exposure_limit,
    )
    size = rm.allowed_position_size(price)
    if size <= 0:
        return
    rm.register_entry('AAA', price, size)
    rm.positions['AAA']['last_price'] = price
    rm.update_equity(capital)
    # After registering a position, the exposure should not exceed configured limit
    total_exposure = sum(abs(pos['quantity']) * pos['last_price'] for pos in rm.positions.values())
    assert total_exposure <= rm.portfolio_equity * rm.max_portfolio_exposure_pct + price
