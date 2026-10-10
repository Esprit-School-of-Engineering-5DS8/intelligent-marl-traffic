from environment.incidents import IncidentInjector, IncidentSpec


class FakeTraCIException(Exception):
    pass


class FakeExceptions:
    TraCIException = FakeTraCIException


class FakeVehicle:
    def __init__(self):
        self.ids = []
        self.stops = []
        self.positions = {}

    def getIDList(self):
        return list(self.ids)

    def getLanePosition(self, veh_id):
        return self.positions.get(veh_id, 10.0)

    def setStop(self, veh_id, edge_id, pos, laneIndex, duration):
        self.stops.append({
            "veh_id": veh_id, "edge_id": edge_id, "pos": pos,
            "lane_index": laneIndex, "duration": duration,
        })

    def add(self, veh_id, route_id, typeID, depart, departLane, departPos, departSpeed):
        self.ids.append(veh_id)


class FakeLane:
    def __init__(self):
        self.vehicles = {}

    def getIDList(self):
        return ["B1B2_0", "B1B2_1", "B0B1_0"]

    def getLength(self, lane_id):
        return 200.0

    def getLastStepVehicleIDs(self, lane_id):
        return list(self.vehicles.get(lane_id, []))


class FakeRoute:
    def __init__(self):
        self.routes = []

    def getIDList(self):
        return list(self.routes)

    def add(self, route_id, edges):
        self.routes.append(route_id)


class FakeTraci:
    def __init__(self):
        self.exceptions = FakeExceptions
        self.vehicle = FakeVehicle()
        self.lane = FakeLane()
        self.route = FakeRoute()


SPEC = IncidentSpec(edge_id="B1B2", start_s=10.0, duration_s=5.0)


def test_schedules_and_blocks_every_lane_once():
    fake = FakeTraci()
    injector = IncidentInjector(SPEC, traci_module=fake)

    injector.apply(9.0)
    assert fake.vehicle.ids == []

    injector.apply(10.0)
    assert fake.vehicle.ids == ["incident_B1B2_0", "incident_B1B2_1"]
    assert fake.route.routes == ["incident_route_B1B2_0", "incident_route_B1B2_1"]
    assert fake.vehicle.stops == []

    injector.apply(11.0)
    assert len(fake.vehicle.stops) == 2
    for stop, lane_index in zip(fake.vehicle.stops, (0, 1)):
        assert stop["edge_id"] == "B1B2"
        assert stop["lane_index"] == lane_index
        assert stop["pos"] == 199.9
        assert stop["duration"] == 4.0

    injector.apply(12.0)
    assert len(fake.vehicle.stops) == 2


def test_stops_existing_front_vehicle_instead_of_adding():
    fake = FakeTraci()
    fake.lane.vehicles["B1B2_0"] = ["veh_rear", "veh_front"]
    fake.vehicle.positions = {"veh_rear": 10.0, "veh_front": 150.0}
    injector = IncidentInjector(SPEC, traci_module=fake)

    injector.apply(10.0)
    assert "veh_front" in [s["veh_id"] for s in fake.vehicle.stops]
    assert "incident_B1B2_0" not in fake.vehicle.ids
    assert fake.vehicle.ids == ["incident_B1B2_1"]


def test_stops_after_incident_end():
    fake = FakeTraci()
    injector = IncidentInjector(SPEC, traci_module=fake)

    injector.apply(10.0)
    injector.apply(11.0)
    injector.apply(16.0)
    adds_before = list(fake.vehicle.ids)
    injector.apply(17.0)
    assert fake.vehicle.ids == adds_before
