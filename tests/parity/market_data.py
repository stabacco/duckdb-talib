"""Shared helpers for loading real price series in parity tests."""

from __future__ import annotations

import numpy as np
import pytest


def load_close_prices(symbol: str, *, history_period: str, min_bars: int) -> np.ndarray:
    import yfinance as yf

    try:
        hist = yf.Ticker(symbol).history(period=history_period, auto_adjust=True)
    except Exception as exc:  # noqa: BLE001 — skip flaky network / API errors
        pytest.skip(f"yfinance could not load {symbol!r}: {exc}")
    if hist.empty or "Close" not in hist.columns:
        pytest.skip(f"no close prices returned for {symbol!r}")
    close = hist["Close"].to_numpy(dtype=np.float64, copy=True)
    close = close[~np.isnan(close)]
    if len(close) < min_bars:
        pytest.skip(
            f"only {len(close)} bars for {symbol!r}; need at least {min_bars} for this case"
        )
    return close


def load_ohlcv(
    symbol: str, *, history_period: str, min_bars: int
) -> dict[str, np.ndarray]:
    import yfinance as yf

    try:
        hist = yf.Ticker(symbol).history(period=history_period, auto_adjust=True)
    except Exception as exc:  # noqa: BLE001 — skip flaky network / API errors
        pytest.skip(f"yfinance could not load {symbol!r}: {exc}")
    required = ("High", "Low", "Close", "Volume")
    if hist.empty or any(c not in hist.columns for c in required):
        pytest.skip(f"missing OHLCV columns for {symbol!r}")
    mask = np.ones(len(hist), dtype=bool)
    for col in required:
        mask &= ~hist[col].isna().to_numpy()
    if not np.any(mask):
        pytest.skip(f"no valid OHLCV rows for {symbol!r}")
    hist = hist.loc[mask]
    high = hist["High"].to_numpy(dtype=np.float64, copy=True)
    low = hist["Low"].to_numpy(dtype=np.float64, copy=True)
    close = hist["Close"].to_numpy(dtype=np.float64, copy=True)
    volume = hist["Volume"].to_numpy(dtype=np.float64, copy=True)
    n = len(close)
    if n < min_bars:
        pytest.skip(
            f"only {n} bars for {symbol!r}; need at least {min_bars} for this case"
        )
    return {"high": high, "low": low, "close": close, "volume": volume}
