from typing import List

from moex_bot.core.live_trading import LiveTrader
from moex_bot.core.risk import RiskManager
from moex_bot.core.broker import OrderResult


class DummyTrader:
    def __init__(self):
        self.orders: List[tuple] = []
        self.cancelled = False

    def buy(self, figi: str, lots: int, limit_price=None):
        order_id = f"buy-{len(self.orders)}"
        self.orders.append(("buy", figi, lots, limit_price))
        return OrderResult(order_id=order_id, status="accepted", lots_requested=lots, lots_executed=lots, limit_price=limit_price)

    def sell(self, figi: str, lots: int, limit_price=None):
        order_id = f"sell-{len(self.orders)}"
        self.orders.append(("sell", figi, lots, limit_price))
        return OrderResult(order_id=order_id, status="accepted", lots_requested=lots, lots_executed=lots, limit_price=limit_price)

    def cancel_all_orders(self):
        self.cancelled = True


def test_live_trader_registers_positions():
    trader = DummyTrader()
    risk = RiskManager(initial_capital=100_000, stop_loss_pct=0.05, take_profit_pct=0.1)
    live = LiveTrader(trader=trader, risk_manager=risk, slippage_bps=0)

    order_id = live.buy("SBER", lots=2, limit_price=100.0)
    assert order_id is not None
    assert order_id.order_id.startswith("buy-")
    assert risk.positions["SBER"]["quantity"] == 2
    assert trader.orders[0] == ("buy", "SBER", 2, 100.0)

    result_sell = live.sell("SBER", lots=2, limit_price=101.0)
    assert result_sell is not None
    assert "SBER" not in risk.positions
    assert trader.orders[1] == ("sell", "SBER", 2, 101.0)


def test_live_trader_honours_risk_halt():
    trader = DummyTrader()
    risk = RiskManager(initial_capital=50_000)
    risk.halt_trading = True
    live = LiveTrader(trader=trader, risk_manager=risk)

    assert live.buy("GAZP", lots=1, limit_price=200.0) is None
    assert not trader.orders


def test_live_trader_updates_trailing_exit():
    trader = DummyTrader()
    risk = RiskManager(initial_capital=100_000, stop_loss_pct=0.05, take_profit_pct=0.1)
    live = LiveTrader(trader=trader, risk_manager=risk, slippage_bps=0)

    live.buy("SBER", lots=1, limit_price=100.0)
    # Update price to trigger stop loss
    live.update_price("SBER", current_price=94.0)
    assert any(order[0] == "sell" for order in trader.orders)


def test_cancel_all_propagates():
    trader = DummyTrader()
    risk = RiskManager(initial_capital=10_000)
    live = LiveTrader(trader=trader, risk_manager=risk)

    live.cancel_all()
    assert trader.cancelled is True


def test_live_trader_journal(tmp_path):
    trader = DummyTrader()
    risk = RiskManager(initial_capital=50_000)
    journal_path = tmp_path / "orders.jsonl"
    live = LiveTrader(trader=trader, risk_manager=risk, journal_path=str(journal_path), slippage_bps=0)

    live.buy("SBER", lots=1, limit_price=100.0)
    live.sync_equity(51_000.0)
    live.journal.flush()
    assert journal_path.exists()
    content = journal_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(content) >= 2
