#!/usr/bin/env python3
"""
generate_ev_routes.py
Shared emergency vehicle demand generator for the SUMO grid scenarios.

Usage:
    python scenarios/generate_ev_routes.py --scenario 2x2
    python scenarios/generate_ev_routes.py --scenario 3x3 --seed 7

Writes grid<scenario>.ev.rou.xml into the matching scenario folder. The EV
file is loaded on top of the regular traffic file, so standard scenarios stay
unchanged.
"""

import os
import argparse
import random
import xml.etree.ElementTree as ET

EV_ROUTES = {
    "2x2": [
        ("ev_w_to_e", "left0A0 A0B0 B0right0"),
        ("ev_e_to_w", "right1B1 B1A1 A1left1"),
        ("ev_s_to_n", "bottom1B0 B0B1 B1top1"),
        ("ev_n_to_s", "top0A1 A1A0 A0bottom0"),
        ("ev_s_to_e", "bottom0A0 A0B0 B0right0"),
        ("ev_n_to_w", "top1B1 B1A1 A1left1"),
    ],
    "3x3": [
        ("ev_w_to_e", "left0A0 A0B0 B0C0 C0right0"),
        ("ev_e_to_w", "right2C2 C2B2 B2A2 A2left2"),
        ("ev_s_to_n", "bottom1B0 B0B1 B1B2 B2top1"),
        ("ev_n_to_s", "top0A2 A2A1 A1A0 A0bottom0"),
        ("ev_s_to_e", "bottom0A0 A0B0 B0C0 C0right0"),
        ("ev_n_to_w", "top2C2 C2B2 B2A2 A2left2"),
    ],
}


def generate_ev_routes(scenario="2x2", output_file=None, duration=3600, interval=240, seed=42):
    scenario_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"grid_{scenario}")
    if output_file is None:
        output_file = f"grid{scenario}.ev.rou.xml"
    out_path = output_file if os.path.isabs(output_file) else os.path.join(scenario_dir, output_file)

    rng = random.Random(seed)
    routes = EV_ROUTES[scenario]
    route_ids = [r[0] for r in routes]

    root = ET.Element("routes")
    root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
    root.set("xsi:noNamespaceSchemaLocation", "http://sumo.dlr.de/xsd/routes_file.xsd")

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

    for r_id, edges in routes:
        r_el = ET.SubElement(root, "route")
        r_el.set("id", r_id)
        r_el.set("edges", edges)

    # Seed-dependent order: every seed covers all six routes, but mixes which
    # approach comes first, so results do not depend on one fixed sequence.
    order = route_ids[:]
    rng.shuffle(order)

    depart = 0.0
    ev_index = 0
    while depart < duration:
        v_el = ET.SubElement(root, "vehicle")
        v_el.set("id", f"ev_{ev_index}")
        v_el.set("type", "emergency")
        v_el.set("route", order[ev_index % len(order)])
        v_el.set("depart", f"{depart:.2f}")
        v_el.set("departLane", "best")
        v_el.set("departSpeed", "max")
        # Jitter avoids always hitting the fixed-time signals at the same point
        # of their cycle, which would bias the baseline comparison.
        depart += interval + rng.uniform(-0.25 * interval, 0.25 * interval)
        ev_index += 1

    tree = ET.ElementTree(root)
    ET.indent(tree, space="    ", level=0)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    print(f"[generate_ev_routes] Wrote {ev_index} emergency vehicles to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate emergency vehicle demand for the SUMO grid scenarios")
    parser.add_argument("--scenario", choices=sorted(EV_ROUTES), default="2x2")
    parser.add_argument("--out", default=None, help="Output file (absolute or relative to the scenario dir)")
    parser.add_argument("--duration", type=int, default=3600, help="Simulation duration in seconds")
    parser.add_argument("--interval", type=int, default=240, help="Seconds between EV dispatches")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    generate_ev_routes(args.scenario, args.out, args.duration, args.interval, args.seed)
