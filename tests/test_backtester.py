from __future__ import annotations

import pandas as pd
import pytest

from src.backtester import Backtester
from src.strategy_base import StrategyBase


class BuyAndHoldStrategy(StrategyBase):
    """Buy full allocation on first bar and hold."""

    def __init__(self, params=None):
        super().__init__(params)
        self.executed = False

    def on_bar(self, bar):
        if not self.executed:
            price = bar["close"]
            equity = self._context.portfolio.total_equity(price)
            qty = equity / price
            self.buy(qty)
            self.executed = True


class LimitOrderStrategy(StrategyBase):
    """Place a buy limit order below the market."""

    def __init__(self, params=None):
        super().__init__(params)
        self.price = (params or {}).get("price", 0.0)
        self.sent = False

    def on_bar(self, bar):
        if not self.sent:
            self.buy(quantity=1, price=self.price)
            self.sent = True


class RoundTripStrategy(StrategyBase):
    """Enter and exit to test PnL and fees."""

    def __init__(self, params=None):
        super().__init__(params)
        self.step = 0

    def on_bar(self, bar):
        if self.step == 0:
            self.buy(1)
        elif self.step == 1:
            self.sell(1)
        self.step += 1


def test_market_order_fill_updates_position():
    data = pd.DataFrame(
        [
            {"timestamp": 0, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1},
            {"timestamp": 1, "open": 101.0, "high": 102.0, "low": 100.0, "close": 101.0, "volume": 1},
        ]
    )
    bt = Backtester(data=data, strategy_cls=BuyAndHoldStrategy, initial_capital=1000.0, fee_rate=0.0)
    metrics, equity_df, trades_df = bt.run()
    assert pytest.approx(bt.portfolio.position_qty, rel=1e-6) == pytest.approx(1000.0 / 100.0)
    assert len(trades_df) == 1
    assert metrics["final_capital"] == pytest.approx(bt.portfolio.total_equity(101.0))


def test_limit_order_fills_when_price_reached():
    data = pd.DataFrame(
        [
            {"timestamp": 0, "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0, "volume": 1},
            {"timestamp": 1, "open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0, "volume": 1},
        ]
    )
    bt = Backtester(
        data=data,
        strategy_cls=LimitOrderStrategy,
        strategy_params={"price": 99.0},
        initial_capital=1000.0,
        fee_rate=0.0,
    )
    _, _, trades_df = bt.run()
    assert len(trades_df) == 1
    assert trades_df.iloc[0]["price"] <= 99.0


def test_fee_deduction_on_round_trip():
    data = pd.DataFrame(
        [
            {"timestamp": 0, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1},
            {"timestamp": 1, "open": 101.0, "high": 102.0, "low": 100.0, "close": 101.0, "volume": 1},
            {"timestamp": 2, "open": 102.0, "high": 103.0, "low": 101.0, "close": 102.0, "volume": 1},
        ]
    )
    bt = Backtester(data=data, strategy_cls=RoundTripStrategy, initial_capital=1000.0, fee_rate=0.001)
    _, equity_df, trades_df = bt.run()
    total_fees = trades_df["fee"].sum()
    assert total_fees > 0
    final_equity = equity_df.iloc[-1]["equity"]
    assert final_equity <= 1000.0
