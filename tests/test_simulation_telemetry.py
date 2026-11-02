"""Live-run contract: choosing saved weights and the telemetry behind the tabs.

The live dashboard must never present a made-up number. These tests pin the two
things that guarantee it:

* ``GET /api/models/live`` maps a scenario to its network and reports which saved
  checkpoints the policy layer would actually accept;
* ``SimulationSession`` derives queues, speeds, history and signal-change events
  from the state it is given, not from configuration.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.simulation import SimulationSession

client = TestClient(app)


class _FakeSimulation:
    def getArrivedNumber(self) -> int:
        return 2

    def getDepartedNumber(self) -> int:
        return 1


class _FakeConnection:
    def __init__(self) -> None:
        self.simulation = _FakeSimulation()


class _FakeEnv:
    def __init__(self) -> None:
        self.conn = _FakeConnection()


def _vehicle(index: int, *, waiting: bool = False) -> dict:
    return {
        "id": f"v{index}",
        "speed": 0.0 if waiting else 8.0,
        "waiting": waiting,
        "lane": f"edge-{index}",
        "waitingTime": 12.0,
    }


def test_live_catalog_rejects_an_unknown_scenario():
    response = client.get("/api/models/live", params={"scenario": "atlantis"})
    assert response.status_code == 404


def test_live_catalog_maps_scenario_to_network(monkeypatch):
    monkeypatch.setattr(
        "api.routes.model_catalog.model_catalog",
        lambda network=None: {"models": []},
    )
    body = client.get("/api/models/live", params={"scenario": "grid-2x2"}).json()
    assert body["scenario"] == "grid-2x2"
    assert body["network"] == "sf_mission_2x2"
    assert body["count"] == 0


def test_start_with_weights_but_no_method_is_refused():
    response = client.post(
        "/api/simulation/start",
        json={
            "scenario": "grid-2x2",
            "checkpoint": "results/checkpoints/rl/sf_mission_2x2/seed1.zip",
        },
    )
    assert response.status_code == 422
    assert "needs the controller method" in response.json()["detail"]


def test_start_honours_the_requested_network(monkeypatch):
    """The stored policy's network must not decide where the run happens."""
    calls: dict = {}

    def fake_start(scenario, speed=1, method=None, checkpoint=None):
        calls.update(scenario=scenario, speed=speed, method=method)
        return {"scenario": scenario, "network": "sf_mission_2x2"}

    monkeypatch.setattr(
        "api.simulation.policy.current",
        lambda: {"method": "mp", "network": "sf_mission_3x3", "label": "Max-Pressure"},
    )
    monkeypatch.setattr("api.routes.simulation.session.start", fake_start)

    body = client.post(
        "/api/simulation/start", json={"network": "sf_mission_2x2", "speed": 4}
    ).json()

    assert calls["scenario"] == "grid-2x2"
    assert calls["speed"] == 4
    assert body["network"] == "sf_mission_2x2"


def test_start_refuses_a_scenario_that_is_not_the_requested_network():
    response = client.post(
        "/api/simulation/start",
        json={"scenario": "grid-3x3", "network": "sf_mission_2x2"},
    )
    assert response.status_code == 422
    assert "not the requested sf_mission_2x2" in response.json()["detail"]


def test_start_refuses_an_unknown_network():
    response = client.post("/api/simulation/start", json={"network": "atlantis"})
    assert response.status_code == 422


def test_resolve_scenario_defaults_when_neither_id_is_given():
    from api.simulation import resolve_scenario

    assert resolve_scenario() == "grid-3x3"
    assert resolve_scenario("grid-2x2") == "grid-2x2"
    assert resolve_scenario(network="sf_mission_2x2") == "grid-2x2"
    assert resolve_scenario("grid-2x2", "sf_mission_2x2") == "grid-2x2"
    with pytest.raises(ValueError, match="unknown network"):
        resolve_scenario(network="atlantis")


def test_live_demand_uses_the_networks_own_rate():
    """Each network declares the rate its live window carries; the benchmark cell stays."""
    from api.simulation import live_demand

    level, scale = live_demand(
        {"demand": {"peak_vehicles_per_hour": 1300, "live_vehicles_per_hour": 2600}}
    )
    assert level == "peak"
    assert scale == pytest.approx(2.0)
    # No live rate declared: the calibrated medium cell, unscaled.
    assert live_demand({"demand": {"peak_vehicles_per_hour": 2600}}) == ("medium", 1.0)
    assert live_demand({}) == ("medium", 1.0)


@pytest.mark.parametrize(
    "network", ["monaco", "tunis", "sf_mission_2x2", "sf_mission_3x3"]
)
def test_live_networks_declare_vehicles_and_pedestrians(network):
    """A live network without its own rates falls back to rates its size outgrows."""
    from cotraffic import config

    dem = config.load("networks", network)["demand"]
    assert dem["live_vehicles_per_hour"] > 0
    assert dem["pedestrians_per_hour"] > 0


def test_metrics_are_measured_and_history_records_a_sample(monkeypatch):
    monkeypatch.setattr("api.simulation._lanes_by_tls", lambda scenario: {})
    session = SimulationSession()
    session._reset_telemetry()
    vehicles = [_vehicle(1), _vehicle(2, waiting=True), _vehicle(3, waiting=True)]

    metrics = session._metrics(_FakeEnv(), "grid-2x2", vehicles, [], [], 10, "00:00:10")

    assert metrics["queued"] == 2
    assert metrics["arrivedTotal"] == 2
    assert metrics["avgSpeedKmh"] > 0
    assert len(session._history) == 1
    sample = session._history[0]
    assert sample["t"] == 10
    assert sample["queued"] == 2


def test_junctions_publish_the_measured_remaining_green(monkeypatch):
    monkeypatch.setattr(
        "api.simulation._lanes_by_tls", lambda scenario: {"J1": ["edge-0", "edge-1"]}
    )
    session = SimulationSession()
    session._reset_telemetry()
    vehicles = [_vehicle(0), _vehicle(1)]
    signals = [{"id": "J1", "green": 27.5, "duration": 86400.0, "phase": 0, "state": "GG"}]

    metrics = session._metrics(_FakeEnv(), "grid-2x2", vehicles, [], signals, 10, "00:00:10")

    junction = metrics["junctions"][0]
    assert junction["green"] == 27.5
    assert junction["duration"] == 86400.0


def test_remaining_green_refuses_a_held_open_phase():
    from api.simulation import _remaining_green

    class _Tls:
        def __init__(self, next_switch: float) -> None:
            self.next_switch = next_switch

        def getNextSwitch(self, tls_id: str) -> float:  # noqa: N802 - TraCI name
            return self.next_switch

    class _Conn:
        def __init__(self, next_switch: float) -> None:
            self.trafficlight = _Tls(next_switch)

    assert _remaining_green(_Conn(45.0), "J1", 10) == 35.0
    # A phase held open for a day is not a split the panel can display.
    assert _remaining_green(_Conn(86400.0), "J1", 10) is None


def test_signal_changes_are_counted_but_not_published():
    session = SimulationSession()
    session._reset_telemetry()
    first = [{"id": "J1", "state": "GrGr", "phase": 0, "duration": 30, "nextSwitch": 40}]
    second = [{"id": "J1", "state": "rGrG", "phase": 1, "duration": 30, "nextSwitch": 70}]

    # The first publish only seeds the comparison; the transition is counted, but
    # publishing every phase change would drown the feed.
    session._publish_events([], [], 10, "00:00:10", first)
    events = session._publish_events([], [], 40, "00:00:40", second)

    assert all(event["kind"] != "signalChange" for event in events)
    assert session._phase_changes == 1


def test_operator_incident_requires_a_live_run():
    session = SimulationSession()
    with pytest.raises(ValueError, match="start a live run"):
        session.inject_incident()


def test_operator_incident_is_published_in_the_snapshot():
    session = SimulationSession()
    session._reset_telemetry()
    with session.lock:
        session.state.update({"status": "running", "simulationTime": 42, "clock": "00:00:42"})

    snapshot = session.inject_incident()

    event = snapshot["events"][-1]
    assert event["kind"] == "incident"
    assert event["severity"] == "critical"
    assert event["detail"]["source"] == "operator"
    assert event["t"] == 42


def test_history_endpoint_reports_samples():
    body = client.get("/api/simulation/history").json()
    assert "samples" in body
    assert isinstance(body["samples"], list)
