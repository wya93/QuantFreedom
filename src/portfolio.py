"""Portfolio and position tracking."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class PortfolioSnapshot:
    """Represents the portfolio value at a specific timestamp index."""

    index: int
    timestamp: str
    price: float
    equity: float
    cash: float
    position: float


@dataclass
class TradeRecord:
    """Stores details about each executed trade."""

    index: int
    side: str
    quantity: float
    price: float
    fee: float
    realized_pnl: float


@dataclass
class Portfolio:
    """Single-asset portfolio model supporting spot/perpetual extensions."""

    initial_capital: float
    cash: float = field(init=False)
    position_qty: float = field(default=0.0, init=False)
    avg_entry_price: float = field(default=0.0, init=False)
    snapshots: List[PortfolioSnapshot] = field(default_factory=list, init=False)
    trades: List[TradeRecord] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.cash = self.initial_capital

    # ---- accounting ------------------------------------------------------
    def update_on_fill(self, fill) -> None:
        """Update cash and positions when a fill is received."""
        qty = fill.quantity
        cost = qty * fill.price
        self.cash -= cost
        self.cash -= fill.fee

        realized_pnl = 0.0
        if qty > 0:
            # Increasing long position
            new_qty = self.position_qty + qty
            if new_qty != 0:
                self.avg_entry_price = (
                    self.avg_entry_price * self.position_qty + fill.price * qty
                ) / new_qty
            self.position_qty = new_qty
        elif qty < 0:
            # Closing existing long position
            closing_qty = min(-qty, self.position_qty)
            realized_pnl = (fill.price - self.avg_entry_price) * closing_qty
            self.position_qty += qty
            if self.position_qty <= 0:
                self.avg_entry_price = 0.0
                self.position_qty = max(self.position_qty, 0.0)

        side = "BUY" if qty > 0 else "SELL"
        self.trades.append(
            TradeRecord(
                index=fill.timestamp,
                side=side,
                quantity=qty,
                price=fill.price,
                fee=fill.fee,
                realized_pnl=realized_pnl,
            )
        )

    def total_equity(self, mark_price: float) -> float:
        """Compute the total portfolio equity."""
        return self.cash + self.position_qty * mark_price

    def record_snapshot(self, index: int, price: float, timestamp: object = None) -> None:
        """Store current equity state for reporting."""
        if hasattr(timestamp, "isoformat"):
            ts = timestamp.isoformat()
        else:
            ts = str(timestamp) if timestamp is not None else str(index)
        snapshot = PortfolioSnapshot(
            index=index,
            timestamp=ts,
            price=price,
            equity=self.total_equity(price),
            cash=self.cash,
            position=self.position_qty,
        )
        self.snapshots.append(snapshot)

    def exposure(self) -> float:
        """Return current position quantity."""
        return self.position_qty
