#!/usr/bin/env python3
"""
generate_routes.py (grid_2x2)
Multi-modal traffic demand generator for the 2x2 SUMO grid network.

Supports:
- Vehicle classes: Passenger cars, Public transit buses, Emergency vehicles
- Pedestrian flows: Pedestrians walking along sidewalks and signalized crossings
- Dynamic traffic scenarios:
    * balanced        : Standard baseline traffic flow
    * rush_hour       : Asymmetric high-volume arterial surge
    * emergency_surge : Periodic emergency vehicle dispatches (Green Corridor tests)
    * pedestrian_heavy: Dense pedestrian crossings (School/Downtown safety tests)
"""

import os
import sys
import argparse
import random
import xml.etree.ElementTree as ET


def generate_multimodal_routes(
    output_file="grid2x2.rou.xml",
    scenario="balanced",
    duration=1800,
    total_vehicles=800,
    total_pedestrians=120,
    seed=42,
):
    random.seed(seed)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(script_dir, output_file)

    # Arterial vehicular routes
    arterial_routes = [
        ("w_to_e_row0", "left0A0 A0B0 B0right0"),
        ("w_to_e_row1", "left1A1 A1B1 B1right1"),
        ("e_to_w_row0", "right0B0 B0A0 A0left0"),
        ("e_to_w_row1", "right1B1 B1A1 A1left1"),
        ("s_to_n_col0", "bottom0A0 A0A1 A1top0"),
        ("s_to_n_col1", "bottom1B0 B0B1 B1top1"),
        ("n_to_s_col0", "top0A1 A1A0 A0bottom0"),
        ("n_to_s_col1", "top1B1 B1B0 B0bottom1"),
        # Turning movements
        ("turn_w_to_n", "left0A0 A0A1 A1top0"),
        ("turn_w_to_s", "left1A1 A1A0 A0bottom0"),
        ("turn_e_to_n", "right0B0 B0B1 B1top1"),
        ("turn_e_to_s", "right1B1 B1B0 B0bottom1"),
        ("turn_s_to_e", "bottom0A0 A0B0 B0right0"),
        ("turn_s_to_w", "bottom1B0 B0A0 A0left0"),
        ("turn_n_to_e", "top0A1 A1B1 B1right1"),
        ("turn_n_to_w", "top1B1 B1A1 A1left1"),
    ]

    # Pedestrian walking corridors
    pedestrian_routes = [
        "left0A0 A0B0 B0right0",
        "right0B0 B0A0 A0left0",
        "left1A1 A1B1 B1right1",
        "right1B1 B1A1 A1left1",
        "bottom0A0 A0A1 A1top0",
        "top0A1 A1A0 A0bottom0",
        "bottom1B0 B0B1 B1top1",
        "top1B1 B1B0 B0bottom1",
    ]

    root = ET.Element("routes")
    root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
    root.set("xsi:noNamespaceSchemaLocation", "http://sumo.dlr.de/xsd/routes_file.xsd")

    # 1. Define Multi-Modal Vehicle Types
    vtype_car = ET.SubElement(root, "vType")
    vtype_car.set("id", "passenger")
    vtype_car.set("vClass", "passenger")
    vtype_car.set("accel", "2.6")
    vtype_car.set("decel", "4.5")
    vtype_car.set("sigma", "0.5")
    vtype_car.set("length", "5.0")
    vtype_car.set("maxSpeed", "13.89")
    vtype_car.set("color", "0.2,0.6,1.0")

    vtype_bus = ET.SubElement(root, "vType")
    vtype_bus.set("id", "bus")
    vtype_bus.set("vClass", "bus")
    vtype_bus.set("accel", "1.2")
    vtype_bus.set("decel", "3.0")
    vtype_bus.set("sigma", "0.3")
    vtype_bus.set("length", "12.0")
    vtype_bus.set("maxSpeed", "11.11")
    vtype_bus.set("color", "1.0,0.8,0.2")

    vtype_ev = ET.SubElement(root, "vType")
    vtype_ev.set("id", "emergency")
    vtype_ev.set("vClass", "emergency")
    vtype_ev.set("guiShape", "emergency")
    vtype_ev.set("accel", "3.5")
    vtype_ev.set("decel", "6.0")
    vtype_ev.set("sigma", "0.1")
    vtype_ev.set("length", "6.5")
    vtype_ev.set("maxSpeed", "20.0")
    vtype_ev.set("speedFactor", "1.4")
    vtype_ev.set("color", "1.0,0.0,0.0")

    # 2. Add Route Definitions
    for r_id, edges in arterial_routes:
        r_el = ET.SubElement(root, "route")
        r_el.set("id", r_id)
        r_el.set("edges", edges)

    # 3. Configure Scenario Parameters
    ev_dispatches = []
    if scenario == "rush_hour":
        # 80% traffic concentrated in main West->East and South->North corridors
        weights = [4 if ("w_to_e" in r[0] or "s_to_n" in r[0]) else 1 for r in arterial_routes]
        ev_interval = 300
    elif scenario == "emergency_surge":
        weights = [1] * len(arterial_routes)
        ev_interval = 120  # EV every 2 minutes
    elif scenario == "pedestrian_heavy":
        weights = [1] * len(arterial_routes)
        total_pedestrians *= 3
        ev_interval = 400
    else:  # balanced
        weights = [1] * len(arterial_routes)
        ev_interval = 300

    # Schedule Emergency Vehicles
    t_ev = 60.0
    while t_ev < duration:
        ev_dispatches.append(t_ev)
        t_ev += ev_interval

    # 4. Generate Vehicular Departures
    vehicle_records = []
    route_choices = [r[0] for r in arterial_routes]

    for i in range(total_vehicles):
        if scenario == "rush_hour":
            # Peak surge centered at 40% of duration
            t = random.gauss(duration * 0.4, duration * 0.15) if random.random() < 0.75 else random.uniform(0, duration)
        else:
            t = random.uniform(0, duration)
        t = max(0.0, min(float(duration), t))
        chosen_route = random.choices(route_choices, weights=weights, k=1)[0]
        v_type = "bus" if random.random() < 0.1 else "passenger"
        vehicle_records.append((t, f"veh_{i}", v_type, chosen_route))

    # Add Emergency Vehicles
    for ev_idx, t in enumerate(ev_dispatches):
        chosen_route = random.choice(["w_to_e_row0", "s_to_n_col0", "w_to_e_row1"])
        vehicle_records.append((t, f"ev_{ev_idx}", "emergency", chosen_route))

    vehicle_records.sort(key=lambda x: x[0])

    for t, v_id, v_type, r_id in vehicle_records:
        v_el = ET.SubElement(root, "vehicle")
        v_el.set("id", v_id)
        v_el.set("type", v_type)
        v_el.set("route", r_id)
        v_el.set("depart", f"{t:.2f}")
        v_el.set("departLane", "best")
        v_el.set("departSpeed", "max")

    # 5. Generate Pedestrian Departures
    pedestrian_records = []
    for p_i in range(total_pedestrians):
        t_ped = random.uniform(0, duration)
        p_edges = random.choice(pedestrian_routes)
        pedestrian_records.append((t_ped, f"ped_{p_i}", p_edges))

    pedestrian_records.sort(key=lambda x: x[0])

    for t_ped, p_id, p_edges in pedestrian_records:
        p_el = ET.SubElement(root, "person")
        p_el.set("id", p_id)
        p_el.set("depart", f"{t_ped:.2f}")
        w_el = ET.SubElement(p_el, "walk")
        w_el.set("edges", p_edges)

    tree = ET.ElementTree(root)
    ET.indent(tree, space="    ", level=0)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    print(
        f"[generate_routes] Generated scenario '{scenario}' ({len(vehicle_records)} vehicles, "
        f"{len(ev_dispatches)} EVs, {len(pedestrian_records)} pedestrians) -> {out_path}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-modal demand generator for 2x2 grid")
    parser.add_argument("--out", default="grid2x2.rou.xml", help="Output route XML file")
    parser.add_argument("--scenario", choices=["balanced", "rush_hour", "emergency_surge", "pedestrian_heavy"], default="balanced")
    parser.add_argument("--duration", type=int, default=1800, help="Simulation duration (s)")
    parser.add_argument("--vehicles", type=int, default=800, help="Total vehicles to spawn")
    parser.add_argument("--pedestrians", type=int, default=120, help="Total pedestrians to spawn")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    generate_multimodal_routes(
        output_file=args.out,
        scenario=args.scenario,
        duration=args.duration,
        total_vehicles=args.vehicles,
        total_pedestrians=args.pedestrians,
        seed=args.seed,
    )
