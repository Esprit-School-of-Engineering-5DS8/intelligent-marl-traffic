"""Metric definitions checked on small hand-written SUMO output files."""

import numpy as np
import pytest

from cotraffic import config
from cotraffic.evaluation.metrics import compute_metrics, count_conflicts, gini

ROUTES = """<routes>
    <vehicle id="car_0" depart="100.00"><route edges="a b"/></vehicle>
    <vehicle id="car_1" depart="1000.00"><route edges="a b"/></vehicle>
    <vehicle id="car_2" depart="1100.00"><route edges="a b"/></vehicle>
    <vehicle id="car_3" depart="1200.00"><route edges="a b"/></vehicle>
    <vehicle id="car_4" depart="1300.00"><route edges="a b"/></vehicle>
    <vehicle id="ev_0" depart="1400.00"><route edges="a b"/></vehicle>
    <vehicle id="incident_0" depart="1500.00"><route edges="a"/></vehicle>
    <flow id="bus_L1_a" begin="1000" end="1600" period="300" route="r"/>
</routes>
"""

EM = '<emissions CO2_abs="{co2}" NOx_abs="100" fuel_abs="1000"/>'


def trip(vid, depart, delay, arrival, wait, count, loss, length=1000.0, co2=200000.0):
    duration = (arrival - depart) if arrival >= 0 else 0
    return (
        f'<tripinfo id="{vid}" depart="{depart}" departDelay="{delay}" arrival="{arrival}" '
        f'duration="{duration}" routeLength="{length}" waitingTime="{wait}" '
        f'waitingCount="{count}" timeLoss="{loss}">{EM.format(co2=co2)}</tripinfo>'
    )


TRIPINFO = (
    "<tripinfos>"
    + "".join(
        [
            trip("car_0", 100, 0, 200, 10, 1, 20),  # warm-up: excluded
            trip("car_1", 1000, 0, 1100, 20, 1, 30),  # normal trip, 100 s
            trip("car_2", 1110, 10, 1300, 40, 2, 60),  # inserted 10 s late: travel 200 s
            trip("car_3", 1200, 0, -1, 50, 3, 80),  # unfinished at the end (t = 2000)
            trip("ev_0", 1400, 0, 1500, 0, 0, 5),  # emergency vehicle
            trip("incident_0", 1500, 0, 1600, 900, 1, 900),  # never counted
            trip("bus_L1_a.0", 1000, 0, 1150, 30, 2, 40),
            trip("bus_L1_a.1", 1300, 0, 1400, 10, 1, 20),
        ]
    )
    + "</tripinfos>"
)
# car_4 has no tripinfo: it was never inserted

STATS = """<statistics>
    <vehicles loaded="9" inserted="8" running="1" waiting="1"/>
    <teleports total="1" jam="1" yield="0" wrongLane="0"/>
    <safety collisions="0" emergencyStops="0" emergencyBraking="4"/>
    <personTeleports total="0"/>
</statistics>"""

SUMMARY = (
    "<summary>"
    + "".join(
        f'<step time="{t}" running="10" waiting="{1 if t >= 1500 else 0}" halting="{t // 100}" '
        f'arrived="0" meanWaitingTime="1" meanSpeed="10"/>'
        for t in range(0, 2000, 100)
    )
    + "</summary>"
)


@pytest.fixture
def outputs(tmp_path):
    (tmp_path / "tripinfo.xml").write_text(TRIPINFO)
    (tmp_path / "statistics.xml").write_text(STATS)
    (tmp_path / "summary.xml").write_text(SUMMARY)
    routes = tmp_path / "routes.rou.xml"
    routes.write_text(ROUTES)
    return tmp_path, routes


def test_population_and_travel_time_definitions(outputs):
    out, routes = outputs
    protocol = config.load_protocol()
    m, series, dist = compute_metrics(
        out, [routes], (900.0, 1600.0), 2000.0, protocol, teleported={"car_1"}, ssm=False
    )
    # population: car_1..car_4, ev_0 and the two buses of the flow (car_0 is in the warm-up)
    assert m["vehicles"] == 7
    assert m["never_inserted"] == 1  # car_4
    assert m["unfinished"] == 2  # car_3 (running) and car_4 (never inserted)
    assert m["teleported_vehicles"] == 1
    travel = {
        "car_1": 100 + 300,  # teleport penalty
        "car_2": 1300 - 1100,  # counted from the planned departure
        "car_3": 2000 - 1200,  # censored at the end
        "car_4": 2000 - 1300,  # never inserted
        "ev_0": 100,
        "bus_L1_a.0": 150,
        "bus_L1_a.1": 100,
    }
    assert m["mean_travel_time"] == pytest.approx(np.mean(list(travel.values())))
    assert m["mean_travel_time_completed"] == pytest.approx(np.mean([200, 100, 150, 100]))
    waits = [20, 40 + 10, 50, 700, 0, 30, 10]
    assert m["mean_waiting_time"] == pytest.approx(np.mean(waits))
    assert m["max_waiting_time"] == pytest.approx(700)
    assert m["ev_count"] == 1 and m["ev_delay"] == pytest.approx(5)
    assert m["bus_count"] == 2
    assert m["teleports_total"] == 1 and m["hard_braking_events"] == 4
    # throughput: arrivals inside [900, 1600) excluding the incident vehicle
    assert m["throughput_per_h"] == pytest.approx(5 * 3600 / 700)
    # queue over the window: halting = t // 100 for t in 900..1500
    assert m["mean_queue"] == pytest.approx(np.mean(range(9, 16)))
    assert list(series.columns[:2]) == ["minute", "halting"]
    assert dist["vehicles"].sum() == 7
    assert m["median_waiting_time"] == pytest.approx(np.median(waits))


def test_person_weighted_delay_counts_bus_passengers(outputs):
    out, routes = outputs
    protocol = config.load_protocol()
    m, _, _ = compute_metrics(out, [routes], (900.0, 1600.0), 2000.0, protocol, ssm=False)
    occ = protocol["occupancy"]
    losses = {
        "car_1": 30,
        "car_2": 70,
        "car_3": 80,
        "car_4": 700,
        "ev_0": 5,
        "bus_L1_a.0": 40,
        "bus_L1_a.1": 20,
    }
    weights = {
        k: occ["bus"]
        if k.startswith("bus")
        else occ["emergency"]
        if k.startswith("ev")
        else occ["passenger"]
        for k in losses
    }
    expected = sum(weights[k] * v for k, v in losses.items()) / sum(weights.values())
    assert m["person_weighted_delay"] == pytest.approx(expected)


def test_gini():
    assert gini(np.array([5.0, 5.0, 5.0])) == pytest.approx(0.0)
    assert gini(np.array([0.0, 0.0, 0.0])) == 0.0
    assert gini(np.array([0.0, 0.0, 0.0, 10.0])) == pytest.approx(0.75)


def conflict(begin, ego, foe, ttc):
    return (
        f'<conflict begin="{begin}" end="{begin + 5}" ego="{ego}" foe="{foe}">'
        f'<minTTC time="{begin + 1}" value="{ttc}"/></conflict>'
    )


def test_ssm_conflicts_are_counted_once_per_pair(tmp_path):
    ssm = tmp_path / "ssm.xml"
    events = [
        conflict(1000.0, "a", "b", 0.8),  # counted
        conflict(1000.0, "b", "a", 0.9),  # same pair and start: not counted twice
        conflict(1100.0, "c", "d", 2.5),  # above the threshold
        conflict(1200.0, "e", "f", "NA"),  # no time-to-collision
        conflict(100.0, "g", "h", 0.5),  # during the warm-up
    ]
    ssm.write_text("<SSMLog>" + "".join(events) + "</SSMLog>")
    assert count_conflicts(ssm, 1.5, 900, 1600) == 1
