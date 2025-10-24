"""Performance metric calculations."""
from __future__ import annotations

from typing import Dict, Iterable, List

from .portfolio import PortfolioSnapshot, TradeRecord
from .utils import annualized_return, sharpe_ratio


def _max_drawdown(equity: Iterable[float]) -> float:
    running_max = float("-inf")
    max_drawdown = 0.0
    for value in equity:
        running_max = max(running_max, value)
        if running_max <= 0:
            continue
        drawdown = value / running_max - 1.0
        if drawdown < max_drawdown:
            max_drawdown = drawdown
    return max_drawdown


def compute_metrics(
    snapshots: List[PortfolioSnapshot],
    trades: List[TradeRecord],
    periods_per_year: int = 24 * 365,
) -> Dict[str, float]:
    """Compute aggregate performance statistics from portfolio history."""
    if not snapshots:
        return {}
    ordered = sorted(snapshots, key=lambda snap: snap.index)
    equity = [snap.equity for snap in ordered]
    returns: List[float] = []
    for prev, curr in zip(equity[:-1], equity[1:]):
        if prev == 0:
            returns.append(0.0)
        else:
            returns.append(curr / prev - 1.0)
    initial_capital = float(equity[0])
    final_capital = float(equity[-1])
    total_return = final_capital / initial_capital - 1.0 if initial_capital else 0.0
    ann_return = annualized_return(total_return, periods_per_year, len(ordered))
    max_dd = _max_drawdown(equity)
    sharpe = sharpe_ratio(returns, periods_per_year=periods_per_year)
    wins = sum(tr.realized_pnl for tr in trades if tr.realized_pnl > 0)
    losses = sum(tr.realized_pnl for tr in trades if tr.realized_pnl < 0)
    win_trades = sum(1 for tr in trades if tr.realized_pnl > 0)
    loss_trades = sum(1 for tr in trades if tr.realized_pnl < 0)
    total_trades = len(trades)
    win_rate = win_trades / (win_trades + loss_trades) if (win_trades + loss_trades) else 0.0
    profit_factor = (
        wins / abs(losses)
        if losses < 0
        else (float("inf") if wins > 0 else 0.0)
    )
    holding_bars = sum(1 for snap in ordered if snap.position != 0)
    metrics = {
        "start": ordered[0].timestamp,
        "end": ordered[-1].timestamp,
        "initial_capital": initial_capital,
        "final_capital": final_capital,
        "total_return": total_return,
        "annualized_return": ann_return,
        "max_drawdown": abs(max_dd),
        "sharpe": sharpe,
        "trades": int(total_trades),
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "holding_bars": holding_bars,
    }
    return metrics
