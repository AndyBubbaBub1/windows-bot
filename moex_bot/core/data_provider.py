from __future__ import annotations
from typing import Optional, Dict

class DataProvider:
    """Market data provider with resilient fallback:
    stream -> REST -> in-memory cache.
    Control network via .enabled flag.
    """
    def __init__(self, stream=None, rest=None):
        self.stream = stream
        self.rest = rest
        self.enabled = True
        self._cache: Dict[str, float] = {}

    def get_price(self, symbol: str) -> Optional[float]:
        if not self.enabled:
            return self._cache.get(symbol)

        if self.stream:
            try:
                px = self.stream.get_last_price(symbol)
                if px:
                    self._cache[symbol] = px
                    return px
            except Exception:
                pass

        if self.rest:
            try:
                px = self.rest.get_last_price(symbol)
                if px:
                    self._cache[symbol] = px
                    return px
            except Exception:
                pass

        return self._cache.get(symbol)
