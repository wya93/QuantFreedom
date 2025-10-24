"""Exchange simulator handling order execution with latency, fees and slippage."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, List, Optional


class OrderSide(Enum):
    """Buy or sell indicator."""

    BUY = auto()
    SELL = auto()


class OrderType(Enum):
    """Supported order types."""

    MARKET = auto()
    LIMIT = auto()
    STOP_MARKET = auto()


@dataclass
class Order:
    """Internal representation of an order."""

    id: int
    timestamp: int
    side: OrderSide
    quantity: float
    order_type: OrderType
    price: Optional[float] = None
    stop_price: Optional[float] = None
    status: str = "open"
    activate_at: int = 0


@dataclass
class Fill:
    """Fill report returned to the backtester."""

    order_id: int
    price: float
    quantity: float
    fee: float
    timestamp: int


class ExchangeSim:
    """Simple matching engine supporting market, limit and stop orders."""

    def __init__(
        self,
        fee_rate: float = 0.0005,
        slippage: float = 0.0,
        slippage_type: str = "bps",
        min_order_size: float = 1e-6,
        order_latency: int = 0,
    ) -> None:
        self.fee_rate = fee_rate
        self.slippage = slippage
        self.slippage_type = slippage_type
        self.min_order_size = min_order_size
        self.order_latency = order_latency
        self.orders: Dict[int, Order] = {}
        self.pending_activation: List[Order] = []
        self.next_order_id = 1

    def submit_order(
        self,
        side: OrderSide,
        quantity: float,
        order_type: OrderType,
        current_index: int,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ) -> Order:
        """Create and enqueue a new order."""
        if abs(quantity) < self.min_order_size:
            raise ValueError("Order quantity below minimum size")
        order = Order(
            id=self.next_order_id,
            timestamp=current_index,
            side=side,
            quantity=quantity,
            order_type=order_type,
            price=price,
            stop_price=stop_price,
            activate_at=current_index + self.order_latency,
        )
        self.orders[order.id] = order
        self.pending_activation.append(order)
        self.next_order_id += 1
        return order

    def _apply_slippage(self, price: float, side: OrderSide) -> float:
        """Adjust fill price according to slippage settings."""
        if self.slippage_type == "bps":
            adjustment = price * self.slippage / 10000.0
        else:
            adjustment = self.slippage
        if side == OrderSide.BUY:
            return price + adjustment
        return max(price - adjustment, 0.0)

    def process_bar(self, bar: Dict[str, float], bar_index: int) -> List[Fill]:
        """Attempt to fill active orders based on the current bar data."""
        fills: List[Fill] = []
        activatable = [o for o in self.pending_activation if o.activate_at <= bar_index]
        for order in activatable:
            if order.status != "open":
                continue
            fill_price = self._match_order(order, bar)
            if fill_price is None:
                continue
            fill_price = self._apply_slippage(fill_price, order.side)
            signed_qty = order.quantity if order.side == OrderSide.BUY else -order.quantity
            fee = abs(signed_qty) * fill_price * self.fee_rate
            fill = Fill(
                order_id=order.id,
                price=fill_price,
                quantity=signed_qty,
                fee=fee,
                timestamp=bar_index,
            )
            fills.append(fill)
            order.status = "filled"
        self.pending_activation = [o for o in self.pending_activation if o.status == "open"]
        return fills

    def _match_order(self, order: Order, bar: Dict[str, float]) -> Optional[float]:
        """Return fill price if the order is executable on this bar."""
        o = order
        if o.order_type == OrderType.MARKET:
            return bar["open"]
        if o.order_type == OrderType.LIMIT:
            if o.side == OrderSide.BUY and bar["low"] <= (o.price or 0):
                return min(o.price or bar["open"], bar["open"])
            if o.side == OrderSide.SELL and bar["high"] >= (o.price or 0):
                return max(o.price or bar["open"], bar["open"])
            return None
        if o.order_type == OrderType.STOP_MARKET:
            trigger_price = o.stop_price or o.price
            if trigger_price is None:
                raise ValueError("Stop order requires stop_price")
            if o.side == OrderSide.BUY and bar["high"] >= trigger_price:
                return bar["open"] if bar["open"] >= trigger_price else trigger_price
            if o.side == OrderSide.SELL and bar["low"] <= trigger_price:
                return bar["open"] if bar["open"] <= trigger_price else trigger_price
            return None
        return None

    def cancel_all(self) -> None:
        """Cancel all open orders."""
        for order in self.orders.values():
            if order.status == "open":
                order.status = "cancelled"
        self.pending_activation.clear()
