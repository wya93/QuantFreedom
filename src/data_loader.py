"""Data loading utilities for historical OHLCV data."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


@dataclass
class MarketDataConfig:
    """Configuration for loading market data."""

    path: Path
    columns: Iterable[str] = ("timestamp", "open", "high", "low", "close", "volume")
    tz: str | None = "UTC"


class CSVDataLoader:
    """Simple CSV loader that returns a sorted DataFrame."""

    def __init__(self, config: MarketDataConfig):
        self.config = config

    def load(self) -> pd.DataFrame:
        """Load OHLCV data from disk and ensure chronological order."""
        df = pd.read_csv(self.config.path, usecols=list(self.config.columns))
        df = df.dropna().copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        if self.config.tz:
            df["timestamp"] = df["timestamp"].dt.tz_convert(self.config.tz)
        df = df.sort_values("timestamp").reset_index(drop=True)
        return df
