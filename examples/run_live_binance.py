"""Execute a strategy live on Binance Futures using QuantFreedom components."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.live import BinanceFuturesClient, LiveTradingSession
from src.utils import setup_logger


def load_strategy(path: str):
    module_path = Path(path).resolve()
    if not module_path.exists():
        raise FileNotFoundError(f"Strategy file not found: {module_path}")
    spec = importlib.util.spec_from_file_location(module_path.stem, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Failed to load strategy module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    strategy_cls = getattr(module, "SMACrossStrategy", None)
    if strategy_cls is None:
        raise AttributeError("Strategy module must define SMACrossStrategy class")
    return strategy_cls


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live trading on Binance Futures")
    parser.add_argument("--symbol", default="BTCUSDT", help="Binance futures symbol")
    parser.add_argument("--interval", default="1h", help="Kline interval, e.g. 1h")
    parser.add_argument("--strategy", default="src/strategies/sma_cross.py", help="Path to strategy file")
    parser.add_argument("--params", default="{}", help="JSON string of strategy parameters")
    parser.add_argument("--capital", type=float, default=20.0, help="Virtual capital used for sizing")
    parser.add_argument("--leverage", type=float, default=10.0, help="Maximum leverage to request")
    parser.add_argument("--lookback", type=int, default=None, help="Override kline lookback length")
    parser.add_argument("--testnet", action="store_true", help="Use Binance futures testnet")
    parser.add_argument("--poll", type=int, default=None, help="Run continuously, polling every N seconds")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    params = json.loads(args.params)
    strategy_cls = load_strategy(args.strategy)
    strategy = strategy_cls(params)
    api_key = os.environ.get("BINANCE_API_KEY")
    api_secret = os.environ.get("BINANCE_API_SECRET")
    if not api_key or not api_secret:
        raise EnvironmentError("BINANCE_API_KEY and BINANCE_API_SECRET must be set for live trading")
    base_url = "https://testnet.binancefuture.com" if args.testnet else "https://fapi.binance.com"
    client = BinanceFuturesClient(api_key=api_key, api_secret=api_secret, base_url=base_url)
    session = LiveTradingSession(
        strategy=strategy,
        client=client,
        symbol=args.symbol.upper(),
        interval=args.interval,
        initial_capital=args.capital,
        max_leverage=args.leverage,
        lookback=args.lookback,
    )
    logger = setup_logger("quantfreedom.live")
    if args.poll:
        logger.info("Entering continuous mode with %s second polling interval", args.poll)
        session.run_forever(poll_seconds=args.poll)
    else:
        account = session.run_once()
        logger.info("Live run complete: %s", account)


if __name__ == "__main__":
    main()
