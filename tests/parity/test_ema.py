from __future__ import annotations

import pytest

from tests.parity.market_data import load_close_prices
from tests.parity.snapshotting import assert_parity_and_match_snapshot
from tests.parity.util import duckdb_list_to_float_array

talib = pytest.importorskip("talib")
pytest.importorskip("yfinance")


@pytest.mark.parametrize("timeperiod", [10, 21, 50, 200])
def test_ema_synthetic_matches_python_talib(
    duckdb_talib, ohlc_df, timeperiod: int, snapshot
) -> None:
    close = ohlc_df["close"].to_numpy()
    if len(close) < timeperiod + 2:
        pytest.skip("fixture too short for this period")
    py = talib.EMA(close, timeperiod=timeperiod)
    (db_list,) = duckdb_talib.execute(
        "SELECT ta_ema(?, ?::BIGINT)",
        [close.tolist(), timeperiod],
    ).fetchone()
    db_arr = duckdb_list_to_float_array(list(db_list))
    assert_parity_and_match_snapshot(snapshot, py, db_arr, mode="full")


@pytest.mark.network
@pytest.mark.parametrize(
    ("symbol", "timeperiod"),
    [
        ("SPY", 10),
        ("SPY", 21),
        ("SPY", 50),
        ("QQQ", 10),
        ("QQQ", 50),
        ("AAPL", 21),
    ],
)
def test_ema_real_ticker_matches_python_talib(
    duckdb_talib,
    symbol: str,
    timeperiod: int,
    snapshot,
) -> None:
    close = load_close_prices(
        symbol,
        history_period="2y",
        min_bars=timeperiod + 5,
    )
    py = talib.EMA(close, timeperiod=timeperiod)
    (db_list,) = duckdb_talib.execute(
        "SELECT ta_ema(?, ?::BIGINT)",
        [close.tolist(), timeperiod],
    ).fetchone()
    db_arr = duckdb_list_to_float_array(list(db_list))
    assert_parity_and_match_snapshot(snapshot, py, db_arr, mode="summary")
