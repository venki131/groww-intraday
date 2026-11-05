"""Nifty 100 symbol universe."""
from __future__ import annotations

from typing import List


NIFTY100_SYMBOLS: List[str] = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
    "HINDUNILVR", "SBIN", "BHARTIARTL", "KOTAKBANK", "LT",
    "AXISBANK", "BAJFINANCE", "ASIANPAINT", "MARUTI", "TITAN",
    "SUNPHARMA", "ULTRACEMCO", "WIPRO", "NESTLEIND", "POWERGRID",
    "NTPC", "TECHM", "HCLTECH", "INDUSINDBK", "BAJAJFINSV",
    "ONGC", "COALINDIA", "M&M", "ADANIENT", "ADANIPORTS",
    "JSWSTEEL", "TATASTEEL", "HINDALCO", "GRASIM", "CIPLA",
    "DRREDDY", "DIVISLAB", "APOLLOHOSP", "SBILIFE", "HDFCLIFE",
    "BAJAJ-AUTO", "HEROMOTOCO", "EICHERMOT", "TATACONSUM", "BRITANNIA",
    "ITC", "PIDILITIND", "BERGEPAINT", "DABUR", "GODREJCP",
    "HAVELLS", "VOLTAS", "WHIRLPOOL", "MARICO", "COLPAL",
    "UPL", "BPCL", "IOC", "GAIL", "INDIGO",
    "TATAPOWER", "TORNTPHARM", "ALKEM", "LUPIN", "BIOCON",
    "MUTHOOTFIN", "CHOLAFIN", "SHRIRAMFIN", "PFC", "RECLTD",
    "DLF", "GODREJPROP", "OBEROIRLTY", "PHOENIXLTD", "PRESTIGE",
    "ZOMATO", "NYKAA", "PAYTM", "POLICYBZR", "DMART",
    "TRENT", "VARUNBEV", "JUBLFOOD", "DEVYANI", "WESTLIFE",
    "RAMCOCEM", "ACC", "AMBUJACEM", "SHREECEM", "JKCEMENT",
    "VEDL", "NMDC", "SAIL", "MOIL", "HINDCOPPER",
    "IRFC", "HUDCO", "SJVN", "NHPC", "CESC",
    "ZYDUSLIFE", "IPCALAB", "ABBOTINDIA", "PFIZER", "GLAXO",
]


class NiftyUniverse:
    """Manages the Nifty 100 trading universe."""

    def __init__(self, symbols: List[str] | None = None) -> None:
        self._symbols = symbols or NIFTY100_SYMBOLS

    @property
    def symbols(self) -> List[str]:
        """Return all symbols in the universe."""
        return list(self._symbols)

    def filter(self, tickers: List[str]) -> List[str]:
        """Return only tickers that are in the Nifty 100 universe."""
        universe_set = set(self._symbols)
        return [t for t in tickers if t in universe_set]

    def __len__(self) -> int:
        return len(self._symbols)

    def __contains__(self, ticker: str) -> bool:
        return ticker in self._symbols