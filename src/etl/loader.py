"""
N100 Financial Intelligence Platform — ETL Data Loader.

Reads all 12 Excel source files and loads them into a single SQLite
database (``nifty100.db``) in the correct FK-dependency order.

Usage
-----
    python -m src.etl.loader

The module:

1. Re-creates the database from ``db/schema.sql``
2. Loads each table with header / column-mapping / type-coercion rules
3. Enforces foreign-key integrity (orphan rows are logged and rejected)
4. Writes a per-table audit trail to ``output/load_audit.csv``
5. Prints a rich summary table to stdout

Author: CH Kaushik
"""

import sqlite3
import pandas as pd
import os
import csv
import logging
import math
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from src.etl.normaliser import normalize_year, normalize_ticker, coerce_numeric

# ════════════════════════════════════════════════════════════════════
# Logging
# ════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════════
# Path Configuration
# ════════════════════════════════════════════════════════════════════

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(os.path.dirname(PROJECT_ROOT), "n100")
SUPPLEMENTARY_DIR = os.path.join(DATA_DIR, "supporting datasets")
DB_PATH = os.path.join(PROJECT_ROOT, "nifty100.db")
SCHEMA_PATH = os.path.join(PROJECT_ROOT, "db", "schema.sql")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")

# ════════════════════════════════════════════════════════════════════
# Load Configuration — one entry per table, in FK-dependency order
# ════════════════════════════════════════════════════════════════════
#
# Fields
# ------
# table            : target SQLite table name
# file             : absolute path to source Excel file
# sheet            : Excel sheet name
# header_row       : row index to use as column header (0 or 1)
# column_map       : {excel_col → db_col} renames  (empty dict = none)
# db_columns       : ordered list of DB columns to INSERT (excluding
#                    auto-increment PKs that SQLite should generate)
# pk_column        : which column holds the primary key
# numeric_columns  : list of columns to pass through coerce_numeric
# year_column      : name of the year/date column to normalise (or None)
# has_company_fk   : whether company_id is a FK that must exist in companies
# text_columns     : columns that should remain TEXT (no coercion)

LOAD_CONFIG: List[Dict[str, Any]] = [
    # ─── 1. companies (master table — no FK) ─────────────────────────
    {
        "table": "companies",
        "file": os.path.join(DATA_DIR, "companies.xlsx"),
        "sheet": "Companies",
        "header_row": 1,
        "column_map": {"id": "company_id"},
        "db_columns": [
            "company_id", "company_name", "company_logo", "chart_link",
            "about_company", "website", "nse_profile", "bse_profile",
            "face_value", "book_value", "roce_percentage", "roe_percentage",
        ],
        "pk_column": "company_id",
        "numeric_columns": ["face_value", "book_value", "roce_percentage", "roe_percentage"],
        "year_column": None,
        "has_company_fk": False,
        "text_columns": [
            "company_id", "company_name", "company_logo", "chart_link",
            "about_company", "website", "nse_profile", "bse_profile",
        ],
    },
    # ─── 2. sectors ──────────────────────────────────────────────────
    {
        "table": "sectors",
        "file": os.path.join(SUPPLEMENTARY_DIR, "sectors.xlsx"),
        "sheet": "Sheet1",
        "header_row": 0,
        "column_map": {},
        "db_columns": [
            "id", "company_id", "broad_sector", "sub_sector",
            "index_weight_pct", "market_cap_category",
        ],
        "pk_column": "id",
        "numeric_columns": ["index_weight_pct"],
        "year_column": None,
        "has_company_fk": True,
        "text_columns": ["company_id", "broad_sector", "sub_sector", "market_cap_category"],
    },
    # ─── 3. peer_groups ──────────────────────────────────────────────
    {
        "table": "peer_groups",
        "file": os.path.join(SUPPLEMENTARY_DIR, "peer_groups.xlsx"),
        "sheet": "Sheet1",
        "header_row": 0,
        "column_map": {},
        "db_columns": [
            "id", "peer_group_name", "company_id", "is_benchmark",
        ],
        "pk_column": "id",
        "numeric_columns": [],
        "year_column": None,
        "has_company_fk": True,
        "text_columns": ["peer_group_name", "company_id"],
    },
    # ─── 4. profitandloss ────────────────────────────────────────────
    {
        "table": "profitandloss",
        "file": os.path.join(DATA_DIR, "profitandloss.xlsx"),
        "sheet": "Profit & Loss",
        "header_row": 1,
        "column_map": {},
        "db_columns": [
            "id", "company_id", "year", "sales", "expenses",
            "operating_profit", "opm_percentage", "other_income",
            "interest", "depreciation", "profit_before_tax",
            "tax_percentage", "net_profit", "eps", "dividend_payout",
        ],
        "pk_column": "id",
        "numeric_columns": [
            "sales", "expenses", "operating_profit", "opm_percentage",
            "other_income", "interest", "depreciation", "profit_before_tax",
            "tax_percentage", "net_profit", "eps", "dividend_payout",
        ],
        "year_column": "year",
        "has_company_fk": True,
        "text_columns": ["company_id"],
    },
    # ─── 5. balancesheet ─────────────────────────────────────────────
    {
        "table": "balancesheet",
        "file": os.path.join(DATA_DIR, "balancesheet.xlsx"),
        "sheet": "Balance Sheet",
        "header_row": 1,
        "column_map": {},
        "db_columns": [
            "id", "company_id", "year", "equity_capital", "reserves",
            "borrowings", "other_liabilities", "total_liabilities",
            "fixed_assets", "cwip", "investments", "other_asset",
            "total_assets",
        ],
        "pk_column": "id",
        "numeric_columns": [
            "equity_capital", "reserves", "borrowings",
            "other_liabilities", "total_liabilities", "fixed_assets",
            "cwip", "investments", "other_asset", "total_assets",
        ],
        "year_column": "year",
        "has_company_fk": True,
        "text_columns": ["company_id"],
    },
    # ─── 6. cashflow ─────────────────────────────────────────────────
    {
        "table": "cashflow",
        "file": os.path.join(DATA_DIR, "cashflow.xlsx"),
        "sheet": "Cash Flow",
        "header_row": 1,
        "column_map": {},
        "db_columns": [
            "id", "company_id", "year", "operating_activity",
            "investing_activity", "financing_activity", "net_cash_flow",
        ],
        "pk_column": "id",
        "numeric_columns": [
            "operating_activity", "investing_activity",
            "financing_activity", "net_cash_flow",
        ],
        "year_column": "year",
        "has_company_fk": True,
        "text_columns": ["company_id"],
    },
    # ─── 7. financial_ratios ─────────────────────────────────────────
    {
        "table": "financial_ratios",
        "file": os.path.join(SUPPLEMENTARY_DIR, "financial_ratios.xlsx"),
        "sheet": "Sheet1",
        "header_row": 0,
        "column_map": {},
        "db_columns": [
            "id", "company_id", "year",
            "net_profit_margin_pct", "operating_profit_margin_pct",
            "return_on_equity_pct", "debt_to_equity", "interest_coverage",
            "asset_turnover", "free_cash_flow_cr", "capex_cr",
            "earnings_per_share", "book_value_per_share",
            "dividend_payout_ratio_pct", "total_debt_cr",
            "cash_from_operations_cr",
        ],
        "pk_column": "id",
        "numeric_columns": [
            "net_profit_margin_pct", "operating_profit_margin_pct",
            "return_on_equity_pct", "debt_to_equity", "interest_coverage",
            "asset_turnover", "free_cash_flow_cr", "capex_cr",
            "earnings_per_share", "book_value_per_share",
            "dividend_payout_ratio_pct", "total_debt_cr",
            "cash_from_operations_cr",
        ],
        "year_column": "year",
        "has_company_fk": True,
        "text_columns": ["company_id"],
    },
    # ─── 8. market_cap ───────────────────────────────────────────────
    {
        "table": "market_cap",
        "file": os.path.join(SUPPLEMENTARY_DIR, "market_cap.xlsx"),
        "sheet": "Sheet1",
        "header_row": 0,
        "column_map": {},
        "db_columns": [
            "id", "company_id", "year",
            "market_cap_crore", "enterprise_value_crore",
            "pe_ratio", "pb_ratio", "ev_ebitda", "dividend_yield_pct",
        ],
        "pk_column": "id",
        "numeric_columns": [
            "market_cap_crore", "enterprise_value_crore",
            "pe_ratio", "pb_ratio", "ev_ebitda", "dividend_yield_pct",
        ],
        "year_column": "year",
        "has_company_fk": True,
        "text_columns": ["company_id"],
    },
    # ─── 9. stock_prices ─────────────────────────────────────────────
    {
        "table": "stock_prices",
        "file": os.path.join(SUPPLEMENTARY_DIR, "stock_prices.xlsx"),
        "sheet": "Sheet1",
        "header_row": 0,
        "column_map": {},
        "db_columns": [
            "id", "company_id", "date",
            "open_price", "high_price", "low_price", "close_price",
            "volume", "adjusted_close",
        ],
        "pk_column": "id",
        "numeric_columns": [
            "open_price", "high_price", "low_price", "close_price",
            "volume", "adjusted_close",
        ],
        "year_column": None,  # date is already ISO, no normalisation needed
        "has_company_fk": True,
        "text_columns": ["company_id", "date"],
    },
    # ─── 10. documents ───────────────────────────────────────────────
    {
        "table": "documents",
        "file": os.path.join(DATA_DIR, "documents.xlsx"),
        "sheet": "Documents",
        "header_row": 1,
        "column_map": {"Year": "year", "Annual_Report": "annual_report"},
        "db_columns": ["id", "company_id", "year", "annual_report"],
        "pk_column": "id",
        "numeric_columns": [],
        "year_column": "year",
        "has_company_fk": True,
        "text_columns": ["company_id", "annual_report"],
    },
    # ─── 11. analysis ────────────────────────────────────────────────
    {
        "table": "analysis",
        "file": os.path.join(DATA_DIR, "analysis.xlsx"),
        "sheet": "Analysis",
        "header_row": 1,
        "column_map": {},
        "db_columns": [
            "id", "company_id",
            "compounded_sales_growth", "compounded_profit_growth",
            "stock_price_cagr", "roe",
        ],
        "pk_column": "id",
        "numeric_columns": [],  # all TEXT (multi-line growth strings)
        "year_column": None,
        "has_company_fk": True,
        "text_columns": [
            "company_id", "compounded_sales_growth",
            "compounded_profit_growth", "stock_price_cagr", "roe",
        ],
    },
    # ─── 12. prosandcons ─────────────────────────────────────────────
    {
        "table": "prosandcons",
        "file": os.path.join(DATA_DIR, "prosandcons.xlsx"),
        "sheet": "Pros & Cons",
        "header_row": 1,
        "column_map": {},
        "db_columns": ["id", "company_id", "pros", "cons"],
        "pk_column": "id",
        "numeric_columns": [],
        "year_column": None,
        "has_company_fk": True,
        "text_columns": ["company_id", "pros", "cons"],
    },
]


# ════════════════════════════════════════════════════════════════════
# Helper — Read & Transform an Excel Sheet
# ════════════════════════════════════════════════════════════════════

def _read_excel(config: Dict[str, Any]) -> pd.DataFrame:
    """Read an Excel file according to *config* and return a cleaned DataFrame."""

    filepath = config["file"]
    sheet = config["sheet"]
    header_row = config["header_row"]

    logger.info("Reading %s  [sheet=%r  header=%d]", os.path.basename(filepath), sheet, header_row)

    df = pd.read_excel(filepath, sheet_name=sheet, header=header_row)

    # ── Column renames ───────────────────────────────────────────────
    if config["column_map"]:
        df = df.rename(columns=config["column_map"])

    # Lowercase ALL column names for uniformity
    df.columns = [str(c).strip().lower() for c in df.columns]

    # ── Ensure only expected columns survive ─────────────────────────
    expected = config["db_columns"]
    # Keep only columns that the DB expects (in that order)
    available = [c for c in expected if c in df.columns]
    missing = [c for c in expected if c not in df.columns]
    if missing:
        logger.warning("Table %s — missing columns in source: %s", config["table"], missing)
        # Add missing columns as NaN so downstream doesn't break
        for col in missing:
            df[col] = None
        available = expected

    df = df[available]

    return df


# ════════════════════════════════════════════════════════════════════
# Helper — Normalise a single row's values
# ════════════════════════════════════════════════════════════════════

def _normalise_row(
    row: Dict[str, Any],
    config: Dict[str, Any],
    valid_company_ids: set,
) -> Tuple[Dict[str, Any], bool, Optional[str]]:
    """Apply ticker, year, and numeric normalisations to a row dict.

    Returns
    -------
    (normalised_row, is_orphan, reject_reason)
        *is_orphan* is True when company_id is not in the master set.
        *reject_reason* is set only if the row should be skipped before
        attempting INSERT (e.g. empty PK).
    """
    table = config["table"]

    # ── 1. Normalise company_id / ticker ─────────────────────────────
    if "company_id" in row:
        raw_ticker = row["company_id"]
        try:
            row["company_id"] = normalize_ticker(raw_ticker)
        except (ValueError, TypeError):
            return row, False, f"Invalid company_id: {raw_ticker!r}"

    # ── 2. Normalise year column ─────────────────────────────────────
    year_col = config["year_column"]
    if year_col and year_col in row:
        raw_year = row[year_col]
        try:
            row[year_col] = normalize_year(raw_year)
        except (ValueError, TypeError):
            return row, False, f"Invalid year: {raw_year!r}"

    # ── 3. Coerce numeric columns ────────────────────────────────────
    for col in config["numeric_columns"]:
        if col in row:
            row[col] = coerce_numeric(row[col])

    # ── 4. Handle is_benchmark boolean → int ─────────────────────────
    if table == "peer_groups" and "is_benchmark" in row:
        val = row["is_benchmark"]
        if isinstance(val, bool):
            row["is_benchmark"] = 1 if val else 0
        elif isinstance(val, str):
            row["is_benchmark"] = 1 if val.strip().lower() in ("true", "1", "yes") else 0
        elif val is None or (isinstance(val, float) and math.isnan(val)):
            row["is_benchmark"] = 0
        else:
            row["is_benchmark"] = int(bool(val))

    # ── 5. Clean text columns (strip, NaN → None) ───────────────────
    for col in config.get("text_columns", []):
        if col in row:
            val = row[col]
            if val is None:
                continue
            if isinstance(val, float) and math.isnan(val):
                row[col] = None
            elif isinstance(val, str):
                row[col] = val.strip() if val.strip() else None

    # ── 6. Coerce PK id to int where applicable ─────────────────────
    pk = config["pk_column"]
    if pk == "id" and pk in row:
        raw_pk = row[pk]
        try:
            row["id"] = int(float(raw_pk)) if raw_pk is not None else None
        except (ValueError, TypeError):
            pass  # will fail on INSERT

    # ── 7. FK check ──────────────────────────────────────────────────
    is_orphan = False
    if config["has_company_fk"] and "company_id" in row:
        cid = row["company_id"]
        if cid and cid not in valid_company_ids:
            is_orphan = True

    return row, is_orphan, None


# ════════════════════════════════════════════════════════════════════
# Core — Load a Single Table
# ════════════════════════════════════════════════════════════════════

def load_table(conn: sqlite3.Connection, config: Dict[str, Any], valid_company_ids: set) -> Dict[str, Any]:
    """Load one Excel sheet into its corresponding SQLite table.

    Returns an audit-trail dict with statistics.
    """
    table = config["table"]
    start = datetime.now()

    # Read source
    df = _read_excel(config)
    total_source = len(df)
    logger.info("Table %-20s — %d rows in source", table, total_source)

    # Prepare INSERT statement
    db_columns = config["db_columns"]
    placeholders = ", ".join(["?"] * len(db_columns))
    col_list = ", ".join(db_columns)
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"

    rows_loaded = 0
    rows_rejected = 0
    orphan_count = 0

    for idx, pandas_row in df.iterrows():
        row = pandas_row.to_dict()

        # Normalise
        row, is_orphan, reject_reason = _normalise_row(row, config, valid_company_ids)

        if reject_reason:
            logger.debug("Table %s row %d SKIPPED: %s", table, idx, reject_reason)
            rows_rejected += 1
            continue

        if is_orphan:
            orphan_count += 1
            logger.debug(
                "Table %s row %d — orphan company_id=%r (not in companies)",
                table, idx, row.get("company_id"),
            )

        # Build values tuple in column order
        values = []
        for col in db_columns:
            val = row.get(col)
            # Convert NaN / NaT → None for SQLite
            if isinstance(val, float) and math.isnan(val):
                val = None
            elif pd.isna(val) if not isinstance(val, str) else False:
                val = None
            values.append(val)

        try:
            conn.execute(sql, values)
        except sqlite3.IntegrityError as exc:
            rows_rejected += 1
            logger.debug("Table %s row %d IntegrityError: %s", table, idx, exc)
        except sqlite3.Error as exc:
            rows_rejected += 1
            logger.warning("Table %s row %d SQLite error: %s", table, idx, exc)
        else:
            rows_loaded += 1

    conn.commit()
    elapsed = (datetime.now() - start).total_seconds()

    logger.info(
        "Table %-20s — loaded %d / %d  (rejected %d, orphans %d)  [%.2fs]",
        table, rows_loaded, total_source, rows_rejected, orphan_count, elapsed,
    )

    return {
        "table": table,
        "source_file": os.path.basename(config["file"]),
        "total_rows_source": total_source,
        "rows_loaded": rows_loaded,
        "rows_rejected": rows_rejected,
        "orphan_rows": orphan_count,
        "elapsed_seconds": round(elapsed, 3),
        "timestamp": start.isoformat(),
    }


# ════════════════════════════════════════════════════════════════════
# Audit Trail — write CSV
# ════════════════════════════════════════════════════════════════════

def save_audit(results: List[Dict[str, Any]]) -> str:
    """Write per-table load statistics to ``output/load_audit.csv``.

    Returns the absolute path to the CSV file.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    audit_path = os.path.join(OUTPUT_DIR, "load_audit.csv")

    fieldnames = [
        "table", "source_file", "total_rows_source",
        "rows_loaded", "rows_rejected", "orphan_rows",
        "elapsed_seconds", "timestamp",
    ]

    with open(audit_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    logger.info("Audit trail written to %s", audit_path)
    return audit_path


# ════════════════════════════════════════════════════════════════════
# Rich Summary
# ════════════════════════════════════════════════════════════════════

def print_summary(results: List[Dict[str, Any]]) -> None:
    """Print a colourful summary table using the rich library."""
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.text import Text

        console = Console()

        console.print()
        console.rule("[bold cyan]N100 ETL Load Summary[/bold cyan]")
        console.print()

        table = Table(
            title="Per-Table Statistics",
            show_header=True,
            header_style="bold magenta",
            border_style="dim",
            title_style="bold white",
        )

        table.add_column("Table", style="cyan", no_wrap=True)
        table.add_column("Source File", style="dim")
        table.add_column("Source Rows", justify="right")
        table.add_column("Loaded", justify="right", style="green")
        table.add_column("Rejected", justify="right", style="red")
        table.add_column("Orphans", justify="right", style="yellow")
        table.add_column("Time (s)", justify="right", style="dim")

        total_source = 0
        total_loaded = 0
        total_rejected = 0

        for r in results:
            total_source += r["total_rows_source"]
            total_loaded += r["rows_loaded"]
            total_rejected += r["rows_rejected"]

            # Colour rejected count if > 0
            rejected_str = str(r["rows_rejected"])
            if r["rows_rejected"] > 0:
                rejected_str = f"[bold red]{r['rows_rejected']}[/bold red]"

            table.add_row(
                r["table"],
                r["source_file"],
                str(r["total_rows_source"]),
                str(r["rows_loaded"]),
                rejected_str,
                str(r["orphan_rows"]),
                str(r["elapsed_seconds"]),
            )

        # Totals row
        table.add_section()
        table.add_row(
            "[bold]TOTAL[/bold]", "",
            f"[bold]{total_source}[/bold]",
            f"[bold green]{total_loaded}[/bold green]",
            f"[bold red]{total_rejected}[/bold red]",
            "", "",
        )

        console.print(table)
        console.print()

        # Success / partial-success message
        if total_rejected == 0:
            console.print("[bold green]✅ All rows loaded successfully![/bold green]")
        else:
            pct = (total_loaded / total_source * 100) if total_source else 0
            console.print(
                f"[bold yellow]⚠  {total_loaded}/{total_source} rows loaded "
                f"({pct:.1f}%) — {total_rejected} rejected[/bold yellow]"
            )
        console.print()

    except ImportError:
        # Fallback if rich is not installed
        logger.info("=" * 60)
        logger.info("  ETL Load Summary")
        logger.info("=" * 60)
        for r in results:
            logger.info(
                "  %-20s  src=%d  loaded=%d  rejected=%d",
                r["table"], r["total_rows_source"], r["rows_loaded"], r["rows_rejected"],
            )
        logger.info("=" * 60)


# ════════════════════════════════════════════════════════════════════
# Orchestrator — load_all()
# ════════════════════════════════════════════════════════════════════

def load_all(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Execute the full ETL pipeline.

    Parameters
    ----------
    db_path : str, optional
        Override the default database path (useful for testing).
        If ``None``, uses the module-level ``DB_PATH``.

    Returns
    -------
    list[dict]
        Audit-trail records, one per table.
    """
    target_db = db_path or DB_PATH

    # ── 1. Remove old database ───────────────────────────────────────
    if os.path.exists(target_db):
        os.remove(target_db)
        logger.info("Removed existing database: %s", target_db)

    # ── 2. Connect & create schema ───────────────────────────────────
    conn = sqlite3.connect(target_db)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")

    logger.info("Creating schema from %s", SCHEMA_PATH)
    with open(SCHEMA_PATH, "r") as fh:
        conn.executescript(fh.read())

    # ── 3. Load tables in order ──────────────────────────────────────
    #    After loading companies, cache the valid company_ids for
    #    FK validation on all subsequent tables.
    valid_company_ids: set = set()
    audit_results: List[Dict[str, Any]] = []

    for config in LOAD_CONFIG:
        result = load_table(conn, config, valid_company_ids)
        audit_results.append(result)

        # After loading companies, populate the FK lookup set
        if config["table"] == "companies":
            cursor = conn.execute("SELECT company_id FROM companies")
            valid_company_ids = {row[0] for row in cursor.fetchall()}
            logger.info("Loaded %d valid company_ids for FK checks", len(valid_company_ids))

    # ── 4. Final FK integrity check ──────────────────────────────────
    fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if fk_violations:
        logger.warning("PRAGMA foreign_key_check found %d violations", len(fk_violations))
        for v in fk_violations[:10]:
            logger.warning("  FK violation: %s", v)
    else:
        logger.info("PRAGMA foreign_key_check — 0 violations ✓")

    conn.close()

    # ── 5. Write audit CSV & print summary ───────────────────────────
    save_audit(audit_results)
    print_summary(audit_results)

    logger.info("Database written to %s", target_db)
    return audit_results


# ════════════════════════════════════════════════════════════════════
# Entry Point
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    load_all()
