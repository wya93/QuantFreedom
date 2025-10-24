"""Core backtesting engine for bar-by-bar simulation."""
from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Type

from .exchange_sim import ExchangeSim, OrderSide, OrderType
from .metrics import compute_metrics
from .portfolio import Portfolio
from .strategy_base import StrategyBase
from .utils import ensure_dir, to_json


class Backtester:
    """Drives the event loop between strategy, exchange simulator and portfolio."""

    def __init__(
        self,
        data: Iterable[Dict[str, Any]],
        strategy_cls: Type[StrategyBase],
        strategy_params: Optional[Dict[str, Any]] = None,
        initial_capital: float = 100_000.0,
        fee_rate: float = 0.0005,
        slippage: float = 0.0,
        slippage_type: str = "bps",
        order_latency: int = 0,
    ) -> None:
        self.data: List[Dict[str, Any]] = [dict(bar) for bar in data]
        self.exchange = ExchangeSim(
            fee_rate=fee_rate,
            slippage=slippage,
            slippage_type=slippage_type,
            order_latency=order_latency,
        )
        self.portfolio = Portfolio(initial_capital=initial_capital)
        self.strategy = strategy_cls(strategy_params or {})
        self.strategy.set_context(self)
        self.current_index = 0

    # ---- context interface exposed to strategies -------------------------
    def place_order(
        self,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ):
        return self.exchange.submit_order(
            side=side,
            quantity=quantity,
            order_type=order_type,
            current_index=self.current_index,
            price=price,
            stop_price=stop_price,
        )

    def cancel_all_orders(self) -> None:
        self.exchange.cancel_all()

    # ---- execution loop ---------------------------------------------------
    def run(self) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Run the backtest and return metrics, equity curve and trade log."""
        self.strategy.on_start()
        for idx, bar in enumerate(self.data):
            self.current_index = idx
            self.strategy.on_bar(bar)
            fills = self.exchange.process_bar(bar, idx)
            for fill in fills:
                self.portfolio.update_on_fill(fill)
                self.strategy.on_fill(fill)
            self.portfolio.record_snapshot(idx, bar["close"], bar.get("timestamp"))
        equity_rows = [asdict(s) for s in self.portfolio.snapshots]
        trades_rows = [asdict(t) for t in self.portfolio.trades]
        metrics = compute_metrics(self.portfolio.snapshots, self.portfolio.trades)
        return metrics, equity_rows, trades_rows

    def save_results(
        self,
        output_dir: Path,
        metrics: Dict[str, Any],
        equity_rows: List[Dict[str, Any]],
        trades_rows: List[Dict[str, Any]],
    ) -> None:
        """Persist backtest outputs to disk."""
        ensure_dir(output_dir)
        self._write_csv(output_dir / "equity_curve.csv", equity_rows)
        self._write_csv(output_dir / "trades.csv", trades_rows)
        to_json(metrics, output_dir / "report.json")

    @staticmethod
    def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            if not rows:
                handle.write("")
                return
            fieldnames = list(rows[0].keys())
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
