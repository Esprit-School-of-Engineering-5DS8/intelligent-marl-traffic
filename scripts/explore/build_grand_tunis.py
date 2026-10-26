import json
import subprocess
from pathlib import Path
import osmium
from shapely.geometry import shape

class GrandTunisFilter(osmium.SimpleHandler):
    """
    Two-pass extractor:
    Pass 1: Collect node IDs of all highways within the Grand Tunis bbox.
    Pass 2: Write all matching nodes and ways to OSM XML.
    """
    def __init__(self, bbox):
        super().__init__()
        self.west, self.south, self.east, self.north = bbox
        self.needed_nodes = set()
        self.needed_ways = set()
        self.in_bbox_nodes = set()

    def record_nodes(self, n):
        lon, lat = n.location.lon, n.location.lat
        if self.west <= lon <= self.east and self.south <= lat <= self.north:
            self.in_bbox_nodes.add(n.id)

    def record_ways(self, w):
        tags = w.tags
        if "highway" in tags:
            # Check if any node is within bbox
            node_ids = [n.ref for n in w.nodes]
            if any(nid in self.in_bbox_nodes for nid in node_ids):
                self.needed_ways.add(w.id)
                self.needed_nodes.update(node_ids)

class NodeCollector(osmium.SimpleHandler):
    def __init__(self, collector):
        super().__init__()
        self.collector = collector
    def node(self, n):
        self.collector.record_nodes(n)

class WayCollector(osmium.SimpleHandler):
    def __init__(self, collector):
        super().__init__()
        self.collector = collector
    def way(self, w):
        self.collector.record_ways(w)

class GrandTunisWriter(osmium.SimpleHandler):
    def __init__(self, writer, needed_nodes, needed_ways):
        super().__init__()
        self.writer = writer
        self.needed_nodes = needed_nodes
        self.needed_ways = needed_ways
        self.node_count = 0
        self.way_count = 0

    def node(self, n):
        if n.id in self.needed_nodes:
            self.writer.add_node(n)
            self.node_count += 1

    def way(self, w):
        if w.id in self.needed_ways:
            self.writer.add_way(w)
            self.way_count += 1

def build_grand_tunis():
    pbf_candidates = [
        Path("sumo_files/tunisia-261025.osm.pbf"),
        Path("sumo_files/tunisia-latest.osm.pbf"),
        Path("sumo_files/cache/tunisia-latest.osm.pbf"),
    ]
    pbf_file = None
    for cand in pbf_candidates:
        if cand.exists():
            pbf_file = cand
            break
    if not pbf_file:
        raise FileNotFoundError(f"Missing Tunisia PBF. Checked {pbf_candidates}")
    print(f"Using Tunisia PBF: {pbf_file} ({pbf_file.stat().st_size:,} bytes)")

    out_dir = Path("sumo_files/tunis")
    out_dir.mkdir(parents=True, exist_ok=True)
    osm_file = out_dir / "tunis.osm.xml"
    net_file = out_dir / "tunis.net.xml"
    border_file = out_dir / "grand_tunis_border.txt"

    print("=== Step 1: Loading Grand Tunis administrative boundary ===")
    geojson_path = Path("sumo_files/boundaries/grand_tunis.geojson")
    with open(geojson_path) as f:
        geo_data = json.load(f)

    geom = shape(geo_data["features"][0]["geometry"])
    main_polygon = geom.geoms[0] if geom.geom_type == "MultiPolygon" else geom

    # Simplify polygon for netconvert CLI (~30m tolerance)
    simplified = main_polygon.simplify(0.0003, preserve_topology=True)
    coords = list(simplified.exterior.coords)
    poly_str = ",".join(f"{lon:.6f},{lat:.6f}" for lon, lat in coords)
    border_file.write_text(poly_str)
    print(f"Saved Grand Tunis boundary polygon ({len(coords)} points)")

    # Grand Tunis Bounding Box
    bbox = [min(p[0] for p in coords) - 0.01,
            min(p[1] for p in coords) - 0.01,
            max(p[0] for p in coords) + 0.01,
            max(p[1] for p in coords) + 0.01]
    print(f"Grand Tunis bbox: {bbox}")

    print("=== Step 2: Extracting highways from Tunisia OSM PBF ===")
    flt = GrandTunisFilter(bbox)

    print("Pass 1a: Scanning nodes in bbox...")
    NodeCollector(flt).apply_file(str(pbf_file))
    print(f"Found {len(flt.in_bbox_nodes):,} nodes in Grand Tunis bbox")

    print("Pass 1b: Scanning highways...")
    WayCollector(flt).apply_file(str(pbf_file))
    print(f"Found {len(flt.needed_ways):,} highways ({len(flt.needed_nodes):,} nodes required)")

    temp_osm = Path("grand_tunis_temp.osm.xml")
    if temp_osm.exists():
        temp_osm.unlink()
    print(f"Pass 2: Writing {temp_osm.name}...")
    writer = osmium.SimpleWriter(str(temp_osm))
    writer_handler = GrandTunisWriter(writer, flt.needed_nodes, flt.needed_ways)
    writer_handler.apply_file(str(pbf_file))
    writer.close()

    import shutil
    shutil.move(str(temp_osm), str(osm_file))
    print(f"Wrote {writer_handler.node_count:,} nodes and {writer_handler.way_count:,} ways to {osm_file}")

    print("=== Step 3: Compiling into SUMO network via netconvert ===")
    netconvert_bin = r"C:\Program Files (x86)\Eclipse\Sumo\bin\netconvert.exe"

    road_types = [
        "highway.motorway", "highway.motorway_link",
        "highway.trunk", "highway.trunk_link",
        "highway.primary", "highway.primary_link",
        "highway.secondary", "highway.secondary_link",
        "highway.tertiary", "highway.tertiary_link",
        "highway.unclassified",
        "highway.residential",
        "highway.living_street",
        "highway.service"
    ]

    cmd = [
        netconvert_bin,
        "--osm-files", str(osm_file),
        "--output-file", str(net_file),
        "--keep-edges.in-geo-boundary", poly_str,
        "--keep-edges.by-type", ",".join(road_types),
        "--keep-edges.components", "1",
        "--remove-edges.isolated", "true",
        "--geometry.remove", "true",
        "--roundabouts.guess", "true",
        "--junctions.join", "true",
        "--junctions.join-dist", "15",
        "--tls.guess-signals", "true",
        "--tls.guess", "true",
        "--tls.join", "true",
        "--tls.join-dist", "30",
        "--sidewalks.guess", "true",
        "--crossings.guess", "true",
        "--output.street-names", "true",
        "--no-warnings", "true"
    ]

    print("Running netconvert (this may take 1-2 minutes for the full metropolitan network)...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print("netconvert failed:", res.stderr)
        raise RuntimeError("netconvert error")

    print(f"[SUCCESS] Compiled Grand Tunis network: {net_file} ({net_file.stat().st_size:,} bytes)")

if __name__ == "__main__":
    build_grand_tunis()
