import numpy as np
import pandas as pd
import pytest

from fraud_p2p.economics import CostConfig, optimal_threshold, savings_curve, serve_daily_queue, wilson_interval


def _data(seed=0, n=6000):
    rng = np.random.default_rng(seed)
    y = (rng.random(n) < 0.02).astype(int)
    score = np.where(y == 1, rng.normal(3, 1, n), rng.normal(-3, 1, n))
    amount = np.where(y == 1, rng.uniform(1e5, 1e6, n), rng.uniform(1e2, 1e4, n))
    days = np.repeat([1, 2, 3], n // 3)
    return y, score, amount, days


def test_threshold_respects_daily_capacity_every_day():
    y, s, a, d = _data()
    costs = CostConfig(daily_capacity=25)
    o = optimal_threshold(y, s, a, d, costs)
    per_day = pd.Series(s >= o["threshold"]).groupby(d).sum()
    assert per_day.max() <= 25  # el cupo se exige en cada día, no en promedio


def test_threshold_is_inside_the_band():
    y, s, a, d = _data(1)
    o = optimal_threshold(y, s, a, d)
    assert o["band_min"] <= o["threshold"] <= o["band_max"]


def test_no_feasible_savings_means_no_alerts():
    y, s, a, d = _data(2)
    o = optimal_threshold(y, s, np.full_like(a, 1.0), d, CostConfig(review_cost=1e9))
    assert o["alerts"] == 0


def test_savings_curve_is_consistent():
    y, s, a, d = _data(3)
    c = savings_curve(y, s, a, d)
    assert (c["tp"] + c["fp"]).is_monotonic_increasing
    assert np.allclose(c["savings"], c["saved"] - 1500 * (c["tp"] + c["fp"]) - 8500 * c["fp"])


def test_daily_queue_serves_first_arrivals():
    cand = np.array([1, 1, 1, 0, 1, 1, 1], dtype=bool)
    days = np.array([1, 1, 1, 1, 2, 2, 2])
    served = serve_daily_queue(cand, days, 2)
    assert served.tolist() == [True, True, False, False, True, True, False]


def test_wilson_interval_handles_extremes():
    lo, hi = wilson_interval(0, 100)
    assert lo == pytest.approx(0, abs=1e-12) and 0 < hi < 0.05
    lo, hi = wilson_interval(4193, 4196)
    assert round(lo, 4) == 0.9979 and round(hi, 4) == 0.9998
