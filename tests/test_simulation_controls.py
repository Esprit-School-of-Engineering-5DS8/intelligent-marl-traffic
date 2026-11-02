"""Live-run controls behind the Optimize tab and Predict's forecast.

The dashboard must not offer a control that changes nothing: these tests pin the signal
queue's validation, the per-junction values, and the forecast endpoint's contract.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routes import simulation as simulation_routes
from api.simulation import NotRunning, SimulationSession

client = TestClient(app)


class _FakeTrafficLight:
    def __init__(self) -> None:
        self.calls: list[tuple[str, float]] = []

    def setPhaseDuration(self, tls: str, green: float) -> None:
        self.calls.append((tls, green))


class _FakeSimulation:
    def getTime(self) -> float:
        return 120.0


class _FakeVehicleType:
    def __init__(self) -> None:
        self.speed = {"car": 1.0, "bus": 0.9}
        self.tau = {"car": 1.0, "bus": 1.2}

    def getIDList(self) -> list[str]:
        return list(self.speed)

    def getSpeedFactor(self, type_id: str) -> float:
        return self.speed[type_id]

    def getTau(self, type_id: str) -> float:
        return self.tau[type_id]

    def setSpeedFactor(self, type_id: str, value: float) -> None:
        self.speed[type_id] = value

    def setTau(self, type_id: str, value: float) -> None:
        self.tau[type_id] = value


class _FakeConnection:
    def __init__(self) -> None:
        self.trafficlight = _FakeTrafficLight()
        self.simulation = _FakeSimulation()
        self.vehicletype = _FakeVehicleType()


def _session(running: bool = True) -> SimulationSession:
    session = SimulationSession()
    session._reset_telemetry()
    with session.lock:
        session.state.update(
            {
                "runId": "live-grid-2x2-1",
                "status": "running" if running else "idle",
                "scenario": "grid-2x2",
                "simulationTime": 120,
                "clock": "00:02:00",
                "signals": [
                    {"id": "J1", "duration": 30, "phase": 0, "state": "GrGr"},
                    {"id": "J2", "duration": 24, "phase": 1, "state": "rGrG"},
                ],
                "metrics": {
                    "junctions": [
                        {"id": "J1", "queue": 4, "pressure": 1.0, "avgSpeedKmh": 18.5},
                        {"id": "J2", "queue": 1, "pressure": 0.3, "avgSpeedKmh": 27.0},
                    ]
                },
            }
        )
    return session


def test_snapshot_carries_a_run_id():
    session = _session()
    assert session.snapshot()["runId"] == "live-grid-2x2-1"


def test_signal_change_needs_a_run():
    session = _session(running=False)
    with pytest.raises(NotRunning, match="start a live run"):
        session.queue_signal("J1", 40)


def test_signal_change_rejects_an_unknown_junction():
    session = _session()
    with pytest.raises(ValueError, match="unknown junction"):
        session.queue_signal("nope", 40)


def test_signal_change_rejects_an_out_of_range_green():
    session = _session()
    with pytest.raises(ValueError, match="between"):
        session.queue_signal("J1", 300)


def test_signal_change_is_applied_on_the_run_thread_and_published():
    session = _session()
    session.queue_signal("J1", 45)
    connection = _FakeConnection()

    assert list(session._pending_signals) == [{"tls": "J1", "green": 45.0}]
    session._apply_pending_signals(connection)

    assert connection.trafficlight.calls == [("J1", 45.0)]
    assert not session._pending_signals
    event = session._events[-1]
    assert event["kind"] == "signalChange"
    assert event["detail"] == {"tls": "J1", "green": 45.0, "source": "operator"}


def test_junctions_report_their_trend(monkeypatch):
    monkeypatch.setattr(
        "api.simulation._lanes_by_tls", lambda scenario: {"J1": frozenset({"edge-1"})}
    )
    session = _session()
    vehicles = [{"id": "v1", "speed": 5.0, "waiting": True, "lane": "edge-1", "waitingTime": 4.0}]

    class _Env:
        class conn:
            class simulation:
                @staticmethod
                def getArrivedNumber() -> int:
                    return 0

                @staticmethod
                def getDepartedNumber() -> int:
                    return 0

    session._metrics(_Env(), "grid-2x2", vehicles, [], [], 120, "00:02:00")
    body = session.junctions()

    junction = body["junctions"][0]
    assert junction["id"] == "J1"
    assert junction["queue"] == 1
    assert junction["avgSpeedKmh"] == pytest.approx(18.0)
    assert junction["trend"][-1]["t"] == 120


def test_forecast_endpoint_requires_a_run(monkeypatch):
    monkeypatch.setattr(simulation_routes, "session", _session(running=False))
    assert client.get("/api/simulation/forecast").status_code == 409


def test_forecast_endpoint_reads_the_run_history(monkeypatch):
    session = _session()
    for step in range(1, 13):
        session._history.append(
            {
                "t": step * 5,
                "clock": f"00:00:{step * 5:02d}",
                "vehicles": 30,
                "queued": 6 + step % 4,
                "avgSpeedKmh": 22.0,
                "arrived": step,
                "throughputPerMin": 4.0,
            }
        )
    monkeypatch.setattr(simulation_routes, "session", session)

    body = client.get("/api/simulation/forecast", params={"horizon": 5}).json()
    assert body["runId"] == "live-grid-2x2-1"
    assert body["samples"] == 12
    assert len(body["points"]) == 5
    assert body["method"].startswith("ewma")
    assert 0.3 <= body["confidence"] <= 0.95


def test_weather_rejects_unknown_conditions():
    session = _session()
    with pytest.raises(ValueError, match="unknown weather"):
        session.set_weather("snow")


def test_rain_slows_vehicles_and_clearing_restores_the_calibration():
    session = _session()
    connection = _FakeConnection()

    session._weather = "rain"
    session._apply_weather(connection)
    assert connection.vehicletype.speed["car"] == pytest.approx(0.75)
    assert connection.vehicletype.speed["bus"] == pytest.approx(0.675)
    assert connection.vehicletype.tau == {"car": 1.6, "bus": 1.6}

    session._weather = "clear"
    session._apply_weather(connection)
    assert connection.vehicletype.speed == {"car": 1.0, "bus": 0.9}
    assert connection.vehicletype.tau == {"car": 1.0, "bus": 1.2}


def test_weather_endpoint_publishes_the_new_condition(monkeypatch):
    session = _session()
    monkeypatch.setattr(simulation_routes, "session", session)

    accepted = client.post("/api/simulation/weather", json={"weather": "rain"})
    assert accepted.status_code == 200
    assert accepted.json()["weather"] == "rain"

    assert client.post("/api/simulation/weather", json={"weather": "snow"}).status_code == 422


def test_signal_endpoint_maps_the_run_and_validation_errors(monkeypatch):
    monkeypatch.setattr(simulation_routes, "session", _session(running=False))
    assert (
        client.post("/api/simulation/signal", json={"junction": "J1", "green": 40}).status_code
        == 409
    )

    monkeypatch.setattr(simulation_routes, "session", _session())
    assert (
        client.post("/api/simulation/signal", json={"junction": "nope", "green": 40}).status_code
        == 422
    )
    # Pydantic refuses values outside the SUMO-safe range before the session sees them.
    assert (
        client.post("/api/simulation/signal", json={"junction": "J1", "green": 400}).status_code
        == 422
    )
    accepted = client.post("/api/simulation/signal", json={"junction": "J1", "green": 45})
    assert accepted.status_code == 200
    assert accepted.json()["runId"] == "live-grid-2x2-1"
