import urllib.request
import urllib.parse
import json
import subprocess
from pathlib import Path
from shapely.geometry import shape

def build_monaco():
    out_dir = Path("sumo_files/monaco")
    out_dir.mkdir(parents=True, exist_ok=True)
    osm_file = out_dir / "monaco.osm.xml"
    net_file = out_dir / "monaco.net.xml"
    poly_file = out_dir / "monaco_border.txt"

    print("=== Step 1: Getting official Monaco border ===")
    border_path = Path("sumo_files/monaco_border.geojson")
    if border_path.exists():
        with open(border_path) as f:
            res = json.load(f)
    else:
        req = urllib.request.Request(
            "https://nominatim.openstreetmap.org/search?country=Monaco&polygon_geojson=1&format=geojson",
            headers={"User-Agent": "Kemetra-Traffic-App/1.0"}
        )
        res = json.loads(urllib.request.urlopen(req, timeout=30).read())
        if "features" in res:
            res = res["features"][0]
        with open(border_path, "w") as f:
            json.dump(res, f)

    geom = shape(res["geometry"] if "geometry" in res else res["features"][0]["geometry"])

    # Extract land points (lat > 43.72) and simplify slightly for netconvert CLI
    # The administrative boundary of Monaco includes a large maritime boundary into the sea.
    # On land, Monaco is bounded by France. To create a precise closed land polygon:
    # Any coordinate with lat > 43.72 is on land.
    # The coastline connects the southwest point to the northeast point.
    raw_coords = list(geom.exterior.coords)
    land_coords = [p for p in raw_coords if p[1] > 43.72]

    # Use the full boundary or land-clipped boundary
    # Note: netconvert will only find roads where roads exist (on land).
    # Using the simplified exterior polygon:
    simplified = geom.simplify(0.00003, preserve_topology=True)
    poly_coords = list(simplified.exterior.coords)
    poly_str = ",".join(f"{lon:.6f},{lat:.6f}" for lon, lat in poly_coords)
    poly_file.write_text(poly_str)
    print(f"Saved Monaco border polygon ({len(poly_coords)} points)")

    # Full Monaco land bounding box: [west, south, east, north]
    west, south, east, north = 7.4080, 43.7240, 7.4420, 43.7530

    print("=== Step 2: Downloading complete OSM data for Monaco ===")
    # Query all highway ways in bbox
    query = f"""[out:xml][timeout:120];
(
  way["highway"]({south},{west},{north},{east});
);
(._;>;);
out body;"""

    data = urllib.parse.urlencode({"data": query}).encode()
    osm_req = urllib.request.Request("https://overpass-api.de/api/interpreter", data=data, headers={"User-Agent": "Kemetra-Traffic-App/1.0"})

    with urllib.request.urlopen(osm_req, timeout=120) as resp:
        osm_data = resp.read()

    if b"<osm" not in osm_data[:500]:
        raise ValueError("Invalid OSM payload received")

    osm_file.write_bytes(osm_data)
    print(f"Saved {len(osm_data):,} bytes to {osm_file}")

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

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print("netconvert failed:", res.stderr)
        raise RuntimeError("netconvert error")

    print(f"[SUCCESS] Compiled {net_file} ({net_file.stat().st_size:,} bytes)")

if __name__ == "__main__":
    build_monaco()
