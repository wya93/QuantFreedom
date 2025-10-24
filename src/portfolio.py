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
        """Update cash, position direction and realised PnL for a fill."""
        qty = fill.quantity  # positive for buy fills, negative for sell fills
        cost = qty * fill.price
        self.cash -= cost
        self.cash -= fill.fee

        realized_pnl = 0.0
        prev_qty = self.position_qty
        new_qty = prev_qty + qty

        if prev_qty == 0:
            # Opening a fresh position (long or short)
            self.avg_entry_price = fill.price if new_qty != 0 else 0.0
        elif prev_qty > 0:
            if new_qty >= 0:
                if qty < 0:
                    # Reducing an existing long
                    closed = min(prev_qty, -qty)
                    realized_pnl = (fill.price - self.avg_entry_price) * closed
                    if new_qty == 0:
                        self.avg_entry_price = 0.0
                else:
                    # Adding to a long position
                    total_qty = prev_qty + qty
                    if total_qty != 0:
                        self.avg_entry_price = (
                            self.avg_entry_price * prev_qty + fill.price * qty
                        ) / total_qty
            else:
                # Long flips to short
                closed = prev_qty
                realized_pnl = (fill.price - self.avg_entry_price) * closed
                self.avg_entry_price = fill.price
        else:  # prev_qty < 0 -> currently short
            if new_qty <= 0:
                if qty > 0:
                    # Reducing an existing short
                    closed = min(-prev_qty, qty)
                    realized_pnl = (self.avg_entry_price - fill.price) * closed
                    if new_qty == 0:
                        self.avg_entry_price = 0.0
                else:
                    # Adding to a short position
                    total_qty = abs(prev_qty) + abs(qty)
                    if total_qty != 0:
                        self.avg_entry_price = (
                            self.avg_entry_price * abs(prev_qty)
                            + fill.price * abs(qty)
                        ) / total_qty
            else:
                # Short flips to long
                closed = -prev_qty
                realized_pnl = (self.avg_entry_price - fill.price) * closed
                self.avg_entry_price = fill.price

        self.position_qty = new_qty

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
