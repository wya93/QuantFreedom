from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.live.binance_client import SymbolFilters
from src.live.session import LiveTradingSession
from src.strategies.sma_cross import SMACrossStrategy


class FakeBinanceClient:
    def __init__(self) -> None:
        self.leverage = None
        self.orders = []

    def get_symbol_filters(self, symbol: str) -> SymbolFilters:
        return SymbolFilters(min_qty=0.001, step_size=0.001, min_notional=1.0)

    def set_leverage(self, symbol: str, leverage: int) -> None:
        self.leverage = leverage

    def get_account_balance(self) -> float:
        return 20.0

    def get_position_information(self, symbol: str) -> dict:
        return {"symbol": symbol, "positionAmt": "0", "entryPrice": "0"}

    def fetch_klines(self, symbol: str, interval: str, limit: int = 500):
        base = datetime.now(timezone.utc) - timedelta(hours=3)
        bars = []
        prices = [100.0, 99.0, 105.0]
        for idx, price in enumerate(prices):
            open_time = base + timedelta(hours=idx)
            close_time = open_time + timedelta(hours=1)
            bars.append(
                [
                    int(open_time.timestamp() * 1000),
                    str(price),
                    str(price + 1),
                    str(price - 1),
                    str(price),
                    "10",
                    int(close_time.timestamp() * 1000),
                    "100",
                    10,
                    "5",
                    "500",
                    "0",
                ]
            )
        return bars

    def place_market_order(self, symbol: str, side: str, quantity: float, reduce_only: bool = False):
        self.orders.append({"symbol": symbol, "side": side, "quantity": quantity})
        return {
            "orderId": 1,
            "executedQty": str(quantity),
            "avgPrice": "105.0",
            "status": "FILLED",
            "updateTime": 1,
            "fills": [
                {"price": "105.0", "qty": str(quantity), "commission": "0.1"},
            ],
        }

    def cancel_all_orders(self, symbol: str) -> None:  # pragma: no cover - not used in test
        self.orders.clear()


class PassiveClient(FakeBinanceClient):
    def __init__(self) -> None:
        super().__init__()

    def fetch_klines(self, symbol: str, interval: str, limit: int = 500):
        base = datetime.now(timezone.utc) - timedelta(hours=3)
        prices = [10.0, 10.0, 10.0]
        bars = []
        for idx, price in enumerate(prices):
            open_time = base + timedelta(hours=idx)
            close_time = open_time + timedelta(hours=1)
            bars.append(
                [
                    int(open_time.timestamp() * 1000),
                    str(price),
                    str(price),
                    str(price),
                    str(price),
                    "10",
                    int(close_time.timestamp() * 1000),
                    "100",
                    10,
                    "5",
                    "500",
                    "0",
                ]
            )
        return bars

    def place_market_order(self, symbol: str, side: str, quantity: float, reduce_only: bool = False):
        raise AssertionError("No live orders expected when notional below minimum")


def test_live_session_places_order_when_signal_changes():
    client = FakeBinanceClient()
    strategy = SMACrossStrategy({"short_window": 1, "long_window": 2, "capital_fraction": 1.0})
    session = LiveTradingSession(
        strategy=strategy,
        client=client,
        symbol="BTCUSDT",
        interval="1h",
        initial_capital=20.0,
        max_leverage=10.0,
    )
    summary = session.run_once()
    assert client.leverage == 10
    assert client.orders
    order = client.orders[0]
    assert order["side"] == "BUY"
    assert summary["position"] > 0
    assert summary["equity"] > 0


def test_live_session_skips_orders_below_min_notional():
    client = PassiveClient()
    # Raise min notional so that computed quantity becomes too small.
    client.get_symbol_filters = lambda symbol: SymbolFilters(min_qty=0.001, step_size=0.001, min_notional=1000.0)
    strategy = SMACrossStrategy({"short_window": 1, "long_window": 2, "capital_fraction": 0.01})
    session = LiveTradingSession(
        strategy=strategy,
        client=client,
        symbol="BTCUSDT",
        interval="1h",
        initial_capital=20.0,
        max_leverage=10.0,
    )
    summary = session.run_once()
    assert not client.orders
    assert summary["position"] == 0
