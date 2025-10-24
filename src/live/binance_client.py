"""Thin Binance Futures REST client for live trading."""
from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

try:  # pragma: no cover - optional dependency for tests
    import requests
except ModuleNotFoundError:  # pragma: no cover
    requests = None  # type: ignore


@dataclass
class SymbolFilters:
    """Lot sizing and notional constraints for a Binance futures symbol."""

    min_qty: float
    step_size: float
    min_notional: float

    def quantize(self, quantity: float) -> float:
        """Round a quantity down to the nearest valid lot size."""
        if quantity <= 0:
            return 0.0
        step = Decimal(str(self.step_size))
        qty = Decimal(str(quantity))
        quantized = (qty / step).to_integral_value(rounding=ROUND_DOWN) * step
        if float(quantized) < self.min_qty:
            return 0.0
        return float(quantized)

    def is_notional_valid(self, quantity: float, price: float) -> bool:
        """Return True if the order notional meets the minimum requirement."""
        return abs(quantity) * price >= self.min_notional


class BinanceFuturesClient:
    """Minimal REST client for Binance USDT-margined futures."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str | None = None,
        session: Optional["requests.Session"] = None,
        recv_window: int = 5000,
    ) -> None:
        if requests is None:
            raise RuntimeError("requests package is required for live trading; install it via pip")
        self.api_key = api_key
        self.api_secret = api_secret.encode("utf-8")
        self.base_url = base_url or "https://fapi.binance.com"
        self.recv_window = recv_window
        self.session = session or requests.Session()

    # ------------------------------------------------------------------
    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = False,
    ) -> Any:
        params = params.copy() if params else {}
        headers = {"X-MBX-APIKEY": self.api_key}
        if signed:
            params.setdefault("recvWindow", self.recv_window)
            params["timestamp"] = int(time.time() * 1000)
            query = urlencode(params, doseq=True)
            signature = hmac.new(self.api_secret, query.encode("utf-8"), hashlib.sha256).hexdigest()
            params["signature"] = signature
        url = f"{self.base_url}{path}"
        response = self.session.request(method, url, params=params, timeout=15, headers=headers)
        response.raise_for_status()
        return response.json()

    # ------------------------------------------------------------------
    def fetch_klines(self, symbol: str, interval: str, limit: int = 500) -> List[List[Any]]:
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        return self._request("GET", "/fapi/v1/klines", params)

    def get_symbol_filters(self, symbol: str) -> SymbolFilters:
        data = self._request("GET", "/fapi/v1/exchangeInfo", {"symbol": symbol})
        symbols = data.get("symbols", [])
        if not symbols:
            raise ValueError(f"Symbol {symbol} not found in exchange info")
        info = symbols[0]
        lot_size = None
        min_notional = None
        for flt in info.get("filters", []):
            if flt.get("filterType") == "LOT_SIZE":
                lot_size = flt
            elif flt.get("filterType") in {"MIN_NOTIONAL", "NOTIONAL"}:
                min_notional = flt
        if lot_size is None:
            raise ValueError(f"LOT_SIZE filter missing for symbol {symbol}")
        if min_notional is None:
            min_notional = {"notional": lot_size.get("minQty", "0")}
        return SymbolFilters(
            min_qty=float(lot_size.get("minQty", "0")),
            step_size=float(lot_size.get("stepSize", "0")),
            min_notional=float(min_notional.get("notional", min_notional.get("minNotional", "0"))),
        )

    def set_leverage(self, symbol: str, leverage: int | float) -> Any:
        leverage = max(1, min(int(leverage), 125))
        return self._request("POST", "/fapi/v1/leverage", {"symbol": symbol, "leverage": leverage}, signed=True)

    def get_account_balance(self) -> float:
        balances = self._request("GET", "/fapi/v2/balance", signed=True)
        total = 0.0
        for entry in balances:
            if entry.get("asset") == "USDT":
                total += float(entry.get("balance", "0"))
        return total

    def get_position_information(self, symbol: str) -> Dict[str, Any]:
        positions = self._request("GET", "/fapi/v2/positionRisk", {"symbol": symbol}, signed=True)
        if isinstance(positions, list):
            for item in positions:
                if item.get("symbol") == symbol:
                    return item
            return positions[0] if positions else {}
        return positions

    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        reduce_only: bool = False,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": quantity,
            "newOrderRespType": "FULL",
        }
        if reduce_only:
            params["reduceOnly"] = "true"
        return self._request("POST", "/fapi/v1/order", params, signed=True)

    def cancel_all_orders(self, symbol: str) -> Any:
        return self._request("DELETE", "/fapi/v1/allOpenOrders", {"symbol": symbol}, signed=True)
