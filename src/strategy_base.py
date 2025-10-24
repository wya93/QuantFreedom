"""Base strategy interface used by all trading strategies."""
from __future__ import annotations

from typing import Any, Dict, Optional

from .exchange_sim import OrderSide, OrderType


class StrategyBase:
    """Abstract base class for bar-driven strategies."""

    def __init__(self, params: Optional[Dict[str, Any]] = None) -> None:
        self.params = params or {}
        self._context = None

    def set_context(self, context: Any) -> None:
        """Attach the backtester context, giving access to order placement."""
        self._context = context

    # ---- lifecycle hooks -------------------------------------------------
    def on_start(self) -> None:
        """Called once before the first bar is processed."""

    def on_bar(self, bar: Dict[str, Any]) -> None:
        """Called on each bar; subclasses must implement signal logic."""
        raise NotImplementedError

    def on_order(self, order: Any) -> None:
        """Called when a new order is accepted by the exchange simulator."""

    def on_fill(self, fill: Any) -> None:
        """Called when an order is executed."""

    # ---- helper methods --------------------------------------------------
    def _ensure_context(self) -> Any:
        if self._context is None:
            raise RuntimeError("Strategy context is not set")
        return self._context

    def send_order(
        self,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        price: float | None = None,
        stop_price: float | None = None,
    ) -> Any:
        """Send an order via the attached context."""
        ctx = self._ensure_context()
        order = ctx.place_order(side=side, quantity=quantity, order_type=order_type, price=price, stop_price=stop_price)
        self.on_order(order)
        return order

    def buy(self, quantity: float, price: float | None = None) -> Any:
        """Convenience method for market or limit buy order."""
        order_type = OrderType.LIMIT if price is not None else OrderType.MARKET
        return self.send_order(OrderSide.BUY, quantity, order_type, price=price)

    def sell(self, quantity: float, price: float | None = None) -> Any:
        """Convenience method for market or limit sell order."""
        order_type = OrderType.LIMIT if price is not None else OrderType.MARKET
        return self.send_order(OrderSide.SELL, quantity, order_type, price=price)

    def stop_loss(self, quantity: float, stop_price: float, side: OrderSide) -> Any:
        """Submit a stop market order for risk management."""
        return self.send_order(side=side, quantity=quantity, order_type=OrderType.STOP_MARKET, stop_price=stop_price)

    def cancel_all(self) -> None:
        """Cancel all active orders."""
        ctx = self._ensure_context()
        ctx.cancel_all_orders()
