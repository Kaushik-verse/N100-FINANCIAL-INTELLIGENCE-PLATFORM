"""
N100 Financial Intelligence Platform — Loader Tests.

Validates that the ETL loader correctly ingests all 12 Excel source
files into the SQLite database with proper normalisation, FK integrity,
and type coercion.

Run with:
    python -m pytest tests/etl/test_loader.py -v
"""

import os
import sys
import sqlite3
import tempfile

import pytest

# ── Ensure project root is on sys.path ───────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.etl.loader import load_all, DB_PATH, OUTPUT_DIR  # noqa: E402


# ════════════════════════════════════════════════════════════════════
# Session-scoped fixture — run the loader ONCE for all tests
# ════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def loaded_db():
    """Load the full dataset into the default nifty100.db (if not present)
    and return an open connection.

    The loader is idempotent — if the DB already exists it is rebuilt
    from scratch to guarantee a clean state.
    """
    load_all()  # Always rebuild so tests are deterministic
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


# ════════════════════════════════════════════════════════════════════
# 1. Companies
# ════════════════════════════════════════════════════════════════════

class TestCompanies:
    """Tests for the master companies table."""

    def test_load_companies_count(self, loaded_db):
        """92 companies should be loaded from companies.xlsx."""
        (count,) = loaded_db.execute("SELECT COUNT(*) FROM companies").fetchone()
        assert count == 92, f"Expected 92 companies, got {count}"

    def test_company_id_is_ticker(self, loaded_db):
        """company_id values should be upper-case ticker symbols like ABB, TCS."""
        rows = loaded_db.execute("SELECT company_id FROM companies").fetchall()
        for row in rows:
            ticker = row["company_id"]
            # Tickers are uppercase alphanumeric (may include & or -)
            assert ticker == ticker.upper(), f"Ticker {ticker!r} is not uppercase"
            assert len(ticker) > 0, "Empty ticker found"

    def test_companies_columns(self, loaded_db):
        """All 12 schema columns should be present in the companies table."""
        cursor = loaded_db.execute("PRAGMA table_info(companies)")
        columns = {row["name"] for row in cursor.fetchall()}
        expected = {
            "company_id", "company_name", "company_logo", "chart_link",
            "about_company", "website", "nse_profile", "bse_profile",
            "face_value", "book_value", "roce_percentage", "roe_percentage",
        }
        assert expected.issubset(columns), f"Missing columns: {expected - columns}"

    def test_companies_no_nulls_in_name(self, loaded_db):
        """company_name should never be NULL."""
        (nulls,) = loaded_db.execute(
            "SELECT COUNT(*) FROM companies WHERE company_name IS NULL"
        ).fetchone()
        assert nulls == 0, f"Found {nulls} NULL company names"


# ════════════════════════════════════════════════════════════════════
# 2. Financial Statements
# ════════════════════════════════════════════════════════════════════

class TestProfitAndLoss:
    """Tests for the profitandloss table."""

    def test_pl_load_count(self, loaded_db):
        """P&L table should have close to 1276 rows (minus orphans)."""
        (count,) = loaded_db.execute("SELECT COUNT(*) FROM profitandloss").fetchone()
        # Allow for some orphan rejections
        assert count > 0, "P&L table is empty"
        assert count <= 1276, f"P&L has more rows ({count}) than source (1276)"

    def test_pl_no_duplicate_company_year(self, loaded_db):
        """No duplicate (company_id, year) pairs in P&L."""
        rows = loaded_db.execute(
            "SELECT company_id, year, COUNT(*) AS c "
            "FROM profitandloss GROUP BY company_id, year HAVING c > 1"
        ).fetchall()
        assert len(rows) == 0, f"Found {len(rows)} duplicate (company_id, year) pairs in P&L"


class TestBalanceSheet:
    """Tests for the balancesheet table."""

    def test_bs_load_count(self, loaded_db):
        """Balance sheet should have rows loaded."""
        (count,) = loaded_db.execute("SELECT COUNT(*) FROM balancesheet").fetchone()
        assert count > 0, "Balance sheet table is empty"
        assert count <= 1312, f"BS has more rows ({count}) than source (1312)"


class TestCashFlow:
    """Tests for the cashflow table."""

    def test_cf_load_count(self, loaded_db):
        """Cash flow should have rows loaded."""
        (count,) = loaded_db.execute("SELECT COUNT(*) FROM cashflow").fetchone()
        assert count > 0, "Cash flow table is empty"
        assert count <= 1187, f"CF has more rows ({count}) than source (1187)"


# ════════════════════════════════════════════════════════════════════
# 3. Supplementary Tables
# ════════════════════════════════════════════════════════════════════

class TestSectors:
    """Tests for the sectors table."""

    def test_sectors_count(self, loaded_db):
        """92 sector rows should be loaded (one per company)."""
        (count,) = loaded_db.execute("SELECT COUNT(*) FROM sectors").fetchone()
        assert count == 92, f"Expected 92 sectors, got {count}"

    def test_sectors_unique_company(self, loaded_db):
        """Each company should appear at most once in sectors (UNIQUE constraint)."""
        rows = loaded_db.execute(
            "SELECT company_id, COUNT(*) AS c FROM sectors GROUP BY company_id HAVING c > 1"
        ).fetchall()
        assert len(rows) == 0, f"Found {len(rows)} duplicate company_ids in sectors"


class TestStockPrices:
    """Tests for the stock_prices table."""

    def test_stock_prices_count(self, loaded_db):
        """stock_prices should have up to 5520 rows."""
        (count,) = loaded_db.execute("SELECT COUNT(*) FROM stock_prices").fetchone()
        assert count > 0, "Stock prices table is empty"
        assert count <= 5520, f"Stock prices has {count} rows, expected ≤ 5520"


class TestMarketCap:
    """Tests for the market_cap table."""

    def test_market_cap_loaded(self, loaded_db):
        """market_cap should have rows loaded."""
        (count,) = loaded_db.execute("SELECT COUNT(*) FROM market_cap").fetchone()
        assert count > 0, "Market cap table is empty"
        assert count <= 552, f"Market cap has {count} rows, expected ≤ 552"


# ════════════════════════════════════════════════════════════════════
# 4. FK Integrity
# ════════════════════════════════════════════════════════════════════

class TestForeignKeys:
    """Foreign-key integrity checks."""

    def test_fk_check_passes(self, loaded_db):
        """PRAGMA foreign_key_check should return 0 violations."""
        violations = loaded_db.execute("PRAGMA foreign_key_check").fetchall()
        assert len(violations) == 0, (
            f"Found {len(violations)} FK violations: "
            + str(violations[:5])
        )


# ════════════════════════════════════════════════════════════════════
# 5. Year Normalisation
# ════════════════════════════════════════════════════════════════════

class TestYearNormalisation:
    """Verify year values are in canonical format after loading."""

    def test_pl_years_normalised(self, loaded_db):
        """P&L years should be in 'Mon YYYY' or 'TTM' format."""
        rows = loaded_db.execute("SELECT DISTINCT year FROM profitandloss").fetchall()
        for row in rows:
            year = row["year"]
            assert year is not None, "NULL year found in P&L"
            # Valid formats: "Mon YYYY" or "TTM"
            import re
            assert re.match(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4}$|^TTM$", year), (
                f"P&L year {year!r} not in canonical format"
            )

    def test_cf_years_normalised(self, loaded_db):
        """Cash flow years (originally Mon-YY) should be normalised to 'Mon YYYY'."""
        rows = loaded_db.execute("SELECT DISTINCT year FROM cashflow").fetchall()
        for row in rows:
            year = row["year"]
            assert year is not None, "NULL year found in cashflow"
            import re
            assert re.match(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4}$|^TTM$", year), (
                f"CF year {year!r} not in canonical 'Mon YYYY' format"
            )


# ════════════════════════════════════════════════════════════════════
# 6. Audit Trail
# ════════════════════════════════════════════════════════════════════

class TestAudit:
    """Verify the audit CSV is generated."""

    def test_load_audit_generated(self, loaded_db):
        """output/load_audit.csv should exist after a load."""
        audit_path = os.path.join(OUTPUT_DIR, "load_audit.csv")
        assert os.path.isfile(audit_path), f"Audit file not found: {audit_path}"

    def test_audit_has_all_tables(self, loaded_db):
        """Audit CSV should have one row per loaded table (12 tables)."""
        import csv

        audit_path = os.path.join(OUTPUT_DIR, "load_audit.csv")
        with open(audit_path, "r") as fh:
            reader = csv.DictReader(fh)
            tables = [row["table"] for row in reader]

        assert len(tables) == 12, f"Expected 12 audit rows, got {len(tables)}"

        expected_tables = {
            "companies", "sectors", "peer_groups", "profitandloss",
            "balancesheet", "cashflow", "financial_ratios", "market_cap",
            "stock_prices", "documents", "analysis", "prosandcons",
        }
        assert set(tables) == expected_tables, f"Missing tables in audit: {expected_tables - set(tables)}"


# ════════════════════════════════════════════════════════════════════
# 7. Numeric Types
# ════════════════════════════════════════════════════════════════════

class TestNumericTypes:
    """Verify numeric columns are stored as REAL, not TEXT."""

    def test_numeric_types_companies(self, loaded_db):
        """face_value, book_value, roce_percentage, roe_percentage should be REAL."""
        row = loaded_db.execute(
            "SELECT face_value, book_value, roce_percentage, roe_percentage "
            "FROM companies LIMIT 1"
        ).fetchone()
        if row:
            for col in ["face_value", "book_value", "roce_percentage", "roe_percentage"]:
                val = row[col]
                assert val is None or isinstance(val, (int, float)), (
                    f"companies.{col} = {val!r} (type={type(val).__name__}) — expected numeric"
                )

    def test_numeric_types_profitandloss(self, loaded_db):
        """P&L numeric columns (sales, net_profit, eps) should be REAL."""
        row = loaded_db.execute(
            "SELECT sales, net_profit, eps FROM profitandloss LIMIT 1"
        ).fetchone()
        if row:
            for col in ["sales", "net_profit", "eps"]:
                val = row[col]
                assert val is None or isinstance(val, (int, float)), (
                    f"profitandloss.{col} = {val!r} (type={type(val).__name__}) — expected numeric"
                )

    def test_numeric_types_stock_prices(self, loaded_db):
        """Stock price numeric columns should be REAL."""
        row = loaded_db.execute(
            "SELECT open_price, close_price, volume FROM stock_prices LIMIT 1"
        ).fetchone()
        if row:
            for col in ["open_price", "close_price", "volume"]:
                val = row[col]
                assert val is None or isinstance(val, (int, float)), (
                    f"stock_prices.{col} = {val!r} (type={type(val).__name__}) — expected numeric"
                )


# ════════════════════════════════════════════════════════════════════
# 8. Documents & Qualitative Tables
# ════════════════════════════════════════════════════════════════════

class TestDocuments:
    """Tests for the documents table."""

    def test_documents_loaded(self, loaded_db):
        """documents table should have rows."""
        (count,) = loaded_db.execute("SELECT COUNT(*) FROM documents").fetchone()
        assert count > 0, "Documents table is empty"

    def test_documents_column_names_lowercase(self, loaded_db):
        """Column names should be lowercase (year, annual_report) not mixed case."""
        cursor = loaded_db.execute("PRAGMA table_info(documents)")
        columns = {row["name"] for row in cursor.fetchall()}
        assert "year" in columns, "'year' column missing (was it loaded as 'Year'?)"
        assert "annual_report" in columns, "'annual_report' column missing (was it loaded as 'Annual_Report'?)"


class TestAnalysis:
    """Tests for the analysis table."""

    def test_analysis_text_columns(self, loaded_db):
        """Growth columns should be stored as TEXT (multi-line strings)."""
        row = loaded_db.execute(
            "SELECT compounded_sales_growth FROM analysis LIMIT 1"
        ).fetchone()
        if row and row["compounded_sales_growth"]:
            val = row["compounded_sales_growth"]
            assert isinstance(val, str), (
                f"analysis.compounded_sales_growth should be TEXT, got {type(val).__name__}"
            )


class TestProsAndCons:
    """Tests for the prosandcons table."""

    def test_prosandcons_loaded(self, loaded_db):
        """prosandcons should have rows loaded."""
        (count,) = loaded_db.execute("SELECT COUNT(*) FROM prosandcons").fetchone()
        assert count > 0, "Pros and cons table is empty"
