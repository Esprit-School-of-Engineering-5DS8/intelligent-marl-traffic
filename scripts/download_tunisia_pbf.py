import urllib.request
from pathlib import Path
import sys

def download_tunisia_pbf():
    cache_dir = Path("sumo_files/cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    pbf_path = cache_dir / "tunisia-latest.osm.pbf"

    if pbf_path.exists() and pbf_path.stat().st_size > 50_000_000:
        print(f"Tunisia PBF already exists: {pbf_path.stat().st_size:,} bytes")
        return pbf_path

    url = "https://download.geofabrik.de/africa/tunisia-latest.osm.pbf"
    print(f"Downloading {url} to {pbf_path}...")

    def reporthook(blocknum, blocksize, totalsize):
        readsofar = blocknum * blocksize
        if totalsize > 0 and blocknum % 500 == 0:
            percent = readsofar * 100 / totalsize
            sys.stdout.write(f"\rDownloading: {readsofar:,} / {totalsize:,} bytes ({percent:.1f}%)")
            sys.stdout.flush()

    urllib.request.urlretrieve(url, str(pbf_path), reporthook=reporthook)
    print(f"\nDownload complete: {pbf_path.stat().st_size:,} bytes")
    return pbf_path

if __name__ == "__main__":
    download_tunisia_pbf()
