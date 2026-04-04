from __future__ import annotations

import numpy as np
import pytest

from tests.parity.util import (
    assert_close_where_both_defined,
    duckdb_list_to_float_array,
)

talib = pytest.importorskip("talib")
pytest.importorskip("yfinance")


def _load_close_prices(
    symbol: str, *, history_period: str, min_bars: int
) -> np.ndarray:
    import yfinance as yf

    try:
        hist = yf.Ticker(symbol).history(period=history_period, auto_adjust=True)
    except Exception as exc:  # noqa: BLE001 — skip flaky network / API errors
        pytest.skip(f"yfinance could not load {symbol!r}: {exc}")
    if hist.empty or "Close" not in hist.columns:
        pytest.skip(f"no close prices returned for {symbol!r}")
    close = hist["Close"].to_numpy(dtype=np.float64, copy=True)
    close = close[~np.isnan(close)]
    if len(close) < min_bars:
        pytest.skip(
            f"only {len(close)} bars for {symbol!r}; need at least {min_bars} for this case"
        )
    return close


def test_sma_synthetic_matches_python_talib(duckdb_talib, ohlc_df) -> None:
    """Fast parity check without network (unchanged fixture)."""
    close = ohlc_df["close"].to_numpy()
    period = 30
    py = talib.SMA(close, timeperiod=period)
    (db_list,) = duckdb_talib.execute(
        "SELECT ta_sma(?, ?::BIGINT)",
        [close.tolist(), period],
    ).fetchone()
    db_arr = duckdb_list_to_float_array(list(db_list))
    assert_close_where_both_defined(py, db_arr)


@pytest.mark.network
@pytest.mark.parametrize(
    ("symbol", "timeperiod"),
    [
        ("SPY", 10),
        ("SPY", 20),
        ("SPY", 50),
        ("QQQ", 10),
        ("QQQ", 50),
        ("AAPL", 20),
    ],
)
def test_sma_real_ticker_matches_python_talib(
    duckdb_talib,
    symbol: str,
    timeperiod: int,
) -> None:
    """SMA on real daily closes vs DuckDB `ta_sma` (same inputs as `talib.SMA`)."""
    close = _load_close_prices(
        symbol,
        history_period="2y",
        min_bars=timeperiod + 5,
    )
    py = talib.SMA(close, timeperiod=timeperiod)
    (db_list,) = duckdb_talib.execute(
        "SELECT ta_sma(?, ?::BIGINT)",
        [close.tolist(), timeperiod],
    ).fetchone()
    db_arr = duckdb_list_to_float_array(list(db_list))
    assert_close_where_both_defined(py, db_arr)
