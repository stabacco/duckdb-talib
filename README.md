# duckdb-talib

DuckDB extension that registers **TA-Lib** technical analysis functions as SQL scalars. Each TA function `TA_RSI`, `TA_MACD`, … is exposed as `ta_rsi`, `ta_macd`, … (lowercase with a `ta_` prefix).

Functions are implemented with the **TA-Lib abstract API** (`TA_ForEachFunc` / `TA_CallFunc`), so new indicators shipped in TA-Lib are picked up automatically when you bump the `ta-lib` submodule and rebuild.

## Prerequisites

- CMake (3.5+), a C++17 toolchain, and either Make or Ninja.
- Git submodules: `duckdb` (this tree targets tag **v1.4.2**), `extension-ci-tools`, and `ta-lib` (pinned to **v0.6.4** here).

```bash
git submodule update --init --recursive
cd duckdb && git checkout v1.4.2 && cd ..
```

On macOS, install Xcode command-line tools so `clang` is available. Put `cmake` and `ninja` on your `PATH` (for example `brew install cmake ninja`).

## Build

From the repo root:

```bash
export PATH="$HOME/.local/bin:$PATH"   # if you use `uv tool install cmake`
make release
```

The loadable artifact is under `build/release/extension/talib/talib.duckdb_extension` (exact path may vary slightly by platform).

To run SQL logic tests (same harness as other DuckDB extensions):

```bash
make test_release LINUX_CI_IN_DOCKER=1
```

## SQL usage

Indicators consume **ordered series per group** as `LIST(DOUBLE)` (and optional `LIST(INTEGER)` where TA-Lib expects integer inputs). Optional TA parameters are **required** in SQL in metadata order, using `BIGINT` for integer options and `DOUBLE` for real options (match TA-Lib defaults from its docs when you want stock behavior).

Warm-up bars are present in the output list but their values are **SQL NULL** (or NaN treated as NULL) until `outBegIdx` as returned by TA-Lib.

Single-output example:

```sql
LOAD 'build/release/extension/talib/talib.duckdb_extension';

SELECT ta_rsi(
    list(close ORDER BY ts),
    14::BIGINT
)
FROM bars
GROUP BY symbol;
```

Multi-output example (`TA_MACD` returns a `STRUCT` of lists; field names match TA-Lib, e.g. `"outMACD"`):

```sql
SELECT
    (ta_macd(list(close ORDER BY ts), 12::BIGINT, 26::BIGINT, 9::BIGINT))."outMACD" AS macd_line
FROM bars
GROUP BY symbol;
```

Functions that take **price groups** (open/high/low/close/…) require one `LIST(DOUBLE)` per required OHLCVOI component, in **open → high → low → close → volume → open interest** order, skipping components that TA-Lib does not request for that function.

## Codegen

Regenerate the catalog include after upgrading TA-Lib headers:

```bash
python3 scripts/gen_talib_catalog.py
```

This writes `extension/src/generated/talib_catalog.inc` (symbol list from `ta_func.h`).

## Python parity check

With the extension built and dev dependencies installed (`TA-Lib` on PyPI still requires the native TA-Lib library on some platforms):

```bash
uv sync --group dev
export TALIB_DUCKDB_EXTENSION="$(pwd)/build/release/extension/talib/talib.duckdb_extension"
uv run pytest tests/parity -q
```

The pytest suite compares indicators against Python `talib`: parametrized **synthetic** cases (no network) plus **real tickers** via `yfinance` (marked `network`). Use `uv run pytest tests/parity -m "not network"` to skip downloads (for example in CI). Tests are skipped if `TALIB_DUCKDB_EXTENSION` is unset or the file is missing.

**Snapshots (syrupy):** Each test records the Python−DuckDB gap. For synthetic data, `py_minus_db` is **`null` when every comparable bar matches** (no divergence); if any bar differs after rounding, the snapshot stores the full per-bar list (with `null` entries only where a bar is not comparable due to NaN alignment). Real tickers use **`max_abs_diff` / `sum_sq_diff`** so snapshots stay stable as history grows. Files live under [`tests/parity/__snapshots__/`](tests/parity/__snapshots__/). After an intentional extension change, refresh them with:

```bash
uv run pytest tests/parity --snapshot-update
```

A small standalone RSI check is still available:

```bash
uv run python scripts/verify_parity.py
```

## Repository layout

| Path | Role |
|------|------|
| `extension/` | DuckDB extension CMake + `talib_extension.cpp` |
| `duckdb/` | DuckDB sources (submodule) |
| `ta-lib/` | TA-Lib C library (submodule) |
| `extension-ci-tools/` | Shared Make + CI helpers (submodule) |
| `scripts/gen_talib_catalog.py` | Header-driven catalog generator |
| `test/sql/talib.test` | SQLLogicTest smoke tests |
| `tests/parity/` | Pytest parity vs Python `talib` (per-indicator modules) |
| `tests/parity/__snapshots__/` | Syrupy regression snapshots (Python − DuckDB deltas) |
