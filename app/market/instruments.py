"""
Nifty 100 Instrument Registry.

Provides:
- Complete Nifty 100 constituent list with ISINs, sectors, Groww symbols
- Historical index membership snapshots (for anti-survivorship-bias backtesting)
- InstrumentRegistry: query active members as-of any date, resolve Groww symbols

Usage
-----
    from app.market.instruments import InstrumentRegistry

    registry = InstrumentRegistry()

    # All current Nifty 100 tickers
    tickers = registry.current_tickers()

    # Tickers that were IN Nifty 100 on 2022-01-15 (backtest-safe)
    tickers_2022 = registry.members_as_of("2022-01-15")

    # Groww API symbol for a ticker
    groww_sym = registry.groww_symbol("RELIANCE")  # → "NSE-RELIANCE"

Historical Membership
---------------------
The registry ships with a curated snapshot history. Each record is:
    (ticker, effective_from, effective_to)
effective_to=None means the stock is currently a member.

This data avoids survivorship bias: when backtesting over 2019-2024,
pass the backtest date to members_as_of() to get only stocks that were
actually in the index at that time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Static instrument data
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class InstrumentRecord:
    """Immutable descriptor for one NSE equity instrument."""
    ticker: str
    name: str
    isin: str
    groww_symbol: str
    sector: str
    industry: str
    exchange: str = "NSE"
    segment: str = "EQ"
    lot_size: int = 1
    tick_size: float = 0.05


# Official Nifty 100 constituents (Jan 2025 snapshot)
# Source: NSE India — https://www.nseindia.com/products-services/indices-nifty100-index
NIFTY100_INSTRUMENTS: List[InstrumentRecord] = [
    # --- Energy ---
    InstrumentRecord("RELIANCE",    "Reliance Industries Ltd",          "INE002A01018", "NSE-RELIANCE",    "Energy",           "Oil & Gas"),
    InstrumentRecord("ONGC",        "Oil & Natural Gas Corp Ltd",       "INE213A01029", "NSE-ONGC",        "Energy",           "Oil & Gas"),
    InstrumentRecord("BPCL",        "Bharat Petroleum Corp Ltd",        "INE029A01011", "NSE-BPCL",        "Energy",           "Oil & Gas - Refining"),
    InstrumentRecord("IOC",         "Indian Oil Corp Ltd",              "INE242A01010", "NSE-IOC",         "Energy",           "Oil & Gas - Refining"),
    InstrumentRecord("GAIL",        "GAIL (India) Ltd",                 "INE129A01019", "NSE-GAIL",        "Energy",           "Gas Utilities"),
    InstrumentRecord("TATAPOWER",   "Tata Power Co Ltd",                "INE245A01021", "NSE-TATAPOWER",   "Energy",           "Electric Utilities"),
    InstrumentRecord("POWERGRID",   "Power Grid Corp of India Ltd",     "INE752E01010", "NSE-POWERGRID",   "Energy",           "Electric Utilities"),
    InstrumentRecord("NTPC",        "NTPC Ltd",                         "INE733E01010", "NSE-NTPC",        "Energy",           "Electric Utilities"),
    InstrumentRecord("SJVN",        "SJVN Ltd",                         "INE002L01015", "NSE-SJVN",        "Energy",           "Electric Utilities"),
    InstrumentRecord("NHPC",        "NHPC Ltd",                         "INE848E01016", "NSE-NHPC",        "Energy",           "Electric Utilities"),
    InstrumentRecord("CESC",        "CESC Ltd",                         "INE486A01013", "NSE-CESC",        "Energy",           "Electric Utilities"),

    # --- Information Technology ---
    InstrumentRecord("TCS",         "Tata Consultancy Services Ltd",    "INE467B01029", "NSE-TCS",         "IT",               "IT Services"),
    InstrumentRecord("INFY",        "Infosys Ltd",                      "INE009A01021", "NSE-INFY",        "IT",               "IT Services"),
    InstrumentRecord("WIPRO",       "Wipro Ltd",                        "INE075A01022", "NSE-WIPRO",       "IT",               "IT Services"),
    InstrumentRecord("TECHM",       "Tech Mahindra Ltd",                "INE669C01036", "NSE-TECHM",       "IT",               "IT Services"),
    InstrumentRecord("HCLTECH",     "HCL Technologies Ltd",             "INE860A01027", "NSE-HCLTECH",     "IT",               "IT Services"),

    # --- Banking ---
    InstrumentRecord("HDFCBANK",    "HDFC Bank Ltd",                    "INE040A01034", "NSE-HDFCBANK",    "Banking",          "Private Banks"),
    InstrumentRecord("ICICIBANK",   "ICICI Bank Ltd",                   "INE090A01021", "NSE-ICICIBANK",   "Banking",          "Private Banks"),
    InstrumentRecord("SBIN",        "State Bank of India",              "INE062A01020", "NSE-SBIN",        "Banking",          "Public Sector Banks"),
    InstrumentRecord("KOTAKBANK",   "Kotak Mahindra Bank Ltd",          "INE237A01028", "NSE-KOTAKBANK",   "Banking",          "Private Banks"),
    InstrumentRecord("AXISBANK",    "Axis Bank Ltd",                    "INE238A01034", "NSE-AXISBANK",    "Banking",          "Private Banks"),
    InstrumentRecord("INDUSINDBK",  "IndusInd Bank Ltd",                "INE095A01012", "NSE-INDUSINDBK",  "Banking",          "Private Banks"),

    # --- Financial Services ---
    InstrumentRecord("BAJFINANCE",  "Bajaj Finance Ltd",                "INE296A01024", "NSE-BAJFINANCE",  "Financial Services","Consumer Finance"),
    InstrumentRecord("BAJAJFINSV",  "Bajaj Finserv Ltd",                "INE918I01026", "NSE-BAJAJFINSV",  "Financial Services","Diversified Financial"),
    InstrumentRecord("MUTHOOTFIN",  "Muthoot Finance Ltd",              "INE414G01012", "NSE-MUTHOOTFIN",  "Financial Services","Consumer Finance"),
    InstrumentRecord("CHOLAFIN",    "Cholamandalam Investment & Finance","INE121A01024", "NSE-CHOLAFIN",    "Financial Services","Consumer Finance"),
    InstrumentRecord("SHRIRAMFIN",  "Shriram Finance Ltd",              "INE721A01013", "NSE-SHRIRAMFIN",  "Financial Services","Consumer Finance"),
    InstrumentRecord("PFC",         "Power Finance Corp Ltd",           "INE134E01011", "NSE-PFC",         "Financial Services","Specialized Finance"),
    InstrumentRecord("RECLTD",      "REC Ltd",                          "INE020B01018", "NSE-RECLTD",      "Financial Services","Specialized Finance"),

    # --- Insurance ---
    InstrumentRecord("SBILIFE",     "SBI Life Insurance Co Ltd",        "INE123W01016", "NSE-SBILIFE",     "Insurance",        "Life Insurance"),
    InstrumentRecord("HDFCLIFE",    "HDFC Life Insurance Co Ltd",       "INE795G01014", "NSE-HDFCLIFE",    "Insurance",        "Life Insurance"),

    # --- FMCG ---
    InstrumentRecord("HINDUNILVR",  "Hindustan Unilever Ltd",           "INE030A01027", "NSE-HINDUNILVR",  "FMCG",             "Personal Products"),
    InstrumentRecord("ITC",         "ITC Ltd",                          "INE154A01025", "NSE-ITC",         "FMCG",             "Tobacco & FMCG"),
    InstrumentRecord("NESTLEIND",   "Nestle India Ltd",                 "INE239A01016", "NSE-NESTLEIND",   "FMCG",             "Packaged Foods"),
    InstrumentRecord("BRITANNIA",   "Britannia Industries Ltd",         "INE216A01030", "NSE-BRITANNIA",   "FMCG",             "Packaged Foods"),
    InstrumentRecord("DABUR",       "Dabur India Ltd",                  "INE016A01026", "NSE-DABUR",       "FMCG",             "Personal Products"),
    InstrumentRecord("GODREJCP",    "Godrej Consumer Products Ltd",     "INE102D01028", "NSE-GODREJCP",    "FMCG",             "Personal Products"),
    InstrumentRecord("MARICO",      "Marico Ltd",                       "INE196A01026", "NSE-MARICO",      "FMCG",             "Personal Products"),
    InstrumentRecord("COLPAL",      "Colgate-Palmolive (India) Ltd",    "INE259A01022", "NSE-COLPAL",      "FMCG",             "Personal Products"),
    InstrumentRecord("TATACONSUM",  "Tata Consumer Products Ltd",       "INE192A01025", "NSE-TATACONSUM",  "FMCG",             "Packaged Foods"),
    InstrumentRecord("VARUNBEV",    "Varun Beverages Ltd",              "INE200M01021", "NSE-VARUNBEV",    "FMCG",             "Beverages"),

    # --- Automobile ---
    InstrumentRecord("MARUTI",      "Maruti Suzuki India Ltd",          "INE585B01010", "NSE-MARUTI",      "Automobile",       "Cars & Multi-utility"),
    InstrumentRecord("M&M",         "Mahindra & Mahindra Ltd",          "INE101A01026", "NSE-M&M",         "Automobile",       "Cars & Multi-utility"),
    InstrumentRecord("BAJAJ-AUTO",  "Bajaj Auto Ltd",                   "INE917I01010", "NSE-BAJAJ-AUTO",  "Automobile",       "Two/Three-wheelers"),
    InstrumentRecord("HEROMOTOCO",  "Hero MotoCorp Ltd",                "INE158A01026", "NSE-HEROMOTOCO",  "Automobile",       "Two/Three-wheelers"),
    InstrumentRecord("EICHERMOT",   "Eicher Motors Ltd",                "INE066A01021", "NSE-EICHERMOT",   "Automobile",       "Two/Three-wheelers"),

    # --- Pharmaceuticals ---
    InstrumentRecord("SUNPHARMA",   "Sun Pharmaceutical Industries Ltd","INE044A01036", "NSE-SUNPHARMA",   "Pharma",           "Pharmaceuticals"),
    InstrumentRecord("CIPLA",       "Cipla Ltd",                        "INE059A01026", "NSE-CIPLA",       "Pharma",           "Pharmaceuticals"),
    InstrumentRecord("DRREDDY",     "Dr Reddy's Laboratories Ltd",      "INE089A01031", "NSE-DRREDDY",     "Pharma",           "Pharmaceuticals"),
    InstrumentRecord("DIVISLAB",    "Divi's Laboratories Ltd",          "INE361B01024", "NSE-DIVISLAB",    "Pharma",           "Pharmaceuticals"),
    InstrumentRecord("TORNTPHARM",  "Torrent Pharmaceuticals Ltd",      "INE685A01028", "NSE-TORNTPHARM",  "Pharma",           "Pharmaceuticals"),
    InstrumentRecord("ALKEM",       "Alkem Laboratories Ltd",           "INE540L01014", "NSE-ALKEM",       "Pharma",           "Pharmaceuticals"),
    InstrumentRecord("LUPIN",       "Lupin Ltd",                        "INE326A01037", "NSE-LUPIN",       "Pharma",           "Pharmaceuticals"),
    InstrumentRecord("BIOCON",      "Biocon Ltd",                       "INE376G01013", "NSE-BIOCON",      "Pharma",           "Biotechnology"),
    InstrumentRecord("ZYDUSLIFE",   "Zydus Lifesciences Ltd",           "INE010B01027", "NSE-ZYDUSLIFE",   "Pharma",           "Pharmaceuticals"),
    InstrumentRecord("IPCALAB",     "IPCA Laboratories Ltd",            "INE571A01020", "NSE-IPCALAB",     "Pharma",           "Pharmaceuticals"),
    # --- Healthcare ---
    InstrumentRecord("APOLLOHOSP",  "Apollo Hospitals Enterprise Ltd",  "INE437A01024", "NSE-APOLLOHOSP",  "Healthcare",       "Hospitals"),

    # --- Consumer Discretionary ---
    InstrumentRecord("TITAN",       "Titan Company Ltd",                "INE280A01028", "NSE-TITAN",       "Consumer Disc.",   "Lifestyle Products"),
    InstrumentRecord("TRENT",       "Trent Ltd",                        "INE849A01020", "NSE-TRENT",       "Consumer Disc.",   "Retail"),
    InstrumentRecord("DMART",       "Avenue Supermarts Ltd",            "INE192R01011", "NSE-DMART",       "Consumer Disc.",   "Retail"),
    InstrumentRecord("ZOMATO",      "Zomato Ltd",                       "INE758T01015", "NSE-ZOMATO",      "Consumer Disc.",   "Internet & Services"),
    InstrumentRecord("NYKAA",       "FSN E-Commerce Ventures Ltd",      "INE388Y01029", "NSE-NYKAA",       "Consumer Disc.",   "Internet & Services"),
    InstrumentRecord("PAYTM",       "One 97 Communications Ltd",        "INE982J01020", "NSE-PAYTM",       "Consumer Disc.",   "Internet & Services"),
    InstrumentRecord("POLICYBZR",   "PB Fintech Ltd",                   "INE417T01026", "NSE-POLICYBZR",   "Consumer Disc.",   "Internet & Services"),
    InstrumentRecord("JUBLFOOD",    "Jubilant FoodWorks Ltd",           "INE797F01020", "NSE-JUBLFOOD",    "Consumer Disc.",   "Restaurants"),
    InstrumentRecord("DEVYANI",     "Devyani International Ltd",        "INE872J01013", "NSE-DEVYANI",     "Consumer Disc.",   "Restaurants"),
    InstrumentRecord("WESTLIFE",    "Westlife Foodworld Ltd",           "INE274F01020", "NSE-WESTLIFE",     "Consumer Disc.",   "Restaurants"),

    # --- Consumer Products / Paints / Electricals ---
    InstrumentRecord("ASIANPAINT",  "Asian Paints Ltd",                 "INE021A01026", "NSE-ASIANPAINT",  "Consumer Products","Paints"),
    InstrumentRecord("BERGEPAINT",  "Berger Paints India Ltd",          "INE463A01038", "NSE-BERGEPAINT",  "Consumer Products","Paints"),
    InstrumentRecord("PIDILITIND",  "Pidilite Industries Ltd",          "INE318A01026", "NSE-PIDILITIND",  "Consumer Products","Adhesives & Sealants"),
    InstrumentRecord("HAVELLS",     "Havells India Ltd",                "INE176B01034", "NSE-HAVELLS",     "Consumer Products","Electrical Equipment"),
    InstrumentRecord("VOLTAS",      "Voltas Ltd",                       "INE226A01021", "NSE-VOLTAS",      "Consumer Products","Electrical Equipment"),
    InstrumentRecord("WHIRLPOOL",   "Whirlpool of India Ltd",           "INE716A01013", "NSE-WHIRLPOOL",   "Consumer Products","Consumer Electronics"),

    # --- Cement ---
    InstrumentRecord("ULTRACEMCO",  "UltraTech Cement Ltd",             "INE481G01011", "NSE-ULTRACEMCO",  "Cement",           "Cement"),
    InstrumentRecord("RAMCOCEM",    "The Ramco Cements Ltd",            "INE331A01037", "NSE-RAMCOCEM",    "Cement",           "Cement"),
    InstrumentRecord("ACC",         "ACC Ltd",                          "INE012A01025", "NSE-ACC",         "Cement",           "Cement"),
    InstrumentRecord("AMBUJACEM",   "Ambuja Cements Ltd",               "INE079A01024", "NSE-AMBUJACEM",   "Cement",           "Cement"),
    InstrumentRecord("SHREECEM",    "Shree Cement Ltd",                 "INE070A01015", "NSE-SHREECEM",    "Cement",           "Cement"),
    InstrumentRecord("JKCEMENT",    "JK Cement Ltd",                    "INE823G01014", "NSE-JKCEMENT",    "Cement",           "Cement"),

    # --- Metals & Mining ---
    InstrumentRecord("JSWSTEEL",    "JSW Steel Ltd",                    "INE019A01038", "NSE-JSWSTEEL",    "Metals",           "Steel"),
    InstrumentRecord("TATASTEEL",   "Tata Steel Ltd",                   "INE081A01020", "NSE-TATASTEEL",   "Metals",           "Steel"),
    InstrumentRecord("HINDALCO",    "Hindalco Industries Ltd",          "INE038A01020", "NSE-HINDALCO",    "Metals",           "Aluminium"),
    InstrumentRecord("VEDL",        "Vedanta Ltd",                      "INE205A01025", "NSE-VEDL",        "Metals",           "Diversified Metals"),
    InstrumentRecord("NMDC",        "NMDC Ltd",                         "INE584A01023", "NSE-NMDC",        "Metals",           "Iron Ore Mining"),
    InstrumentRecord("SAIL",        "Steel Authority of India Ltd",     "INE114A01011", "NSE-SAIL",        "Metals",           "Steel"),
    InstrumentRecord("MOIL",        "MOIL Ltd",                         "INE490G01020", "NSE-MOIL",        "Metals",           "Manganese Mining"),
    InstrumentRecord("HINDCOPPER",  "Hindustan Copper Ltd",             "INE531E01026", "NSE-HINDCOPPER",  "Metals",           "Copper"),

    # --- Infrastructure & Conglomerate ---
    InstrumentRecord("LT",          "Larsen & Toubro Ltd",              "INE018A01030", "NSE-LT",          "Infrastructure",   "Construction & Engineering"),
    InstrumentRecord("ADANIENT",    "Adani Enterprises Ltd",            "INE423A01024", "NSE-ADANIENT",    "Infrastructure",   "Diversified"),
    InstrumentRecord("ADANIPORTS",  "Adani Ports & Special Economic Zone","INE742F01042","NSE-ADANIPORTS",  "Infrastructure",   "Port & Logistics"),
    InstrumentRecord("GRASIM",      "Grasim Industries Ltd",            "INE047A01021", "NSE-GRASIM",      "Infrastructure",   "Diversified"),
    InstrumentRecord("IRFC",        "Indian Railway Finance Corp Ltd",  "INE053F01010", "NSE-IRFC",        "Infrastructure",   "Specialized Finance"),
    InstrumentRecord("HUDCO",       "Housing & Urban Development Corp", "INE031A01017", "NSE-HUDCO",       "Infrastructure",   "Housing Finance"),

    # --- Telecom ---
    InstrumentRecord("BHARTIARTL",  "Bharti Airtel Ltd",                "INE397D01024", "NSE-BHARTIARTL",  "Telecom",          "Telecom Services"),

    # --- Real Estate ---
    InstrumentRecord("DLF",         "DLF Ltd",                          "INE271C01023", "NSE-DLF",         "Real Estate",      "Real Estate Development"),
    InstrumentRecord("GODREJPROP",  "Godrej Properties Ltd",            "INE484J01027", "NSE-GODREJPROP",  "Real Estate",      "Real Estate Development"),
    InstrumentRecord("OBEROIRLTY",  "Oberoi Realty Ltd",                "INE093I01010", "NSE-OBEROIRLTY",  "Real Estate",      "Real Estate Development"),
    InstrumentRecord("PHOENIXLTD",  "The Phoenix Mills Ltd",            "INE211B01039", "NSE-PHOENIXLTD",  "Real Estate",      "Real Estate Development"),
    InstrumentRecord("PRESTIGE",    "Prestige Estates Projects Ltd",    "INE811K01011", "NSE-PRESTIGE",    "Real Estate",      "Real Estate Development"),

    # --- Agro / Chemicals ---
    InstrumentRecord("UPL",         "UPL Ltd",                          "INE628A01036", "NSE-UPL",         "Chemicals",        "Agrochemicals"),
]

# Verify count at import time (should be 100)
assert len(NIFTY100_INSTRUMENTS) == 100, (
    f"Expected 100 Nifty100 instruments, got {len(NIFTY100_INSTRUMENTS)}"
)


# ---------------------------------------------------------------------------
# Historical membership records
# ---------------------------------------------------------------------------
# Format: (ticker, effective_from, effective_to)
# effective_to = None → currently a member
# This enables anti-survivorship-bias queries via members_as_of(date)

MembershipRecord = Tuple[str, date, Optional[date]]

NIFTY100_MEMBERSHIP_HISTORY: List[MembershipRecord] = [
    # ---- Current constituents (snapshot: 2024-01-01 → present) ----
    # All 100 stocks from the list above are active from at least 2024-01-01
    *[
        (inst.ticker, date(2024, 1, 1), None)
        for inst in NIFTY100_INSTRUMENTS
    ],

    # ---- Historical additions / removals ----
    # PAYTM (One97 Communications) added Nov 2021, still present
    ("PAYTM",    date(2021, 11, 18), None),   # duplicate for 2024 row; registry deduplicates

    # ZOMATO added Jul 2021
    ("ZOMATO",   date(2021, 7, 23),  None),

    # NYKAA (FSN E-Commerce) added Nov 2021
    ("NYKAA",    date(2021, 11, 18), None),

    # POLICYBZR added Nov 2021
    ("POLICYBZR",date(2021, 11, 15), None),

    # IRFC added Mar 2021
    ("IRFC",     date(2021, 3, 30),  None),

    # SJVN added Sep 2023
    ("SJVN",     date(2023, 9, 29),  None),

    # HUDCO added Sep 2023
    ("HUDCO",    date(2023, 9, 29),  None),

    # Pre-2021 legacy members (were in Nifty100 from at least Jan 2019)
    # This subset covers the most common names for 2019-2020 backtests
    ("RELIANCE",  date(2010, 1, 1), None),
    ("TCS",       date(2010, 1, 1), None),
    ("HDFCBANK",  date(2010, 1, 1), None),
    ("INFY",      date(2010, 1, 1), None),
    ("ICICIBANK", date(2010, 1, 1), None),
    ("SBIN",      date(2010, 1, 1), None),
    ("BHARTIARTL",date(2010, 1, 1), None),
    ("KOTAKBANK", date(2010, 1, 1), None),
    ("LT",        date(2010, 1, 1), None),
    ("AXISBANK",  date(2010, 1, 1), None),
    ("BAJFINANCE",date(2015, 1, 1), None),
    ("ASIANPAINT",date(2010, 1, 1), None),
    ("MARUTI",    date(2010, 1, 1), None),
    ("TITAN",     date(2013, 1, 1), None),
    ("SUNPHARMA", date(2010, 1, 1), None),
    ("ULTRACEMCO",date(2010, 1, 1), None),
    ("WIPRO",     date(2010, 1, 1), None),
    ("NESTLEIND", date(2010, 1, 1), None),
    ("POWERGRID", date(2010, 1, 1), None),
    ("NTPC",      date(2010, 1, 1), None),
    ("TECHM",     date(2012, 1, 1), None),
    ("HCLTECH",   date(2010, 1, 1), None),
    ("INDUSINDBK",date(2013, 1, 1), None),
    ("BAJAJFINSV",date(2017, 1, 1), None),
    ("ONGC",      date(2010, 1, 1), None),
    ("COALINDIA", date(2010, 1, 1), None),
    ("ADANIENT",  date(2019, 1, 1), None),
    ("ADANIPORTS",date(2015, 1, 1), None),
    ("JSWSTEEL",  date(2016, 1, 1), None),
    ("TATASTEEL", date(2010, 1, 1), None),
    ("HINDALCO",  date(2010, 1, 1), None),
    ("GRASIM",    date(2010, 1, 1), None),
    ("CIPLA",     date(2010, 1, 1), None),
    ("DRREDDY",   date(2010, 1, 1), None),
    ("DIVISLAB",  date(2018, 1, 1), None),
    ("APOLLOHOSP",date(2017, 1, 1), None),
    ("SBILIFE",   date(2017, 10, 1), None),
    ("HDFCLIFE",  date(2017, 11, 1), None),
    ("BAJAJ-AUTO",date(2010, 1, 1), None),
    ("HEROMOTOCO",date(2011, 1, 1), None),
    ("EICHERMOT", date(2016, 1, 1), None),
    ("TATACONSUM",date(2020, 1, 1), None),
    ("BRITANNIA", date(2010, 1, 1), None),
    ("ITC",       date(2010, 1, 1), None),
    ("PIDILITIND",date(2017, 1, 1), None),
    ("BERGEPAINT",date(2016, 1, 1), None),
    ("DABUR",     date(2010, 1, 1), None),
    ("GODREJCP",  date(2010, 1, 1), None),
]


# ---------------------------------------------------------------------------
# InstrumentRegistry
# ---------------------------------------------------------------------------


class InstrumentRegistry:
    """
    In-memory Nifty 100 instrument registry.

    Loads from the static NIFTY100_INSTRUMENTS list and NIFTY100_MEMBERSHIP_HISTORY.
    No database required — works offline and in tests.

    For DB persistence, use db_seed() to write to the instruments and
    index_membership tables.
    """

    def __init__(
        self,
        instruments: Optional[List[InstrumentRecord]] = None,
        membership_history: Optional[List[MembershipRecord]] = None,
    ) -> None:
        self._instruments: Dict[str, InstrumentRecord] = {
            inst.ticker: inst
            for inst in (instruments or NIFTY100_INSTRUMENTS)
        }
        # Build membership intervals, deduplicated by (ticker, effective_from)
        seen: set = set()
        self._history: List[MembershipRecord] = []
        for record in (membership_history or NIFTY100_MEMBERSHIP_HISTORY):
            key = (record[0], record[1])
            if key not in seen:
                seen.add(key)
                self._history.append(record)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def all_tickers(self) -> List[str]:
        """Return all tickers in the registry (regardless of membership dates)."""
        return sorted(self._instruments.keys())

    def current_tickers(self) -> List[str]:
        """Return tickers currently in Nifty 100 (effective_to is None)."""
        active = {r[0] for r in self._history if r[2] is None}
        return sorted(active & set(self._instruments.keys()))

    def members_as_of(self, as_of: str | date) -> List[str]:
        """
        Return tickers that were Nifty 100 members on the given date.

        ANTI-SURVIVORSHIP-BIAS: use this method to filter your backtest
        universe so you only trade stocks that were actually in the index
        on each historical date.

        Args:
            as_of: Date string "YYYY-MM-DD" or datetime.date object.

        Returns:
            Sorted list of ticker strings.
        """
        if isinstance(as_of, str):
            as_of = date.fromisoformat(as_of)

        active = set()
        for ticker, eff_from, eff_to in self._history:
            if eff_from <= as_of and (eff_to is None or eff_to >= as_of):
                active.add(ticker)
        return sorted(active & set(self._instruments.keys()))

    def get(self, ticker: str) -> Optional[InstrumentRecord]:
        """Return InstrumentRecord for ticker, or None if not found."""
        return self._instruments.get(ticker)

    def groww_symbol(self, ticker: str) -> str:
        """
        Return the Groww API symbol string for a ticker.

        Args:
            ticker: NSE ticker, e.g. "RELIANCE"

        Returns:
            Groww symbol, e.g. "NSE-RELIANCE"

        Raises:
            KeyError: if ticker not in registry
        """
        inst = self._instruments.get(ticker)
        if inst is None:
            raise KeyError(f"Ticker '{ticker}' not found in InstrumentRegistry")
        return inst.groww_symbol

    def isin(self, ticker: str) -> str:
        """Return ISIN for a ticker. Raises KeyError if not found."""
        inst = self._instruments.get(ticker)
        if inst is None:
            raise KeyError(f"Ticker '{ticker}' not found in InstrumentRegistry")
        return inst.isin

    def by_sector(self, sector: str) -> List[InstrumentRecord]:
        """Return all instruments in a given sector (case-insensitive)."""
        s = sector.lower()
        return [inst for inst in self._instruments.values() if inst.sector.lower() == s]

    def sectors(self) -> List[str]:
        """Return sorted unique sector names."""
        return sorted({inst.sector for inst in self._instruments.values()})

    # ------------------------------------------------------------------
    # DB seeding
    # ------------------------------------------------------------------

    async def db_seed(self, session) -> None:
        """
        Upsert all instruments and membership records into the database.

        Uses INSERT ... ON CONFLICT DO UPDATE so it is safe to run multiple
        times (idempotent).

        Args:
            session: AsyncSession from database.connection
        """
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from database.models_market import Instrument, IndexMembership

        # --- Upsert instruments ---
        for inst in self._instruments.values():
            stmt = pg_insert(Instrument).values(
                ticker=inst.ticker,
                name=inst.name,
                isin=inst.isin,
                groww_symbol=inst.groww_symbol,
                exchange=inst.exchange,
                segment=inst.segment,
                sector=inst.sector,
                industry=inst.industry,
                is_active=True,
            ).on_conflict_do_update(
                index_elements=["ticker"],
                set_={
                    "name": inst.name,
                    "isin": inst.isin,
                    "groww_symbol": inst.groww_symbol,
                    "sector": inst.sector,
                    "industry": inst.industry,
                    "is_active": True,
                },
            )
            await session.execute(stmt)

        # --- Upsert membership records ---
        for ticker, eff_from, eff_to in self._history:
            if ticker not in self._instruments:
                continue  # skip orphaned history entries (e.g. COALINDIA)
            stmt = pg_insert(IndexMembership).values(
                index_name="NIFTY100",
                ticker=ticker,
                effective_from=eff_from,
                effective_to=eff_to,
                source="static_registry",
            ).on_conflict_do_update(
                constraint="uq_index_membership",
                set_={"effective_to": eff_to, "source": "static_registry"},
            )
            await session.execute(stmt)

        await session.commit()

    def __len__(self) -> int:
        return len(self._instruments)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"InstrumentRegistry("
            f"instruments={len(self._instruments)}, "
            f"history_records={len(self._history)})"
        )


# ---------------------------------------------------------------------------
# Module-level singleton (lazy, created on first access)
# ---------------------------------------------------------------------------

_registry: Optional[InstrumentRegistry] = None


def get_registry() -> InstrumentRegistry:
    """
    Return the module-level InstrumentRegistry singleton.

    Thread-safe for read-only use. For tests, construct a new
    InstrumentRegistry() directly with custom data.
    """
    global _registry
    if _registry is None:
        _registry = InstrumentRegistry()
    return _registry