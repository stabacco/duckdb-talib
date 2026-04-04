"""Build serializable Python TA-Lib minus DuckDB deltas for snapshot regression tests."""

from __future__ import annotations

from typing import Any, Literal

import numpy as np

from tests.parity.util import (
    assert_close_where_both_defined,
    duckdb_list_to_float_array,
)

Mode = Literal["full", "summary"]


def _as_float64(a: np.ndarray) -> np.ndarray:
    return np.asarray(a, dtype=np.float64)


def py_minus_db_per_bar(
    py: np.ndarray, db_arr: np.ndarray, *, decimals: int = 12
) -> list[float | None]:
    """Per-index (Python − DuckDB); None where either side is NaN (not comparable)."""
    py = _as_float64(py)
    db_arr = _as_float64(db_arr)
    assert py.shape == db_arr.shape
    out: list[float | None] = []
    for i in range(py.size):
        if np.isnan(py[i]) and np.isnan(db_arr[i]):
            out.append(None)
        elif np.isnan(py[i]) or np.isnan(db_arr[i]):
            out.append(None)
        else:
            out.append(round(float(py[i] - db_arr[i]), decimals))
    return out


def py_minus_db_for_snapshot(
    py: np.ndarray, db_arr: np.ndarray, *, decimals: int = 12
) -> list[float | None] | None:
    """Snapshot value for `py_minus_db`: null when parity is exact on every comparable bar.

    If any comparable bar has a non-zero (post-rounding) gap, return the full per-bar
    list so regressions stay debuggable bar-by-bar.
    """
    per_bar = py_minus_db_per_bar(py, db_arr, decimals=decimals)
    comparable = [x for x in per_bar if x is not None]
    if not comparable:
        return None
    if all(x == 0.0 for x in comparable):
        return None
    return per_bar


def py_minus_db_summary(
    py: np.ndarray, db_arr: np.ndarray, *, decimals: int = 12
) -> dict[str, Any]:
    """Stable when parity holds (zeros), even as real ticker series grows in length."""
    py = _as_float64(py)
    db_arr = _as_float64(db_arr)
    mask = ~np.isnan(py) & ~np.isnan(db_arr)
    if not np.any(mask):
        return {"max_abs_diff": None, "sum_sq_diff": None}
    d = (py - db_arr)[mask]
    return {
        "max_abs_diff": round(float(np.max(np.abs(d))), decimals),
        "sum_sq_diff": round(float(np.sum(d * d)), decimals),
    }


def assert_parity_and_match_snapshot(
    snapshot: Any,
    py: np.ndarray,
    db_arr: np.ndarray,
    *,
    mode: Mode,
) -> None:
    assert_close_where_both_defined(py, db_arr)
    if mode == "full":
        payload = {"py_minus_db": py_minus_db_for_snapshot(py, db_arr)}
    else:
        payload = py_minus_db_summary(py, db_arr)
    assert payload == snapshot


def struct_parity_snapshot_payload(
    py_by_field: dict[str, np.ndarray],
    struct_row: dict,
    *,
    mode: Mode,
    fields: tuple[str, ...],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field in fields:
        py = py_by_field[field]
        db_arr = duckdb_list_to_float_array(list(struct_row[field]))
        assert_close_where_both_defined(py, db_arr)
        if mode == "full":
            out[field] = {"py_minus_db": py_minus_db_for_snapshot(py, db_arr)}
        else:
            out[field] = py_minus_db_summary(py, db_arr)
    return out


def macd_parity_snapshot_payload(
    py_by_field: dict[str, np.ndarray],
    struct_row: dict,
    *,
    mode: Mode,
    fields: tuple[str, ...],
) -> dict[str, Any]:
    return struct_parity_snapshot_payload(
        py_by_field, struct_row, mode=mode, fields=fields
    )
