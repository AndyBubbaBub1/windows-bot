import pandas as pd

from moex_bot.core.backtester import run_backtest_for_df


def _trend_strategy(df: pd.DataFrame) -> pd.Series:
    sig = pd.Series(0.0, index=df.index)
    sig.iloc[1:] = 1.0
    return sig


def test_commission_and_slippage_reduce_returns() -> None:
    df = pd.DataFrame({
        'close': [100.0, 105.0, 110.0],
        'volume': [10.0, 10.0, 10.0],
    })
    baseline = run_backtest_for_df(
        df,
        {'trend': _trend_strategy},
        start_capital=1000.0,
        leverage=1.0,
        commission_pct=0.0,
        slippage_bps=0.0,
    )
    with_costs = run_backtest_for_df(
        df,
        {'trend': _trend_strategy},
        start_capital=1000.0,
        leverage=1.0,
        commission_pct=0.001,
        slippage_bps=50.0,
    )
    assert with_costs.loc[0, 'pnl_pct'] < baseline.loc[0, 'pnl_pct']


def test_volume_cap_limits_leverage() -> None:
    df = pd.DataFrame({
        'close': [100.0, 102.0, 104.0, 106.0],
        'volume': [1.0, 1.0, 1.0, 1.0],
    })
    baseline = run_backtest_for_df(
        df,
        {'trend': _trend_strategy},
        start_capital=1000.0,
        leverage=5.0,
        max_volume_pct=None,
    )
    capped = run_backtest_for_df(
        df,
        {'trend': _trend_strategy},
        start_capital=1000.0,
        leverage=5.0,
        max_volume_pct=0.5,
    )
    assert capped.loc[0, 'avg_leverage'] <= baseline.loc[0, 'avg_leverage']
