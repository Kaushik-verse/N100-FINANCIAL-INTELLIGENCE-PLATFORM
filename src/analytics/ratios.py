from typing import Optional, Tuple

def _safe_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None

def net_profit_margin(net_profit, sales) -> Optional[float]:
    """Calculate net profit margin."""
    np = _safe_float(net_profit)
    s = _safe_float(sales)
    if np is None or s is None or s <= 0:
        return None
    return (np / s) * 100

def operating_profit_margin(operating_profit, sales) -> Optional[float]:
    """Calculate operating profit margin."""
    op = _safe_float(operating_profit)
    s = _safe_float(sales)
    if op is None or s is None or s <= 0:
        return None
    return (op / s) * 100

def return_on_equity(net_profit, equity_capital, reserves) -> Optional[float]:
    """Calculate return on equity."""
    np = _safe_float(net_profit)
    eq = _safe_float(equity_capital)
    res = _safe_float(reserves)
    if np is None or eq is None or res is None:
        return None
    denom = eq + res
    if denom <= 0:
        return None
    return (np / denom) * 100

def return_on_capital_employed(ebit, equity_capital, reserves, borrowings) -> Optional[float]:
    """Calculate return on capital employed."""
    e = _safe_float(ebit)
    eq = _safe_float(equity_capital)
    res = _safe_float(reserves)
    b = _safe_float(borrowings)
    if e is None or eq is None or res is None or b is None:
        return None
    denom = eq + res + b
    if denom <= 0:
        return None
    return (e / denom) * 100

def return_on_assets(net_profit, total_assets) -> Optional[float]:
    """Calculate return on assets."""
    np = _safe_float(net_profit)
    ta = _safe_float(total_assets)
    if np is None or ta is None or ta <= 0:
        return None
    return (np / ta) * 100

def debt_to_equity(borrowings, equity_capital, reserves) -> Optional[float]:
    """Calculate debt to equity ratio."""
    b = _safe_float(borrowings)
    eq = _safe_float(equity_capital)
    res = _safe_float(reserves)
    if b is None or eq is None or res is None:
        return None
    if b <= 0:
        return 0.0
    denom = eq + res
    if denom <= 0:
        return None
    return b / denom

def interest_coverage_ratio(operating_profit, other_income, interest) -> Tuple[Optional[float], Optional[str]]:
    """Calculate interest coverage ratio."""
    op = _safe_float(operating_profit)
    oi = _safe_float(other_income)
    int_ = _safe_float(interest)
    if op is None or oi is None or int_ is None:
        return (None, None)
    if int_ <= 0:
        return (None, "Debt Free")
    val = (op + oi) / int_
    return (val, None)

def net_debt(borrowings, investments) -> Optional[float]:
    """Calculate net debt."""
    b = _safe_float(borrowings)
    inv = _safe_float(investments)
    if b is None or inv is None:
        return None
    return b - inv

def asset_turnover(sales, total_assets) -> Optional[float]:
    """Calculate asset turnover."""
    s = _safe_float(sales)
    ta = _safe_float(total_assets)
    if s is None or ta is None or ta <= 0:
        return None
    return s / ta

def high_leverage_flag(de_ratio, is_financials_sector: bool) -> bool:
    """Flag high leverage if D/E > 5 and not financials sector."""
    de = _safe_float(de_ratio)
    if de is None:
        return False
    return de > 5 and not is_financials_sector

def opm_cross_check(stored_opm, computed_opm, threshold=1.0) -> Optional[float]:
    """Cross check operating profit margin."""
    stored = _safe_float(stored_opm)
    computed = _safe_float(computed_opm)
    if stored is None or computed is None:
        return None
    return abs(stored - computed)
