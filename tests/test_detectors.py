from environment.detectors import Alert, QueueAlertDetector, QueueDetectorConfig


def _states(ns=0, ew=0, tls="A"):
    return {tls: {"ns_queue": ns, "ew_queue": ew}}


def test_fires_after_sustain():
    detector = QueueAlertDetector(QueueDetectorConfig(queue_threshold=10, sustain_s=20.0))
    for t in (0.0, 10.0, 19.0):
        assert detector.update(_states(ns=12), t) == []
    fired = detector.update(_states(ns=12), 20.0)
    assert len(fired) == 1
    assert fired[0].kind == "queue_growth"
    assert fired[0].tls_id == "A" and fired[0].axis == "NS"
    assert fired[0].severity == "medium"


def test_below_threshold_resets():
    detector = QueueAlertDetector(QueueDetectorConfig(queue_threshold=10, sustain_s=20.0))
    detector.update(_states(ns=12), 0.0)
    detector.update(_states(ns=5), 10.0)
    assert detector.update(_states(ns=12), 19.0) == []
    assert detector.update(_states(ns=12), 38.0) == []
    assert len(detector.update(_states(ns=12), 39.0)) == 1


def test_cooldown_ttl_and_reactivation():
    detector = QueueAlertDetector(QueueDetectorConfig(
        queue_threshold=10, sustain_s=10.0, cooldown_s=60.0, alert_ttl_s=30.0))
    detector.update(_states(ns=12), 0.0)
    fired = detector.update(_states(ns=12), 10.0)
    assert len(fired) == 1

    assert len(detector.active(10.0)) == 1
    assert len(detector.active(39.0)) == 1
    assert detector.active(40.0) == []

    assert detector.update(_states(ns=12), 20.0) == []
    assert detector.update(_states(ns=12), 69.0) == []
    assert len(detector.update(_states(ns=12), 70.0)) == 1
    assert detector.count == 2


def test_high_severity():
    detector = QueueAlertDetector(QueueDetectorConfig(
        queue_threshold=10, sustain_s=5.0, high_severity_queue=25))
    detector.update(_states(ns=30), 0.0)
    fired = detector.update(_states(ns=30), 5.0)
    assert fired[0].severity == "high"


def test_axes_and_tls_are_independent():
    detector = QueueAlertDetector(QueueDetectorConfig(queue_threshold=10, sustain_s=5.0))
    states = {"A": {"ns_queue": 12, "ew_queue": 12}, "B": {"ns_queue": 12, "ew_queue": 0}}
    detector.update(states, 0.0)
    fired = detector.update(states, 5.0)
    keys = {(a.tls_id, a.axis) for a in fired}
    assert keys == {("A", "NS"), ("A", "EW"), ("B", "NS")}


def test_alert_to_dict():
    alert = Alert(kind="queue_growth", tls_id="B1", axis="EW", queue=18,
                  since_s=12.5, severity="medium", t=100.0)
    record = alert.to_dict()
    assert record == {"kind": "queue_growth", "tls": "B1", "axis": "EW",
                      "queue": 18, "since_s": 12.5, "severity": "medium"}
