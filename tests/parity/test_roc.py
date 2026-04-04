from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd
import pytest

from tests.parity.market_data import load_close_prices
from tests.parity.snapshotting import assert_parity_and_match_snapshot
from tests.parity.util import duckdb_list_to_float_array

talib = pytest.importorskip("talib")
pytest.importorskip("yfinance")


def _run_roc(
    duckdb_talib,
    close: Sequence[float] | np.ndarray,
    timeperiod: int,
) -> tuple[np.ndarray, np.ndarray]:
    c = np.asarray(close, dtype=np.float64)
    py = talib.ROC(c, timeperiod=timeperiod)
    (db_list,) = duckdb_talib.execute(
        "SELECT ta_roc(?, ?::BIGINT)",
        [c.tolist(), timeperiod],
    ).fetchone()
    db_arr = duckdb_list_to_float_array(list(db_list))
    return py, db_arr


@pytest.mark.parametrize("timeperiod", [5, 10, 14])
def test_roc_synthetic_matches_python_talib(
    duckdb_talib, ohlc_df: pd.DataFrame, timeperiod: int, snapshot
) -> None:
    close = ohlc_df["close"].to_numpy()
    if len(close) < timeperiod + 5:
        pytest.skip("fixture too short for this period")
    py, db_arr = _run_roc(duckdb_talib, close, timeperiod)
    assert_parity_and_match_snapshot(snapshot, py, db_arr, mode="full")


@pytest.mark.network
@pytest.mark.parametrize(
    ("symbol", "timeperiod"),
    [
        ("SPY", 5),
        ("SPY", 10),
        ("QQQ", 10),
        ("AAPL", 14),
    ],
)
def test_roc_real_ticker_matches_python_talib(
    duckdb_talib,
    symbol: str,
    timeperiod: int,
    snapshot,
) -> None:
    close = load_close_prices(
        symbol,
        history_period="2y",
        min_bars=timeperiod + 10,
    )
    py, db_arr = _run_roc(duckdb_talib, close, timeperiod)
    assert_parity_and_match_snapshot(snapshot, py, db_arr, mode="summary")
