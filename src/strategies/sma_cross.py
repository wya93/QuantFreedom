"""Simple moving average crossover strategy."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np

from src.strategy_base import StrategyBase


@dataclass
class SMACrossParams:
    """Parameters for the SMA crossover strategy."""

    short_window: int = 50
    long_window: int = 200
    capital_fraction: float = 0.5


class SMACrossStrategy(StrategyBase):
    """Long-only SMA crossover strategy.

    When the short-term moving average crosses above the long-term moving average
    the strategy enters a long position allocating a fraction of capital. A cross
    below exits the entire position.
    """

    def __init__(self, params: Dict | None = None) -> None:
        base_params = SMACrossParams()
        if params:
            base_params.short_window = params.get("short_window", base_params.short_window)
            base_params.long_window = params.get("long_window", base_params.long_window)
            base_params.capital_fraction = params.get("capital_fraction", base_params.capital_fraction)
        super().__init__({
            "short_window": base_params.short_window,
            "long_window": base_params.long_window,
            "capital_fraction": base_params.capital_fraction,
        })
        self.short_window = base_params.short_window
        self.long_window = base_params.long_window
        self.capital_fraction = base_params.capital_fraction
        self.prices: list[float] = []
        self.last_signal: int = 0  # -1 short, 0 flat, 1 long

    def on_bar(self, bar: Dict) -> None:
        price = bar["close"]
        self.prices.append(price)
        if len(self.prices) < self.long_window:
            return
        short_ma = float(np.mean(self.prices[-self.short_window :]))
        long_ma = float(np.mean(self.prices[-self.long_window :]))
        position = self._context.portfolio.exposure()
        equity = self._context.portfolio.total_equity(price)
        target_qty = (equity * self.capital_fraction) / price
        if short_ma > long_ma and self.last_signal <= 0:
            qty = max(target_qty - position, 0)
            if qty > 0:
                self.buy(qty)
            self.last_signal = 1
        elif short_ma < long_ma and (position > 0 or self.last_signal == 1):
            if position > 0:
                self.sell(position)
            self.last_signal = -1

    def on_fill(self, fill) -> None:
        # No additional actions required for this simple strategy.
        pass
