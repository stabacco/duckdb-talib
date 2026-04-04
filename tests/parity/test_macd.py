from __future__ import annotations

from typing import Any, Sequence, cast

import numpy as np
import pytest

from tests.parity.market_data import load_close_prices
from tests.parity.snapshotting import macd_parity_snapshot_payload

talib = pytest.importorskip("talib")
pytest.importorskip("yfinance")

MACD_FIELDS = ("outMACD", "outMACDSignal", "outMACDHist")


def _run_macd(
    duckdb_talib,
    close: Sequence[float] | np.ndarray,
    fastperiod: int,
    slowperiod: int,
    signalperiod: int,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    c = np.asarray(close, dtype=np.float64)
    py_macd, py_signal, py_hist = talib.MACD(
        c,
        fastperiod=fastperiod,
        slowperiod=slowperiod,
        signalperiod=signalperiod,
    )
    py_by_field = {
        "outMACD": py_macd,
        "outMACDSignal": py_signal,
        "outMACDHist": py_hist,
    }
    (struct_row,) = duckdb_talib.execute(
        "SELECT ta_macd(?, ?::BIGINT, ?::BIGINT, ?::BIGINT)",
        [c.tolist(), fastperiod, slowperiod, signalperiod],
    ).fetchone()
    assert struct_row is not None
    for field in MACD_FIELDS:
        assert field in struct_row, (
            f"missing struct field {field!r}, keys={list(struct_row.keys())}"
        )
    return py_by_field, cast(dict[str, Any], struct_row)


@pytest.mark.parametrize(
    ("fastperiod", "slowperiod", "signalperiod"),
    [
        (12, 26, 9),
        (5, 35, 5),
        (8, 17, 9),
    ],
)
def test_macd_synthetic_matches_python_talib(
    duckdb_talib,
    ohlc_df,
    fastperiod: int,
    slowperiod: int,
    signalperiod: int,
    snapshot,
) -> None:
    close = ohlc_df["close"].to_numpy()
    min_bars = slowperiod + signalperiod + 10
    if len(close) < min_bars:
        pytest.skip("fixture too short for these MACD parameters")
    py_by_field, struct_row = _run_macd(
        duckdb_talib,
        close.tolist(),
        fastperiod,
        slowperiod,
        signalperiod,
    )
    payload = macd_parity_snapshot_payload(
        py_by_field,
        struct_row,
        mode="full",
        fields=MACD_FIELDS,
    )
    assert payload == snapshot


@pytest.mark.network
@pytest.mark.parametrize("symbol", ["SPY", "QQQ", "AAPL"])
def test_macd_real_ticker_default_params_matches_python_talib(
    duckdb_talib,
    symbol: str,
    snapshot,
) -> None:
    fast, slow, signal = 12, 26, 9
    close_arr = load_close_prices(
        symbol,
        history_period="2y",
        min_bars=slow + signal + 20,
    )
    py_by_field, struct_row = _run_macd(
        duckdb_talib,
        close_arr.tolist(),
        fast,
        slow,
        signal,
    )
    payload = macd_parity_snapshot_payload(
        py_by_field,
        struct_row,
        mode="summary",
        fields=MACD_FIELDS,
    )
    assert payload == snapshot


@pytest.mark.network
@pytest.mark.parametrize(
    ("fastperiod", "slowperiod", "signalperiod"),
    [
        (12, 26, 9),
        (8, 21, 5),
        (19, 39, 9),
    ],
)
def test_macd_real_ticker_parametrized_matches_python_talib(
    duckdb_talib,
    fastperiod: int,
    slowperiod: int,
    signalperiod: int,
    snapshot,
) -> None:
    """Several MACD settings on one liquid symbol (fewer downloads)."""
    min_bars = slowperiod + signalperiod + 20
    close_arr = load_close_prices(
        "SPY",
        history_period="5y",
        min_bars=min_bars,
    )
    py_by_field, struct_row = _run_macd(
        duckdb_talib,
        close_arr.tolist(),
        fastperiod,
        slowperiod,
        signalperiod,
    )
    payload = macd_parity_snapshot_payload(
        py_by_field,
        struct_row,
        mode="summary",
        fields=MACD_FIELDS,
    )
    assert payload == snapshot
