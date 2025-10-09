from __future__ import annotations
import threading
from typing import Dict, Iterable, Optional, List
try:
    from tinkoff.invest import Client, MarketDataRequest, SubscribeLastPriceRequest, LastPriceInstrument
except Exception:
    Client = None  # allows import without package installed

class TinkoffStreamAdapter:
    """Threaded gRPC stream reader for last prices. Safe for Windows.

    Usage:
        stream = TinkoffStreamAdapter(token, tickers=['SBER','GAZP'])
        stream.start()
        price = stream.get_last_price('SBER')
        stream.stop()
    """
    def __init__(self, token: str, tickers: Iterable[str] | None = None) -> None:
        self.token = token
        self.tickers = [t.upper() for t in (tickers or [])]
        self._prices: Dict[str, float] = {}
        self._lock = threading.RLock()
        self._thr: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._thr and self._thr.is_alive():
            return
        self._stop.clear()
        self._thr = threading.Thread(target=self._run, name="tks-stream", daemon=True)
        self._thr.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thr:
            self._thr.join(timeout=2.0)

    def get_last_price(self, ticker: str) -> Optional[float]:
        with self._lock:
            return self._prices.get(ticker.upper())

    # --- internal ---
    def _run(self) -> None:
        if Client is None:
            return
        try:
            with Client(self.token) as client:
                # resolve tickers -> instruments for subscription
                instruments: List[LastPriceInstrument] = []
                if self.tickers:
                    found = client.instruments.find_instrument(query=" ".join(self.tickers)).instruments
                    by_ticker = {i.ticker.upper(): i for i in found}
                    for t in self.tickers:
                        inst = by_ticker.get(t)
                        if inst:
                            instruments.append(LastPriceInstrument(figi=inst.figi))
                last_price_sub = SubscribeLastPriceRequest(instruments=instruments, subscribe=True)
                mdr = MarketDataRequest(subscribe_last_price_request=last_price_sub)
                with client.market_data_stream.market_data_stream() as stream:
                    stream.send(mdr)
                    for event in stream:
                        if self._stop.is_set():
                            break
                        lp = event.last_price
                        if lp:
                            price = float(lp.price.units + lp.price.nano / 1e9)
                            figi = lp.figi
                            # resolve FIGI -> ticker only once
                            try:
                                inst = client.instruments.get_instrument_by(id_type=1, id=figi).instrument
                                ticker = inst.ticker.upper()
                            except Exception:
                                ticker = None
                            if ticker:
                                with self._lock:
                                    self._prices[ticker] = price
        except Exception:
            # swallow to keep app alive; DataProvider will fallback
            return
