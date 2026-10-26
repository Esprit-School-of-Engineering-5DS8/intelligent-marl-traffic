import urllib.request
import json
import urllib.parse

query = """[out:json][timeout:30];
relation["boundary"="administrative"]["admin_level"="2"]["name"="Monaco"];
out geom;"""

data = urllib.parse.urlencode({"data": query}).encode()
req = urllib.request.Request("https://overpass-api.de/api/interpreter", data=data, headers={"User-Agent": "Kemetra-App/1.0"})
with urllib.request.urlopen(req, timeout=30) as resp:
    res = json.loads(resp.read().decode())

print("Elements:", len(res["elements"]))
rel = res["elements"][0]
members = rel.get("members", [])
print("Members count:", len(members))
for m in members[:5]:
    print(m.get("type"), m.get("role"), len(m.get("geometry", [])))
