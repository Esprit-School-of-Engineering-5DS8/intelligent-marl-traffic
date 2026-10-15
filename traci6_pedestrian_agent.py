"""Demand-responsive agent for one signalized pedestrian crossing."""


class PedestrianSignalAgent:
    MINIMUM_GROUP_SIZE = 2

    def __init__(
        self,
        traci,
        name,
        approach_edge,
        waiting_lane,
        crossing_lane,
        link_index,
        step_length,
        minimum_group_size=MINIMUM_GROUP_SIZE,
        minimum_green_seconds=10.0,
        maximum_green_seconds=60.0,
        clearance_seconds=1.0,
    ):
        self.traci = traci
        self.name = name
        self.approach_lane = f"{approach_edge}_0"
        self.waiting_lane = waiting_lane
        self.crossing_lane = crossing_lane
        self.link_index = link_index
        self.step_length = step_length
        self.minimum_group_size = minimum_group_size
        self.minimum_green_steps = round(minimum_green_seconds / step_length)
        self.maximum_green_steps = round(maximum_green_seconds / step_length)
        self.clearance_steps = round(clearance_seconds / step_length)

    def waiting_pedestrian_count(self):
        """Count only people waiting at this crossing."""
        waiting = 0
        for person_id in self.traci.person.getIDList():
            lane_id = self.traci.person.getLaneID(person_id)
            if lane_id == self.waiting_lane:
                waiting += 1
            elif lane_id == self.approach_lane:
                position = self.traci.person.getLanePosition(person_id)
                if position <= 8.0:
                    waiting += 1
        return waiting

    def has_request(self):
        """Request a crossing once the configured group has assembled."""
        return self.waiting_pedestrian_count() >= self.minimum_group_size

    def has_pedestrians_to_clear(self):
        """Check whether anyone is waiting at or using this crossing."""
        for person_id in self.traci.person.getIDList():
            lane_id = self.traci.person.getLaneID(person_id)
            if lane_id in (self.waiting_lane, self.crossing_lane):
                return True
            if lane_id == self.approach_lane:
                position = self.traci.person.getLanePosition(person_id)
                if position <= 8.0:
                    return True
        return False

    def serve_request(self, advance_step, set_crossing_state):
        """Serve this crossing's queue while other signal links remain red."""
        if not self.has_request():
            return False

        set_crossing_state("G")
        for step in range(self.maximum_green_steps):
            if step >= self.minimum_green_steps and not self.has_pedestrians_to_clear():
                break
            if not advance_step():
                return False
        else:
            raise RuntimeError(
                f"Pedestrian crossing {self.name} did not clear within "
                f"{self.maximum_green_steps * self.step_length:g} seconds"
            )

        set_crossing_state("r")
        for _ in range(self.clearance_steps):
            if not advance_step():
                return False

        return True
