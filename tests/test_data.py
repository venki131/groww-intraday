"""
Tests for the Nifty 100 market-data collection module.

All tests are PURE (no DB, no network, no Groww API).
Covers:
  - InstrumentRegistry (instruments.py)
  - validate_candles, detect_missing_intervals, normalize_to_utc (candles.py)
  - DataQualityReport properties
  - apply_quality_flags
  - _nse_session_slots_utc (via detect_missing_intervals)
"""

from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from app.market.instruments import (
    InstrumentRecord,
    InstrumentRegistry,
    NIFTY100_INSTRUMENTS,
    NIFTY100_MEMBERSHIP_HISTORY,
    get_registry,
)
from app.market.candles import (
    QualityFlag,
    DataQualityIssue,
    DataQualityReport,
    normalize_to_utc,
    detect_missing_intervals,
    validate_candles,
    apply_quality_flags,
    _nse_session_slots_utc,
    _SLOTS_PER_DAY,
)

IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc


# ===========================================================================
# Fixtures
# ===========================================================================


def _make_candle_df(
    dates: list[date] | None = None,
    n_per_day: int = 75,
    ticker: str = "RELIANCE",
    bad_ohlc: bool = False,
    zero_vol: bool = False,
    with_zero_volume_on_idx: int | None = None,
) -> pd.DataFrame:
    """
    Build a synthetic candle DataFrame in UTC.

    Args:
        dates           : list of trading dates (default: 2024-01-02)
        n_per_day       : number of candles per day (default: 75 = full session)
        bad_ohlc        : if True, inject an OHLC error on first candle
        zero_vol        : if True, all candles have volume=0
        with_zero_volume_on_idx: index of a single zero-volume candle
    """
    if dates is None:
        dates = [date(2024, 1, 2)]  # Tuesday, trading day

    rows = []
    for d in dates:
        # First bar: 09:15 IST = 03:45 UTC
        slot_ist = datetime(d.year, d.month, d.day, 9, 15, 0, tzinfo=IST)
        for i in range(n_per_day):
            ts_utc = slot_ist.astimezone(UTC)
            o, h, l, c = 100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i
            if bad_ohlc and i == 0:
                h = 99.0  # high < open → OHLC error
            vol = 0 if zero_vol else 1000 + i * 10
            rows.append({
                "timestamp_utc": ts_utc,
                "open": o, "high": h, "low": l, "close": c,
                "volume": vol,
            })
            slot_ist += timedelta(minutes=5)

    df = pd.DataFrame(rows)
    if with_zero_volume_on_idx is not None and len(df) > with_zero_volume_on_idx:
        df.loc[with_zero_volume_on_idx, "volume"] = 0
    return df


# ===========================================================================
# InstrumentRegistry tests
# ===========================================================================


class TestInstrumentRegistry:

    def test_total_instrument_count(self):
        """NIFTY100_INSTRUMENTS must contain exactly 100 entries."""
        assert len(NIFTY100_INSTRUMENTS) == 100

    def test_no_duplicate_tickers(self):
        tickers = [i.ticker for i in NIFTY100_INSTRUMENTS]
        assert len(tickers) == len(set(tickers)), "Duplicate tickers found"

    def test_no_duplicate_isins(self):
        isins = [i.isin for i in NIFTY100_INSTRUMENTS]
        assert len(isins) == len(set(isins)), "Duplicate ISINs found"

    def test_all_tickers_have_groww_symbol(self):
        for inst in NIFTY100_INSTRUMENTS:
            assert inst.groww_symbol.startswith("NSE-"), (
                f"{inst.ticker} has bad groww_symbol: {inst.groww_symbol}"
            )

    def test_registry_len(self):
        r = InstrumentRegistry()
        assert len(r) == 100

    def test_current_tickers_count(self):
        r = InstrumentRegistry()
        current = r.current_tickers()
        assert len(current) == 100, f"Expected 100 current tickers, got {len(current)}"

    def test_all_tickers_sorted(self):
        r = InstrumentRegistry()
        tickers = r.all_tickers()
        assert tickers == sorted(tickers)

    def test_groww_symbol_lookup(self):
        r = InstrumentRegistry()
        assert r.groww_symbol("RELIANCE") == "NSE-RELIANCE"
        assert r.groww_symbol("TCS") == "NSE-TCS"
        assert r.groww_symbol("HDFCBANK") == "NSE-HDFCBANK"

    def test_groww_symbol_raises_for_unknown(self):
        r = InstrumentRegistry()
        with pytest.raises(KeyError, match="FAKECO"):
            r.groww_symbol("FAKECO")

    def test_isin_lookup(self):
        r = InstrumentRegistry()
        assert r.isin("TCS") == "INE467B01029"
        assert r.isin("INFY") == "INE009A01021"

    def test_isin_raises_for_unknown(self):
        r = InstrumentRegistry()
        with pytest.raises(KeyError):
            r.isin("DOESNOTEXIST")

    def test_get_returns_none_for_unknown(self):
        r = InstrumentRegistry()
        assert r.get("DOESNOTEXIST") is None

    def test_get_returns_record(self):
        r = InstrumentRegistry()
        inst = r.get("RELIANCE")
        assert inst is not None
        assert inst.ticker == "RELIANCE"
        assert inst.sector == "Energy"

    def test_by_sector_pharma(self):
        r = InstrumentRegistry()
        pharma = r.by_sector("Pharma")
        tickers = [i.ticker for i in pharma]
        assert "SUNPHARMA" in tickers
        assert "CIPLA" in tickers
        assert "DRREDDY" in tickers
        # Non-pharma should not appear
        assert "RELIANCE" not in tickers

    def test_by_sector_case_insensitive(self):
        r = InstrumentRegistry()
        it = r.by_sector("it")
        banking = r.by_sector("BANKING")
        assert len(it) > 0
        assert len(banking) > 0

    def test_sectors_returns_sorted_unique(self):
        r = InstrumentRegistry()
        sectors = r.sectors()
        assert sectors == sorted(set(sectors))
        assert "Energy" in sectors
        assert "IT" in sectors
        assert "Banking" in sectors

    def test_members_as_of_current_date(self):
        r = InstrumentRegistry()
        members = r.members_as_of("2025-01-01")
        assert len(members) == 100

    def test_members_as_of_2022(self):
        """Should return a reasonable subset — ZOMATO was added Jul 2021."""
        r = InstrumentRegistry()
        members_2022 = r.members_as_of("2022-01-01")
        assert "ZOMATO" in members_2022
        assert "NYKAA" in members_2022     # added Nov 2021
        assert "PAYTM" in members_2022     # added Nov 2021

    def test_members_as_of_2020(self):
        """ZOMATO was not in Nifty 100 before Jul 2021."""
        r = InstrumentRegistry()
        members_2020 = r.members_as_of("2020-01-01")
        assert "ZOMATO" not in members_2020
        assert "PAYTM" not in members_2020
        assert "NYKAA" not in members_2020
        # Long-established names should be present
        assert "RELIANCE" in members_2020
        assert "TCS" in members_2020
        assert "HDFCBANK" in members_2020

    def test_members_as_of_accepts_date_object(self):
        r = InstrumentRegistry()
        d = date(2024, 6, 1)
        members = r.members_as_of(d)
        assert isinstance(members, list)
        assert len(members) > 0

    def test_registry_deduplicates_history(self):
        """Registry must deduplicate membership records with same (ticker, effective_from)."""
        r = InstrumentRegistry()
        # Count records for RELIANCE; there may be duplicates in raw history
        reliance_records = [rec for rec in r._history if rec[0] == "RELIANCE"]
        # All effective_from dates must be unique for RELIANCE
        froms = [rec[1] for rec in reliance_records]
        assert len(froms) == len(set(froms)), "Duplicate (ticker, effective_from) in registry"

    def test_singleton_registry(self):
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2

    def test_custom_registry(self):
        """Registry accepts custom instruments for testing."""
        custom = [
            InstrumentRecord("FAKE1", "Fake Corp 1", "INE000X00001", "NSE-FAKE1", "IT", "Software"),
            InstrumentRecord("FAKE2", "Fake Corp 2", "INE000X00002", "NSE-FAKE2", "IT", "Software"),
        ]
        history = [("FAKE1", date(2020, 1, 1), None), ("FAKE2", date(2021, 1, 1), None)]
        r = InstrumentRegistry(instruments=custom, membership_history=history)
        assert len(r) == 2
        assert r.groww_symbol("FAKE1") == "NSE-FAKE1"
        assert "FAKE1" in r.members_as_of("2024-01-01")
        assert "FAKE2" not in r.members_as_of("2020-06-01")  # FAKE2 added 2021


# ===========================================================================
# normalize_to_utc tests
# ===========================================================================


class TestNormalizeToUtc:

    def test_naive_ist_converted_to_utc(self):
        """Naive timestamps assumed IST; 09:15 IST → 03:45 UTC."""
        df = pd.DataFrame({
            "timestamp": [datetime(2024, 1, 2, 9, 15, 0)]
        })
        result = normalize_to_utc(df)
        expected_utc = datetime(2024, 1, 2, 3, 45, 0, tzinfo=UTC)
        got = result["timestamp_utc"].iloc[0]
        assert got.tzinfo is not None
        assert got == expected_utc

    def test_aware_ist_converted_to_utc(self):
        """tz-aware IST timestamps properly converted."""
        ts_ist = datetime(2024, 1, 2, 9, 15, 0, tzinfo=IST)
        df = pd.DataFrame({"timestamp": [ts_ist]})
        result = normalize_to_utc(df)
        got = result["timestamp_utc"].iloc[0]
        expected_utc = datetime(2024, 1, 2, 3, 45, 0, tzinfo=UTC)
        assert got == expected_utc

    def test_original_col_removed(self):
        df = pd.DataFrame({"timestamp": [datetime(2024, 1, 2, 9, 15)]})
        result = normalize_to_utc(df)
        assert "timestamp" not in result.columns
        assert "timestamp_utc" in result.columns

    def test_already_utc_col_preserved(self):
        """If col already named timestamp_utc and UTC-aware, no-op conversion."""
        ts_utc = datetime(2024, 1, 2, 3, 45, 0, tzinfo=UTC)
        df = pd.DataFrame({"timestamp_utc": [ts_utc]})
        result = normalize_to_utc(df, ts_col="timestamp_utc")
        got = result["timestamp_utc"].iloc[0]
        assert got == ts_utc

    def test_15_30_ist_is_10_00_utc(self):
        """15:30 IST = 10:00 UTC."""
        df = pd.DataFrame({"timestamp": [datetime(2024, 1, 2, 15, 30, 0)]})
        result = normalize_to_utc(df)
        got = result["timestamp_utc"].iloc[0]
        assert got.hour == 10 and got.minute == 0

    def test_original_df_not_mutated(self):
        df = pd.DataFrame({"timestamp": [datetime(2024, 1, 2, 9, 15)]})
        _ = normalize_to_utc(df)
        assert "timestamp" in df.columns  # original unchanged


# ===========================================================================
# _nse_session_slots_utc tests
# ===========================================================================


class TestNseSessionSlots:

    def test_slot_count(self):
        slots = _nse_session_slots_utc(date(2024, 1, 2))
        assert len(slots) == _SLOTS_PER_DAY  # 75

    def test_first_slot_is_0345_utc(self):
        """09:15 IST = 03:45 UTC (IST is UTC+5:30)."""
        slots = _nse_session_slots_utc(date(2024, 1, 2))
        first = slots[0]
        assert first.hour == 3 and first.minute == 45

    def test_last_slot_is_1025_utc(self):
        """15:25 IST = 09:55 UTC (last bar opens at 15:25, session closes 15:30)."""
        slots = _nse_session_slots_utc(date(2024, 1, 2))
        last = slots[-1]
        assert last.hour == 9 and last.minute == 55

    def test_all_slots_5min_apart(self):
        slots = _nse_session_slots_utc(date(2024, 1, 2))
        for i in range(1, len(slots)):
            diff = (slots[i] - slots[i - 1]).total_seconds()
            assert diff == 300, f"Gap at index {i}: {diff}s"

    def test_all_slots_utc_aware(self):
        slots = _nse_session_slots_utc(date(2024, 1, 2))
        for s in slots:
            assert s.tzinfo is not None


# ===========================================================================
# detect_missing_intervals tests
# ===========================================================================


class TestDetectMissingIntervals:

    def test_no_missing_full_session(self):
        """A complete 75-candle session should return no missing intervals."""
        df = _make_candle_df(dates=[date(2024, 1, 2)], n_per_day=75)
        missing = detect_missing_intervals(df, [date(2024, 1, 2)])
        assert missing == []

    def test_empty_df_all_missing(self):
        df = pd.DataFrame(columns=["timestamp_utc"])
        missing = detect_missing_intervals(df, [date(2024, 1, 2)])
        assert len(missing) == 75

    def test_one_candle_missing(self):
        df = _make_candle_df(dates=[date(2024, 1, 2)], n_per_day=74)
        missing = detect_missing_intervals(df, [date(2024, 1, 2)])
        assert len(missing) == 1

    def test_missing_across_two_days(self):
        """With 2 trading days and 70 candles per day, expect 10 missing total."""
        days = [date(2024, 1, 2), date(2024, 1, 3)]
        df = _make_candle_df(dates=days, n_per_day=70)
        missing = detect_missing_intervals(df, days)
        assert len(missing) == 10  # 5 per day × 2

    def test_missing_sorted_ascending(self):
        df = _make_candle_df(dates=[date(2024, 1, 2)], n_per_day=70)
        missing = detect_missing_intervals(df, [date(2024, 1, 2)])
        assert missing == sorted(missing)

    def test_missing_all_utc_aware(self):
        df = pd.DataFrame(columns=["timestamp_utc"])
        missing = detect_missing_intervals(df, [date(2024, 1, 2)])
        for ts in missing:
            assert ts.tzinfo is not None


# ===========================================================================
# validate_candles tests
# ===========================================================================


class TestValidateCandles:

    def test_clean_data_no_issues(self):
        df = _make_candle_df()
        report = validate_candles(df, ticker="RELIANCE")
        assert report.total_candles == 75
        assert report.is_clean
        assert len(report.issues) == 0

    def test_ohlc_error_detected(self):
        """High < open should produce OHLC_ERROR flag."""
        df = _make_candle_df(bad_ohlc=True)
        report = validate_candles(df, ticker="RELIANCE")
        assert report.ohlc_error_count >= 1
        assert not report.is_clean

    def test_zero_volume_detected(self):
        df = _make_candle_df(zero_vol=True)
        report = validate_candles(df, ticker="RELIANCE")
        assert report.zero_volume_count == 75
        # zero_volume is non-fatal → is_clean still True
        assert report.is_clean

    def test_single_zero_volume(self):
        df = _make_candle_df(with_zero_volume_on_idx=0)
        report = validate_candles(df, ticker="RELIANCE")
        assert report.zero_volume_count == 1

    def test_duplicate_timestamp_detected(self):
        df = _make_candle_df()
        # Duplicate the first row
        duplicate = df.iloc[[0]].copy()
        df = pd.concat([df, duplicate], ignore_index=True)
        report = validate_candles(df, ticker="RELIANCE")
        assert report.duplicate_count >= 1
        assert not report.is_clean

    def test_negative_price_detected(self):
        df = _make_candle_df()
        df.loc[0, "close"] = -1.0
        report = validate_candles(df, ticker="RELIANCE")
        # Negative close also triggers OHLC error; at minimum NEGATIVE_PRICE
        assert any(i.flag == QualityFlag.NEGATIVE_PRICE for i in report.issues)
        assert not report.is_clean

    def test_empty_df_returns_empty_report(self):
        df = pd.DataFrame(columns=["timestamp_utc", "open", "high", "low", "close", "volume"])
        report = validate_candles(df, ticker="RELIANCE")
        assert report.total_candles == 0
        assert report.issues == []

    def test_report_summary_string(self):
        df = _make_candle_df()
        report = validate_candles(df, ticker="RELIANCE")
        s = report.summary()
        assert "RELIANCE" in s
        assert "75 candles" in s

    def test_report_start_end_utc(self):
        df = _make_candle_df()
        report = validate_candles(df, ticker="RELIANCE")
        assert report.start_utc is not None
        assert report.end_utc is not None
        assert report.start_utc <= report.end_utc

    def test_out_of_session_detected(self):
        """A candle outside 09:15–15:25 IST should be flagged."""
        df = _make_candle_df()
        # Inject an 18:00 IST candle = out of session
        out_ts = datetime(2024, 1, 2, 18, 0, 0, tzinfo=IST).astimezone(UTC)
        extra = pd.DataFrame([{
            "timestamp_utc": out_ts,
            "open": 100, "high": 101, "low": 99, "close": 100, "volume": 500,
        }])
        df = pd.concat([df, extra], ignore_index=True)
        report = validate_candles(df, ticker="RELIANCE")
        assert report.out_of_session_count >= 1
        assert not report.is_clean

    def test_multiple_issues_counted_separately(self):
        df = _make_candle_df(bad_ohlc=True, with_zero_volume_on_idx=5)
        report = validate_candles(df, ticker="RELIANCE")
        assert report.ohlc_error_count >= 1
        assert report.zero_volume_count >= 1

    def test_issue_str_contains_ticker(self):
        df = _make_candle_df(bad_ohlc=True)
        report = validate_candles(df, ticker="RELIANCE")
        for issue in report.issues:
            if issue.flag == QualityFlag.OHLC_ERROR:
                assert "RELIANCE" in str(issue)
                break


# ===========================================================================
# apply_quality_flags tests
# ===========================================================================


class TestApplyQualityFlags:

    def test_flags_added(self):
        df = _make_candle_df()
        result = apply_quality_flags(df)
        assert "is_zero_volume" in result.columns
        assert "has_ohlc_error" in result.columns
        assert "is_interpolated" in result.columns

    def test_zero_volume_flag_true(self):
        df = _make_candle_df(zero_vol=True)
        result = apply_quality_flags(df)
        assert result["is_zero_volume"].all()

    def test_zero_volume_flag_false_for_normal(self):
        df = _make_candle_df()
        result = apply_quality_flags(df)
        assert not result["is_zero_volume"].any()

    def test_ohlc_error_flag(self):
        df = _make_candle_df(bad_ohlc=True)
        result = apply_quality_flags(df)
        assert result["has_ohlc_error"].iloc[0]

    def test_ohlc_error_false_for_normal(self):
        df = _make_candle_df()
        result = apply_quality_flags(df)
        assert not result["has_ohlc_error"].any()

    def test_is_interpolated_defaults_false(self):
        df = _make_candle_df()
        result = apply_quality_flags(df)
        assert not result["is_interpolated"].any()

    def test_existing_is_interpolated_preserved(self):
        df = _make_candle_df()
        df["is_interpolated"] = True
        result = apply_quality_flags(df)
        assert result["is_interpolated"].all()

    def test_original_df_not_mutated(self):
        df = _make_candle_df()
        _ = apply_quality_flags(df)
        assert "is_zero_volume" not in df.columns


# ===========================================================================
# DataQualityReport tests
# ===========================================================================


class TestDataQualityReport:

    def test_zero_counts_on_empty_issues(self):
        report = DataQualityReport(ticker="TEST")
        assert report.zero_volume_count == 0
        assert report.ohlc_error_count == 0
        assert report.missing_count == 0
        assert report.duplicate_count == 0
        assert report.out_of_session_count == 0

    def test_is_clean_with_only_zero_volume(self):
        """zero_volume is a warning, not fatal → is_clean remains True."""
        report = DataQualityReport(ticker="TEST")
        report.issues.append(DataQualityIssue(
            flag=QualityFlag.ZERO_VOLUME,
            ticker="TEST",
            timestamp_utc=datetime(2024, 1, 2, 3, 45, tzinfo=UTC),
        ))
        assert report.is_clean

    def test_is_not_clean_with_ohlc_error(self):
        report = DataQualityReport(ticker="TEST")
        report.issues.append(DataQualityIssue(
            flag=QualityFlag.OHLC_ERROR,
            ticker="TEST",
            timestamp_utc=datetime(2024, 1, 2, 3, 45, tzinfo=UTC),
        ))
        assert not report.is_clean

    def test_summary_contains_all_counts(self):
        report = DataQualityReport(ticker="TEST", total_candles=10)
        s = report.summary()
        assert "TEST" in s
        assert "10 candles" in s