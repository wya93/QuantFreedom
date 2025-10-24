"""Live trading session management."""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.exchange_sim import Fill, OrderSide, OrderType
from src.portfolio import Portfolio
from src.strategy_base import StrategyBase
from src.utils import setup_logger, to_datetime

from .binance_client import BinanceFuturesClient, SymbolFilters


@dataclass
class LiveOrderResult:
    """Summary of a live order submission."""

    order_id: Optional[int]
    status: str
    executed_qty: float
    avg_price: float


class LiveContext:
    """Bridges a strategy with the Binance client for live execution."""

    def __init__(
        self,
        client: BinanceFuturesClient,
        portfolio: Portfolio,
        symbol: str,
        symbol_filters: SymbolFilters,
        logger_name: str = "quantfreedom.live",
    ) -> None:
        self.client = client
        self.portfolio = portfolio
        self.symbol = symbol
        self.symbol_filters = symbol_filters
        self.logger = setup_logger(logger_name)
        self.current_timestamp: Optional[datetime] = None
        self._current_price: Optional[float] = None
        self.trading_enabled = False
        self.max_leverage = portfolio.max_leverage
        self.strategy: Optional[StrategyBase] = None

    def set_timestamp(self, timestamp: Any) -> None:
        self.current_timestamp = to_datetime(timestamp)

    def set_market_price(self, price: float) -> None:
        self._current_price = price

    def place_order(
        self,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ) -> LiveOrderResult:
        if quantity <= 0:
            raise ValueError("Quantity must be positive for live orders")
        if order_type != OrderType.MARKET:
            raise NotImplementedError("Only market orders are supported in live mode")
        price_ref = price or (self.current_price or 0.0)
        rounded_qty = self.symbol_filters.quantize(quantity)
        if rounded_qty <= 0:
            self.logger.warning("Quantity %s fell below step size; skipping order", quantity)
            return LiveOrderResult(order_id=None, status="skipped", executed_qty=0.0, avg_price=price_ref)
        mark_price = price_ref if price_ref > 0 else self.current_price or 0.0
        if mark_price <= 0:
            raise ValueError("Cannot infer reference price for live order")
        if not self.symbol_filters.is_notional_valid(rounded_qty, mark_price):
            self.logger.warning(
                "Order notional below minimum: qty=%s price=%s min_notional=%s",
                rounded_qty,
                mark_price,
                self.symbol_filters.min_notional,
            )
            return LiveOrderResult(order_id=None, status="skipped", executed_qty=0.0, avg_price=mark_price)
        if not self.trading_enabled:
            self.logger.debug("Trading disabled; ignoring order side=%s qty=%s", side, rounded_qty)
            return LiveOrderResult(order_id=None, status="warmup", executed_qty=0.0, avg_price=mark_price)
        side_str = "BUY" if side == OrderSide.BUY else "SELL"
        response = self.client.place_market_order(self.symbol, side_str, rounded_qty)
        executed_qty = float(response.get("executedQty", response.get("origQty", rounded_qty)))
        avg_price = float(response.get("avgPrice") or 0.0)
        if avg_price == 0.0:
            cum_quote = float(response.get("cumQuote", 0.0))
            if executed_qty:
                avg_price = cum_quote / executed_qty
        fee = 0.0
        for fill in response.get("fills", []):
            fee += float(fill.get("commission", 0.0))
        timestamp = int(response.get("updateTime") or response.get("transactTime") or int(time.time() * 1000))
        signed_qty = executed_qty if side == OrderSide.BUY else -executed_qty
        fill = Fill(
            order_id=int(response.get("orderId", 0)),
            price=avg_price,
            quantity=signed_qty,
            fee=fee,
            timestamp=timestamp,
        )
        trade_record = self.portfolio.update_on_fill(fill, self.current_timestamp, mark_price=avg_price)
        self.logger.info(
            "Executed %s %s @ %s qty=%s fee=%s trade_pnl=%s equity=%s",
            self.symbol,
            side_str,
            avg_price,
            executed_qty,
            fee,
            trade_record.trade_pnl,
            trade_record.equity_after,
        )
        if self.strategy is not None:
            self.strategy.on_fill(fill)
        return LiveOrderResult(
            order_id=int(response.get("orderId", 0)),
            status=response.get("status", "FILLED"),
            executed_qty=executed_qty,
            avg_price=avg_price,
        )

    def cancel_all_orders(self) -> None:
        self.client.cancel_all_orders(self.symbol)

    @property
    def current_price(self) -> Optional[float]:
        return self._current_price


class LiveTradingSession:
    """Coordinates historical warm-up and live execution on Binance."""

    def __init__(
        self,
        strategy: StrategyBase,
        client: BinanceFuturesClient,
        symbol: str,
        interval: str = "1h",
        initial_capital: float = 20.0,
        max_leverage: float = 10.0,
        lookback: Optional[int] = None,
    ) -> None:
        self.strategy = strategy
        self.client = client
        self.symbol = symbol
        self.interval = interval
        self.lookback = lookback
        self.portfolio = Portfolio(initial_capital=initial_capital, max_leverage=max_leverage)
        self.logger = setup_logger("quantfreedom.live")
        self.symbol_filters = self.client.get_symbol_filters(symbol)
        self.context = LiveContext(client, self.portfolio, symbol, self.symbol_filters)
        self.context.max_leverage = max_leverage
        self.context.strategy = self.strategy
        self.strategy.set_context(self.context)
        self.strategy.on_start()

    def _determine_lookback(self) -> int:
        long_window = self.strategy.params.get("long_window", 200)
        warmup = self.strategy.params.get("warmup_bars", 0)
        return max(self.lookback or 0, long_window + warmup + 5)

    def sync_account_state(self) -> None:
        balance = self.client.get_account_balance()
        if balance:
            self.portfolio.cash = balance
        position = self.client.get_position_information(self.symbol)
        if position:
            qty = float(position.get("positionAmt", 0.0))
            entry_price = float(position.get("entryPrice", 0.0))
            self.portfolio.position_qty = qty
            self.portfolio.avg_entry_price = entry_price if qty != 0 else 0.0

    def run_once(self) -> Dict[str, Any]:
        self.logger.info("Starting live cycle for %s", self.symbol)
        self.client.set_leverage(self.symbol, self.portfolio.max_leverage)
        self.sync_account_state()
        klines = self.client.fetch_klines(self.symbol, self.interval, limit=self._determine_lookback())
        now = datetime.now(timezone.utc)
        bars: List[Dict[str, Any]] = []
        for entry in klines:
            close_time = datetime.fromtimestamp(entry[6] / 1000.0, tz=timezone.utc)
            if close_time > now:
                continue
            bars.append(
                {
                    "timestamp": datetime.fromtimestamp(entry[0] / 1000.0, tz=timezone.utc),
                    "open": float(entry[1]),
                    "high": float(entry[2]),
                    "low": float(entry[3]),
                    "close": float(entry[4]),
                    "volume": float(entry[5]),
                }
            )
        if len(bars) < 2:
            raise RuntimeError("Insufficient closed candles returned from Binance")
        for bar in bars[:-1]:
            self.context.trading_enabled = False
            self.context.set_timestamp(bar["timestamp"])
            self.context.set_market_price(bar["close"])
            self.strategy.on_bar(bar)
        latest = bars[-1]
        self.context.trading_enabled = True
        self.context.set_timestamp(latest["timestamp"])
        self.context.set_market_price(latest["close"])
        self.strategy.on_bar(latest)
        account = {
            "cash": self.portfolio.cash,
            "position": self.portfolio.position_qty,
            "equity": self.portfolio.total_equity(latest["close"]),
            "last_price": latest["close"],
        }
        self.logger.info("Completed live cycle equity=%s position=%s", account["equity"], account["position"])
        return account

    def run_forever(self, poll_seconds: int = 60) -> None:
        import time

        while True:
            try:
                self.run_once()
            except Exception as exc:  # pragma: no cover - runtime guard
                self.logger.exception("Live trading cycle failed: %s", exc)
            time.sleep(poll_seconds)
