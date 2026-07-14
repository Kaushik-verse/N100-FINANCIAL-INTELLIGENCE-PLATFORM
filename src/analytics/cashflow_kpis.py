from typing import List, Tuple, Optional

def free_cash_flow(cfo: float, cfi: float) -> float:
    return cfo + cfi

def cfo_quality_score(cfo_values: List[float], pat_values: List[float]) -> Tuple[Optional[float], Optional[str]]:
    if not cfo_values or not pat_values or len(cfo_values) != len(pat_values):
        return None, None
        
    avg_cfo = sum(cfo_values) / len(cfo_values)
    avg_pat = sum(pat_values) / len(pat_values)
    
    if avg_pat <= 0:
        return None, None
        
    ratio = avg_cfo / avg_pat
    
    if ratio > 1.0:
        return ratio, "High Quality"
    elif 0.5 <= ratio <= 1.0:
        return ratio, "Moderate"
    else:
        return ratio, "Accrual Risk"

def capex_intensity(cfi: float, sales: float) -> Tuple[Optional[float], Optional[str]]:
    if sales <= 0:
        return None, None
        
    intensity = (abs(cfi) / sales) * 100
    
    if intensity < 3:
        return intensity, "Asset Light"
    elif 3 <= intensity <= 8:
        return intensity, "Moderate"
    else:
        return intensity, "Capital Intensive"

def fcf_conversion_rate(fcf: float, operating_profit: float) -> Optional[float]:
    if operating_profit == 0:
        return None
    return (fcf / operating_profit) * 100

def classify_capital_allocation(cfo: float, cfi: float, cff: float, cfo_pat_ratio: Optional[float] = None) -> str:
    cfo_pos = cfo > 0
    cfi_pos = cfi > 0
    cff_pos = cff > 0
    
    if cfo_pos and not cfi_pos and not cff_pos:
        if cfo_pat_ratio is not None and cfo_pat_ratio > 1:
            return "Shareholder Returns"
        return "Reinvestor"
        
    if cfo_pos and cfi_pos and not cff_pos:
        return "Liquidating Assets"
        
    if not cfo_pos and cfi_pos and cff_pos:
        return "Distress Signal"
        
    if not cfo_pos and not cfi_pos and cff_pos:
        return "Growth Funded by Debt"
        
    if cfo_pos and cfi_pos and cff_pos:
        return "Cash Accumulator"
        
    if not cfo_pos and not cfi_pos and not cff_pos:
        return "Pre-Revenue"
        
    return "Mixed"
