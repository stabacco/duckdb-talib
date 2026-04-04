from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd
import pytest

from tests.parity.market_data import load_ohlcv
from tests.parity.snapshotting import assert_parity_and_match_snapshot
from tests.parity.util import duckdb_list_to_float_array

talib = pytest.importorskip("talib")
pytest.importorskip("yfinance")


def _run_obv(
    duckdb_talib,
    close: Sequence[float] | np.ndarray,
    volume: Sequence[float] | np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    c = np.asarray(close, dtype=np.float64)
    v = np.asarray(volume, dtype=np.float64)
    py = talib.OBV(c, v)
    (db_list,) = duckdb_talib.execute(
        "SELECT ta_obv(?, ?)",
        [c.tolist(), v.tolist()],
    ).fetchone()
    db_arr = duckdb_list_to_float_array(list(db_list))
    return py, db_arr


def test_obv_synthetic_matches_python_talib(
    duckdb_talib, ohlc_df: pd.DataFrame, snapshot
) -> None:
    close = ohlc_df["close"].to_numpy()
    volume = ohlc_df["volume"].to_numpy()
    if len(close) < 10:
        pytest.skip("fixture too short")
    py, db_arr = _run_obv(duckdb_talib, close, volume)
    assert_parity_and_match_snapshot(snapshot, py, db_arr, mode="full")


@pytest.mark.network
@pytest.mark.parametrize("symbol", ["SPY", "QQQ", "AAPL"])
def test_obv_real_ticker_matches_python_talib(
    duckdb_talib,
    symbol: str,
    snapshot,
) -> None:
    o = load_ohlcv(
        symbol,
        history_period="2y",
        min_bars=50,
    )
    py, db_arr = _run_obv(duckdb_talib, o["close"], o["volume"])
    assert_parity_and_match_snapshot(snapshot, py, db_arr, mode="summary")
