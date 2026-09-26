"""Display names, order and colours shared by tables, figures and the dashboard."""

from __future__ import annotations

METHOD_LABELS = {
    "ft": "FT",
    "act": "ACT",
    "mp": "MP",
    "ev_rule": "EV-RULE",
    "ind": "IND",
    "coop": "COOP",
    "coop_eco05": "COOP-ECO (λ=0.5)",
    "coop_eco": "COOP-ECO (λ=1.0)",
    "coop_full": "COOP-FULL",
    "random": "Random",
}
METHOD_ORDER = list(METHOD_LABELS)
BASELINE_METHODS = ("ft", "act", "mp", "ev_rule")
DEMAND_ORDER = ["low", "medium", "peak", "rush_profile"]

# Categorical hues checked for colour-vision deficiency and normal-vision separation in
# the orders the figures use (adjacent CVD delta E >= 9.2 in OKLab x100). FT is the
# status-quo reference and is drawn in neutral grey on purpose; it is always labelled.
METHOD_COLORS = {
    "ft": "#8f8d88",
    "act": "#4a3aa7",
    "mp": "#eb6834",
    "ev_rule": "#e34948",
    "ind": "#1baf7a",
    "coop": "#2a78d6",
    "coop_eco05": "#e87ba4",
    "coop_eco": "#008300",
    "coop_full": "#eda100",
    "random": "#52514e",
}
SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e4e3df"
SEQUENTIAL_CMAP = "Blues"
DIVERGING_CMAP = "RdBu"


METRIC_LABELS = {
    "mean_travel_time": "Mean travel time (s)",
    "mean_waiting_time": "Mean waiting time (s)",
    "mean_time_loss": "Mean time loss (s)",
    "mean_queue": "Mean queue (veh)",
    "throughput_per_h": "Throughput (veh/h)",
    "unfinished": "Unfinished vehicles",
    "teleports_total": "Teleports",
    "never_inserted": "Never-inserted vehicles",
    "co2_total_kg": "CO2 total (kg)",
    "co2_g_per_km": "CO2 (g/km)",
    "nox_total_g": "NOx total (g)",
    "fuel_total_kg": "Fuel (kg)",
    "stops_per_vehicle": "Stops per vehicle",
    "ssm_conflicts_per_1000_veh": "Conflicts TTC<1.5 s per 1000 veh",
    "hard_braking_events": "Hard-braking events",
    "shield_interventions": "Shield interventions",
    "p95_waiting_time": "P95 waiting time (s)",
    "max_waiting_time": "Max waiting time (s)",
    "gini_waiting_time": "Gini of waiting times",
    "person_weighted_delay": "Person-weighted delay (s)",
    "ped_mean_waiting_time": "Pedestrian mean wait (s)",
    "ped_max_waiting_time": "Pedestrian max wait (s)",
    "bus_delay": "Bus delay (s)",
    "ev_travel_time": "EV travel time (s)",
    "ev_delay": "EV delay (s)",
    "inference_ms_per_decision": "Inference per decision (ms)",
    "sim_wall_time_s": "Simulation wall time (s)",
}
HIGHER_IS_BETTER = {"throughput_per_h"}


def label(method: str) -> str:
    return METHOD_LABELS.get(method, method)


def method_sort_key(method: str) -> int:
    return METHOD_ORDER.index(method) if method in METHOD_ORDER else len(METHOD_ORDER)
