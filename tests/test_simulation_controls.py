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


class _FakeVehicle:
    """A vehicle already driving when the weather changes."""

    def __init__(self) -> None:
        self.speed = {"car.0": 1.0, "car.1": 0.95}

    def getIDList(self) -> list[str]:
        return list(self.speed)

    def getSpeedFactor(self, vehicle_id: str) -> float:
        return self.speed[vehicle_id]

    def setSpeedFactor(self, vehicle_id: str, value: float) -> None:
        self.speed[vehicle_id] = value


class _FakeConnection:
    def __init__(self) -> None:
        self.trafficlight = _FakeTrafficLight()
        self.simulation = _FakeSimulation()
        self.vehicletype = _FakeVehicleType()
        self.vehicle = _FakeVehicle()


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


def test_rain_slows_the_traffic_already_driving_and_restores_it():
    """SUMO copies a type's speedFactor at insertion, so the type alone is not enough."""
    session = _session()
    connection = _FakeConnection()

    session._weather = "rain"
    session._apply_weather(connection)
    assert connection.vehicle.speed == {
        "car.0": pytest.approx(0.75),
        "car.1": pytest.approx(0.7125),
    }

    session._weather = "clear"
    session._apply_weather(connection)
    assert connection.vehicle.speed == {
        "car.0": pytest.approx(1.0),
        "car.1": pytest.approx(0.95),
    }


def test_weather_is_remembered_before_a_run_starts():
    """Turning rain on before starting must survive into the next run."""
    session = _session(running=False)
    body = session.set_weather("rain")
    assert body["weather"] == "rain"
    assert session.snapshot()["weather"] == "rain"


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

# --- demand dial -------------------------------------------------------------------

def test_demand_level_is_remembered_before_a_run_starts():
    """Choosing a level before starting must survive into the next run."""
    session = _session(running=False)
    body = session.set_demand_level("low")
    assert body["demandLevel"] == "low"
    assert session.snapshot()["demandLevel"] == "low"


def test_demand_level_rejects_an_unknown_level():
    session = _session()
    with pytest.raises(ValueError, match="unknown demand level"):
        session.set_demand_level("gridlock")


def test_demand_level_endpoint_round_trips():
    session = _session()
    simulation_routes.session = session
    response = client.post("/api/simulation/demand", json={"level": "medium"})
    assert response.status_code == 200
    assert response.json()["demandLevel"] == "medium"


def test_demand_level_endpoint_refuses_a_bad_level():
    simulation_routes.session = _session()
    assert client.post("/api/simulation/demand", json={"level": "gridlock"}).status_code == 422


def test_demand_scale_multiplies_the_networks_own_live_rate():
    """The dial is a fraction of each network's live calibration, not a shared level.

    ``high`` has to reproduce the live map's previous behaviour exactly, otherwise
    adding the dial would silently change every existing run.
    """
    from api.simulation import DEFAULT_DEMAND_LEVEL, live_demand, live_demand_scale

    net_cfg = {"demand": {"peak_vehicles_per_hour": 13000, "live_vehicles_per_hour": 14000}}
    _, base = live_demand(net_cfg)

    assert DEFAULT_DEMAND_LEVEL == "high"
    assert live_demand_scale(net_cfg, "high") == pytest.approx(base)
    assert live_demand_scale(net_cfg, "medium") == pytest.approx(base * 0.7)
    assert live_demand_scale(net_cfg, "low") == pytest.approx(base * 0.45)


def test_demand_scale_falls_back_when_a_network_declares_no_live_rate():
    from api.simulation import live_demand_scale

    net_cfg = {"demand": {"peak_vehicles_per_hour": 900}}
    assert live_demand_scale(net_cfg, "high") == pytest.approx(1.0)
    assert live_demand_scale(net_cfg, "low") == pytest.approx(0.45)
