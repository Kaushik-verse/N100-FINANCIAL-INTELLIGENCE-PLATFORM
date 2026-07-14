import pytest
from src.analytics.cashflow_kpis import (
    free_cash_flow,
    cfo_quality_score,
    capex_intensity,
    fcf_conversion_rate,
    classify_capital_allocation
)

def test_free_cash_flow():
    assert free_cash_flow(100, -20) == 80
    assert free_cash_flow(50, 10) == 60

def test_cfo_quality_score():
    ratio, quality = cfo_quality_score([120, 110], [100, 100])
    assert ratio == 1.15
    assert quality == "High Quality"

    ratio, quality = cfo_quality_score([80, 70], [100, 100])
    assert ratio == 0.75
    assert quality == "Moderate"

    ratio, quality = cfo_quality_score([40, 30], [100, 100])
    assert ratio == 0.35
    assert quality == "Accrual Risk"

    ratio, quality = cfo_quality_score([100], [-10])
    assert ratio is None
    assert quality is None

def test_capex_intensity():
    val, cat = capex_intensity(-2, 100)
    assert val == 2.0
    assert cat == "Asset Light"

    val, cat = capex_intensity(-5, 100)
    assert val == 5.0
    assert cat == "Moderate"

    val, cat = capex_intensity(-10, 100)
    assert val == 10.0
    assert cat == "Capital Intensive"

    val, cat = capex_intensity(-10, 0)
    assert val is None
    assert cat is None

def test_fcf_conversion_rate():
    assert fcf_conversion_rate(50, 100) == 50.0
    assert fcf_conversion_rate(50, 0) is None

def test_classify_capital_allocation():
    # (+, -, -)
    assert classify_capital_allocation(100, -50, -50) == "Reinvestor"
    assert classify_capital_allocation(100, -50, -50, cfo_pat_ratio=1.5) == "Shareholder Returns"
    
    # (+, +, -)
    assert classify_capital_allocation(100, 50, -50) == "Liquidating Assets"
    
    # (-, +, +)
    assert classify_capital_allocation(-10, 50, 50) == "Distress Signal"
    
    # (-, -, +)
    assert classify_capital_allocation(-10, -50, 100) == "Growth Funded by Debt"
    
    # (+, +, +)
    assert classify_capital_allocation(100, 50, 50) == "Cash Accumulator"
    
    # (-, -, -)
    assert classify_capital_allocation(-10, -10, -10) == "Pre-Revenue"
    
    # (+, -, +)
    assert classify_capital_allocation(100, -50, 50) == "Mixed"
