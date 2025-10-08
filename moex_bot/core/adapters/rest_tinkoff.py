from __future__ import annotations
from typing import Optional
try:
    from tinkoff.invest import Client
except Exception:
    Client = None

class TinkoffRestAdapter:
    """Lightweight REST-ish adapter using sync Client for last price."""
    def __init__(self, token: str) -> None:
        self.token = token

    def get_last_price(self, ticker: str) -> Optional[float]:
        if Client is None:
            return None
        t = ticker.strip().upper()
        try:
            with Client(self.token) as client:
                res = client.instruments.find_instrument(query=t)
                match = next((i for i in res.instruments if i.ticker.upper()==t), None)
                inst = match or (res.instruments[0] if res.instruments else None)
                if not inst:
                    return None
                last = client.market_data.get_last_prices(figi=[inst.figi]).last_prices
                if not last:
                    return None
                p = last[0].price
                return float(p.units + p.nano/1e9)
        except Exception:
            return None
