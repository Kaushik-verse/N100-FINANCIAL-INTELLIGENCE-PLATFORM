-- =============================================================================
-- N100 Financial Intelligence Platform — Exploratory SQL Queries
-- =============================================================================
-- Target database : nifty100.db (SQLite)
-- These queries are designed to be run interactively to explore the data
-- landscape, identify patterns, and surface data-quality signals.
-- =============================================================================


-- ---------------------------------------------------------------------------
-- Query 1: Total number of companies
-- ---------------------------------------------------------------------------
-- Quick sanity check — we expect 92 Nifty-100 companies.
SELECT COUNT(*) AS total_companies
FROM   companies;


-- ---------------------------------------------------------------------------
-- Query 2: Top 10 companies by revenue (latest year)
-- ---------------------------------------------------------------------------
-- Identifies the largest revenue generators in the most recent fiscal year
-- available in the P&L table.
SELECT c.company_name,
       p.year,
       p.sales AS revenue
FROM   profitandloss p
JOIN   companies     c ON c.company_id = p.company_id
WHERE  p.year = (SELECT MAX(year) FROM profitandloss)
ORDER  BY p.sales DESC
LIMIT  10;


-- ---------------------------------------------------------------------------
-- Query 3: Companies by sector distribution
-- ---------------------------------------------------------------------------
-- Shows how many companies fall into each sector/industry classification.
SELECT sector,
       COUNT(*) AS company_count
FROM   companies
GROUP  BY sector
ORDER  BY company_count DESC;


-- ---------------------------------------------------------------------------
-- Query 4: Year-over-year profit growth for top 10 companies
-- ---------------------------------------------------------------------------
-- Computes the YoY net-profit growth rate for the 10 largest companies
-- (by latest-year revenue). Uses a self-join on consecutive years.
WITH top10 AS (
    SELECT company_id
    FROM   profitandloss
    WHERE  year = (SELECT MAX(year) FROM profitandloss)
    ORDER  BY sales DESC
    LIMIT  10
)
SELECT c.company_name,
       cur.year,
       cur.net_profit                                           AS current_profit,
       prev.net_profit                                          AS previous_profit,
       ROUND((cur.net_profit - prev.net_profit)
             / NULLIF(ABS(prev.net_profit), 0) * 100, 2)       AS yoy_growth_pct
FROM   profitandloss cur
JOIN   profitandloss prev ON prev.company_id = cur.company_id
                          AND prev.year      = cur.year - 1
JOIN   companies     c    ON c.company_id    = cur.company_id
WHERE  cur.company_id IN (SELECT company_id FROM top10)
ORDER  BY c.company_name, cur.year;


-- ---------------------------------------------------------------------------
-- Query 5: Companies with highest ROCE (Return on Capital Employed)
-- ---------------------------------------------------------------------------
-- Pulls the top-15 ROCE values from the financial_ratios table for the
-- most recent year available.
SELECT c.company_name,
       fr.year,
       fr.roce AS roce_pct
FROM   financial_ratios fr
JOIN   companies        c ON c.company_id = fr.company_id
WHERE  fr.year = (SELECT MAX(year) FROM financial_ratios)
       AND fr.roce IS NOT NULL
ORDER  BY fr.roce DESC
LIMIT  15;


-- ---------------------------------------------------------------------------
-- Query 6: Debt-to-equity distribution by sector
-- ---------------------------------------------------------------------------
-- Computes the average debt-to-equity ratio per sector for the latest year.
-- A high ratio may indicate capital-intensive industries.
SELECT c.sector,
       ROUND(AVG(b.borrowings / NULLIF(b.equity_capital + b.reserves, 0)), 3)
           AS avg_debt_to_equity,
       COUNT(*) AS companies_counted
FROM   balancesheet b
JOIN   companies    c ON c.company_id = b.company_id
WHERE  b.year = (SELECT MAX(year) FROM balancesheet)
       AND b.borrowings      IS NOT NULL
       AND b.equity_capital  IS NOT NULL
       AND b.reserves        IS NOT NULL
GROUP  BY c.sector
ORDER  BY avg_debt_to_equity DESC;


-- ---------------------------------------------------------------------------
-- Query 7: Stock price performance — latest vs earliest close
-- ---------------------------------------------------------------------------
-- For each company, compares the earliest and latest available closing
-- prices and computes the total return percentage.
WITH bounds AS (
    SELECT company_id,
           MIN(date) AS earliest_date,
           MAX(date) AS latest_date
    FROM   stock_prices
    GROUP  BY company_id
)
SELECT c.company_name,
       sp_early.date       AS earliest_date,
       sp_early.close_price AS earliest_close,
       sp_late.date         AS latest_date,
       sp_late.close_price  AS latest_close,
       ROUND((sp_late.close_price - sp_early.close_price)
             / NULLIF(sp_early.close_price, 0) * 100, 2)
           AS total_return_pct
FROM   bounds b
JOIN   stock_prices sp_early ON sp_early.company_id = b.company_id
                             AND sp_early.date       = b.earliest_date
JOIN   stock_prices sp_late  ON sp_late.company_id  = b.company_id
                             AND sp_late.date        = b.latest_date
JOIN   companies    c        ON c.company_id         = b.company_id
ORDER  BY total_return_pct DESC;


-- ---------------------------------------------------------------------------
-- Query 8: Companies with missing data across key financial tables
-- ---------------------------------------------------------------------------
-- Lists companies that are absent from at least one of the three core
-- financial tables (P&L, Balance Sheet, Cash Flow).
SELECT c.company_id,
       c.company_name,
       CASE WHEN p.company_id  IS NULL THEN 'MISSING' ELSE 'OK' END AS profitandloss,
       CASE WHEN bs.company_id IS NULL THEN 'MISSING' ELSE 'OK' END AS balancesheet,
       CASE WHEN cf.company_id IS NULL THEN 'MISSING' ELSE 'OK' END AS cashflow
FROM   companies c
LEFT   JOIN (SELECT DISTINCT company_id FROM profitandloss) p  ON p.company_id  = c.company_id
LEFT   JOIN (SELECT DISTINCT company_id FROM balancesheet)  bs ON bs.company_id = c.company_id
LEFT   JOIN (SELECT DISTINCT company_id FROM cashflow)      cf ON cf.company_id = c.company_id
WHERE  p.company_id IS NULL
   OR  bs.company_id IS NULL
   OR  cf.company_id IS NULL;


-- ---------------------------------------------------------------------------
-- Query 9: Sector-wise average Operating Profit Margin (OPM)
-- ---------------------------------------------------------------------------
-- Highlights which sectors are structurally more profitable from an
-- operating standpoint. Uses the latest year of data.
SELECT c.sector,
       ROUND(AVG(p.opm_percentage), 2) AS avg_opm_pct,
       COUNT(*) AS companies_counted
FROM   profitandloss p
JOIN   companies     c ON c.company_id = p.company_id
WHERE  p.year = (SELECT MAX(year) FROM profitandloss)
       AND p.opm_percentage IS NOT NULL
GROUP  BY c.sector
ORDER  BY avg_opm_pct DESC;


-- ---------------------------------------------------------------------------
-- Query 10: Balance-sheet health check — equity vs. borrowings
-- ---------------------------------------------------------------------------
-- Classifies each company's leverage posture in the latest year:
--   • Conservative : borrowings < 0.5 × equity
--   • Moderate     : 0.5–1 × equity
--   • Aggressive   : > 1 × equity
SELECT c.company_name,
       b.year,
       b.equity_capital + b.reserves AS total_equity,
       b.borrowings,
       ROUND(b.borrowings / NULLIF(b.equity_capital + b.reserves, 0), 3)
           AS leverage_ratio,
       CASE
           WHEN b.borrowings / NULLIF(b.equity_capital + b.reserves, 0) < 0.5
               THEN 'Conservative'
           WHEN b.borrowings / NULLIF(b.equity_capital + b.reserves, 0) BETWEEN 0.5 AND 1.0
               THEN 'Moderate'
           ELSE 'Aggressive'
       END AS leverage_posture
FROM   balancesheet b
JOIN   companies    c ON c.company_id = b.company_id
WHERE  b.year = (SELECT MAX(year) FROM balancesheet)
       AND b.equity_capital IS NOT NULL
       AND b.reserves       IS NOT NULL
       AND b.borrowings     IS NOT NULL
ORDER  BY leverage_ratio DESC;
