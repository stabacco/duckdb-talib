from __future__ import annotations

from typing import Any, Sequence, cast

import numpy as np
import pandas as pd
import pytest

from tests.parity.market_data import load_ohlcv
from tests.parity.snapshotting import struct_parity_snapshot_payload

talib = pytest.importorskip("talib")
pytest.importorskip("yfinance")

STOCH_FIELDS = ("outSlowK", "outSlowD")


def _run_stoch(
    duckdb_talib,
    high: Sequence[float] | np.ndarray,
    low: Sequence[float] | np.ndarray,
    close: Sequence[float] | np.ndarray,
    fastk_period: int,
    slowk_period: int,
    slowk_matype: int,
    slowd_period: int,
    slowd_matype: int,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    h = np.asarray(high, dtype=np.float64)
    lo = np.asarray(low, dtype=np.float64)
    c = np.asarray(close, dtype=np.float64)
    py_k, py_d = talib.STOCH(
        h,
        lo,
        c,
        fastk_period=fastk_period,
        slowk_period=slowk_period,
        slowk_matype=slowk_matype,
        slowd_period=slowd_period,
        slowd_matype=slowd_matype,
    )
    py_by_field = {"outSlowK": py_k, "outSlowD": py_d}
    (struct_row,) = duckdb_talib.execute(
        "SELECT ta_stoch(?, ?, ?, ?::BIGINT, ?::BIGINT, ?::BIGINT, ?::BIGINT, ?::BIGINT)",
        [
            h.tolist(),
            lo.tolist(),
            c.tolist(),
            fastk_period,
            slowk_period,
            slowk_matype,
            slowd_period,
            slowd_matype,
        ],
    ).fetchone()
    assert struct_row is not None
    for field in STOCH_FIELDS:
        assert field in struct_row, (
            f"missing struct field {field!r}, keys={list(struct_row.keys())}"
        )
    return py_by_field, cast(dict[str, Any], struct_row)


@pytest.mark.parametrize(
    ("fastk_period", "slowk_period", "slowk_matype", "slowd_period", "slowd_matype"),
    [
        (5, 3, 0, 3, 0),
        (14, 3, 0, 3, 0),
        (5, 5, 1, 5, 0),
    ],
)
def test_stoch_synthetic_matches_python_talib(
    duckdb_talib,
    ohlc_df: pd.DataFrame,
    fastk_period: int,
    slowk_period: int,
    slowk_matype: int,
    slowd_period: int,
    slowd_matype: int,
    snapshot,
) -> None:
    high = ohlc_df["high"].to_numpy()
    low = ohlc_df["low"].to_numpy()
    close = ohlc_df["close"].to_numpy()
    min_bars = fastk_period + slowk_period + slowd_period + 20
    if len(close) < min_bars:
        pytest.skip("fixture too short for these STOCH parameters")
    py_by_field, struct_row = _run_stoch(
        duckdb_talib,
        high,
        low,
        close,
        fastk_period,
        slowk_period,
        slowk_matype,
        slowd_period,
        slowd_matype,
    )
    payload = struct_parity_snapshot_payload(
        py_by_field,
        struct_row,
        mode="full",
        fields=STOCH_FIELDS,
    )
    assert payload == snapshot


@pytest.mark.network
@pytest.mark.parametrize(
    ("symbol", "fastk_period", "slowk_period", "slowd_period"),
    [
        ("SPY", 5, 3, 3),
        ("QQQ", 5, 3, 3),
        ("AAPL", 14, 3, 3),
    ],
)
def test_stoch_real_ticker_matches_python_talib(
    duckdb_talib,
    symbol: str,
    fastk_period: int,
    slowk_period: int,
    slowd_period: int,
    snapshot,
) -> None:
    slowk_matype = 0
    slowd_matype = 0
    min_bars = fastk_period + slowk_period + slowd_period + 30
    o = load_ohlcv(
        symbol,
        history_period="2y",
        min_bars=min_bars,
    )
    py_by_field, struct_row = _run_stoch(
        duckdb_talib,
        o["high"],
        o["low"],
        o["close"],
        fastk_period,
        slowk_period,
        slowk_matype,
        slowd_period,
        slowd_matype,
    )
    payload = struct_parity_snapshot_payload(
        py_by_field,
        struct_row,
        mode="summary",
        fields=STOCH_FIELDS,
    )
    assert payload == snapshot
