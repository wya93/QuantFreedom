from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.backtester import Backtester
from src.strategy_base import StrategyBase
from src.strategies.sma_cross import SMACrossStrategy


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


class ShortCoverStrategy(StrategyBase):
    """Open a short then cover to verify short accounting."""

    def __init__(self, params=None):
        super().__init__(params)
        self.step = 0

    def on_bar(self, bar):
        if self.step == 0:
            self.sell(1)
        elif self.step == 1:
            self.buy(1)
        self.step += 1


class FlipStrategy(StrategyBase):
    """Flip from long to short in a single order."""

    def __init__(self, params=None):
        super().__init__(params)
        self.step = 0

    def on_bar(self, bar):
        if self.step == 0:
            self.buy(1)
        elif self.step == 1:
            self.sell(2)
        self.step += 1


class LeveragedLongStrategy(StrategyBase):
    """Attempt to enter a leveraged long position on the first bar."""

    def __init__(self, params=None):
        super().__init__(params)
        self.executed = False

    def on_bar(self, bar):
        if self.executed:
            return
        price = bar["close"]
        equity = self._context.portfolio.total_equity(price)
        multiplier = self.params.get("multiplier", 2.0)
        qty = (equity * multiplier) / price
        self.buy(qty)
        self.executed = True


def test_market_order_fill_updates_position():
    data = [
        {"timestamp": 0, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1},
        {"timestamp": 1, "open": 101.0, "high": 102.0, "low": 100.0, "close": 101.0, "volume": 1},
    ]
    bt = Backtester(data=data, strategy_cls=BuyAndHoldStrategy, initial_capital=1000.0, fee_rate=0.0)
    metrics, equity_rows, trades_rows = bt.run()
    assert pytest.approx(bt.portfolio.position_qty, rel=1e-6) == pytest.approx(1000.0 / 100.0)
    assert len(trades_rows) == 1
    assert metrics["final_capital"] == pytest.approx(bt.portfolio.total_equity(101.0))


def test_limit_order_fills_when_price_reached():
    data = [
        {"timestamp": 0, "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0, "volume": 1},
        {"timestamp": 1, "open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0, "volume": 1},
    ]
    bt = Backtester(
        data=data,
        strategy_cls=LimitOrderStrategy,
        strategy_params={"price": 99.0},
        initial_capital=1000.0,
        fee_rate=0.0,
    )
    _, _, trades = bt.run()
    assert len(trades) == 1
    assert trades[0]["price"] <= 99.0


def test_fee_deduction_on_round_trip():
    data = [
        {"timestamp": 0, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1},
        {"timestamp": 1, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1},
        {"timestamp": 2, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1},
    ]
    bt = Backtester(data=data, strategy_cls=RoundTripStrategy, initial_capital=1000.0, fee_rate=0.001)
    _, equity_rows, trades_rows = bt.run()
    total_fees = sum(row["fee"] for row in trades_rows)
    assert total_fees > 0
    final_equity = equity_rows[-1]["equity"]
    assert final_equity <= 1000.0


def test_short_position_generates_positive_pnl_when_price_falls():
    data = [
        {"timestamp": 0, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1},
        {"timestamp": 1, "open": 90.0, "high": 91.0, "low": 89.0, "close": 90.0, "volume": 1},
    ]
    bt = Backtester(data=data, strategy_cls=ShortCoverStrategy, initial_capital=1000.0, fee_rate=0.0)
    metrics, equity_rows, trades_rows = bt.run()
    assert bt.portfolio.position_qty == pytest.approx(0.0)
    assert trades_rows[-1]["realized_pnl"] == pytest.approx(10.0)
    assert trades_rows[-1]["trade_pnl"] == pytest.approx(10.0)
    assert metrics["final_capital"] == pytest.approx(1010.0)


def test_flip_from_long_to_short_records_realized_pnl():
    data = [
        {"timestamp": 0, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1},
        {"timestamp": 1, "open": 110.0, "high": 110.0, "low": 110.0, "close": 110.0, "volume": 1},
    ]
    bt = Backtester(data=data, strategy_cls=FlipStrategy, initial_capital=1000.0, fee_rate=0.0)
    _, _, trades_rows = bt.run()
    assert trades_rows[1]["realized_pnl"] == pytest.approx(10.0)
    assert trades_rows[1]["trade_pnl"] == pytest.approx(10.0)
    assert bt.portfolio.position_qty == pytest.approx(-1.0)
    assert bt.portfolio.avg_entry_price == pytest.approx(110.0)


def test_leverage_allows_larger_notional_when_enabled():
    data = [
        {"timestamp": 0, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1},
    ]
    bt = Backtester(
        data=data,
        strategy_cls=LeveragedLongStrategy,
        initial_capital=1000.0,
        fee_rate=0.0,
        max_leverage=2.0,
    )
    bt.run()
    assert bt.portfolio.position_qty == pytest.approx((1000.0 * 2) / 100.0)


def test_leverage_violation_raises_error():
    data = [
        {"timestamp": 0, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1},
    ]
    bt = Backtester(
        data=data,
        strategy_cls=LeveragedLongStrategy,
        initial_capital=1000.0,
        fee_rate=0.0,
        max_leverage=1.0,
    )
    with pytest.raises(ValueError, match="exceeds max leverage"):
        bt.run()


def test_sma_cross_position_scales_with_leverage():
    data = [
        {"timestamp": 0, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1},
        {"timestamp": 1, "open": 101.0, "high": 101.0, "low": 101.0, "close": 101.0, "volume": 1},
        {"timestamp": 2, "open": 102.0, "high": 102.0, "low": 102.0, "close": 102.0, "volume": 1},
    ]

    def run_with_leverage(leverage: float) -> float:
        bt = Backtester(
            data=data,
            strategy_cls=SMACrossStrategy,
            strategy_params={
                "short_window": 1,
                "long_window": 2,
                "capital_fraction": 0.5,
                "allow_short": False,
            },
            initial_capital=1000.0,
            fee_rate=0.0,
            max_leverage=leverage,
        )
        _, _, trades = bt.run()
        return trades[0]["quantity"]

    qty_low = run_with_leverage(2.0)
    qty_high = run_with_leverage(10.0)

    assert qty_high > qty_low
    expected_ratio = 10.0 / 2.0
    assert qty_high == pytest.approx(qty_low * expected_ratio, rel=1e-6)


def test_sma_cross_warmup_delays_trading_until_history_is_ready():
    data = [
        {"timestamp": i, "open": 100.0 + i, "high": 100.0 + i, "low": 100.0 + i, "close": 100.0 + i, "volume": 1}
        for i in range(6)
    ]

    def first_trade_index(warmup: int) -> int:
        bt = Backtester(
            data=data,
            strategy_cls=SMACrossStrategy,
            strategy_params={
                "short_window": 1,
                "long_window": 2,
                "capital_fraction": 0.5,
                "allow_short": False,
                "warmup_bars": warmup,
            },
            initial_capital=1000.0,
            fee_rate=0.0,
        )
        _, _, trades = bt.run()
        return trades[0]["index"] if trades else -1

    assert first_trade_index(0) == 1
    assert first_trade_index(2) == 3
