#!/usr/bin/env python3
"""
Compare ta_rsi from this extension against the Python `talib` package.

RSI (and MACD, SMA) are also covered by pytest under `tests/parity/`.

Prerequisites:
  - Built loadable extension (see README).
  - `uv sync --group dev` (installs talib + numpy).

Usage:
  TALIB_DUCKDB_EXTENSION=/path/to/talib_loadable_extension.duckdb_extension \\
    uv run python scripts/verify_parity.py
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    ext = os.environ.get("TALIB_DUCKDB_EXTENSION")
    if not ext or not os.path.isfile(ext):
        print(
            "Set TALIB_DUCKDB_EXTENSION to the built .duckdb_extension file.",
            file=sys.stderr,
        )
        return 1

    try:
        import duckdb
        import numpy as np
        import talib
    except ImportError as e:
        print(f"Missing dependency: {e}", file=sys.stderr)
        return 1

    close = np.arange(1, 32, dtype=np.float64)
    period = 14
    py = talib.RSI(close, timeperiod=period)

    con = duckdb.connect(config={"allow_unsigned_extensions": "true"})
    con.execute(f"LOAD '{ext}'")
    (db,) = con.execute(
        "SELECT ta_rsi(?, ?::BIGINT)",
        [close.tolist(), period],
    ).fetchone()
    # DuckDB returns a list aligned to input length; NULL warm-up → NaN for compare
    db_arr = np.array([np.nan if v is None else float(v) for v in db], dtype=np.float64)
    mask = ~np.isnan(py) & ~np.isnan(db_arr)
    if not np.allclose(py[mask], db_arr[mask], rtol=0, atol=1e-9):
        print(
            "Mismatch:\n Python:", py[mask], "\n DuckDB:", db_arr[mask], file=sys.stderr
        )
        return 2
    print("ta_rsi matches Python talib within tolerance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
