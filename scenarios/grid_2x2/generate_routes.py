#!/usr/bin/env python3
"""
generate_routes.py
Generates traffic demand for the 2x2 SUMO grid network.
Supports:
1. Synthetic corridor flows (East-West and North-South flows + turns)
2. Uniform random trips via SUMO's randomTrips tool
"""

import os
import sys
import argparse
import random
import xml.etree.ElementTree as ET

def generate_corridor_routes(output_file, duration=3600, total_vehicles=1000, seed=42):
    """
    Directly generates realistic synthetic route demand for the 2x2 grid.
    Includes major arterial flows across the grid plus cross-grid turning movements.
    """
    random.seed(seed)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(script_dir, output_file)

    # Pre-defined arterial paths (West <-> East and South <-> North + turns)
    arterial_routes = [
        # West to East corridors
        ("w_to_e_row0", "left0A0 A0B0 B0right0"),
        ("w_to_e_row1", "left1A1 A1B1 B1right1"),
        # East to West corridors
        ("e_to_w_row0", "right0B0 B0A0 A0left0"),
        ("e_to_w_row1", "right1B1 B1A1 A1left1"),
        # South to North corridors
        ("s_to_n_col0", "bottom0A0 A0A1 A1top0"),
        ("s_to_n_col1", "bottom1B0 B0B1 B1top1"),
        # North to South corridors
        ("n_to_s_col0", "top0A1 A1A0 A0bottom0"),
        ("n_to_s_col1", "top1B1 B1B0 B0bottom1"),
        # Turning movements (Cross-grid)
        ("turn_w_to_n", "left0A0 A0A1 A1top0"),
        ("turn_w_to_s", "left1A1 A1A0 A0bottom0"),
        ("turn_e_to_n", "right0B0 B0B1 B1top1"),
        ("turn_e_to_s", "right1B1 B1B0 B0bottom1"),
        ("turn_s_to_e", "bottom0A0 A0B0 B0right0"),
        ("turn_s_to_w", "bottom1B0 B0A0 A0left0"),
        ("turn_n_to_e", "top0A1 A1B1 B1right1"),
        ("turn_n_to_w", "top1B1 B1A1 A1left1"),
    ]

    root = ET.Element("routes")
    root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
    root.set("xsi:noNamespaceSchemaLocation", "http://sumo.dlr.de/xsd/routes_file.xsd")

    # Define vehicle types
    vtype_car = ET.SubElement(root, "vType")
    vtype_car.set("id", "passenger")
    vtype_car.set("accel", "2.6")
    vtype_car.set("decel", "4.5")
    vtype_car.set("sigma", "0.5")
    vtype_car.set("length", "5.0")
    vtype_car.set("maxSpeed", "13.89")
    vtype_car.set("color", "0.2,0.6,1.0")

    vtype_bus = ET.SubElement(root, "vType")
    vtype_bus.set("id", "bus")
    vtype_bus.set("accel", "1.2")
    vtype_bus.set("decel", "3.0")
    vtype_bus.set("sigma", "0.3")
    vtype_bus.set("length", "12.0")
    vtype_bus.set("maxSpeed", "11.11")
    vtype_bus.set("color", "1.0,0.8,0.2")

    # Add routes
    for r_id, edges in arterial_routes:
        r_el = ET.SubElement(root, "route")
        r_el.set("id", r_id)
        r_el.set("edges", edges)

    # Generate departures
    route_ids = [r[0] for r in arterial_routes]

    # Distribute vehicles across time window [0, duration]
    departure_times = []
    for _ in range(total_vehicles):
        if random.random() < 0.5:
            t = random.uniform(0, duration)
        else:
            t = random.gauss(duration * 0.45, duration * 0.2)
            t = max(0.0, min(float(duration), t))
        departure_times.append(t)

    departure_times.sort()

    for idx, dep_time in enumerate(departure_times):
        v_el = ET.SubElement(root, "vehicle")
        v_el.set("id", f"veh_{idx}")
        # 90% cars, 10% buses
        v_type = "passenger" if random.random() > 0.1 else "bus"
        v_el.set("type", v_type)
        v_el.set("route", random.choice(route_ids))
        v_el.set("depart", f"{dep_time:.2f}")
        v_el.set("departLane", "best")
        v_el.set("departSpeed", "max")

    tree = ET.ElementTree(root)
    ET.indent(tree, space="    ", level=0)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    print(f"[generate_routes] Successfully wrote {len(departure_times)} vehicles to {out_path}!")

def generate_random_trips(output_file, duration=3600, period=2.5):
    """
    Alternative generator using SUMO's randomTrips.py if SUMO tools are available.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    net_path = os.path.join(script_dir, "grid2x2.net.xml")
    out_path = os.path.join(script_dir, output_file)

    sumo_home = os.environ.get("SUMO_HOME", "")
    if not sumo_home:
        if sys.platform == "win32":
            candidate = r"C:\Program Files (x86)\Eclipse\Sumo"
            if os.path.exists(candidate):
                sumo_home = candidate
        else:
            if os.path.exists("/usr/share/sumo"):
                sumo_home = "/usr/share/sumo"

    rt_script = os.path.join(sumo_home, "tools", "randomTrips.py") if sumo_home else ""

    if not rt_script or not os.path.exists(rt_script):
        print(f"[generate_routes] randomTrips.py not found, falling back to synthetic generator.")
        generate_corridor_routes(output_file, duration)
        return

    import subprocess
    cmd = [
        sys.executable,
        rt_script,
        "-n", net_path,
        "-e", str(duration),
        "-p", str(period),
        "--route-file", out_path
    ]
    print(f"[generate_routes] Running randomTrips.py...")
    subprocess.run(cmd, check=True)
    print(f"[generate_routes] Successfully generated {out_path}!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate route demand for 2x2 SUMO grid")
    parser.add_argument("--out", default="grid2x2.rou.xml", help="Output route XML file")
    parser.add_argument("--duration", type=int, default=3600, help="Simulation duration in seconds")
    parser.add_argument("--vehicles", type=int, default=1000, help="Total vehicles to spawn")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--method", choices=["corridor", "randomtrips"], default="corridor")
    args = parser.parse_args()

    if args.method == "corridor":
        generate_corridor_routes(args.out, duration=args.duration, total_vehicles=args.vehicles, seed=args.seed)
    else:
        generate_random_trips(args.out, duration=args.duration)
