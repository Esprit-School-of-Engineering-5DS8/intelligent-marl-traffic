"""Build the SUMO networks described in ``configs/networks``."""

from __future__ import annotations

import shutil
from pathlib import Path

from cotraffic import config
from cotraffic.paths import REPO_ROOT, SUMO_DIR


def network_dir(name: str) -> Path:
    return SUMO_DIR / name


def net_file(name: str) -> Path:
    return network_dir(name) / f"{name}.net.xml"


def build_network(name: str, force: bool = False) -> Path:
    """Build (or reuse) the network ``name`` and return the path of its .net.xml."""
    cfg = config.load("networks", name)
    protocol = config.load_protocol()
    out = net_file(cfg["name"])
    if out.is_file() and not force:
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    kind = cfg.get("kind")
    if kind == "grid":
        from cotraffic.networks.grid import build_grid

        build_grid(cfg, protocol, out)
    elif kind == "osm":
        from cotraffic.networks.osm import build_osm

        build_osm(cfg, protocol, out)
    elif kind == "prebuilt":
        _copy_prebuilt(cfg, out)
    else:
        raise ValueError(f"network {name}: unknown kind {kind!r}")
    if not out.is_file():
        raise RuntimeError(f"network build for {name} did not produce {out}")
    return out


def _copy_prebuilt(cfg: dict, out: Path) -> None:
    """Vendor a published .net.xml (e.g. MoSTScenario) instead of building one."""
    pre = cfg["prebuilt"]
    source = (REPO_ROOT / pre["checkout"] / pre["net"]).resolve()
    if not source.is_file():
        name = cfg.get("name", "")
        chk = pre.get("checkout", "")
        src = pre.get("source", "")
        lines = [
            f"network {name}: {source} is missing.",
            f"  git clone --depth 1 {src} {chk}",
            f"then re-run `python -m cotraffic networks {name} --force`.",
        ]
        raise RuntimeError("\n".join(lines))
    shutil.copyfile(source, out)


def ensure_network(name: str) -> Path:
    out = net_file(name)
    return out if out.is_file() else build_network(name)
