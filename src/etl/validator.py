"""
N100 Financial Intelligence Platform — Data Quality Validator
=============================================================
Runs 16 DQ (Data-Quality) rules against the nifty100.db SQLite database
and produces:
  • output/validation_failures.csv  – every failing row
  • A colour-coded Rich summary table printed to the console

Usage:
    python -m src.etl.validator
"""

import sqlite3
import csv
import os
import json
from datetime import datetime

from rich.console import Console
from rich.table import Table

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TABLES_WITH_ID_PK = [
    "profitandloss",
    "balancesheet",
    "cashflow",
    "financial_ratios",
    "documents",
    "stock_prices",
]

COMPOSITE_KEY_TABLES = [
    "profitandloss",
    "balancesheet",
    "cashflow",
    "financial_ratios",
]

KEY_TABLES = ["profitandloss", "balancesheet", "cashflow"]

SEVERITY_COLOURS = {
    "CRITICAL": "bold red",
    "WARNING": "yellow",
    "INFO": "blue",
}


def _table_exists(conn, table_name):
    """Return True if *table_name* exists in the database."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cur.fetchone() is not None


def _get_all_tables(conn):
    """Return a list of all user tables in the database."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%'"
    )
    return [row[0] for row in cur.fetchall()]


def _get_columns(conn, table):
    """Return column names for *table*."""
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cur.fetchall()]


def _build_result(rule_id, severity, table, description, failing_count, sample_rows=None):
    """Construct a standardised result dict."""
    return {
        "rule_id": rule_id,
        "severity": severity,
        "table": table,
        "description": description,
        "failing_count": failing_count,
        "sample_rows": json.dumps(sample_rows[:5]) if sample_rows else "",
    }


# ---------------------------------------------------------------------------
# DQ Rules
# ---------------------------------------------------------------------------


def run_dq_01(conn):
    """DQ-01 · CRITICAL · PK uniqueness across all tables."""
    results = []

    # companies table uses company_id as PK
    if _table_exists(conn, "companies"):
        cur = conn.execute(
            "SELECT company_id, COUNT(*) AS cnt "
            "FROM companies GROUP BY company_id HAVING cnt > 1"
        )
        rows = cur.fetchall()
        results.append(
            _build_result(
                "DQ-01", "CRITICAL", "companies",
                "Primary-key (company_id) uniqueness",
                len(rows),
                [{"company_id": r[0], "count": r[1]} for r in rows],
            )
        )

    # Other tables use 'id' as PK
    for table in TABLES_WITH_ID_PK:
        if not _table_exists(conn, table):
            continue
        columns = _get_columns(conn, table)
        if "id" not in columns:
            continue
        cur = conn.execute(
            f"SELECT id, COUNT(*) AS cnt FROM {table} GROUP BY id HAVING cnt > 1"
        )
        rows = cur.fetchall()
        results.append(
            _build_result(
                "DQ-01", "CRITICAL", table,
                "Primary-key (id) uniqueness",
                len(rows),
                [{"id": r[0], "count": r[1]} for r in rows],
            )
        )

    return results


def run_dq_02(conn):
    """DQ-02 · CRITICAL · Composite key (company_id, year) uniqueness."""
    results = []
    for table in COMPOSITE_KEY_TABLES:
        if not _table_exists(conn, table):
            continue
        columns = _get_columns(conn, table)
        if "company_id" not in columns or "year" not in columns:
            continue
        cur = conn.execute(
            f"SELECT company_id, year, COUNT(*) AS cnt "
            f"FROM {table} GROUP BY company_id, year HAVING cnt > 1"
        )
        rows = cur.fetchall()
        results.append(
            _build_result(
                "DQ-02", "CRITICAL", table,
                "Composite key (company_id, year) uniqueness",
                len(rows),
                [{"company_id": r[0], "year": r[1], "count": r[2]} for r in rows],
            )
        )
    return results


def run_dq_03(conn):
    """DQ-03 · CRITICAL · Foreign-key integrity."""
    cur = conn.execute("PRAGMA foreign_key_check")
    rows = cur.fetchall()
    return [
        _build_result(
            "DQ-03", "CRITICAL", "all",
            "Foreign-key integrity (PRAGMA foreign_key_check)",
            len(rows),
            [{"table": r[0], "rowid": r[1], "parent": r[2], "fkid": r[3]} for r in rows],
        )
    ]


def run_dq_04(conn):
    """DQ-04 · WARNING · Balance-sheet equation: assets ≈ liabilities (1 %)."""
    results = []
    if not _table_exists(conn, "balancesheet"):
        return results
    cur = conn.execute(
        "SELECT id, company_id, year, total_assets, total_liabilities, "
        "abs(total_assets - total_liabilities) / NULLIF(total_assets, 0) AS diff_pct "
        "FROM balancesheet "
        "WHERE total_assets IS NOT NULL AND total_liabilities IS NOT NULL "
        "AND abs(total_assets - total_liabilities) / NULLIF(total_assets, 0) >= 0.01"
    )
    rows = cur.fetchall()
    results.append(
        _build_result(
            "DQ-04", "WARNING", "balancesheet",
            "Balance check: |total_assets − total_liabilities| / total_assets < 1 %",
            len(rows),
            [{"id": r[0], "company_id": r[1], "year": r[2],
              "total_assets": r[3], "total_liabilities": r[4],
              "diff_pct": round(r[5], 4) if r[5] else None} for r in rows],
        )
    )
    return results


def run_dq_05(conn):
    """DQ-05 · WARNING · OPM cross-check within 2 % tolerance."""
    results = []
    if not _table_exists(conn, "profitandloss"):
        return results
    columns = _get_columns(conn, "profitandloss")
    needed = {"opm_percentage", "operating_profit", "sales"}
    if not needed.issubset(set(columns)):
        return results
    cur = conn.execute(
        "SELECT id, company_id, year, opm_percentage, operating_profit, sales, "
        "abs(opm_percentage - (operating_profit / NULLIF(sales, 0)) * 100) AS opm_diff "
        "FROM profitandloss "
        "WHERE opm_percentage IS NOT NULL AND sales IS NOT NULL AND sales != 0 "
        "AND abs(opm_percentage - (operating_profit / NULLIF(sales, 0)) * 100) >= 2"
    )
    rows = cur.fetchall()
    results.append(
        _build_result(
            "DQ-05", "WARNING", "profitandloss",
            "OPM cross-check: |stored OPM − computed OPM| < 2 %",
            len(rows),
            [{"id": r[0], "company_id": r[1], "year": r[2],
              "opm_pct": r[3], "op": r[4], "sales": r[5],
              "diff": round(r[6], 4) if r[6] else None} for r in rows],
        )
    )
    return results


def run_dq_06(conn):
    """DQ-06 · WARNING · Positive sales check."""
    results = []
    if not _table_exists(conn, "profitandloss"):
        return results
    cur = conn.execute(
        "SELECT id, company_id, year, sales "
        "FROM profitandloss WHERE sales IS NOT NULL AND sales <= 0"
    )
    rows = cur.fetchall()
    results.append(
        _build_result(
            "DQ-06", "WARNING", "profitandloss",
            "Positive sales: sales > 0",
            len(rows),
            [{"id": r[0], "company_id": r[1], "year": r[2], "sales": r[3]} for r in rows],
        )
    )
    return results


def run_dq_07(conn):
    """DQ-07 · WARNING · Net cash-flow = operating + investing + financing (±₹1 Cr)."""
    results = []
    if not _table_exists(conn, "cashflow"):
        return results
    columns = _get_columns(conn, "cashflow")
    needed = {"net_cash_flow", "operating_activity", "investing_activity", "financing_activity"}
    if not needed.issubset(set(columns)):
        return results
    cur = conn.execute(
        "SELECT id, company_id, year, net_cash_flow, "
        "operating_activity, investing_activity, financing_activity, "
        "abs(net_cash_flow - (operating_activity + investing_activity + financing_activity)) AS diff "
        "FROM cashflow "
        "WHERE net_cash_flow IS NOT NULL "
        "AND operating_activity IS NOT NULL "
        "AND investing_activity IS NOT NULL "
        "AND financing_activity IS NOT NULL "
        "AND abs(net_cash_flow - (operating_activity + investing_activity + financing_activity)) > 1"
    )
    rows = cur.fetchall()
    results.append(
        _build_result(
            "DQ-07", "WARNING", "cashflow",
            "Net cash = operating + investing + financing (within ₹1 Cr)",
            len(rows),
            [{"id": r[0], "company_id": r[1], "year": r[2],
              "net_cf": r[3], "ops": r[4], "inv": r[5], "fin": r[6],
              "diff": round(r[7], 2) if r[7] else None} for r in rows],
        )
    )
    return results


def run_dq_08(conn):
    """DQ-08 · WARNING · Tax-rate sanity: 0 ≤ tax % ≤ 50."""
    results = []
    if not _table_exists(conn, "profitandloss"):
        return results
    columns = _get_columns(conn, "profitandloss")
    if "tax_percentage" not in columns:
        return results
    cur = conn.execute(
        "SELECT id, company_id, year, tax_percentage "
        "FROM profitandloss "
        "WHERE tax_percentage IS NOT NULL "
        "AND (tax_percentage < 0 OR tax_percentage > 50)"
    )
    rows = cur.fetchall()
    results.append(
        _build_result(
            "DQ-08", "WARNING", "profitandloss",
            "Tax-rate sanity: 0 ≤ tax_percentage ≤ 50",
            len(rows),
            [{"id": r[0], "company_id": r[1], "year": r[2], "tax_pct": r[3]} for r in rows],
        )
    )
    return results


def run_dq_09(conn):
    """DQ-09 · WARNING · Dividend cap: dividend_payout ≤ net_profit."""
    results = []
    if not _table_exists(conn, "profitandloss"):
        return results
    columns = _get_columns(conn, "profitandloss")
    if "dividend_payout" not in columns or "net_profit" not in columns:
        return results
    cur = conn.execute(
        "SELECT id, company_id, year, dividend_payout, net_profit "
        "FROM profitandloss "
        "WHERE dividend_payout IS NOT NULL AND net_profit IS NOT NULL "
        "AND net_profit > 0 AND dividend_payout > net_profit"
    )
    rows = cur.fetchall()
    results.append(
        _build_result(
            "DQ-09", "WARNING", "profitandloss",
            "Dividend cap: dividend_payout ≤ net_profit (where net_profit > 0)",
            len(rows),
            [{"id": r[0], "company_id": r[1], "year": r[2],
              "div": r[3], "net_profit": r[4]} for r in rows],
        )
    )
    return results


def run_dq_10(conn):
    """DQ-10 · INFO · URL format for annual_report."""
    results = []
    if not _table_exists(conn, "documents"):
        return results
    columns = _get_columns(conn, "documents")
    if "annual_report" not in columns:
        return results
    cur = conn.execute(
        "SELECT id, company_id, annual_report "
        "FROM documents "
        "WHERE annual_report IS NOT NULL AND annual_report NOT LIKE 'http%'"
    )
    rows = cur.fetchall()
    results.append(
        _build_result(
            "DQ-10", "INFO", "documents",
            "URL format: annual_report should start with 'http'",
            len(rows),
            [{"id": r[0], "company_id": r[1], "annual_report": r[2]} for r in rows],
        )
    )
    return results


def run_dq_11(conn):
    """DQ-11 · WARNING · EPS sign must match net_profit sign."""
    results = []
    if not _table_exists(conn, "profitandloss"):
        return results
    columns = _get_columns(conn, "profitandloss")
    if "eps" not in columns or "net_profit" not in columns:
        return results
    cur = conn.execute(
        "SELECT id, company_id, year, eps, net_profit "
        "FROM profitandloss "
        "WHERE eps IS NOT NULL AND net_profit IS NOT NULL "
        "AND eps != 0 AND net_profit != 0 "
        "AND SIGN(eps) != SIGN(net_profit)"
    )
    rows = cur.fetchall()
    results.append(
        _build_result(
            "DQ-11", "WARNING", "profitandloss",
            "EPS sign consistency: sign(eps) = sign(net_profit)",
            len(rows),
            [{"id": r[0], "company_id": r[1], "year": r[2],
              "eps": r[3], "net_profit": r[4]} for r in rows],
        )
    )
    return results


def run_dq_12(conn):
    """DQ-12 · WARNING · Liability decomposition within 1 %."""
    results = []
    if not _table_exists(conn, "balancesheet"):
        return results
    columns = _get_columns(conn, "balancesheet")
    needed = {"total_liabilities", "equity_capital", "reserves", "borrowings", "other_liabilities"}
    if not needed.issubset(set(columns)):
        return results
    cur = conn.execute(
        "SELECT id, company_id, year, total_liabilities, "
        "equity_capital, reserves, borrowings, other_liabilities, "
        "abs(total_liabilities - (equity_capital + reserves + borrowings + other_liabilities)) "
        "  / NULLIF(total_liabilities, 0) AS diff_pct "
        "FROM balancesheet "
        "WHERE total_liabilities IS NOT NULL "
        "AND equity_capital IS NOT NULL AND reserves IS NOT NULL "
        "AND borrowings IS NOT NULL AND other_liabilities IS NOT NULL "
        "AND abs(total_liabilities - (equity_capital + reserves + borrowings + other_liabilities)) "
        "  / NULLIF(total_liabilities, 0) >= 0.01"
    )
    rows = cur.fetchall()
    results.append(
        _build_result(
            "DQ-12", "WARNING", "balancesheet",
            "Liability decomposition: |total − sum(components)| / total < 1 %",
            len(rows),
            [{"id": r[0], "company_id": r[1], "year": r[2],
              "total_liab": r[3], "diff_pct": round(r[8], 4) if r[8] else None} for r in rows],
        )
    )
    return results


def run_dq_13(conn):
    """DQ-13 · INFO · Year coverage: companies with < 5 years of P&L data."""
    results = []
    if not _table_exists(conn, "profitandloss"):
        return results
    cur = conn.execute(
        "SELECT company_id, COUNT(DISTINCT year) AS yrs "
        "FROM profitandloss GROUP BY company_id HAVING yrs < 5"
    )
    rows = cur.fetchall()
    results.append(
        _build_result(
            "DQ-13", "INFO", "profitandloss",
            "Year coverage: companies with fewer than 5 years of P&L data",
            len(rows),
            [{"company_id": r[0], "years": r[1]} for r in rows],
        )
    )
    return results


def run_dq_14(conn):
    """DQ-14 · WARNING · All 92 companies present in key financial tables."""
    results = []
    if not _table_exists(conn, "companies"):
        return results
    for table in KEY_TABLES:
        if not _table_exists(conn, table):
            continue
        cur = conn.execute(
            f"SELECT c.company_id, c.company_name "
            f"FROM companies c "
            f"WHERE c.company_id NOT IN (SELECT DISTINCT company_id FROM {table})"
        )
        rows = cur.fetchall()
        results.append(
            _build_result(
                "DQ-14", "WARNING", table,
                f"Company completeness: companies missing from {table}",
                len(rows),
                [{"company_id": r[0], "company_name": r[1]} for r in rows],
            )
        )
    return results


def run_dq_15(conn):
    """DQ-15 · INFO · Null percentage > 20 % per column per table."""
    results = []
    for table in _get_all_tables(conn):
        columns = _get_columns(conn, table)
        cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
        total = cur.fetchone()[0]
        if total == 0:
            continue
        high_null_cols = []
        for col in columns:
            cur = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL"
            )
            null_count = cur.fetchone()[0]
            pct = null_count / total
            if pct > 0.20:
                high_null_cols.append(
                    {"column": col, "null_count": null_count,
                     "total": total, "null_pct": round(pct * 100, 2)}
                )
        if high_null_cols:
            results.append(
                _build_result(
                    "DQ-15", "INFO", table,
                    f"Columns with > 20 % NULLs ({len(high_null_cols)} cols)",
                    len(high_null_cols),
                    high_null_cols,
                )
            )
    return results


def run_dq_16(conn):
    """DQ-16 · WARNING · Stock-price sanity checks."""
    results = []
    if not _table_exists(conn, "stock_prices"):
        return results
    columns = _get_columns(conn, "stock_prices")
    needed = {"high_price", "close_price", "low_price", "open_price"}
    if not needed.issubset(set(columns)):
        return results
    cur = conn.execute(
        "SELECT id, company_id, high_price, close_price, low_price, open_price "
        "FROM stock_prices "
        "WHERE NOT ("
        "  high_price >= close_price "
        "  AND close_price >= low_price "
        "  AND open_price > 0"
        ")"
    )
    rows = cur.fetchall()
    results.append(
        _build_result(
            "DQ-16", "WARNING", "stock_prices",
            "Price sanity: high ≥ close ≥ low AND open > 0",
            len(rows),
            [{"id": r[0], "company_id": r[1], "high": r[2],
              "close": r[3], "low": r[4], "open": r[5]} for r in rows],
        )
    )
    return results


# ---------------------------------------------------------------------------
# Runner / IO / Display
# ---------------------------------------------------------------------------

ALL_RULES = [
    run_dq_01, run_dq_02, run_dq_03, run_dq_04,
    run_dq_05, run_dq_06, run_dq_07, run_dq_08,
    run_dq_09, run_dq_10, run_dq_11, run_dq_12,
    run_dq_13, run_dq_14, run_dq_15, run_dq_16,
]


def run_all_rules(db_path):
    """Execute every DQ rule against the database at *db_path*."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    results = []
    for rule_fn in ALL_RULES:
        try:
            results.extend(rule_fn(conn))
        except Exception as exc:  # noqa: BLE001
            results.append(
                _build_result(
                    rule_fn.__doc__.split("·")[0].strip() if rule_fn.__doc__ else "??",
                    "CRITICAL",
                    "error",
                    f"Rule execution error: {exc}",
                    -1,
                )
            )
    conn.close()
    return results


def save_results(results, output_path):
    """Persist *results* as a CSV file."""
    fieldnames = ["rule_id", "severity", "table", "description",
                   "failing_count", "sample_rows"]
    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)


def print_summary(results):
    """Print a colour-coded Rich table summarising every rule result."""
    console = Console()
    console.print()
    console.rule("[bold]N100 Data-Quality Validation Summary[/bold]")
    console.print()

    table = Table(
        title="DQ Rule Results",
        show_lines=True,
        title_style="bold cyan",
    )
    table.add_column("Rule", style="bold", width=8)
    table.add_column("Severity", width=10)
    table.add_column("Table", width=18)
    table.add_column("Description", min_width=30)
    table.add_column("Failures", justify="right", width=10)
    table.add_column("Status", justify="center", width=8)

    pass_count = 0
    fail_count = 0

    for r in results:
        severity = r["severity"]
        style = SEVERITY_COLOURS.get(severity, "")
        failing = r["failing_count"]
        status = "[green]✔ PASS[/green]" if failing == 0 else "[red]✘ FAIL[/red]"

        if failing == 0:
            pass_count += 1
        else:
            fail_count += 1

        table.add_row(
            r["rule_id"],
            f"[{style}]{severity}[/{style}]",
            r["table"],
            r["description"],
            str(failing),
            status,
        )

    console.print(table)
    console.print()
    console.print(
        f"  [green]Passed: {pass_count}[/green]  "
        f"[red]Failed: {fail_count}[/red]  "
        f"Total: {pass_count + fail_count}"
    )
    console.print(
        f"  Run completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    console.print()


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------


def main():
    """CLI entry-point for ``python -m src.etl.validator``."""
    db_path = "nifty100.db"
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)

    console = Console()
    console.print(f"\n[bold cyan]Validating:[/bold cyan] {db_path}")

    results = run_all_rules(db_path)
    output_path = os.path.join(output_dir, "validation_failures.csv")
    save_results(results, output_path)
    console.print(f"[dim]Results saved → {output_path}[/dim]")

    print_summary(results)


if __name__ == "__main__":
    main()
