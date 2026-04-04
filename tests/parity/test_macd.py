from __future__ import annotations

import pytest

from tests.parity.util import (
    assert_close_where_both_defined,
    duckdb_list_to_float_array,
)

talib = pytest.importorskip("talib")

MACD_FIELDS = ("outMACD", "outMACDSignal", "outMACDHist")


def test_macd_matches_python_talib(duckdb_talib, ohlc_df) -> None:
    close = ohlc_df["close"].to_numpy()
    py_macd, py_signal, py_hist = talib.MACD(
        close, fastperiod=12, slowperiod=26, signalperiod=9
    )
    py_by_field = {
        "outMACD": py_macd,
        "outMACDSignal": py_signal,
        "outMACDHist": py_hist,
    }

    (struct_row,) = duckdb_talib.execute(
        "SELECT ta_macd(?, 12::BIGINT, 26::BIGINT, 9::BIGINT)",
        [close.tolist()],
    ).fetchone()

    assert struct_row is not None
    for field in MACD_FIELDS:
        assert field in struct_row, (
            f"missing struct field {field!r}, keys={list(struct_row.keys())}"
        )

    for field in MACD_FIELDS:
        py = py_by_field[field]
        db_arr = duckdb_list_to_float_array(list(struct_row[field]))
        assert_close_where_both_defined(py, db_arr)
