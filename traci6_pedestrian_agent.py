"""Independent tabular Q-learning agent for one signalized crossing."""

import random


WAIT = 0
REQUEST_CROSSING = 1
ACTION_COUNT = 2
ALPHA = 0.1
GAMMA = 0.9
MAX_WAIT_BEFORE_REQUEST_SECONDS = 60.0


def _bucket(value, thresholds):
    for index, threshold in enumerate(thresholds):
        if value <= threshold:
            return index
    return len(thresholds)


class PedestrianSignalAgent:
    def __init__(
        self,
        traci,
        name,
        approach_edge,
        waiting_lane,
        crossing_lane,
        link_index,
        step_length,
        q_values=None,
    ):
        self.traci = traci
        self.name = name
        self.approach_lane = f"{approach_edge}_0"
        self.waiting_lane = waiting_lane
        self.crossing_lane = crossing_lane
        self.link_index = link_index
        self.step_length = step_length
        self.minimum_green_steps = round(10.0 / step_length)
        self.maximum_green_steps = round(60.0 / step_length)
        self.clearance_steps = round(1.0 / step_length)
        self.q_values = q_values if q_values is not None else {}
        self.requested = False
        self._first_seen = {}
        self._last_state = None
        self._last_action = None
        self._last_time = None
        self._last_waiting_count = 0
        self._service_reward = 0.0
        self.learned_since_last_decision = False

    def _waiting_people(self):
        """Return pedestrians who have reached the crossing approach."""
        people = {}
        for person_id in self.traci.person.getIDList():
            lane_id = self.traci.person.getLaneID(person_id)
            if lane_id == self.waiting_lane:
                people[person_id] = lane_id
            elif lane_id == self.approach_lane:
                if self.traci.person.getLanePosition(person_id) <= 8.0:
                    people[person_id] = lane_id

        now = self.traci.simulation.getTime()
        for person_id in people:
            self._first_seen.setdefault(person_id, now)
        self._first_seen = {
            person_id: seen_at
            for person_id, seen_at in self._first_seen.items()
            if person_id in people
        }
        return people, now

    def waiting_pedestrian_count(self):
        """Count only people waiting at this crossing."""
        people, _ = self._waiting_people()
        return len(people)

    def oldest_waiting_seconds(self):
        people, now = self._waiting_people()
        if not people:
            return 0.0
        return max(now - self._first_seen[person_id] for person_id in people)

    def observation(self, vehicle_context):
        """Build a local state augmented with information from the vehicle agent."""
        count = self.waiting_pedestrian_count()
        oldest_wait = self.oldest_waiting_seconds()
        vehicle_queues = vehicle_context["vehicle_queues"]
        vehicle_pressure = max(vehicle_queues, default=0)
        return (
            _bucket(count, (0, 1, 3, 6)),
            _bucket(oldest_wait, (0, 15, 30, 60)),
            _bucket(vehicle_pressure, (0, 2, 5, 9)),
            int(vehicle_context["active_signal"]),
            int(vehicle_context["emergency"]),
        )

    @staticmethod
    def _state_key(observation):
        return ",".join(map(str, observation))

    def _learn_previous_action(self, next_state, now):
        self.learned_since_last_decision = False
        if self._last_state is None:
            return

        elapsed = max(0.0, now - self._last_time)
        reward = -self._last_waiting_count * elapsed + self._service_reward
        current_values = self.q_values.setdefault(
            self._last_state, [0.0] * ACTION_COUNT
        )
        next_values = self.q_values.setdefault(next_state, [0.0] * ACTION_COUNT)
        discount = GAMMA ** (elapsed / 10.0)
        target = reward + discount * max(next_values)
        current_values[self._last_action] += ALPHA * (
            target - current_values[self._last_action]
        )
        self._service_reward = 0.0
        self.learned_since_last_decision = True

    def decide(self, vehicle_context, epsilon):
        """Choose whether to wait or request service, then learn from the last action."""
        observation = self.observation(vehicle_context)
        state = self._state_key(observation)
        count = self.waiting_pedestrian_count()
        now = self.traci.simulation.getTime()
        self._learn_previous_action(state, now)

        if count == 0:
            action = WAIT
            self.requested = False
        elif self.requested:
            action = REQUEST_CROSSING
        elif self.oldest_waiting_seconds() >= MAX_WAIT_BEFORE_REQUEST_SECONDS:
            action = REQUEST_CROSSING
        elif random.random() < epsilon:
            action = random.randrange(ACTION_COUNT)
        else:
            values = self.q_values.setdefault(state, [0.0] * ACTION_COUNT)
            best_value = max(values)
            best_actions = [
                index for index, value in enumerate(values) if value == best_value
            ]
            action = random.choice(best_actions)

        self.requested = self.requested or (
            action == REQUEST_CROSSING and count > 0
        )
        self._last_state = state
        self._last_action = action
        self._last_time = now
        self._last_waiting_count = count
        return self.requested

    def mark_served(self):
        """Reward the RL policy when its crossing request is successfully served."""
        if self.requested:
            self._service_reward += 15.0
            self.requested = False

    def has_request(self):
        return self.requested and self.waiting_pedestrian_count() > 0

    def pedestrians_to_clear(self):
        """Snapshot the people already waiting when a crossing phase begins."""
        return {
            person_id
            for person_id in self.traci.person.getIDList()
            if self._is_waiting_or_crossing(person_id)
        }

    def has_pedestrians_to_clear_from(self, person_ids):
        """Ignore arrivals after green starts so they cannot extend this phase."""
        return any(
            person_id in self.traci.person.getIDList()
            and self._is_waiting_or_crossing(person_id)
            for person_id in person_ids
        )

    def _is_waiting_or_crossing(self, person_id):
        lane_id = self.traci.person.getLaneID(person_id)
        if lane_id in (self.waiting_lane, self.crossing_lane):
            return True
        return (
            lane_id == self.approach_lane
            and self.traci.person.getLanePosition(person_id) <= 8.0
        )
