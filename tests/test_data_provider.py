import time
from pathlib import Path

import pandas as pd

from moex_bot.core.data_provider import DataProvider


class DummySource:
    def __init__(self, price=None, fail=False):
        self.price = price
        self.fail = fail
        self.calls = 0

    def get_last_price(self, symbol: str):
        self.calls += 1
        if self.fail:
            raise RuntimeError("source failure")
        return self.price


def test_stream_preferred_and_cached(tmp_path):
    stream = DummySource(price=105.5)
    rest = DummySource(price=90)
    provider = DataProvider(data_dir=str(tmp_path), stream=stream, rest=rest, cache_ttl=0.5)

    price = provider.get_price("SBER")
    assert price == 105.5
    assert stream.calls == 1
    # Update stream to fail so REST is used while cache fallback remains
    stream.fail = True
    rest.price = 91.0
    price = provider.get_price("SBER")
    assert price == 91.0
    # Disable network and ensure cached value is returned
    provider.disable_network()
    price = provider.get_price("SBER")
    assert price == 91.0


def test_latest_price_reads_history(tmp_path):
    data_dir = Path(tmp_path)
    df = pd.DataFrame({"datetime": ["2024-01-01", "2024-01-02"], "close": [100.0, 102.5]})
    file_path = data_dir / "SBER_hour_90d.csv"
    df.to_csv(file_path, index=False)

    provider = DataProvider(data_dir=str(data_dir))
    price = provider.latest_price("SBER")
    assert price == 102.5

    history = provider.load_history("SBER", interval="hour", days=90)
    assert not history.empty
    assert history.iloc[-1]["close"] == 102.5


def test_invalid_prices_are_discarded(tmp_path):
    stream = DummySource(price=-1)
    rest = DummySource(price=10)
    provider = DataProvider(data_dir=str(tmp_path), stream=stream, rest=rest)

    price = provider.get_price("GAZP")
    assert price == 10
    assert rest.calls == 1
