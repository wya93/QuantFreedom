"""Core backtesting engine for bar-by-bar simulation."""
from __future__ import annotations

import csv
from dataclasses import asdict
from logging import Logger
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Type

from .exchange_sim import ExchangeSim, OrderSide, OrderType
from .metrics import compute_metrics
from .portfolio import Portfolio
from .strategy_base import StrategyBase
from .utils import ensure_dir, setup_logger, to_json


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
        max_leverage: float = 1.0,
        logger: Optional[Logger] = None,
    ) -> None:
        self.data: List[Dict[str, Any]] = [dict(bar) for bar in data]
        self.exchange = ExchangeSim(
            fee_rate=fee_rate,
            slippage=slippage,
            slippage_type=slippage_type,
            order_latency=order_latency,
        )
        self.portfolio = Portfolio(initial_capital=initial_capital, max_leverage=max_leverage)
        self.max_leverage = max_leverage
        self.strategy = strategy_cls(strategy_params or {})
        self.strategy.set_context(self)
        self.current_index = 0
        self.logger: Logger = logger or setup_logger()

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
                trade_record = self.portfolio.update_on_fill(
                    fill,
                    bar_timestamp=bar.get("timestamp"),
                    mark_price=bar.get("close"),
                )
                self.logger.info(
                    "Trade %03d | ts=%s | side=%s | qty=%.6f | price=%.6f | fee=%.6f | "
                    "realized_pnl=%.6f | position=%.6f | cash=%.6f | equity=%.6f",
                    len(self.portfolio.trades),
                    trade_record.timestamp,
                    trade_record.side,
                    trade_record.quantity,
                    trade_record.price,
                    trade_record.fee,
                    trade_record.realized_pnl,
                    trade_record.position_after,
                    trade_record.cash_after,
                    trade_record.equity_after,
                )
                self.strategy.on_fill(fill)
            self.portfolio.record_snapshot(idx, bar["close"], bar.get("timestamp"))
        equity_rows = [asdict(s) for s in self.portfolio.snapshots]
        trades_rows = [asdict(t) for t in self.portfolio.trades]
        metrics = compute_metrics(self.portfolio.snapshots, self.portfolio.trades)
        self._log_trade_summary(trades_rows)
        return metrics, equity_rows, trades_rows

    def _log_trade_summary(self, trades_rows: List[Dict[str, Any]]) -> None:
        """Emit a concise summary of executed trades to the logger."""
        if not trades_rows:
            self.logger.info("No trades executed during backtest.")
            return
        total_trades = len(trades_rows)
        buy_trades = [row for row in trades_rows if row["quantity"] > 0]
        sell_trades = [row for row in trades_rows if row["quantity"] < 0]
        total_volume = sum(abs(row["quantity"]) for row in trades_rows)
        total_realized = sum(row["realized_pnl"] for row in trades_rows)
        total_fees = sum(row["fee"] for row in trades_rows)
        self.logger.info(
            "Trade summary | total=%d | buys=%d | sells=%d | gross_volume=%.6f | "
            "realized_pnl=%.6f | fees=%.6f | net_pnl=%.6f",
            total_trades,
            len(buy_trades),
            len(sell_trades),
            total_volume,
            total_realized,
            total_fees,
            total_realized - total_fees,
        )

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
