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


def _run_mfi(
    duckdb_talib,
    high: Sequence[float] | np.ndarray,
    low: Sequence[float] | np.ndarray,
    close: Sequence[float] | np.ndarray,
    volume: Sequence[float] | np.ndarray,
    timeperiod: int,
) -> tuple[np.ndarray, np.ndarray]:
    h = np.asarray(high, dtype=np.float64)
    lo = np.asarray(low, dtype=np.float64)
    c = np.asarray(close, dtype=np.float64)
    v = np.asarray(volume, dtype=np.float64)
    py = talib.MFI(h, lo, c, v, timeperiod=timeperiod)
    (db_list,) = duckdb_talib.execute(
        "SELECT ta_mfi(?, ?, ?, ?, ?::BIGINT)",
        [h.tolist(), lo.tolist(), c.tolist(), v.tolist(), timeperiod],
    ).fetchone()
    db_arr = duckdb_list_to_float_array(list(db_list))
    return py, db_arr


@pytest.mark.parametrize("timeperiod", [10, 14, 20])
def test_mfi_synthetic_matches_python_talib(
    duckdb_talib, ohlc_df: pd.DataFrame, timeperiod: int, snapshot
) -> None:
    high = ohlc_df["high"].to_numpy()
    low = ohlc_df["low"].to_numpy()
    close = ohlc_df["close"].to_numpy()
    volume = ohlc_df["volume"].to_numpy()
    if len(close) < timeperiod + 5:
        pytest.skip("fixture too short for this period")
    py, db_arr = _run_mfi(duckdb_talib, high, low, close, volume, timeperiod)
    assert_parity_and_match_snapshot(snapshot, py, db_arr, mode="full")


@pytest.mark.network
@pytest.mark.parametrize(
    ("symbol", "timeperiod"),
    [
        ("SPY", 10),
        ("SPY", 14),
        ("QQQ", 14),
        ("AAPL", 14),
    ],
)
def test_mfi_real_ticker_matches_python_talib(
    duckdb_talib,
    symbol: str,
    timeperiod: int,
    snapshot,
) -> None:
    o = load_ohlcv(
        symbol,
        history_period="2y",
        min_bars=timeperiod + 10,
    )
    py, db_arr = _run_mfi(
        duckdb_talib,
        o["high"],
        o["low"],
        o["close"],
        o["volume"],
        timeperiod,
    )
    assert_parity_and_match_snapshot(snapshot, py, db_arr, mode="summary")
