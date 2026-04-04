from __future__ import annotations

from typing import Any, Sequence, cast

import numpy as np
import pandas as pd
import pytest

from tests.parity.market_data import load_close_prices
from tests.parity.snapshotting import struct_parity_snapshot_payload

talib = pytest.importorskip("talib")
pytest.importorskip("yfinance")

STOCHRSI_FIELDS = ("outFastK", "outFastD")


def _run_stochrsi(
    duckdb_talib,
    close: Sequence[float] | np.ndarray,
    timeperiod: int,
    fastk_period: int,
    fastd_period: int,
    fastd_matype: int,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    c = np.asarray(close, dtype=np.float64)
    py_k, py_d = talib.STOCHRSI(
        c,
        timeperiod=timeperiod,
        fastk_period=fastk_period,
        fastd_period=fastd_period,
        fastd_matype=fastd_matype,
    )
    py_by_field = {"outFastK": py_k, "outFastD": py_d}
    (struct_row,) = duckdb_talib.execute(
        "SELECT ta_stochrsi(?, ?::BIGINT, ?::BIGINT, ?::BIGINT, ?::BIGINT)",
        [c.tolist(), timeperiod, fastk_period, fastd_period, fastd_matype],
    ).fetchone()
    assert struct_row is not None
    for field in STOCHRSI_FIELDS:
        assert field in struct_row, (
            f"missing struct field {field!r}, keys={list(struct_row.keys())}"
        )
    return py_by_field, cast(dict[str, Any], struct_row)


@pytest.mark.parametrize(
    ("timeperiod", "fastk_period", "fastd_period", "fastd_matype"),
    [
        (14, 5, 3, 0),
        (10, 5, 3, 0),
        (14, 3, 5, 1),
    ],
)
def test_stochrsi_synthetic_matches_python_talib(
    duckdb_talib,
    ohlc_df: pd.DataFrame,
    timeperiod: int,
    fastk_period: int,
    fastd_period: int,
    fastd_matype: int,
    snapshot,
) -> None:
    close = ohlc_df["close"].to_numpy()
    min_bars = timeperiod + fastk_period + fastd_period + 20
    if len(close) < min_bars:
        pytest.skip("fixture too short for these STOCHRSI parameters")
    py_by_field, struct_row = _run_stochrsi(
        duckdb_talib,
        close,
        timeperiod,
        fastk_period,
        fastd_period,
        fastd_matype,
    )
    payload = struct_parity_snapshot_payload(
        py_by_field,
        struct_row,
        mode="full",
        fields=STOCHRSI_FIELDS,
    )
    assert payload == snapshot


@pytest.mark.network
@pytest.mark.parametrize("symbol", ["SPY", "QQQ", "AAPL"])
def test_stochrsi_real_ticker_default_params_matches_python_talib(
    duckdb_talib,
    symbol: str,
    snapshot,
) -> None:
    timeperiod, fastk, fastd, matype = 14, 5, 3, 0
    close_arr = load_close_prices(
        symbol,
        history_period="2y",
        min_bars=timeperiod + fastk + fastd + 20,
    )
    py_by_field, struct_row = _run_stochrsi(
        duckdb_talib,
        close_arr,
        timeperiod,
        fastk,
        fastd,
        matype,
    )
    payload = struct_parity_snapshot_payload(
        py_by_field,
        struct_row,
        mode="summary",
        fields=STOCHRSI_FIELDS,
    )
    assert payload == snapshot


@pytest.mark.network
@pytest.mark.parametrize(
    ("timeperiod", "fastk_period", "fastd_period", "fastd_matype"),
    [
        (14, 5, 3, 0),
        (10, 5, 3, 0),
        (21, 5, 5, 0),
    ],
)
def test_stochrsi_real_ticker_parametrized_matches_python_talib(
    duckdb_talib,
    timeperiod: int,
    fastk_period: int,
    fastd_period: int,
    fastd_matype: int,
    snapshot,
) -> None:
    min_bars = timeperiod + fastk_period + fastd_period + 25
    close_arr = load_close_prices(
        "SPY",
        history_period="5y",
        min_bars=min_bars,
    )
    py_by_field, struct_row = _run_stochrsi(
        duckdb_talib,
        close_arr,
        timeperiod,
        fastk_period,
        fastd_period,
        fastd_matype,
    )
    payload = struct_parity_snapshot_payload(
        py_by_field,
        struct_row,
        mode="summary",
        fields=STOCHRSI_FIELDS,
    )
    assert payload == snapshot
