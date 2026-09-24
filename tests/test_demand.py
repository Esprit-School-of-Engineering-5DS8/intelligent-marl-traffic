import xml.etree.ElementTree as ET

import pytest

from cotraffic.demand.generator import DemandRequest, generate

pytestmark = pytest.mark.sumo


def _departures(path, tag="vehicle"):
    root = ET.parse(path).getroot()
    return [(el.get("id"), float(el.get("depart"))) for el in root.iter(tag)]


def test_same_seed_gives_identical_demand():
    a = generate(DemandRequest("grid2x2", "low", (), seed=11, duration=900), force=True)
    first = a.route_files[0].read_text(encoding="utf-8").split("-->", 2)[-1]
    b = generate(DemandRequest("grid2x2", "low", (), seed=11, duration=900), force=True)
    assert b.route_files[0].read_text(encoding="utf-8").split("-->", 2)[-1] == first


def test_different_seeds_give_different_demand():
    a = generate(DemandRequest("grid2x2", "low", (), seed=1, duration=900))
    b = generate(DemandRequest("grid2x2", "low", (), seed=2, duration=900))
    assert _departures(a.route_files[0]) != _departures(b.route_files[0])


def test_scenarios_share_the_car_demand_of_their_seed():
    normal = generate(DemandRequest("grid2x2", "medium", (), seed=5, duration=900))
    events = generate(
        DemandRequest("grid2x2", "medium", ("emergency", "incident"), seed=5, duration=900)
    )
    cars = [d for d in _departures(normal.route_files[0]) if d[0].startswith("car_")]
    cars_events = [d for d in _departures(events.route_files[0]) if d[0].startswith("car_")]
    assert cars == cars_events
    assert events.meta["emergency"] and events.meta["incident"]["edge"] == "A1B1"


def test_volume_follows_the_demand_level():
    low = generate(DemandRequest("grid2x2", "low", (), seed=3, duration=3600)).meta["cars"]
    peak = generate(DemandRequest("grid2x2", "peak", (), seed=3, duration=3600)).meta["cars"]
    assert 1300 * 0.45 * 0.85 < low < 1300 * 0.45 * 1.15
    assert 1300 * 0.85 < peak < 1300 * 1.15


def test_emergency_vehicles_depart_inside_the_window():
    b = generate(DemandRequest("grid2x2", "low", ("emergency",), seed=4, offset=900, duration=3600))
    departs = [ev["depart"] for ev in b.meta["emergency"]]
    assert 3 <= len(departs) <= 5
    assert all(900 + 300 <= t <= 900 + 3300 for t in departs)


def test_pedestrians_and_buses_are_written():
    b = generate(DemandRequest("grid2x2", "low", ("pedestrians", "buses"), seed=4, duration=900))
    names = [p.name for p in b.route_files]
    assert "persons.rou.xml" in names and "buses.rou.xml" in names
    assert b.meta["pedestrians"] > 0 and len(b.meta["bus_lines"]) == 2
