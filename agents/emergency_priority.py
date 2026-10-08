"""agents/emergency_priority.py
Emergency Vehicle Priority Agent — Owner: Amen Allah Ben Aissa (E1, E2)

Two priority mechanisms:
- Reactive (M2): an ambulance within ACTIVATION_DISTANCE_M of the light gets
  the axis it needs immediately.
- Predictive corridor (M3): for any upcoming light, if the ETA model predicts
  the ambulance arrives within ETA_TRIGGER_S, clear that light early too.

Environment knobs (no file edits needed):
    EV_ACTIVATION_DISTANCE_M=150   reactive range in meters
    EV_ETA_TRIGGER_S=10            corridor trigger horizon in seconds (0 = off)
"""

import os
import traci

from forecasting.ev_arrival_predictor import EVArrivalPredictor, extract_ev_features

ACTIVATION_DISTANCE_M = float(os.environ.get("EV_ACTIVATION_DISTANCE_M", "150"))
ETA_TRIGGER_S = float(os.environ.get("EV_ETA_TRIGGER_S", "0"))

_PREDICTOR = None


def axis_of(road_id: str) -> int:
    """Return 0 for a North-South road, 1 for East-West. Works on both grids."""
    if "top" in road_id or "bottom" in road_id:
        return 0
    if "left" in road_id or "right" in road_id:
        return 1
    return 0 if road_id[0] == road_id[2] else 1


def lane_axis(lane_id: str) -> int:
    """Same as axis_of but for lane IDs like 'A1A0_0'."""
    return axis_of(lane_id.rsplit("_", 1)[0])


def axis_from_link(tls_id: str, link_index: int):
    """Axis of the approach that uses this signal link, from the light's own
    controlled links (correct even when the ambulance will turn)."""
    try:
        links = traci.trafficlight.getControlledLinks(tls_id)
    except Exception:
        return None
    if 0 <= link_index < len(links) and links[link_index]:
        incoming_lane = links[link_index][0][0]
        return axis_of(incoming_lane.rsplit("_", 1)[0])
    return None


def detect_approaching_evs(tls_id: str):
    """Return [(ev_id, distance_m, axis)] for ambulances whose next light is
    this one, nearest first."""
    approaching = []
    for veh_id in traci.vehicle.getIDList():
        if traci.vehicle.getVehicleClass(veh_id) != "emergency":
            continue
        road_id = traci.vehicle.getRoadID(veh_id)
        if road_id.startswith(":"):
            continue
        next_tls = traci.vehicle.getNextTLS(veh_id)
        if not next_tls:
            continue
        light_id, _, distance, _ = next_tls[0]
        if light_id != tls_id:
            continue
        approaching.append((veh_id, distance, axis_of(road_id)))
    approaching.sort(key=lambda item: item[1])
    return approaching


def select_action_max_pressure(state: dict) -> int:
    ns_queue = 0
    ew_queue = 0
    for lane_id, queue in state["lane_queues"].items():
        if lane_axis(lane_id) == 0:
            ns_queue += queue
        else:
            ew_queue += queue
    return 0 if ns_queue >= ew_queue else 1


def _get_predictor():
    global _PREDICTOR
    if _PREDICTOR is None and ETA_TRIGGER_S > 0:
        try:
            _PREDICTOR = EVArrivalPredictor().load()
        except Exception:
            _PREDICTOR = False
    return _PREDICTOR if _PREDICTOR not in (None, False) else None


def eta_priority_axis(tls_id: str):
    """Axis to serve if an ambulance is predicted to reach this light within
    ETA_TRIGGER_S; None otherwise."""
    predictor = _get_predictor()
    if predictor is None:
        return None
    best = None
    for veh_id in traci.vehicle.getIDList():
        if traci.vehicle.getVehicleClass(veh_id) != "emergency":
            continue
        if traci.vehicle.getRoadID(veh_id).startswith(":"):
            continue
        for rank, (light_id, link_index, _, _) in enumerate(
                traci.vehicle.getNextTLS(veh_id), start=1):
            if light_id != tls_id:
                continue
            axis = axis_from_link(light_id, link_index)
            if axis is None:
                continue
            features = extract_ev_features(traci, veh_id, light_id, rank)
            if features is None:
                continue
            eta = predictor.predict(features)
            if eta <= ETA_TRIGGER_S and (best is None or eta < best[0]):
                best = (eta, axis)
    return best[1] if best else None


def select_action_priority(tls_id: str, state: dict) -> int:
    approaching = detect_approaching_evs(tls_id)
    if approaching:
        _, distance, axis = approaching[0]
        if distance <= ACTIVATION_DISTANCE_M:
            return axis
    if ETA_TRIGGER_S > 0:
        axis = eta_priority_axis(tls_id)
        if axis is not None:
            return axis
    return select_action_max_pressure(state)
