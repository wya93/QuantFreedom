"""Run a sample backtest using the QuantFreedom framework."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

try:  # Optional dependency for plotting
    import matplotlib.pyplot as plt
except ImportError:  # pragma: no cover - environment dependent
    plt = None

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.backtester import Backtester
from src.data_loader import CSVDataLoader, MarketDataConfig
from src.strategy_base import StrategyBase
from src.utils import ensure_dir, setup_logger


def load_strategy(path: str) -> Type[StrategyBase]:
    """Dynamically load a strategy class from a python file."""
    strategy_path = Path(path)
    if not strategy_path.exists():
        raise FileNotFoundError(f"Strategy file not found: {path}")
    module_name = strategy_path.stem
    spec = importlib.util.spec_from_file_location(module_name, strategy_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load strategy module from {path}")
    module = importlib.util.module_from_spec(spec)
    # Ensure the module is discoverable for decorators relying on sys.modules
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    for attr in module.__dict__.values():
        if isinstance(attr, type) and issubclass(attr, StrategyBase) and attr is not StrategyBase:
            return attr
    raise ValueError("No StrategyBase subclass found in strategy file")


def parse_params(params: Optional[str]) -> Dict[str, Any]:
    if not params:
        return {}
    return json.loads(params)


def plot_equity(
    equity_rows: List[Dict[str, Any]],
    trades_rows: List[Dict[str, Any]],
    output_path: Path,
) -> None:
    """Generate an equity curve plot with buy/sell markers."""
    if plt is None:
        raise RuntimeError("matplotlib is not available to generate plots")
    if not equity_rows:
        return
    x_axis = [row["index"] for row in equity_rows]
    equity_values = [row["equity"] for row in equity_rows]
    price_values = [row.get("price", 0.0) for row in equity_rows]

    fig, ax1 = plt.subplots(figsize=(10, 5))
    ax1.plot(x_axis, equity_values, label="Equity", color="tab:blue")
    ax1.set_xlabel("Bar")
    ax1.set_ylabel("Equity", color="tab:blue")
    ax1.tick_params(axis="y", labelcolor="tab:blue")

    ax2 = ax1.twinx()
    ax2.plot(x_axis, price_values, label="Close", color="tab:gray", alpha=0.4)
    ax2.set_ylabel("Price", color="tab:gray")
    ax2.tick_params(axis="y", labelcolor="tab:gray")

    buys = [row for row in trades_rows if row.get("quantity", 0.0) > 0]
    sells = [row for row in trades_rows if row.get("quantity", 0.0) < 0]
    if buys:
        ax2.scatter(
            [row["index"] for row in buys],
            [row["price"] for row in buys],
            color="green",
            marker="^",
            label="Buy",
        )
    if sells:
        ax2.scatter(
            [row["index"] for row in sells],
            [row["price"] for row in sells],
            color="red",
            marker="v",
            label="Sell",
        )

    fig.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="QuantFreedom backtest runner")
    parser.add_argument("--data", required=True, help="Path to CSV OHLCV data")
    parser.add_argument(
        "--strategy",
        default="src/strategies/sma_cross.py",
        help="Path to strategy python file",
    )
    parser.add_argument("--output", default="outputs", help="Directory to store results")
    parser.add_argument("--initial_capital", type=float, default=100_000.0)
    parser.add_argument("--fee", type=float, default=0.0005, help="Fee rate (fraction)")
    parser.add_argument("--slippage", type=float, default=0.0, help="Slippage in bps")
    parser.add_argument("--params", help="Strategy parameter JSON string", default=None)
    args = parser.parse_args()

    logger = setup_logger()

    data_loader = CSVDataLoader(MarketDataConfig(path=Path(args.data)))
    data = data_loader.load()
    logger.info("Loaded %s bars from %s", len(data), args.data)

    strategy_cls = load_strategy(args.strategy)
    strategy_params = parse_params(args.params)

    backtester = Backtester(
        data=data,
        strategy_cls=strategy_cls,
        strategy_params=strategy_params,
        initial_capital=args.initial_capital,
        fee_rate=args.fee,
        slippage=args.slippage,
    )
    metrics, equity_rows, trades_rows = backtester.run()

    output_dir = ensure_dir(args.output)
    backtester.save_results(output_dir, metrics, equity_rows, trades_rows)
    if plt is not None:
        plot_equity(equity_rows, trades_rows, output_dir / "equity_plot.png")
    else:
        logger.warning("matplotlib not installed; skipping equity plot generation")

    logger.info("Backtest metrics: %s", json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
