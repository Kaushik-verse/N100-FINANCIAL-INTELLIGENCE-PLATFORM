import pytest
from src.analytics.ratios import (
    net_profit_margin,
    return_on_equity,
    return_on_capital_employed,
    debt_to_equity,
    interest_coverage_ratio,
    high_leverage_flag
)

def test_npm_normal():
    # NPM = 10/100 * 100 = 10%
    assert net_profit_margin(10, 100) == 10.0

def test_npm_zero_sales():
    # returns None
    assert net_profit_margin(10, 0) is None
    assert net_profit_margin(10, -5) is None

def test_roe_normal():
    # Net Profit=20, Eq=50, Res=50 -> 20%
    assert return_on_equity(20, 50, 50) == 20.0

def test_roe_negative_equity():
    # Eq=50, Res=-100 -> returns None
    assert return_on_equity(20, 50, -100) is None

def test_roce_normal():
    # EBIT=30, Eq=50, Res=20, Debt=30 -> 30%
    assert return_on_capital_employed(30, 50, 20, 30) == 30.0

def test_de_debt_free():
    # Borrowings=0, Eq=100, Res=50 -> 0.0
    assert debt_to_equity(0, 100, 50) == 0.0

def test_icr_no_interest():
    # Interest=0 -> returns (None, "Debt Free")
    assert interest_coverage_ratio(100, 20, 0) == (None, "Debt Free")
    assert interest_coverage_ratio(100, 20, -10) == (None, "Debt Free")

def test_high_leverage_flag():
    # Tests threshold > 5 and sector exclusion.
    assert high_leverage_flag(6.0, False) is True
    assert high_leverage_flag(6.0, True) is False
    assert high_leverage_flag(4.0, False) is False
