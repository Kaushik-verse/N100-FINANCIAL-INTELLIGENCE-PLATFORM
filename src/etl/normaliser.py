"""
Normaliser module for the N100 Financial Intelligence Platform ETL pipeline.

Provides functions to normalise year labels, ticker symbols, and numeric values
extracted from heterogeneous Excel source data into consistent canonical forms.
"""

import re
import math
from typing import Optional, Union

# Valid three-letter month abbreviations
_VALID_MONTHS = {
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
}

# Pre-compiled patterns
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MON_YYYY_RE = re.compile(r"^([A-Za-z]{3})\s+(\d{4})$")
_MON_DASH_YY_RE = re.compile(r"^([A-Za-z]{3})-(\d{2})$")


def normalize_year(value: Union[str, int, float, None]) -> str:
    """Normalise a year/period value into a canonical string form.

    Handles the following date format variants found in source Excel data:

    - ``"Dec 2012"`` → ``"Dec 2012"``  (already canonical Mon YYYY)
    - ``"Mar-13"``   → ``"Mar 2013"``  (abbreviated year with dash)
    - ``"Jun-99"``   → ``"Jun 1999"``  (pre-2000 abbreviated)
    - ``2019`` (int) → ``"2019"``      (integer year from market_cap)
    - ``2024.0`` (float) → ``"2024"``  (float year)
    - ``"2020-01-01"`` → ``"2020-01-01"`` (ISO date passthrough)
    - ``"TTM"`` → ``"TTM"``           (trailing twelve months passthrough)

    Args:
        value: The raw year/period value from source data.

    Returns:
        A canonical string representation of the year/period.

    Raises:
        ValueError: If *value* is None, NaN, empty, or an unrecognised format.
    """
    # 1. Handle None / NaN / empty
    if value is None:
        raise ValueError("Year value cannot be None")

    if isinstance(value, float) and math.isnan(value):
        raise ValueError("Year value cannot be NaN")

    # 2. If int or float → convert to string year
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(int(value))

    # From here on, value must be a string
    if not isinstance(value, str):
        raise ValueError(f"Unrecognised year format: {value!r}")

    stripped = value.strip()

    if stripped == "":
        raise ValueError("Year value cannot be empty")

    # 3. ISO date passthrough (YYYY-MM-DD)
    if _ISO_DATE_RE.match(stripped):
        return stripped

    # 4. TTM passthrough
    if stripped == "TTM":
        return "TTM"

    # 5. Mon YYYY (e.g. "Dec 2012")
    m = _MON_YYYY_RE.match(stripped)
    if m:
        month_str = m.group(1).capitalize()
        if month_str not in _VALID_MONTHS:
            raise ValueError(f"Invalid month abbreviation: {month_str!r}")
        year_str = m.group(2)
        return f"{month_str} {year_str}"

    # 6. Mon-YY (e.g. "Mar-13", "Jun-99")
    m = _MON_DASH_YY_RE.match(stripped)
    if m:
        month_str = m.group(1).capitalize()
        if month_str not in _VALID_MONTHS:
            raise ValueError(f"Invalid month abbreviation: {month_str!r}")
        yy = int(m.group(2))
        full_year = 1900 + yy if yy >= 50 else 2000 + yy
        return f"{month_str} {full_year}"

    # 7. Unrecognised format
    raise ValueError(f"Unrecognised year format: {stripped!r}")


def normalize_ticker(value: Union[str, None]) -> str:
    """Normalise a company ticker symbol to uppercase with whitespace stripped.

    Args:
        value: The raw ticker string from source data.

    Returns:
        The cleaned, uppercased ticker symbol.

    Raises:
        ValueError: If *value* is None, NaN, or empty/whitespace-only.
    """
    if value is None:
        raise ValueError("Ticker value cannot be None")

    if isinstance(value, float) and math.isnan(value):
        raise ValueError("Ticker value cannot be NaN")

    if not isinstance(value, str):
        raise ValueError(f"Unrecognised ticker type: {type(value).__name__}")

    stripped = value.strip()

    if stripped == "":
        raise ValueError("Ticker value cannot be empty")

    return stripped.upper()


def coerce_numeric(value: Union[str, int, float, None]) -> Optional[float]:
    """Safely coerce a value to float, returning None for non-convertible inputs.

    Handles common Excel artifacts such as comma-separated thousands,
    trailing percentage signs, and dash placeholders.

    Args:
        value: The raw value to convert.

    Returns:
        The value as a ``float``, or ``None`` if the value cannot be
        meaningfully converted.
    """
    # None / NaN → None
    if value is None:
        return None

    if isinstance(value, float) and math.isnan(value):
        return None

    # Already numeric (int/float, but not bool)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)

    # String processing
    if isinstance(value, str):
        cleaned = value.strip()

        # Dash placeholder or empty → None
        if cleaned in ("", "-"):
            return None

        # Remove commas (thousands separators)
        cleaned = cleaned.replace(",", "")

        # Remove trailing %
        if cleaned.endswith("%"):
            cleaned = cleaned[:-1].rstrip()

        # Handle empty after stripping
        if cleaned == "":
            return None

        try:
            return float(cleaned)
        except (ValueError, OverflowError):
            return None

    # Unrecognised type → None
    return None
