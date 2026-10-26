import urllib.request
import urllib.parse
import time

query = """[out:xml][timeout:30];
(
  way["highway"](36.80, 10.16, 36.83, 10.20);
);
(._;>;);
out body;"""

servers = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
for s in servers:
    t0 = time.time()
    req = urllib.request.Request(
        s,
        data=urllib.parse.urlencode({"data": query}).encode(),
        headers={"User-Agent": "Kemetra-Traffic/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            res = resp.read()
        print(f"{s}: SUCCESS in {time.time() - t0:.2f}s, size = {len(res):,} bytes")
        break
    except Exception as e:
        print(f"{s}: FAILED ({e}) in {time.time() - t0:.2f}s")

print(f"Bbox query succeeded in {time.time() - t0:.2f}s, size = {len(res):,} bytes")
