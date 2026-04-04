from __future__ import annotations

import numpy as np


def duckdb_list_to_float_array(lst: list) -> np.ndarray:
    """Map DuckDB LIST(DOUBLE) (NULL elements) to float64 with NaN for missing."""
    out = np.empty(len(lst), dtype=np.float64)
    for i, v in enumerate(lst):
        if v is None:
            out[i] = np.nan
        else:
            out[i] = float(v)
    return out


def assert_close_where_both_defined(
    py: np.ndarray,
    db_arr: np.ndarray,
    *,
    rtol: float = 0,
    atol: float = 1e-9,
) -> None:
    py = np.asarray(py, dtype=np.float64)
    db_arr = np.asarray(db_arr, dtype=np.float64)
    assert py.shape == db_arr.shape, (py.shape, db_arr.shape)
    mask = ~np.isnan(py) & ~np.isnan(db_arr)
    assert np.any(mask), (
        "no overlapping defined values between Python TA-Lib and DuckDB"
    )
    assert np.allclose(py[mask], db_arr[mask], rtol=rtol, atol=atol), (
        f"py[mask]={py[mask]}\ndb[mask]={db_arr[mask]}"
    )
