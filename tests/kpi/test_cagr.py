import pytest
from src.analytics.cagr import compute_cagr, compute_metric_cagr, CAGRFlag

def test_compute_cagr_ok():
    val, flag = compute_cagr(100, 121, 2)
    assert flag == CAGRFlag.OK
    assert pytest.approx(val, 0.01) == 10.0

def test_compute_cagr_insufficient():
    val, flag = compute_cagr(None, 100, 2)
    assert flag == CAGRFlag.INSUFFICIENT
    
    val, flag = compute_cagr(100, 121, 0)
    assert flag == CAGRFlag.INSUFFICIENT

def test_compute_cagr_zero_base():
    val, flag = compute_cagr(0, 100, 2)
    assert flag == CAGRFlag.ZERO_BASE

def test_compute_cagr_decline_to_loss():
    val, flag = compute_cagr(100, -50, 2)
    assert flag == CAGRFlag.DECLINE_TO_LOSS

def test_compute_cagr_turnaround():
    val, flag = compute_cagr(-50, 100, 2)
    assert flag == CAGRFlag.TURNAROUND

def test_compute_cagr_both_negative():
    val, flag = compute_cagr(-100, -50, 2)
    assert flag == CAGRFlag.BOTH_NEGATIVE

def test_compute_metric_cagr_valid():
    series = [("2019", 100), ("2020", None), ("2024", 200)]
    val, flag = compute_metric_cagr(series, window_years=5)
    assert flag == CAGRFlag.OK
    assert pytest.approx(val, 0.1) == 14.87

def test_compute_metric_cagr_insufficient_window():
    series = [("2019", 100), ("2020", 120)]
    val, flag = compute_metric_cagr(series, window_years=5)
    assert flag == CAGRFlag.INSUFFICIENT

def test_compute_metric_cagr_insufficient_data():
    series = [("2019", 100)]
    val, flag = compute_metric_cagr(series, window_years=5)
    assert flag == CAGRFlag.INSUFFICIENT
