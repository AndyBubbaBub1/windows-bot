"""Base classes for trading strategies.

This module defines abstract base classes that can be used to
implement trading strategies in an object‑oriented fashion.  A
strategy subclass should implement the :meth:`generate_signals`
method, which accepts a pandas DataFrame of price data and returns
a pandas Series of trade signals (-1 for short, 0 for flat, 1 for
long).  Instances of a subclass are callable; calling them is
equivalent to calling :meth:`generate_signals` directly.  This
convention allows both function‑based and class‑based strategies to
be treated uniformly by the backtesting engine.

Example:

.. code-block:: python

    from moex_bot.strategies.base import BaseStrategy
    import pandas as pd

    class SMAStrategy(BaseStrategy):
        def __init__(self, short_window: int = 5, long_window: int = 20) -> None:
            super().__init__(short_window=short_window, long_window=long_window)
            self.short_window = short_window
            self.long_window = long_window

        def generate_signals(self, df: pd.DataFrame) -> pd.Series:
            c = df["close"].astype(float)
            short = c.rolling(self.short_window).mean()
            long = c.rolling(self.long_window).mean()
            sig = (short > long).astype(int) - (short < long).astype(int)
            sig = sig.where(sig != sig.shift(1), 0)
            return sig.fillna(0)

    # usage
    strategy = SMAStrategy(short_window=10, long_window=50)
    signals = strategy(df)

"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict
import pandas as pd


class BaseStrategy(ABC):
    """Abstract base class for trading strategies.

    Subclasses must implement :meth:`generate_signals`.  Any
    parameters required by the strategy should be provided as keyword
    arguments to the constructor.  Subclasses may store these
    parameters for later use.
    """

    def __init__(self, **params: Any) -> None:
        """Initialise the strategy with arbitrary parameters.

        Subclasses should call ``super().__init__(**params)`` to
        preserve the behaviour defined here.  All keyword arguments
        are stored on the instance to make them easily inspectable.
        """
        for k, v in params.items():
            setattr(self, k, v)

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Generate a signal series for the given data.

        The returned series should have the same index as ``df`` and
        contain integer values -1, 0 or 1 indicating a short, flat
        or long position respectively.  Implementations may return
        signals of type float as long as they represent these values.
        """
        raise NotImplementedError

    def __call__(self, df: pd.DataFrame) -> pd.Series:
        """Make the strategy instance callable.

        Calling a strategy instance is equivalent to calling
        :meth:`generate_signals` directly.  This allows the backtest
        engine to treat strategy objects and plain functions in a
        uniform manner.
        """
        return self.generate_signals(df)


__all__ = ["BaseStrategy"]