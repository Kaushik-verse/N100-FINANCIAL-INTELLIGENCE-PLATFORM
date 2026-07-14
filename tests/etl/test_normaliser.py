"""
Unit tests for the normaliser module.

Covers normalize_year, normalize_ticker, and coerce_numeric with 50+ test
cases exercising canonical formats, edge cases, and error conditions.
"""

import math

import pytest

from src.etl.normaliser import coerce_numeric, normalize_ticker, normalize_year


# ──────────────────────────────────────────────────────────────────────────────
# normalize_year
# ──────────────────────────────────────────────────────────────────────────────


class TestNormalizeYear:
    """Tests for normalize_year covering all supported format variants."""

    # --- Mon YYYY passthrough ---

    def test_dec_2012(self):
        assert normalize_year("Dec 2012") == "Dec 2012"

    def test_mar_2014(self):
        assert normalize_year("Mar 2014") == "Mar 2014"

    def test_jan_2020(self):
        assert normalize_year("Jan 2020") == "Jan 2020"

    # --- Mon-YY expansion ---

    def test_mar_dash_13(self):
        assert normalize_year("Mar-13") == "Mar 2013"

    def test_mar_dash_14(self):
        assert normalize_year("Mar-14") == "Mar 2014"

    def test_jun_dash_99(self):
        assert normalize_year("Jun-99") == "Jun 1999"

    def test_sep_dash_05(self):
        assert normalize_year("Sep-05") == "Sep 2005"

    def test_dec_dash_00(self):
        assert normalize_year("Dec-00") == "Dec 2000"

    def test_jan_dash_50(self):
        assert normalize_year("Jan-50") == "Jan 1950"

    # --- Integer year ---

    def test_int_2019(self):
        assert normalize_year(2019) == "2019"

    def test_int_2024(self):
        assert normalize_year(2024) == "2024"

    # --- Float year ---

    def test_float_2019(self):
        assert normalize_year(2019.0) == "2019"

    def test_float_2024(self):
        assert normalize_year(2024.0) == "2024"

    # --- ISO date passthrough ---

    def test_iso_date(self):
        assert normalize_year("2020-01-01") == "2020-01-01"

    def test_iso_date_other(self):
        assert normalize_year("2023-06-15") == "2023-06-15"

    # --- TTM passthrough ---

    def test_ttm(self):
        assert normalize_year("TTM") == "TTM"

    # --- Error conditions ---

    def test_none_raises(self):
        with pytest.raises(ValueError):
            normalize_year(None)

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            normalize_year("")

    def test_nan_raises(self):
        with pytest.raises(ValueError):
            normalize_year(float("nan"))

    def test_invalid_string_raises(self):
        with pytest.raises(ValueError):
            normalize_year("foobar")

    def test_invalid_month_raises(self):
        with pytest.raises(ValueError):
            normalize_year("Xyz 2020")

    def test_invalid_month_dash_raises(self):
        with pytest.raises(ValueError):
            normalize_year("Xyz-13")

    # --- Whitespace handling ---

    def test_whitespace_stripped(self):
        assert normalize_year(" Mar 2014 ") == "Mar 2014"

    def test_whitespace_stripped_dash(self):
        assert normalize_year(" Jun-99 ") == "Jun 1999"


# ──────────────────────────────────────────────────────────────────────────────
# normalize_ticker
# ──────────────────────────────────────────────────────────────────────────────


class TestNormalizeTicker:
    """Tests for normalize_ticker covering casing, whitespace, and errors."""

    def test_normal_ticker(self):
        assert normalize_ticker("HDFCBANK") == "HDFCBANK"

    def test_strip_whitespace(self):
        assert normalize_ticker(" TCS ") == "TCS"

    def test_lowercase(self):
        assert normalize_ticker("hdfcbank") == "HDFCBANK"

    def test_mixed_case(self):
        assert normalize_ticker("HdfcBank") == "HDFCBANK"

    def test_none_raises(self):
        with pytest.raises(ValueError):
            normalize_ticker(None)

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            normalize_ticker("")

    def test_nan_raises(self):
        with pytest.raises(ValueError):
            normalize_ticker(float("nan"))

    def test_single_char(self):
        assert normalize_ticker("A") == "A"

    def test_with_ampersand(self):
        assert normalize_ticker("M&M") == "M&M"

    def test_adaniensol(self):
        assert normalize_ticker("ADANIENSOL") == "ADANIENSOL"

    def test_tabs_stripped(self):
        assert normalize_ticker("\tRELIANCE\t") == "RELIANCE"

    def test_newline_stripped(self):
        assert normalize_ticker("INFY\n") == "INFY"

    def test_spaces_only_raises(self):
        with pytest.raises(ValueError):
            normalize_ticker("   ")

    def test_numeric_ticker(self):
        assert normalize_ticker("360ONE") == "360ONE"

    def test_underscore_ticker(self):
        assert normalize_ticker("NIFTY_BANK") == "NIFTY_BANK"

    def test_lowercase_with_numbers(self):
        assert normalize_ticker("360one") == "360ONE"


# ──────────────────────────────────────────────────────────────────────────────
# coerce_numeric
# ──────────────────────────────────────────────────────────────────────────────


class TestCoerceNumeric:
    """Tests for coerce_numeric covering type coercion and edge cases."""

    def test_none_returns_none(self):
        assert coerce_numeric(None) is None

    def test_nan_returns_none(self):
        assert coerce_numeric(float("nan")) is None

    def test_int_value(self):
        assert coerce_numeric(42) == 42.0

    def test_float_value(self):
        assert coerce_numeric(3.14) == 3.14

    def test_string_int(self):
        assert coerce_numeric("100") == 100.0

    def test_string_float(self):
        assert coerce_numeric("3.14") == 3.14

    def test_string_with_commas(self):
        assert coerce_numeric("1,234,567") == 1234567.0

    def test_string_with_percent(self):
        assert coerce_numeric("85.5%") == 85.5

    def test_dash_returns_none(self):
        assert coerce_numeric("-") is None

    def test_empty_returns_none(self):
        assert coerce_numeric("") is None

    def test_whitespace_returns_none(self):
        assert coerce_numeric("   ") is None

    def test_non_numeric_string_returns_none(self):
        assert coerce_numeric("abc") is None

    def test_negative_number(self):
        assert coerce_numeric("-42.5") == -42.5

    def test_string_with_spaces(self):
        assert coerce_numeric("  100  ") == 100.0

    def test_zero(self):
        assert coerce_numeric(0) == 0.0

    def test_string_zero(self):
        assert coerce_numeric("0") == 0.0

    def test_large_number_with_commas(self):
        assert coerce_numeric("10,00,000") == 1000000.0

    def test_percent_with_spaces(self):
        assert coerce_numeric(" 12.5% ") == 12.5
