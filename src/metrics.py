"""Performance metric calculations."""
from __future__ import annotations

from dataclasses import asdict
from typing import Dict, List
import pandas as pd

from .portfolio import PortfolioSnapshot, TradeRecord
from .utils import annualized_return, sharpe_ratio


def _max_drawdown(equity: pd.Series) -> float:
    running_max = equity.cummax()
    drawdowns = equity / running_max - 1.0
    return float(drawdowns.min()) if not drawdowns.empty else 0.0


def compute_metrics(
    snapshots: List[PortfolioSnapshot],
    trades: List[TradeRecord],
    periods_per_year: int = 24 * 365,
) -> Dict[str, float]:
    """Compute aggregate performance statistics from portfolio history."""
    if not snapshots:
        return {}
    df = pd.DataFrame([asdict(s) for s in snapshots])
    df = df.sort_values("index").reset_index(drop=True)
    equity = df["equity"]
    equity_returns = equity.pct_change().fillna(0.0).to_numpy()
    initial_capital = float(equity.iloc[0])
    final_capital = float(equity.iloc[-1])
    total_return = final_capital / initial_capital - 1.0
    ann_return = annualized_return(total_return, periods_per_year, len(df))
    max_dd = _max_drawdown(equity)
    sharpe = sharpe_ratio(equity_returns, periods_per_year=periods_per_year)
    trade_df = pd.DataFrame([asdict(t) for t in trades]) if trades else pd.DataFrame(columns=["realized_pnl"])
    wins = trade_df.loc[trade_df["realized_pnl"] > 0, "realized_pnl"].sum()
    losses = trade_df.loc[trade_df["realized_pnl"] < 0, "realized_pnl"].sum()
    win_trades = (trade_df["realized_pnl"] > 0).sum()
    loss_trades = (trade_df["realized_pnl"] < 0).sum()
    win_rate = win_trades / (win_trades + loss_trades) if (win_trades + loss_trades) > 0 else 0.0
    profit_factor = wins / abs(losses) if losses < 0 else float("inf") if wins > 0 else 0.0
    metrics = {
        "start": df["timestamp"].iloc[0],
        "end": df["timestamp"].iloc[-1],
        "initial_capital": initial_capital,
        "final_capital": final_capital,
        "total_return": total_return,
        "annualized_return": ann_return,
        "max_drawdown": abs(max_dd),
        "sharpe": sharpe,
        "trades": int(len(trade_df)),
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "holding_bars": int((df["position"] != 0).sum()),
    }
    return metrics
