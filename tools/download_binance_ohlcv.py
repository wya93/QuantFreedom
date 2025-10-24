"""Download OHLCV candles from Binance and save them as CSV."""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.utils import ensure_dir, setup_logger  # noqa: E402

BINANCE_API = "https://api.binance.com/api/v3/klines"
MAX_CHUNK = 1000
LOGGER = setup_logger("quantfreedom.data")


def parse_time(value: Optional[str]) -> Optional[int]:
    """Convert CLI time values into Binance millisecond timestamps."""
    if value in (None, ""):
        return None
    value = value.strip()
    if value.isdigit():
        return int(value)
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return int(dt.timestamp() * 1000)


def isoformat_from_ms(epoch_ms: int) -> str:
    """Render Binance epoch milliseconds as ISO8601 (UTC) strings."""
    dt = datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def fetch_chunk(
    symbol: str,
    interval: str,
    start_ms: Optional[int],
    end_ms: Optional[int],
    limit: int,
) -> List[List[object]]:
    params = {"symbol": symbol.upper(), "interval": interval, "limit": min(limit, MAX_CHUNK)}
    if start_ms is not None:
        params["startTime"] = start_ms
    if end_ms is not None:
        params["endTime"] = end_ms
    query = urlencode(params)
    request = Request(f"{BINANCE_API}?{query}")
    try:
        with urlopen(request, timeout=10) as response:
            payload = response.read().decode("utf-8")
    except HTTPError as exc:  # pragma: no cover - network behaviour
        LOGGER.error("HTTP error %s when requesting data: %s", exc.code, exc.reason)
        raise
    except URLError as exc:  # pragma: no cover - network behaviour
        LOGGER.error("Failed to reach Binance: %s", exc.reason)
        raise
    data = json.loads(payload)
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected response: {data}")
    return data


def iter_klines(
    symbol: str,
    interval: str,
    start_ms: Optional[int],
    end_ms: Optional[int],
    limit: Optional[int],
    pause: float,
) -> Iterable[List[object]]:
    """Stream klines from Binance handling pagination and limits."""
    fetched = 0
    cursor = start_ms
    while True:
        remaining = MAX_CHUNK if limit is None else max(0, min(MAX_CHUNK, limit - fetched))
        if limit is not None and remaining == 0:
            break
        chunk = fetch_chunk(symbol, interval, cursor, end_ms, remaining or MAX_CHUNK)
        if not chunk:
            break
        for row in chunk:
            fetched += 1
            yield row
            if limit is not None and fetched >= limit:
                return
        last_open_time = chunk[-1][0]
        cursor = int(last_open_time) + 1
        if end_ms is not None and cursor > end_ms:
            break
        time.sleep(pause)


def write_csv(rows: Iterable[List[object]], path: Path) -> int:
    """Persist klines to CSV with QuantFreedom's expected header order."""
    ensure_dir(path.parent)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        count = 0
        for row in rows:
            writer.writerow(
                [
                    isoformat_from_ms(int(row[0])),
                    row[1],
                    row[2],
                    row[3],
                    row[4],
                    row[5],
                ]
            )
            count += 1
    return count


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Download Binance OHLCV data to CSV")
    parser.add_argument("--symbol", required=True, help="交易对，如 BTCUSDT")
    parser.add_argument("--interval", default="1h", help="K线周期，如 1m、1h、1d")
    parser.add_argument("--start", help="开始时间，ISO8601 或毫秒时间戳")
    parser.add_argument("--end", help="结束时间，ISO8601 或毫秒时间戳")
    parser.add_argument("--limit", type=int, help="下载的最大K线数量")
    parser.add_argument("--pause", type=float, default=0.2, help="分页请求之间的休眠秒数")
    parser.add_argument("--output", required=True, help="输出 CSV 路径")

    args = parser.parse_args(argv)
    start_ms = parse_time(args.start)
    end_ms = parse_time(args.end)

    LOGGER.info(
        "Requesting %s interval %s start=%s end=%s limit=%s", args.symbol, args.interval, args.start, args.end, args.limit
    )

    rows = list(
        iter_klines(
            symbol=args.symbol,
            interval=args.interval,
            start_ms=start_ms,
            end_ms=end_ms,
            limit=args.limit,
            pause=args.pause,
        )
    )
    if not rows:
        LOGGER.warning("No data returned from Binance")
        return
    count = write_csv(rows, Path(args.output))
    LOGGER.info("Saved %s rows to %s", count, args.output)


if __name__ == "__main__":
    main()
