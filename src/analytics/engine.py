import sqlite3
import pandas as pd
import logging
import os
import csv
from collections import defaultdict
from typing import Dict, List, Any

from src.analytics import ratios, cagr, cashflow_kpis

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DB_PATH = 'nifty100.db'
MIGRATION_PATH = 'db/migrate_sprint2.sql'
OUTPUT_CSV = 'output/capital_allocation.csv'
OUTPUT_LOG = 'output/ratio_edge_cases.log'

def apply_migration(conn):
    try:
        with open(MIGRATION_PATH, 'r') as f:
            migration_sql = f.read()
            
        cursor = conn.cursor()
        for statement in migration_sql.split(';'):
            statement = statement.strip()
            if statement:
                try:
                    cursor.execute(statement)
                except sqlite3.OperationalError as e:
                    if 'duplicate column name' not in str(e).lower():
                        logger.warning(f"Error applying statement '{statement}': {e}")
        conn.commit()
        logger.info("Sprint 2 migration applied successfully.")
    except Exception as e:
        logger.error(f"Failed to apply migration: {e}")

def get_year_int(year_str):
    if not isinstance(year_str, str):
        return 0
    # "Dec 2012", "TTM", etc.
    try:
        return int(year_str.split(' ')[-1])
    except:
        return 9999 if year_str == 'TTM' else 0

def compute_composite_score(roe, rev_cagr, npm, de, icr, cfo_score, fcf_conv):
    """
    Computes composite score 0-100.
    ROE (20%), Rev CAGR 5yr (15%), NPM (15%), D/E inverse (15%), ICR (10%), CFO Quality (15%), FCF Conv (10%).
    """
    score = 0
    if roe and roe > 15: score += 20
    elif roe and roe > 0: score += 10
    
    if rev_cagr and rev_cagr > 10: score += 15
    elif rev_cagr and rev_cagr > 0: score += 7
    
    if npm and npm > 10: score += 15
    elif npm and npm > 0: score += 7
    
    if de is not None:
        if de < 1: score += 15
        elif de < 3: score += 7
        
    if icr and icr > 3: score += 10
    elif icr and icr > 1.5: score += 5
    
    if cfo_score and cfo_score > 1.0: score += 15
    elif cfo_score and cfo_score > 0.5: score += 7
    
    if fcf_conv and fcf_conv > 50: score += 10
    elif fcf_conv and fcf_conv > 0: score += 5
        
    return score

def run_engine():
    os.makedirs('output', exist_ok=True)
    os.makedirs('db', exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    
    apply_migration(conn)
    
    query = """
        SELECT 
            c.company_id, s.broad_sector, c.roce_percentage as src_roce, c.roe_percentage as src_roe,
            p.year,
            p.sales, p.operating_profit, p.other_income, p.interest, p.profit_before_tax, p.net_profit, p.eps, p.opm_percentage as stored_opm,
            b.equity_capital, b.reserves, b.borrowings, b.total_assets, b.investments,
            cf.operating_activity as cfo, cf.investing_activity as cfi, cf.financing_activity as cff
        FROM companies c
        LEFT JOIN sectors s ON c.company_id = s.company_id
        JOIN profitandloss p ON c.company_id = p.company_id
        LEFT JOIN balancesheet b ON p.company_id = b.company_id AND p.year = b.year
        LEFT JOIN cashflow cf ON p.company_id = cf.company_id AND p.year = cf.year
    """
    
    df = pd.read_sql_query(query, conn)
    logger.info(f"Loaded {len(df)} rows from raw data")
    
    # Sort by company and year for time-series computations
    df['year_val'] = df['year'].apply(get_year_int)
    df = df.sort_values(['company_id', 'year_val'])
    
    company_groups = df.groupby('company_id')
    
    updates = []
    inserts = []
    allocations = []
    edge_cases = []
    
    # Get existing financial_ratios keys
    existing = set()
    cursor = conn.cursor()
    cursor.execute("SELECT company_id, year FROM financial_ratios")
    for row in cursor.fetchall():
        existing.add((row[0], row[1]))
    
    for idx, row in df.iterrows():
        cid = row['company_id']
        yr = row['year']
        sector = row['broad_sector']
        is_fin = (sector == 'Financials')
        
        # 1. Profitability
        npm = ratios.net_profit_margin(row['net_profit'], row['sales'])
        opm = ratios.operating_profit_margin(row['operating_profit'], row['sales'])
        roe = ratios.return_on_equity(row['net_profit'], row['equity_capital'], row['reserves'])
        ebit = (row['operating_profit'] or 0) + (row['other_income'] or 0)
        roce = ratios.return_on_capital_employed(ebit, row['equity_capital'], row['reserves'], row['borrowings'])
        roa = ratios.return_on_assets(row['net_profit'], row['total_assets'])
        
        opm_diff = ratios.opm_cross_check(row['stored_opm'], opm, 1.0)
        if opm_diff and opm_diff > 1.0:
            edge_cases.append(f"{cid} {yr} - OPM Mismatch (Source: {row['stored_opm']}, Computed: {opm}) [Formula discrepancy]")
            
        if roce is not None and row['src_roce'] is not None and yr == 'TTM':
            if abs(roce - row['src_roce']) > 5.0:
                edge_cases.append(f"{cid} {yr} - ROCE Mismatch (Source: {row['src_roce']}, Computed: {roce}) [Formula discrepancy]")

        # 2. Leverage
        de = ratios.debt_to_equity(row['borrowings'], row['equity_capital'], row['reserves'])
        icr_val, icr_label = ratios.interest_coverage_ratio(row['operating_profit'], row['other_income'], row['interest'])
        net_debt = ratios.net_debt(row['borrowings'], row['investments'])
        net_debt_cr = net_debt if net_debt is not None else None
        ato = ratios.asset_turnover(row['sales'], row['total_assets'])
        hlf = ratios.high_leverage_flag(de, is_fin) if de is not None else False
        
        # 3. Cashflow
        fcf = cashflow_kpis.free_cash_flow(row['cfo'] or 0, row['cfi'] or 0)
        capex_val, capex_lbl = cashflow_kpis.capex_intensity(row['cfi'], row['sales'])
        fcf_conv = cashflow_kpis.fcf_conversion_rate(fcf, row['operating_profit'])
        
        # Time-series computations
        cg = company_groups.get_group(cid)
        cg = cg[cg['year_val'] <= row['year_val']]
        
        rev_series = list(zip(cg['year'], cg['sales']))
        pat_series = list(zip(cg['year'], cg['net_profit']))
        eps_series = list(zip(cg['year'], cg['eps']))
        
        rev_3yr, _ = cagr.compute_metric_cagr(rev_series, 3)
        rev_5yr, rev_5yr_flag = cagr.compute_metric_cagr(rev_series, 5)
        rev_10yr, _ = cagr.compute_metric_cagr(rev_series, 10)
        
        pat_3yr, _ = cagr.compute_metric_cagr(pat_series, 3)
        pat_5yr, pat_5yr_flag = cagr.compute_metric_cagr(pat_series, 5)
        pat_10yr, _ = cagr.compute_metric_cagr(pat_series, 10)
        
        eps_3yr, _ = cagr.compute_metric_cagr(eps_series, 3)
        eps_5yr, eps_5yr_flag = cagr.compute_metric_cagr(eps_series, 5)
        eps_10yr, _ = cagr.compute_metric_cagr(eps_series, 10)
        
        cfo_list = cg['cfo'].tolist()[-5:]
        pat_list = cg['net_profit'].tolist()[-5:]
        cfo_score, cfo_lbl = cashflow_kpis.cfo_quality_score(cfo_list, pat_list)
        
        cap_alloc = cashflow_kpis.classify_capital_allocation(row['cfo'] or 0, row['cfi'] or 0, row['cff'] or 0, cfo_score)
        allocations.append({
            'company_id': cid, 'year': yr,
            'cfo_sign': '+' if (row['cfo'] or 0) > 0 else '-',
            'cfi_sign': '+' if (row['cfi'] or 0) > 0 else '-',
            'cff_sign': '+' if (row['cff'] or 0) > 0 else '-',
            'pattern_label': cap_alloc
        })
        
        comp_score = compute_composite_score(roe, rev_5yr, npm, de, icr_val, cfo_score, fcf_conv)
        
        record = (
            npm, opm, roe, de, icr_val, ato, fcf, capex_val, row['eps'], None, None, row['borrowings'], row['cfo'],
            roa, roce, icr_label, int(hlf), net_debt_cr,
            rev_3yr, rev_5yr, rev_10yr, pat_3yr, pat_5yr, pat_10yr, eps_3yr, eps_5yr, eps_10yr,
            rev_5yr_flag.name, pat_5yr_flag.name, eps_5yr_flag.name,
            cfo_score, cfo_lbl, capex_lbl, fcf_conv, cap_alloc, comp_score,
            cid, yr
        )
        
        if (cid, yr) in existing:
            updates.append(record)
        else:
            inserts.append((cid, yr) + record[:-2]) # drop cid, yr from end, add to front

    logger.info("Executing DB updates...")
    
    update_sql = """
        UPDATE financial_ratios SET
            net_profit_margin_pct = ?, operating_profit_margin_pct = ?, return_on_equity_pct = ?,
            debt_to_equity = ?, interest_coverage = ?, asset_turnover = ?, free_cash_flow_cr = ?, capex_cr = ?, 
            earnings_per_share = ?, book_value_per_share = ?, dividend_payout_ratio_pct = ?, total_debt_cr = ?, cash_from_operations_cr = ?,
            roa_pct = ?, roce_pct = ?, icr_label = ?, high_leverage_flag = ?, net_debt_cr = ?,
            revenue_cagr_3yr = ?, revenue_cagr_5yr = ?, revenue_cagr_10yr = ?,
            pat_cagr_3yr = ?, pat_cagr_5yr = ?, pat_cagr_10yr = ?,
            eps_cagr_3yr = ?, eps_cagr_5yr = ?, eps_cagr_10yr = ?,
            revenue_cagr_5yr_flag = ?, pat_cagr_5yr_flag = ?, eps_cagr_5yr_flag = ?,
            cfo_quality_score = ?, cfo_quality_label = ?, capex_intensity_label = ?, 
            fcf_conversion_pct = ?, capital_allocation_pattern = ?, composite_quality_score = ?
        WHERE company_id = ? AND year = ?
    """
    cursor.executemany(update_sql, updates)
    
    insert_sql = """
        INSERT INTO financial_ratios (
            company_id, year,
            net_profit_margin_pct, operating_profit_margin_pct, return_on_equity_pct,
            debt_to_equity, interest_coverage, asset_turnover, free_cash_flow_cr, capex_cr, 
            earnings_per_share, book_value_per_share, dividend_payout_ratio_pct, total_debt_cr, cash_from_operations_cr,
            roa_pct, roce_pct, icr_label, high_leverage_flag, net_debt_cr,
            revenue_cagr_3yr, revenue_cagr_5yr, revenue_cagr_10yr,
            pat_cagr_3yr, pat_cagr_5yr, pat_cagr_10yr,
            eps_cagr_3yr, eps_cagr_5yr, eps_cagr_10yr,
            revenue_cagr_5yr_flag, pat_cagr_5yr_flag, eps_cagr_5yr_flag,
            cfo_quality_score, cfo_quality_label, capex_intensity_label, 
            fcf_conversion_pct, capital_allocation_pattern, composite_quality_score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    cursor.executemany(insert_sql, inserts)
    
    conn.commit()
    logger.info(f"Updated {len(updates)} rows, inserted {len(inserts)} rows into financial_ratios")
    
    # Write outputs
    pd.DataFrame(allocations).to_csv(OUTPUT_CSV, index=False)
    logger.info(f"Wrote {len(allocations)} rows to {OUTPUT_CSV}")
    
    with open(OUTPUT_LOG, 'w') as f:
        for ec in edge_cases:
            f.write(ec + '\\n')
    logger.info(f"Wrote {len(edge_cases)} anomalies to {OUTPUT_LOG}")
    
    conn.close()

if __name__ == '__main__':
    run_engine()
