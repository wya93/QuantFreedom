"""Core backtesting engine for bar-by-bar simulation."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Tuple, Type

import pandas as pd

from .exchange_sim import ExchangeSim, OrderSide, OrderType
from .metrics import compute_metrics
from .portfolio import Portfolio
from .strategy_base import StrategyBase
from .utils import ensure_dir, to_json


class Backtester:
    """Drives the event loop between strategy, exchange simulator and portfolio."""

    def __init__(
        self,
        data: pd.DataFrame,
        strategy_cls: Type[StrategyBase],
        strategy_params: Dict[str, Any] | None = None,
        initial_capital: float = 100_000.0,
        fee_rate: float = 0.0005,
        slippage: float = 0.0,
        slippage_type: str = "bps",
        order_latency: int = 0,
    ) -> None:
        self.data = data.reset_index(drop=True)
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
        price: float | None = None,
        stop_price: float | None = None,
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
    def run(self) -> Tuple[Dict[str, Any], pd.DataFrame, pd.DataFrame]:
        """Run the backtest and return metrics, equity curve and trade log."""
        self.strategy.on_start()
        for idx, bar in self.data.iterrows():
            self.current_index = idx
            bar_dict = bar.to_dict()
            self.strategy.on_bar(bar_dict)
            fills = self.exchange.process_bar(bar_dict, idx)
            for fill in fills:
                self.portfolio.update_on_fill(fill)
                self.strategy.on_fill(fill)
            self.portfolio.record_snapshot(idx, bar_dict["close"], bar_dict.get("timestamp"))
        equity_df = pd.DataFrame([asdict(s) for s in self.portfolio.snapshots])
        trades_df = pd.DataFrame([asdict(t) for t in self.portfolio.trades])
        metrics = compute_metrics(self.portfolio.snapshots, self.portfolio.trades)
        return metrics, equity_df, trades_df

    def save_results(
        self,
        output_dir: Path,
        metrics: Dict[str, Any],
        equity_df: pd.DataFrame,
        trades_df: pd.DataFrame,
    ) -> None:
        """Persist backtest outputs to disk."""
        ensure_dir(output_dir)
        equity_df.to_csv(output_dir / "equity_curve.csv", index=False)
        trades_df.to_csv(output_dir / "trades.csv", index=False)
        to_json(metrics, output_dir / "report.json")
