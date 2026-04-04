from __future__ import annotations

import pytest

from tests.parity.util import (
    assert_close_where_both_defined,
    duckdb_list_to_float_array,
)

talib = pytest.importorskip("talib")


def test_rsi_matches_python_talib(duckdb_talib, ohlc_df) -> None:
    close = ohlc_df["close"].to_numpy()
    period = 14
    py = talib.RSI(close, timeperiod=period)
    (db_list,) = duckdb_talib.execute(
        "SELECT ta_rsi(?, ?::BIGINT)",
        [close.tolist(), period],
    ).fetchone()
    db_arr = duckdb_list_to_float_array(list(db_list))
    assert_close_where_both_defined(py, db_arr)
