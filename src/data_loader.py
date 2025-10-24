"""Data loading utilities for historical OHLCV data."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, MutableMapping, Optional, Union

try:  # Python 3.9+
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - fallback for older runtimes
    ZoneInfo = None  # type: ignore


@dataclass
class MarketDataConfig:
    """Configuration for loading market data."""

    path: Path
    columns: Iterable[str] = ("timestamp", "open", "high", "low", "close", "volume")
    tz: Optional[str] = "UTC"


class CSVDataLoader:
    """Simple CSV loader that returns a list of OHLCV bar dictionaries."""

    def __init__(self, config: MarketDataConfig):
        self.config = config

    def _parse_timestamp(self, value: str) -> Union[datetime, str]:
        value = value.strip()
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
        if self.config.tz and ZoneInfo is not None and timestamp.tzinfo is not None:
            try:
                timestamp = timestamp.astimezone(ZoneInfo(self.config.tz))
            except Exception:  # pragma: no cover - optional conversion
                pass
        return timestamp

    def load(self) -> List[MutableMapping[str, object]]:
        """Load OHLCV data from disk and ensure chronological order."""
        bars: List[MutableMapping[str, object]] = []
        with open(self.config.path, "r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            expected = set(self.config.columns)
            missing = expected.difference(reader.fieldnames or [])
            if missing:
                raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
            for row in reader:
                if any(row[col] in ("", None) for col in self.config.columns):
                    continue
                parsed_row: MutableMapping[str, object] = {}
                for col in self.config.columns:
                    value = row[col]
                    if col == "timestamp":
                        parsed_row[col] = self._parse_timestamp(str(value))
                    else:
                        parsed_row[col] = float(value)
                bars.append(parsed_row)
        bars.sort(key=lambda item: str(item["timestamp"]))
        return bars
