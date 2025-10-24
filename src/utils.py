"""Utility helpers for the QuantFreedom backtesting framework."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import numpy as np


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


def ensure_dir(path: os.PathLike[str] | str) -> Path:
    """Create a directory if it does not exist and return its Path object."""
    path_obj = Path(path)
    path_obj.mkdir(parents=True, exist_ok=True)
    return path_obj


def to_datetime(value: Any) -> datetime:
    """Parse timestamps from strings or pass through datetime objects."""
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def to_json(data: Dict[str, Any], path: os.PathLike[str] | str) -> None:
    """Persist a dictionary as a JSON file with UTF-8 encoding."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def annualized_return(total_return: float, periods_per_year: int, num_periods: int) -> float:
    """Compute annualized return given total return and number of periods."""
    if num_periods == 0:
        return 0.0
    return (1 + total_return) ** (periods_per_year / num_periods) - 1


def sharpe_ratio(returns: np.ndarray, risk_free_rate: float = 0.0, periods_per_year: int = 252) -> float:
    """Calculate the annualized Sharpe ratio from periodic returns."""
    if returns.size == 0:
        return 0.0
    excess = returns - risk_free_rate / periods_per_year
    std = np.std(excess, ddof=1)
    if std == 0:
        return 0.0
    return np.sqrt(periods_per_year) * np.mean(excess) / std
