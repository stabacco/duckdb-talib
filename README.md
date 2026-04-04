# duckdb-talib

DuckDB extension that registers **TA-Lib** technical analysis functions as SQL scalars. Each TA function `TA_RSI`, `TA_MACD`, … is exposed as `ta_rsi`, `ta_macd`, … (lowercase with a `ta_` prefix).

Functions are implemented with the **TA-Lib abstract API** (`TA_ForEachFunc` / `TA_CallFunc`), so new indicators shipped in TA-Lib are picked up automatically when you bump the `ta-lib` submodule and rebuild.

## Version compatibility

| Piece | Version / constraint |
|--------|----------------------|
| **DuckDB** (sources in `duckdb/` submodule) | Tag **[v1.5.1](https://github.com/duckdb/duckdb/releases/tag/v1.5.1)** — keep this in sync when building the extension |
| **TA-Lib** C library (`ta-lib/` submodule) | **0.6.4** (see `ta-lib/CMakeLists.txt`) |
| **Runtime** | Use a DuckDB **1.5.x** client (CLI, Python `duckdb`, etc.) built for the same platform as the `.duckdb_extension` artifact |
| **Python** (optional; parity tests / tooling only) | **Python ≥ 3.13**, `duckdb>=1.5.1` (see `pyproject.toml`) |

There is no prebuilt community extension in this repo; you compile the loadable extension locally and `LOAD` it by path.

## Install (build the extension)

### Prerequisites

- **Git** with submodule support.
- **CMake** 3.18 or newer (the bundled TA-Lib project requires 3.18; on Windows, TA-Lib may require 3.30 — see `ta-lib/CMakeLists.txt`).
- A **C++17** toolchain (`clang` / `gcc` / MSVC).
- **Make** or **Ninja** (Ninja is typical on macOS via `brew install cmake ninja`).

### 1. Clone and sync submodules

```bash
git clone https://github.com/stabacco/duckdb-talib.git
cd duckdb-talib
git submodule update --init --recursive
```

### 2. Pin the DuckDB submodule

This tree is tested against DuckDB **v1.5.1**:

```bash
cd duckdb && git fetch --tags && git checkout v1.5.1 && cd ..
```

### 3. Compile (release)

From the repository root:

```bash
export PATH="$HOME/.local/bin:$PATH"   # if you use `uv tool install cmake`
make release
```

The loadable artifact is:

`build/release/extension/talib/talib.duckdb_extension`

(Path is the same on macOS and Linux; on Windows the build layout under `build/release` is the same, but you run DuckDB from that environment.)

### 4. Allow loading local extensions

Locally built extensions are not signed. In SQL (or your client config), enable:

```sql
SET allow_unsigned_extensions = true;
```

The Python parity tests use the same setting via `duckdb.connect(config={"allow_unsigned_extensions": "true"})`.

### 5. Load in DuckDB

Use an **absolute** path if a relative path fails (depends on the process working directory):

```sql
LOAD '/absolute/path/to/duckdb-talib/build/release/extension/talib/talib.duckdb_extension';
```

## Usage examples (OHLCV-style data)

Indicators take **ordered series per group** as `LIST(DOUBLE)` (and optional `LIST(INTEGER)` where TA-Lib expects integers). Build lists with `list(column ORDER BY time_column)` and `GROUP BY` the asset key.

Warm-up bars stay in the list but values are **NULL** until TA-Lib’s `outBegIdx` (documented behavior).

### Sample bars table

The following is realistic OHLCV shape: symbol, timestamp, open, high, low, close, volume.

```sql
CREATE TABLE bars AS
SELECT * FROM (VALUES
  ('ACME', DATE '2024-01-02', 100.0,  101.2,  99.4, 100.8, 1200000::BIGINT),
  ('ACME', DATE '2024-01-03', 100.9,  102.5, 100.1, 101.9, 1180000::BIGINT),
  ('ACME', DATE '2024-01-04', 101.8,  103.0, 101.0, 102.4, 1320000::BIGINT),
  ('ACME', DATE '2024-01-05', 102.3,  103.8, 101.6, 102.9, 1280000::BIGINT),
  ('ACME', DATE '2024-01-08', 102.8,  104.1, 102.0, 103.6, 1410000::BIGINT),
  ('ACME', DATE '2024-01-09', 103.5,  104.5, 102.8, 103.9, 1350000::BIGINT),
  ('ACME', DATE '2024-01-10', 103.8,  105.0, 103.1, 104.5, 1390000::BIGINT),
  ('ACME', DATE '2024-01-11', 104.4,  105.6, 103.7, 105.0, 1420000::BIGINT),
  ('ACME', DATE '2024-01-12', 104.9,  106.2, 104.2, 105.7, 1380000::BIGINT),
  ('ACME', DATE '2024-01-16', 105.6,  106.8, 104.9, 106.1, 1450000::BIGINT),
  ('ACME', DATE '2024-01-17', 106.0,  107.0, 105.3, 106.4, 1400000::BIGINT),
  ('ACME', DATE '2024-01-18', 106.3,  107.5, 105.6, 107.0, 1480000::BIGINT),
  ('ACME', DATE '2024-01-19', 106.9,  108.0, 106.2, 107.5, 1520000::BIGINT),
  ('ACME', DATE '2024-01-22', 107.4,  108.5, 106.8, 108.0, 1500000::BIGINT),
  ('ACME', DATE '2024-01-23', 107.9,  109.0, 107.2, 108.4, 1550000::BIGINT),
  ('ACME', DATE '2024-01-24', 108.3,  109.2, 107.5, 108.8, 1490000::BIGINT),
  ('ACME', DATE '2024-01-25', 108.7,  109.8, 108.0, 109.2, 1580000::BIGINT),
  ('ACME', DATE '2024-01-26', 109.1,  110.0, 108.4, 109.6, 1600000::BIGINT),
  ('ACME', DATE '2024-01-29', 109.5,  110.5, 108.9, 110.0, 1620000::BIGINT),
  ('ACME', DATE '2024-01-30', 109.8,  111.0, 109.2, 110.5, 1650000::BIGINT)
) AS t(symbol, ts, open, high, low, close, volume);
```

After `SET allow_unsigned_extensions = true` and `LOAD '…talib.duckdb_extension'`:

### RSI on close (single series)

Optional TA parameters are **required** in SQL in metadata order; use `BIGINT` for integer options and `DOUBLE` for real options.

```sql
SELECT
  symbol,
  ta_rsi(list(close ORDER BY ts), 14::BIGINT) AS rsi
FROM bars
GROUP BY symbol;
```

### ATR from high, low, close (OHLC-style)

Functions that need price groups take one `LIST(DOUBLE)` per required input in **open → high → low → close → volume → open interest** order; omit lists that TA-Lib does not use for that function (ATR uses high, low, close).

```sql
SELECT
  symbol,
  ta_atr(
    list(high ORDER BY ts),
    list(low ORDER BY ts),
    list(close ORDER BY ts),
    14::BIGINT
  ) AS atr
FROM bars
GROUP BY symbol;
```

### MACD (multi-output struct)

Multi-output functions return a `STRUCT` of lists; field names match TA-Lib (e.g. `"outMACD"`, `"outMACDSignal"`, `"outMACDHist"`). Compute the struct once per group (for example with a CTE) so TA-Lib is not invoked twice per row.

```sql
WITH macd_per_symbol AS (
  SELECT
    symbol,
    ta_macd(list(close ORDER BY ts), 12::BIGINT, 26::BIGINT, 9::BIGINT) AS m
  FROM bars
  GROUP BY symbol
)
SELECT
  symbol,
  m."outMACD" AS macd_line,
  m."outMACDSignal" AS signal_line
FROM macd_per_symbol;
```

### Python (`duckdb` package ≥ 1.5.1)

```python
import duckdb

ext = "/absolute/path/to/build/release/extension/talib/talib.duckdb_extension"
con = duckdb.connect(config={"allow_unsigned_extensions": "true"})
con.execute(f"LOAD '{ext}'")
# use con.execute("SELECT ta_rsi(...)")
```

## SQL reference (short)

- **Inputs:** `LIST(DOUBLE)` (and optional `LIST(INTEGER)` / `BIGINT` / `DOUBLE` parameters as required by each function).
- **Grouping:** Always aggregate with `list(col ORDER BY …)` and `GROUP BY` so each group is one time-ordered series.
- **Catalog:** Regenerate after upgrading TA-Lib headers with `python3 scripts/gen_talib_catalog.py` (writes `extension/src/generated/talib_catalog.inc`).

## Build tests (extension maintainers)

```bash
make test_release LINUX_CI_IN_DOCKER=1
```

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
