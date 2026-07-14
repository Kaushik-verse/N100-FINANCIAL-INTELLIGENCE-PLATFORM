"""
Tests for src.etl.validator
============================
Uses pytest ``tmp_path`` fixtures to spin up disposable SQLite databases
populated with controlled test data.
"""

import sqlite3
import pytest

from src.etl.validator import (
    run_dq_01,
    run_dq_04,
    run_dq_06,
    run_all_rules,
)


# ---------------------------------------------------------------------------
# Helpers — schema & seed utilities
# ---------------------------------------------------------------------------


def _create_companies_table(conn):
    """Create a minimal ``companies`` table."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS companies (
            company_id   INTEGER PRIMARY KEY,
            company_name TEXT
        )
        """
    )


def _create_profitandloss_table(conn):
    """Create a minimal ``profitandloss`` table."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS profitandloss (
            id               INTEGER PRIMARY KEY,
            company_id       INTEGER,
            year             INTEGER,
            sales            REAL,
            operating_profit REAL,
            opm_percentage   REAL,
            net_profit       REAL,
            eps              REAL,
            dividend_payout  REAL,
            tax_percentage   REAL,
            FOREIGN KEY (company_id) REFERENCES companies(company_id)
        )
        """
    )


def _create_balancesheet_table(conn):
    """Create a minimal ``balancesheet`` table."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS balancesheet (
            id                INTEGER PRIMARY KEY,
            company_id        INTEGER,
            year              INTEGER,
            total_assets      REAL,
            total_liabilities REAL,
            equity_capital    REAL,
            reserves          REAL,
            borrowings        REAL,
            other_liabilities REAL,
            FOREIGN KEY (company_id) REFERENCES companies(company_id)
        )
        """
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def clean_db(tmp_path):
    """Return a path to a fresh SQLite DB with one company and no dupes."""
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")

    _create_companies_table(conn)
    conn.execute("INSERT INTO companies VALUES (1, 'TestCo')")

    _create_profitandloss_table(conn)
    conn.execute(
        "INSERT INTO profitandloss "
        "(id, company_id, year, sales, operating_profit, opm_percentage, "
        " net_profit, eps, dividend_payout, tax_percentage) "
        "VALUES (1, 1, 2023, 1000, 200, 20, 150, 15.0, 50, 25)"
    )

    _create_balancesheet_table(conn)
    conn.execute(
        "INSERT INTO balancesheet "
        "(id, company_id, year, total_assets, total_liabilities, "
        " equity_capital, reserves, borrowings, other_liabilities) "
        "VALUES (1, 1, 2023, 5000, 5000, 100, 3900, 500, 500)"
    )

    conn.commit()
    conn.close()
    return db_path


@pytest.fixture()
def duplicate_db(tmp_path):
    """Return a DB path where ``companies`` has duplicate PKs."""
    db_path = str(tmp_path / "dup.db")
    conn = sqlite3.connect(db_path)
    # Deliberately skip PK constraint so we can insert dupes
    conn.execute(
        "CREATE TABLE companies (company_id INTEGER, company_name TEXT)"
    )
    conn.execute("INSERT INTO companies VALUES (1, 'Alpha')")
    conn.execute("INSERT INTO companies VALUES (1, 'Alpha Dup')")
    conn.commit()
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# Tests — DQ-01: PK uniqueness
# ---------------------------------------------------------------------------


def test_dq_01_no_duplicates(clean_db):
    """Clean data should produce zero DQ-01 failures."""
    conn = sqlite3.connect(clean_db)
    conn.execute("PRAGMA foreign_keys = ON")
    results = run_dq_01(conn)
    conn.close()
    for r in results:
        assert r["failing_count"] == 0, f"Unexpected failures in {r['table']}"


def test_dq_01_with_duplicates(duplicate_db):
    """Duplicate PKs should be caught by DQ-01."""
    conn = sqlite3.connect(duplicate_db)
    results = run_dq_01(conn)
    conn.close()
    companies_result = [r for r in results if r["table"] == "companies"]
    assert len(companies_result) == 1
    assert companies_result[0]["failing_count"] > 0


# ---------------------------------------------------------------------------
# Tests — DQ-04: Balance-sheet equation
# ---------------------------------------------------------------------------


def test_dq_04_balanced(clean_db):
    """When total_assets == total_liabilities the rule should pass."""
    conn = sqlite3.connect(clean_db)
    results = run_dq_04(conn)
    conn.close()
    assert len(results) == 1
    assert results[0]["failing_count"] == 0


def test_dq_04_unbalanced(tmp_path):
    """A large gap between assets and liabilities should be flagged."""
    db_path = str(tmp_path / "unbal.db")
    conn = sqlite3.connect(db_path)
    _create_companies_table(conn)
    conn.execute("INSERT INTO companies VALUES (1, 'TestCo')")
    _create_balancesheet_table(conn)
    # assets = 5000, liabilities = 3000 → 40 % gap
    conn.execute(
        "INSERT INTO balancesheet "
        "(id, company_id, year, total_assets, total_liabilities, "
        " equity_capital, reserves, borrowings, other_liabilities) "
        "VALUES (1, 1, 2023, 5000, 3000, 100, 1900, 500, 500)"
    )
    conn.commit()
    results = run_dq_04(conn)
    conn.close()
    assert results[0]["failing_count"] > 0


# ---------------------------------------------------------------------------
# Tests — DQ-06: Positive sales
# ---------------------------------------------------------------------------


def test_dq_06_positive_sales(clean_db):
    """Positive-sales row should not be flagged."""
    conn = sqlite3.connect(clean_db)
    results = run_dq_06(conn)
    conn.close()
    assert results[0]["failing_count"] == 0


def test_dq_06_negative_sales(tmp_path):
    """Negative/zero sales should be flagged by DQ-06."""
    db_path = str(tmp_path / "neg_sales.db")
    conn = sqlite3.connect(db_path)
    _create_companies_table(conn)
    conn.execute("INSERT INTO companies VALUES (1, 'TestCo')")
    _create_profitandloss_table(conn)
    conn.execute(
        "INSERT INTO profitandloss "
        "(id, company_id, year, sales, operating_profit, opm_percentage, "
        " net_profit, eps, dividend_payout, tax_percentage) "
        "VALUES (1, 1, 2023, -500, 200, 20, 150, 15.0, 50, 25)"
    )
    conn.commit()
    results = run_dq_06(conn)
    conn.close()
    assert results[0]["failing_count"] > 0


# ---------------------------------------------------------------------------
# Tests — result format
# ---------------------------------------------------------------------------


def test_results_format(clean_db):
    """Every result dict must contain the five canonical keys."""
    results = run_all_rules(clean_db)
    required_keys = {"rule_id", "severity", "table", "description",
                     "failing_count", "sample_rows"}
    for r in results:
        assert required_keys.issubset(r.keys()), (
            f"Missing keys in result: {required_keys - r.keys()}"
        )
