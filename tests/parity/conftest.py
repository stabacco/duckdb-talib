from __future__ import annotations

import os

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
def duckdb_talib(talib_extension_path: str) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": "true"})
    con.execute(f"LOAD '{talib_extension_path}'")
    return con


@pytest.fixture
def ohlc_df() -> pd.DataFrame:
    """Synthetic monotonic close series; long enough for MACD and SMA warm-up."""
    n = 120
    close = np.arange(1, n + 1, dtype=np.float64)
    return pd.DataFrame({"close": close})
