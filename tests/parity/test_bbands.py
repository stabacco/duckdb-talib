from __future__ import annotations

from typing import Any, Sequence, cast

import numpy as np
import pytest

from tests.parity.market_data import load_close_prices
from tests.parity.snapshotting import struct_parity_snapshot_payload

talib = pytest.importorskip("talib")
pytest.importorskip("yfinance")

BBANDS_FIELDS = ("outRealUpperBand", "outRealMiddleBand", "outRealLowerBand")


def _run_bbands(
    duckdb_talib,
    close: Sequence[float] | np.ndarray,
    timeperiod: int,
    nbdevup: float,
    nbdevdn: float,
    matype: int,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    c = np.asarray(close, dtype=np.float64)
    py_u, py_m, py_l = talib.BBANDS(
        c,
        timeperiod=timeperiod,
        nbdevup=nbdevup,
        nbdevdn=nbdevdn,
        matype=matype,
    )
    py_by_field = {
        "outRealUpperBand": py_u,
        "outRealMiddleBand": py_m,
        "outRealLowerBand": py_l,
    }
    (struct_row,) = duckdb_talib.execute(
        "SELECT ta_bbands(?, ?::BIGINT, ?::DOUBLE, ?::DOUBLE, ?::BIGINT)",
        [c.tolist(), timeperiod, nbdevup, nbdevdn, matype],
    ).fetchone()
    assert struct_row is not None
    for field in BBANDS_FIELDS:
        assert field in struct_row, (
            f"missing struct field {field!r}, keys={list(struct_row.keys())}"
        )
    return py_by_field, cast(dict[str, Any], struct_row)


@pytest.mark.parametrize(
    ("timeperiod", "nbdevup", "nbdevdn", "matype"),
    [
        (5, 2.0, 2.0, 0),
        (10, 2.0, 2.0, 0),
        (20, 2.5, 2.5, 0),
    ],
)
def test_bbands_synthetic_matches_python_talib(
    duckdb_talib,
    ohlc_df,
    timeperiod: int,
    nbdevup: float,
    nbdevdn: float,
    matype: int,
    snapshot,
) -> None:
    close = ohlc_df["close"].to_numpy()
    if len(close) < timeperiod + 5:
        pytest.skip("fixture too short for these BBANDS parameters")
    py_by_field, struct_row = _run_bbands(
        duckdb_talib,
        close,
        timeperiod,
        nbdevup,
        nbdevdn,
        matype,
    )
    payload = struct_parity_snapshot_payload(
        py_by_field,
        struct_row,
        mode="full",
        fields=BBANDS_FIELDS,
    )
    assert payload == snapshot


@pytest.mark.network
@pytest.mark.parametrize(
    ("symbol", "timeperiod"),
    [
        ("SPY", 10),
        ("SPY", 20),
        ("QQQ", 20),
        ("AAPL", 20),
    ],
)
def test_bbands_real_ticker_default_dev_matches_python_talib(
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
    py_by_field, struct_row = _run_bbands(
        duckdb_talib,
        close,
        timeperiod,
        2.0,
        2.0,
        0,
    )
    payload = struct_parity_snapshot_payload(
        py_by_field,
        struct_row,
        mode="summary",
        fields=BBANDS_FIELDS,
    )
    assert payload == snapshot
