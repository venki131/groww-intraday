"""Report generator - produces trade logs and P&L summaries as DataFrames/CSV."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import List

import pandas as pd

from backtesting.engine import BacktestReport, BacktestTrade
from config.logging_config import get_logger

logger = get_logger(__name__)


class ReportGenerator:
    """
    Converts BacktestReport data into pandas DataFrames and CSV exports.

    Args:
        output_dir: Directory to write CSV files (created if absent).
    """

    def __init__(self, output_dir: str = "reports") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def trades_to_dataframe(self, trades: List[BacktestTrade]) -> pd.DataFrame:
        """Convert trade list to DataFrame."""
        if not trades:
            return pd.DataFrame()
        return pd.DataFrame([
            {
                "ticker": t.ticker,
                "entry_time": t.entry_time,
                "exit_time": t.exit_time,
                "entry_price": float(t.entry_price),
                "exit_price": float(t.exit_price),
                "quantity": t.quantity,
                "gross_pnl": float(t.gross_pnl),
                "commission": float(t.commission),
                "net_pnl": float(t.net_pnl),
                "exit_reason": t.exit_reason,
                "winning": t.net_pnl > 0,
            }
            for t in trades
        ])

    def export_backtest(self, report: BacktestReport, filename: str = "") -> Path:
        """
        Export backtest trades to CSV.

        Args:
            report: BacktestReport to export.
            filename: Output filename (auto-generated if empty).

        Returns:
            Path to the written CSV file.
        """
        name = filename or f"backtest_{report.strategy_name}_{report.ticker}.csv"
        path = self.output_dir / name
        df = self.trades_to_dataframe(report.trades)
        df.to_csv(path, index=False)
        logger.info("Backtest report exported", path=str(path), trades=len(report.trades))
        return path

    def equity_curve_dataframe(self, report: BacktestReport) -> pd.DataFrame:
        """Return equity curve as DataFrame."""
        return pd.DataFrame(report.equity_curve)

    def summary_dataframe(self, reports: List[BacktestReport]) -> pd.DataFrame:
        """Aggregate multiple backtest reports into one summary DataFrame."""
        return pd.DataFrame([r.to_dict() for r in reports])