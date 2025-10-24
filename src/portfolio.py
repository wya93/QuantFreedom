"""Portfolio and position tracking."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


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
    timestamp: str
    order_id: Optional[int]
    side: str
    quantity: float
    price: float
    fee: float
    realized_pnl: float
    trade_pnl: float
    cash_after: float
    position_after: float
    equity_after: float


@dataclass
class Portfolio:
    """Single-asset portfolio model supporting spot/perpetual extensions."""

    initial_capital: float
    max_leverage: float = 1.0
    cash: float = field(init=False)
    position_qty: float = field(default=0.0, init=False)
    avg_entry_price: float = field(default=0.0, init=False)
    snapshots: List[PortfolioSnapshot] = field(default_factory=list, init=False)
    trades: List[TradeRecord] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        if self.max_leverage <= 0:
            raise ValueError("max_leverage must be positive")
        self.cash = self.initial_capital

    # ---- accounting ------------------------------------------------------
    def update_on_fill(self, fill, bar_timestamp: Optional[object] = None, mark_price: Optional[float] = None) -> TradeRecord:
        """Update cash, position direction and realised PnL for a fill.

        Parameters
        ----------
        fill
            Fill event produced by the exchange simulator.
        bar_timestamp: Optional[object]
            Optional timestamp associated with the bar that generated the fill.
        mark_price: Optional[float]
            Price used for valuing open positions immediately after the fill. If
            omitted, the fill price is used as the mark.
        """
        qty = fill.quantity  # positive for buy fills, negative for sell fills
        cost = qty * fill.price
        prev_qty = self.position_qty
        new_qty = prev_qty + qty
        prospective_cash = self.cash - cost - fill.fee
        equity_after = prospective_cash + new_qty * fill.price

        increasing_exposure = abs(new_qty) > abs(prev_qty)
        if increasing_exposure:
            if equity_after <= 0:
                raise ValueError("Trade would reduce equity below zero; adjust leverage or size")
            allowed_notional = equity_after * self.max_leverage
            actual_notional = abs(new_qty) * fill.price
            if actual_notional - allowed_notional > 1e-9:
                raise ValueError(
                    f"Trade exceeds max leverage {self.max_leverage:.2f}x: "
                    f"notional {actual_notional:.6f} > allowed {allowed_notional:.6f}"
                )

        self.cash = prospective_cash

        realized_pnl = 0.0

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
        timestamp_label = (
            bar_timestamp.isoformat()
            if hasattr(bar_timestamp, "isoformat")
            else (str(bar_timestamp) if bar_timestamp is not None else str(fill.timestamp))
        )
        mark = fill.price if mark_price is None else mark_price
        equity_after = self.total_equity(mark)
        trade_pnl = realized_pnl - fill.fee

        record = TradeRecord(
            index=fill.timestamp,
            timestamp=timestamp_label,
            order_id=getattr(fill, "order_id", None),
            side=side,
            quantity=qty,
            price=fill.price,
            fee=fill.fee,
            realized_pnl=realized_pnl,
            trade_pnl=trade_pnl,
            cash_after=self.cash,
            position_after=self.position_qty,
            equity_after=equity_after,
        )
        self.trades.append(record)
        return record

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
