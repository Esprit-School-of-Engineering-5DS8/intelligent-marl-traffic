#!/usr/bin/env python3
"""
generate_person_flows.py
Seeded pedestrian demand for the S4 scenario: bursts of walking trips at the
two central corridors during a controlled window, in their own route file
(SUMO requires persons in a separate, time-sorted route file listed after the
vehicle file).

Usage:
    python scenarios/grid_3x3_ped/generate_person_flows.py --duration 1800
"""

import argparse
import os
import xml.etree.ElementTree as ET


def generate_person_flows(output_file="grid3x3_ped.persons.rou.xml",
                          begin=300.0, end=600.0,
                          row_flow=160, col_flow=140):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(script_dir, output_file)

    root = ET.Element("routes")
    root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
    root.set("xsi:noNamespaceSchemaLocation", "http://sumo.dlr.de/xsd/routes_file.xsd")

    vtype = ET.SubElement(root, "vType")
    vtype.set("id", "pedestrian")
    vtype.set("vClass", "pedestrian")
    vtype.set("speedDev", "0.15")
    vtype.set("maxSpeed", "1.5")

    # Concentrated burst at the central junction B1: one flow walking east
    # (crosses the NS street, served by the EW vehicle phase) and one walking
    # north (crosses the EW street, served by the NS phase). The two short
    # walks approach B1 from all four corners, creating sustained waits at the
    # crossings that the Pedestrian agent has to arbitrate against vehicle
    # queues. The rest of the grid keeps its normal vehicle demand.
    flows = [
        ("ped_b1_ew", "A1B1", "B1C1", row_flow),
        ("ped_b1_ns", "B0B1", "B1B2", col_flow),
    ]
    for flow_id, from_edge, to_edge, number in flows:
        flow = ET.SubElement(root, "personFlow")
        flow.set("id", flow_id)
        flow.set("type", "pedestrian")
        flow.set("begin", f"{begin:.1f}")
        flow.set("end", f"{end:.1f}")
        flow.set("number", str(number))
        walk = ET.SubElement(flow, "walk")
        walk.set("from", from_edge)
        walk.set("to", to_edge)

    tree = ET.ElementTree(root)
    ET.indent(tree, space="    ", level=0)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    total = row_flow + col_flow
    print(f"[generate_person_flows] Wrote {total} pedestrians "
          f"({row_flow} east + {col_flow} north) at B1 between {begin:.0f}-{end:.0f}s to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate pedestrian demand for the S4 scenario")
    parser.add_argument("--out", default="grid3x3_ped.persons.rou.xml")
    parser.add_argument("--begin", type=float, default=300.0)
    parser.add_argument("--end", type=float, default=600.0)
    parser.add_argument("--row-flow", type=int, default=160)
    parser.add_argument("--col-flow", type=int, default=140)
    args = parser.parse_args()
    generate_person_flows(args.out, args.begin, args.end, args.row_flow, args.col_flow)
