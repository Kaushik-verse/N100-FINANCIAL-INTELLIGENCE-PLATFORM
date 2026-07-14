-- ════════════════════════════════════════════════════════════════════
-- N100 Financial Intelligence Platform — Database Schema
-- Sprint 1: Data Foundation
-- Author: CH Kaushik
-- 
-- 11 tables · PK/FK constraints · PRAGMA foreign_keys = ON
-- ════════════════════════════════════════════════════════════════════

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ─── Master Table ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS companies (
    company_id          TEXT PRIMARY KEY,
    company_name        TEXT NOT NULL,
    company_logo        TEXT,
    chart_link          TEXT,
    about_company       TEXT,
    website             TEXT,
    nse_profile         TEXT,
    bse_profile         TEXT,
    face_value          REAL,
    book_value          REAL,
    roce_percentage     REAL,
    roe_percentage      REAL
);

-- ─── Classification ────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS sectors (
    id                  INTEGER PRIMARY KEY,
    company_id          TEXT NOT NULL UNIQUE,
    broad_sector        TEXT NOT NULL,
    sub_sector          TEXT NOT NULL,
    index_weight_pct    REAL,
    market_cap_category TEXT,
    FOREIGN KEY (company_id) REFERENCES companies(company_id)
);

CREATE TABLE IF NOT EXISTS peer_groups (
    id                  INTEGER PRIMARY KEY,
    peer_group_name     TEXT NOT NULL,
    company_id          TEXT NOT NULL,
    is_benchmark        INTEGER DEFAULT 0,
    FOREIGN KEY (company_id) REFERENCES companies(company_id)
);

-- ─── Financial Statements ──────────────────────────────────────────

CREATE TABLE IF NOT EXISTS profitandloss (
    id                  INTEGER PRIMARY KEY,
    company_id          TEXT NOT NULL,
    year                TEXT NOT NULL,
    sales               REAL,
    expenses            REAL,
    operating_profit    REAL,
    opm_percentage      REAL,
    other_income        REAL,
    interest            REAL,
    depreciation        REAL,
    profit_before_tax   REAL,
    tax_percentage      REAL,
    net_profit          REAL,
    eps                 REAL,
    dividend_payout     REAL,
    UNIQUE(company_id, year),
    FOREIGN KEY (company_id) REFERENCES companies(company_id)
);

CREATE TABLE IF NOT EXISTS balancesheet (
    id                  INTEGER PRIMARY KEY,
    company_id          TEXT NOT NULL,
    year                TEXT NOT NULL,
    equity_capital      REAL,
    reserves            REAL,
    borrowings          REAL,
    other_liabilities   REAL,
    total_liabilities   REAL,
    fixed_assets        REAL,
    cwip                REAL,
    investments         REAL,
    other_asset         REAL,
    total_assets        REAL,
    UNIQUE(company_id, year),
    FOREIGN KEY (company_id) REFERENCES companies(company_id)
);

CREATE TABLE IF NOT EXISTS cashflow (
    id                  INTEGER PRIMARY KEY,
    company_id          TEXT NOT NULL,
    year                TEXT NOT NULL,
    operating_activity  REAL,
    investing_activity  REAL,
    financing_activity  REAL,
    net_cash_flow       REAL,
    UNIQUE(company_id, year),
    FOREIGN KEY (company_id) REFERENCES companies(company_id)
);

-- ─── Ratios & Valuation ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS financial_ratios (
    id                          INTEGER PRIMARY KEY,
    company_id                  TEXT NOT NULL,
    year                        TEXT NOT NULL,
    net_profit_margin_pct       REAL,
    operating_profit_margin_pct REAL,
    return_on_equity_pct        REAL,
    debt_to_equity              REAL,
    interest_coverage           REAL,
    asset_turnover              REAL,
    free_cash_flow_cr           REAL,
    capex_cr                    REAL,
    earnings_per_share          REAL,
    book_value_per_share        REAL,
    dividend_payout_ratio_pct   REAL,
    total_debt_cr               REAL,
    cash_from_operations_cr     REAL,
    UNIQUE(company_id, year),
    FOREIGN KEY (company_id) REFERENCES companies(company_id)
);

CREATE TABLE IF NOT EXISTS market_cap (
    id                      INTEGER PRIMARY KEY,
    company_id              TEXT NOT NULL,
    year                    INTEGER NOT NULL,
    market_cap_crore        REAL,
    enterprise_value_crore  REAL,
    pe_ratio                REAL,
    pb_ratio                REAL,
    ev_ebitda               REAL,
    dividend_yield_pct      REAL,
    UNIQUE(company_id, year),
    FOREIGN KEY (company_id) REFERENCES companies(company_id)
);

-- ─── Market Data ───────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS stock_prices (
    id                  INTEGER PRIMARY KEY,
    company_id          TEXT NOT NULL,
    date                TEXT NOT NULL,
    open_price          REAL,
    high_price          REAL,
    low_price           REAL,
    close_price         REAL,
    volume              INTEGER,
    adjusted_close      REAL,
    UNIQUE(company_id, date),
    FOREIGN KEY (company_id) REFERENCES companies(company_id)
);

-- ─── Documents & Qualitative ───────────────────────────────────────

CREATE TABLE IF NOT EXISTS documents (
    id                  INTEGER PRIMARY KEY,
    company_id          TEXT NOT NULL,
    year                INTEGER,
    annual_report       TEXT,
    FOREIGN KEY (company_id) REFERENCES companies(company_id)
);

CREATE TABLE IF NOT EXISTS analysis (
    id                          INTEGER PRIMARY KEY,
    company_id                  TEXT NOT NULL,
    compounded_sales_growth     TEXT,
    compounded_profit_growth    TEXT,
    stock_price_cagr            TEXT,
    roe                         TEXT,
    FOREIGN KEY (company_id) REFERENCES companies(company_id)
);

CREATE TABLE IF NOT EXISTS prosandcons (
    id                  INTEGER PRIMARY KEY,
    company_id          TEXT NOT NULL,
    pros                TEXT,
    cons                TEXT,
    FOREIGN KEY (company_id) REFERENCES companies(company_id)
);

-- ─── Indexes for Performance ───────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_pl_company_year ON profitandloss(company_id, year);
CREATE INDEX IF NOT EXISTS idx_bs_company_year ON balancesheet(company_id, year);
CREATE INDEX IF NOT EXISTS idx_cf_company_year ON cashflow(company_id, year);
CREATE INDEX IF NOT EXISTS idx_fr_company_year ON financial_ratios(company_id, year);
CREATE INDEX IF NOT EXISTS idx_mc_company_year ON market_cap(company_id, year);
CREATE INDEX IF NOT EXISTS idx_sp_company_date ON stock_prices(company_id, date);
CREATE INDEX IF NOT EXISTS idx_doc_company ON documents(company_id);
CREATE INDEX IF NOT EXISTS idx_sectors_company ON sectors(company_id);
CREATE INDEX IF NOT EXISTS idx_pg_company ON peer_groups(company_id);
