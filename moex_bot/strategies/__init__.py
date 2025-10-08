"""Strategy definitions for backtesting.

Each module in this package implements a trading strategy as a
function ``strategy(df: pandas.DataFrame) -> pandas.Series``.  The
function returns a series of signals where ``1`` denotes a long
position, ``-1`` denotes a short position and ``0`` denotes no
position.  Modules may also define a ``STRATEGY_NAME`` constant to
explicitly name the strategy.

Use :func:`load_all_strategies` to discover and load all available
strategies into a dictionary.
"""

from __future__ import annotations

from importlib import import_module
import pkgutil
from pathlib import Path
from typing import Callable, Dict

def load_all_strategies() -> Dict[str, Callable]:
    """Discover and load all strategy functions.

    Returns:
        A mapping from strategy name to callable.
    """
    strategies: Dict[str, Callable] = {}
    pkg_path = Path(__file__).resolve().parent
    for _, mod_name, ispkg in pkgutil.iter_modules([pkg_path.as_posix()]):
        if ispkg:
            continue
        if mod_name == '__init__':
            continue
        mod = import_module(f'{__name__}.{mod_name}')
        fn = getattr(mod, 'strategy', None)
        if callable(fn):
            name = getattr(mod, 'STRATEGY_NAME', mod_name)
            strategies[name] = fn
    return strategies

__all__ = ['load_all_strategies']