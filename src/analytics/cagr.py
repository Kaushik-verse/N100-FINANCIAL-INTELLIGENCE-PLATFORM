from enum import Enum
from typing import Optional, Tuple, List

class CAGRFlag(Enum):
    OK = "OK"
    DECLINE_TO_LOSS = "DECLINE_TO_LOSS"
    TURNAROUND = "TURNAROUND"
    BOTH_NEGATIVE = "BOTH_NEGATIVE"
    ZERO_BASE = "ZERO_BASE"
    INSUFFICIENT = "INSUFFICIENT"

def compute_cagr(start_value: Optional[float], end_value: Optional[float], years: int) -> Tuple[Optional[float], CAGRFlag]:
    if start_value is None or end_value is None:
        return None, CAGRFlag.INSUFFICIENT
    if years < 1:
        return None, CAGRFlag.INSUFFICIENT
    if start_value == 0:
        return None, CAGRFlag.ZERO_BASE
    if start_value > 0 and end_value < 0:
        return None, CAGRFlag.DECLINE_TO_LOSS
    if start_value < 0 and end_value > 0:
        return None, CAGRFlag.TURNAROUND
    if start_value < 0 and end_value <= 0:
        return None, CAGRFlag.BOTH_NEGATIVE
        
    cagr = ((end_value / start_value) ** (1 / years) - 1) * 100
    return cagr, CAGRFlag.OK

def compute_metric_cagr(series: List[Tuple[str, float]], window_years: int) -> Tuple[Optional[float], CAGRFlag]:
    valid_series = [s for s in series if s[1] is not None]
    if len(valid_series) < 2:
        return None, CAGRFlag.INSUFFICIENT
        
    try:
        years = [int(str(s[0]).split(' ')[-1]) for s in valid_series if str(s[0]).split(' ')[-1].isdigit()]
        if len(years) < 2:
            return None, CAGRFlag.INSUFFICIENT
    except ValueError:
        return None, CAGRFlag.INSUFFICIENT
        
    start_year = years[0]
    end_year = years[-1]
    actual_years = end_year - start_year
    
    if actual_years < window_years:
        return None, CAGRFlag.INSUFFICIENT
        
    start_val = valid_series[0][1]
    end_val = valid_series[-1][1]
    
    return compute_cagr(start_val, end_val, actual_years)
