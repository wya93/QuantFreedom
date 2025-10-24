"""Utility helpers for the QuantFreedom backtesting framework."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from math import sqrt
from pathlib import Path
from statistics import StatisticsError, mean, stdev
from typing import Any, Dict, Iterable, Union


def setup_logger(name: str = "quantfreedom") -> logging.Logger:
    """Create or retrieve a logger with a consistent format.

    Parameters
    ----------
    name: str
        Logger name.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def ensure_dir(path: Union[os.PathLike, str]) -> Path:
    """Create a directory if it does not exist and return its Path object."""
    path_obj = Path(path)
    path_obj.mkdir(parents=True, exist_ok=True)
    return path_obj


def to_bool(value: Any) -> bool:
    """Interpret common truthy/falsey inputs as booleans.

    Parameters
    ----------
    value: Any
        Value to coerce. Strings such as ``"true"``/``"false"`` (case insensitive)
        and integers ``1``/``0`` are handled explicitly. Other objects fall back to
        Python's truthiness rules.
    """

    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off"}:
            return False
        return bool(normalized)
    if isinstance(value, (int, float)):
        return value != 0
    return bool(value)


def to_datetime(value: Any) -> datetime:
    """Parse timestamps from strings or pass through datetime objects."""
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def to_json(data: Dict[str, Any], path: Union[os.PathLike, str]) -> None:
    """Persist a dictionary as a JSON file with UTF-8 encoding."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def annualized_return(total_return: float, periods_per_year: int, num_periods: int) -> float:
    """Compute annualized return given total return and number of periods."""
    if num_periods == 0:
        return 0.0
    return (1 + total_return) ** (periods_per_year / num_periods) - 1


def sharpe_ratio(
    returns: Iterable[float],
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """Calculate the annualized Sharpe ratio from periodic returns."""
    returns = list(returns)
    if len(returns) < 2:
        return 0.0
    adjustment = risk_free_rate / periods_per_year
    excess = [value - adjustment for value in returns]
    try:
        std_dev = stdev(excess)
    except StatisticsError:
        return 0.0
    if std_dev == 0:
        return 0.0
    avg = mean(excess)
    return sqrt(periods_per_year) * avg / std_dev
