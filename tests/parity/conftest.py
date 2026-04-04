from __future__ import annotations

import os
from typing import Any

import duckdb
import numpy as np
import pandas as pd
import pytest


@pytest.fixture(scope="session")
def talib_extension_path() -> str:
    path = os.environ.get("TALIB_DUCKDB_EXTENSION", "")
    if not path or not os.path.isfile(path):
        pytest.skip(
            "Set TALIB_DUCKDB_EXTENSION to the built .duckdb_extension file "
            "(see README build instructions)."
        )
    return path


@pytest.fixture
def duckdb_talib(talib_extension_path: str) -> Any:
    con = duckdb.connect(  # type: ignore[attr-defined]
        config={"allow_unsigned_extensions": "true"}
    )
    con.execute(f"LOAD '{talib_extension_path}'")
    return con


@pytest.fixture
def ohlc_df() -> pd.DataFrame:
    """Synthetic OHLCV coherent with monotonic close; long enough for EMA(200), MACD, ATR/ADX."""
    n = 260
    close = np.arange(1, n + 1, dtype=np.float64)
    eps = 0.5
    return pd.DataFrame(
        {
            "open": close - 0.25,
            "high": close + eps,
            "low": close - eps,
            "close": close,
            "volume": 1_000_000.0 + np.arange(n, dtype=np.float64) * 100.0,
        }
    )
