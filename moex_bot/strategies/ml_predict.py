"""Machine learning based strategy using gradient boosting.

This strategy uses historical price-based features to train a
GradientBoostingClassifier from scikit‑learn.  The model predicts the
direction of the next return and generates signals accordingly.  The
data is split chronologically into a training and test set to
avoid lookahead bias.  Only simple price features are used here but
additional technical indicators could be incorporated.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .base import BaseStrategy

STRATEGY_NAME = 'ml_predict'

def _build_features(df: pd.DataFrame) -> pd.DataFrame:
    close = df['close']
    returns = close.pct_change()
    feat = pd.DataFrame(index=df.index)
    feat['returns'] = returns
    feat['ma5'] = close.rolling(5).mean()
    feat['ma10'] = close.rolling(10).mean()
    feat['momentum'] = close - close.shift(10)
    feat['volatility'] = returns.rolling(10).std()
    # Forward fill then backfill missing values
    return feat.ffill().bfill()

def strategy(df: pd.DataFrame, train_size: float = 0.7) -> pd.Series:
    """Generate signals using a Gradient Boosting model.

    Args:
        df: DataFrame with at least 'close' column.
        train_size: Fraction of data to use for training (the remainder
            is used for generating signals).  Must be between 0 and 1.

    Returns:
        Series of signals: 1 (predicted up), -1 (predicted down), 0 for no trade.
    """
    if 'close' not in df.columns:
        return pd.Series(0, index=df.index)
    features = _build_features(df)
    # Target: sign of next return
    target = np.sign(df['close'].pct_change().shift(-1)).fillna(0)
    # Align features and target
    X = features
    y = target
    n = len(X)
    split = int(n * train_size)
    if split < 10:
        return pd.Series(0, index=df.index)
    X_train, X_test = X.iloc[:split], X.iloc[split:]
    y_train = y.iloc[:split]
    # Build pipeline with scaling and model
    model = Pipeline([
        ('scaler', StandardScaler()),
        ('gb', GradientBoostingClassifier())
    ])
    try:
        model.fit(X_train, y_train)
    except Exception:
        return pd.Series(0, index=df.index)
    # Predict on test set
    y_pred = model.predict(X_test)
    # Build full signal series, fill training part with 0
    signal = pd.Series(0, index=df.index)
    signal.iloc[split:] = y_pred
    return signal


class MLPredictStrategy(BaseStrategy):
    """Wrapper class for the machine learning predictive strategy.

    This class delegates signal generation to the module‑level
    ``strategy`` function defined above.  It accepts optional
    parameters such as ``window`` and ``model`` to maintain a
    consistent signature with the configuration file, but these
    parameters are not currently used.  In a future revision the
    underlying algorithm could be updated to honour these values (for
    example, selecting different machine learning models).

    Args:
        window: Lookback window used for training/test split.
        model: Name of the sklearn model to use (ignored for now).
    """

    def __init__(self, window: int = 30, model: str = 'RandomForest') -> None:
        # Store parameters for inspection; not used at the moment
        super().__init__(window=window, model=model)
        self.window = window
        self.model = model

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Generate signals by calling the module‑level strategy function."""
        return strategy(df)


__all__ = ['STRATEGY_NAME', 'strategy', 'MLPredictStrategy']