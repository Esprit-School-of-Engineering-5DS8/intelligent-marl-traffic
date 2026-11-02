"""The forecast math is verifiable without SUMO.

The live Predict tab must show the run's own numbers: the EWMA, the trend and the
projection are pure functions, so these tests pin their behaviour directly instead of
going through a simulation.
"""

from __future__ import annotations

import pytest

from cotraffic.forecast import confidence, ewma, linear_trend, project


def _sample(t: int, queue: float, rate: float = 4.0, speed: float = 20.0) -> dict:
    return {
        "t": t,
        "clock": f"00:00:{t:02d}",
        "queue": queue,
        "throughputPerMin": rate,
        "avgSpeedKmh": speed,
    }


def test_ewma_seeds_on_the_first_value_and_smooths_after():
    assert ewma([10, 20, 20], 0.5) == [10, 15.0, 17.5]


def test_ewma_rejects_a_degenerate_alpha():
    # alpha is clamped, so a caller mistake cannot produce a frozen series
    assert ewma([1, 5], 0)[-1] == pytest.approx(1.04, abs=1e-6)


def test_linear_trend_recovers_a_known_slope():
    slope, intercept = linear_trend([(0, 1), (10, 3), (20, 5)])
    assert slope == pytest.approx(0.2)
    assert intercept == pytest.approx(1.0)


def test_linear_trend_needs_two_distinct_points():
    assert linear_trend([]) == (0.0, 0.0)
    assert linear_trend([(5, 3)]) == (0.0, 3.0)
    assert linear_trend([(5, 3), (5, 9)]) == (0.0, 6.0)


def test_projection_grows_with_a_rising_queue_and_stays_physical():
    samples = [_sample(t, 10 + t * 0.5) for t in range(0, 60, 5)]
    result = project(samples, horizon_minutes=5)

    assert result["horizonMin"] == 5
    assert result["samples"] == len(samples)
    assert len(result["points"]) == 5
    assert all(point["queue"] >= 0 for point in result["points"])
    assert result["points"][-1]["queue"] > result["current"]["queue"]
    assert result["peak"]["queue"] == max(point["queue"] for point in result["points"])


def test_projection_never_goes_negative_when_the_queue_falls():
    samples = [_sample(t, 40 - t) for t in range(0, 30, 5)]
    result = project(samples, horizon_minutes=10)
    assert min(point["queue"] for point in result["points"]) >= 0


def test_confidence_is_bounded_and_rises_with_samples():
    few = confidence([_sample(t, 10) for t in range(0, 10, 5)])
    many = confidence([_sample(t, 10) for t in range(0, 120, 5)])
    assert 0.3 <= few <= many <= 0.95


def test_confidence_drops_when_the_queue_swings():
    steady = confidence([_sample(t, 10) for t in range(0, 60, 5)])
    swinging = confidence([_sample(t, 10 if t % 10 else 80) for t in range(0, 60, 5)])
    assert swinging < steady


def test_projection_reads_the_session_history_schema():
    # The run's history stores the field as `queued`; a forecast that only read `queue`
    # reported a flat zero corridor while the vehicles were queued.
    samples = [
        {
            "t": t,
            "clock": f"00:00:{t:02d}",
            "queued": 12 + t,
            "throughputPerMin": 3,
            "avgSpeedKmh": 18,
        }
        for t in range(0, 30, 5)
    ]
    result = project(samples, horizon_minutes=5)
    assert result["measured"][-1]["queue"] == pytest.approx(37.0)
    assert result["current"]["queue"] > 0
    assert min(point["queue"] for point in result["points"]) > 0


def test_forecast_needs_two_samples():
    with pytest.raises(ValueError, match="at least two"):
        project([_sample(0, 5)])
