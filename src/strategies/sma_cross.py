"""Simple moving average crossover strategy."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from src.strategy_base import StrategyBase
from src.utils import to_bool


@dataclass
class SMACrossParams:
    """Parameters for the SMA crossover strategy."""

    short_window: int = 50
    long_window: int = 200
    capital_fraction: float = 0.5
    allow_short: bool = True
    warmup_bars: int = 0


class SMACrossStrategy(StrategyBase):
    """Bidirectional SMA crossover strategy.

    When the short-term moving average crosses above the long-term moving average
    the strategy enters a long position allocating a fraction of capital. A cross
    below either flips into a short (if ``allow_short`` is True) or exits to flat.
    ``warmup_bars`` can be used to require additional history beyond the long
    window before any trades are placed, which helps stabilise indicators when
    the dataset begins mid-trend.
    """

    def __init__(self, params: Optional[Dict[str, float]] = None) -> None:
        base_params = SMACrossParams()
        if params:
            base_params.short_window = params.get("short_window", base_params.short_window)
            base_params.long_window = params.get("long_window", base_params.long_window)
            base_params.capital_fraction = params.get("capital_fraction", base_params.capital_fraction)
            allow_short_param = params.get("allow_short", base_params.allow_short)
            base_params.allow_short = to_bool(allow_short_param)
            base_params.warmup_bars = params.get("warmup_bars", base_params.warmup_bars)
        super().__init__({
            "short_window": base_params.short_window,
            "long_window": base_params.long_window,
            "capital_fraction": base_params.capital_fraction,
            "allow_short": base_params.allow_short,
            "warmup_bars": base_params.warmup_bars,
        })
        self.short_window = base_params.short_window
        self.long_window = base_params.long_window
        self.capital_fraction = base_params.capital_fraction
        self.allow_short = base_params.allow_short
        self.warmup_bars = max(0, base_params.warmup_bars)
        self.prices: List[float] = []
        self.last_signal: int = 0  # -1 short, 0 flat, 1 long

    def on_bar(self, bar: Dict) -> None:
        price = bar["close"]
        self.prices.append(price)
        if len(self.prices) < self.long_window:
            return
        if len(self.prices) < self.long_window + self.warmup_bars:
            return
        short_slice = self.prices[-self.short_window :]
        long_slice = self.prices[-self.long_window :]
        short_ma = sum(short_slice) / len(short_slice)
        long_ma = sum(long_slice) / len(long_slice)
        position = self._context.portfolio.exposure()
        equity = self._context.portfolio.total_equity(price)
        max_leverage = getattr(self._context, "max_leverage", 1.0)
        max_notional = equity * max_leverage
        desired_notional = equity * self.capital_fraction * max_leverage
        notional = min(desired_notional, max_notional)
        target_qty = notional / price if price != 0 else 0.0

        desired_signal = self.last_signal
        if short_ma > long_ma:
            desired_signal = 1
        elif short_ma < long_ma:
            desired_signal = -1 if self.allow_short else 0

        if desired_signal == self.last_signal:
            return

        desired_position = 0.0
        if desired_signal == 1:
            desired_position = target_qty
        elif desired_signal == -1:
            desired_position = -target_qty

        delta = desired_position - position
        if delta > 0:
            self.buy(delta)
        elif delta < 0:
            self.sell(abs(delta))

        self.last_signal = desired_signal

    def on_fill(self, fill) -> None:
        # No additional actions required for this simple strategy.
        pass
