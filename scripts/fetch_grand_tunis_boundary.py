import urllib.request
import json
import urllib.parse
from shapely.geometry import shape, mapping
from shapely.ops import unary_union
from pathlib import Path

governorates = [
    "Tunis Governorate, Tunisia",
    "Ariana Governorate, Tunisia",
    "Ben Arous Governorate, Tunisia",
    "Manouba Governorate, Tunisia"
]

shapes = []
features = []

for gov in governorates:
    url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(gov)}&countrycodes=tn&polygon_geojson=1&format=geojson"
    req = urllib.request.Request(url, headers={"User-Agent": "Kemetra-Traffic-App/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode())
    if not data["features"]:
        print(f"FAILED to find {gov}")
        continue
    feat = data["features"][0]
    features.append(feat)
    s = shape(feat["geometry"])
    if not s.is_valid:
        s = s.buffer(0)
    shapes.append(s)
    print(f"Loaded {gov}: {s.geom_type}, bounds={s.bounds}")

union_geom = unary_union(shapes)
print("Union geom type:", union_geom.geom_type)
print("Union bounds:", union_geom.bounds)

out_dir = Path("sumo_files/boundaries")
out_dir.mkdir(parents=True, exist_ok=True)

# Save combined Grand Tunis GeoJSON
grand_tunis_geojson = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"name": "Grand Tunis (Tunis, Ariana, Ben Arous, Manouba)"},
            "geometry": mapping(union_geom)
        }
    ]
}
with open(out_dir / "grand_tunis.geojson", "w") as f:
    json.dump(grand_tunis_geojson, f)

print("Saved grand_tunis.geojson")
