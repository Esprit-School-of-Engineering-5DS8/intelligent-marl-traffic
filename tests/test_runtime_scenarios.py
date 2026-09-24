import numpy as np
import pytest

from cotraffic.scenarios.runtime import CommDropout, SensorNoise, runtime_perturbations


class FakeMeasurements:
    def __init__(self, lanes):
        self.lanes = lanes
        self.count = dict.fromkeys(lanes, 10.0)
        self.halting = dict.fromkeys(lanes, 4.0)
        self.speed = dict.fromkeys(lanes, 8.0)


def test_sensor_noise_fails_the_requested_share_of_detectors():
    lanes = [f"l{i}" for i in range(50)]
    noise = SensorNoise(count_std_veh=2.0, failed_fraction=0.2)
    noise.reset(lanes, np.random.default_rng(0))
    assert len(noise.failed) == 10
    meas = FakeMeasurements(lanes)
    noise.apply(meas, np.random.default_rng(1))
    for lane in lanes:
        if lane in noise.failed:
            assert meas.count[lane] == meas.halting[lane] == meas.speed[lane] == 0.0
        else:
            assert 0.0 <= meas.halting[lane] <= meas.count[lane]


def test_sensor_noise_has_the_configured_spread():
    lanes = [f"l{i}" for i in range(2000)]
    noise = SensorNoise(count_std_veh=2.0, failed_fraction=0.0)
    noise.reset(lanes, np.random.default_rng(0))
    meas = FakeMeasurements(lanes)
    noise.apply(meas, np.random.default_rng(3))
    assert np.std(list(meas.count.values())) == pytest.approx(2.0, rel=0.1)


def test_dropout_zero_mode_loses_about_p_of_messages():
    d = CommDropout(p=0.3, mode="zero")
    rng = np.random.default_rng(0)
    msg = np.ones(3, dtype=np.float32)
    out = [d.transmit("k", msg, rng) for _ in range(5000)]
    lost = sum(not o.any() for o in out)
    assert lost / 5000 == pytest.approx(0.3, abs=0.02)
    assert d.lost == lost and d.sent == 5000


def test_dropout_stale_mode_repeats_the_last_received_message():
    d = CommDropout(p=1.0, mode="stale")
    rng = np.random.default_rng(0)
    first = d.transmit("k", np.array([1.0, 2.0, 3.0]), rng)
    assert not first.any()  # nothing received yet
    d.p = 0.0
    d.transmit("k", np.array([4.0, 5.0, 6.0]), rng)
    d.p = 1.0
    assert d.transmit("k", np.array([7.0, 8.0, 9.0]), rng).tolist() == [4.0, 5.0, 6.0]


def test_runtime_perturbations_from_configs():
    out = runtime_perturbations(["sensor_noise", "comm_dropout_30"])
    assert out["sensor_noise"].failed_fraction == pytest.approx(0.2)
    assert out["comm_dropout"].p == pytest.approx(0.3)
    assert runtime_perturbations(["normal", "incident"]) == {}
