import urllib.request
import urllib.parse
import json
import time

query = """[out:json][timeout:60];
(
  area["admin_level"="4"]["name:en"="Tunis"]->.a;
  area["admin_level"="4"]["name:en"="Ariana"]->.b;
  area["admin_level"="4"]["name:en"="Ben Arous"]->.c;
  area["admin_level"="4"]["name:en"="Manouba"]->.d;
);
(
  way["highway"](area.a);
  way["highway"](area.b);
  way["highway"](area.c);
  way["highway"](area.d);
);
out count;"""

req = urllib.request.Request(
    "https://overpass.kumi.systems/api/interpreter",
    data=urllib.parse.urlencode({"data": query}).encode(),
    headers={"User-Agent": "Kemetra-App/1.0"}
)
t0 = time.time()
with urllib.request.urlopen(req, timeout=40) as resp:
    data = json.loads(resp.read().decode())
print(f"Time: {time.time() - t0:.2f}s")
print(json.dumps(data, indent=2))
