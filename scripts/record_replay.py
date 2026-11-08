"""Record a side-by-side replay for the dashboard: the same episode under two controllers.

Both runs are ordinary evaluation episodes (same demand, events and SUMO seed); a step
hook samples every road user and every signal during a window of the measured hour. The
episode's own metrics are stored with the frames, so the replay's numbers are those of a
real run. The window starts 30 s before the first emergency vehicle departs when there is
one, otherwise 20 min into the measured hour.

    python scripts/record_replay.py --net grid3x3 --scenarios emergency --demand peak \
        --left ft --right llm [--seed 3] [--window 480] [--every 2]

A side may also name a version saved in the model registry, so the dashboard can play the
user's own policies rather than a baseline:

    --left model:generalist-shortpilot --right model:rl-shortpilot
    --left model:rl-shortpilot@v2 --right ft

Output: frontend/public/data/replays/<net>__<scenarios>__<demand>__s<seed>[_<sides>].json
(positions in decimetres, speeds in dm/s, angles in degrees: integers keep the file small).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from cotraffic.controllers.registry import LEARNED, make_controller
from cotraffic.evaluation.runner import run_episode
from cotraffic.paths import RESULTS_DIR, default_checkpoint

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend" / "public" / "data" / "replays"
KIND = {"car": 0, "bus": 1, "emergency": 2, "incident": 3}
MAX_ACTORS = 1500  # per frame: a 7 800-vehicle network would otherwise write ~80 MB

KPIS = [
    "mean_travel_time",
    "mean_waiting_time",
    "mean_time_loss",
    "stops_per_vehicle",
    "throughput_per_h",
    "co2_total_kg",
    "ev_delay",
    "ev_travel_time",
    "ped_mean_waiting_time",
    "bus_delay",
    "person_weighted_delay",
]


class Recorder:
    """Step hook: samples the scene every ``every`` seconds inside ``[start, start+window)``."""

    def __init__(self, window: float, every: int) -> None:
        self.window = window
        self.every = every
        self.stride = 1
        self.start: float | None = None
        self.ids: dict[str, int] = {}
        self.kinds: dict[str, int] = {}
        self.signals: list[str] = []
        self.frames: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.seen_ev: set[str] = set()

    def _start(self, env) -> float:
        meta = env.episode.bundle.meta
        evs = meta.get("emergency") or []
        if evs:
            return max(env.episode.measure_from, min(e["depart"] for e in evs) - 30.0)
        if meta.get("incident"):
            return max(env.episode.measure_from, float(meta["incident"]["start"]) - 60.0)
        return env.episode.measure_from + 1200.0

    def _kind(self, conn, vid: str) -> int:
        if vid not in self.kinds:
            vtype = conn.vehicle.getTypeID(vid)
            self.kinds[vid] = KIND.get(vtype, KIND["bus"] if "bus" in vtype else 0)
        return self.kinds[vid]

    def __call__(self, env, now: float) -> None:
        if self.start is None:
            self.start = self._start(env)
            self.signals = sorted(env.conn.trafficlight.getIDList())
        if not (self.start <= now < self.start + self.window):
            return
        if round(now - self.start) % self.every:
            return
        conn = env.conn
        live = conn.vehicle.getIDList()
        if self.stride == 1 and len(live) > MAX_ACTORS:
            # Big network (Tunis, Monaco): keep the time window, thin the fleet. A stride
            # by vehicle slot is stable across frames, and emergency vehicles always stay.
            self.stride = -(-len(live) // MAX_ACTORS)
            self.every = max(self.every, 4)
        vehicles: list[int] = []
        for vid in live:
            kind = self._kind(conn, vid)
            if kind == KIND["emergency"] and vid not in self.seen_ev:
                self.seen_ev.add(vid)
                self.events.append({"t": round(now - self.start), "type": "emergency", "id": vid})
            slot = self.ids.setdefault(vid, len(self.ids))
            if self.stride > 1 and kind != KIND["emergency"] and slot % self.stride:
                continue
            x, y = conn.vehicle.getPosition(vid)
            vehicles += [
                slot,
                kind,
                round(x * 10),
                round(y * 10),
                round(conn.vehicle.getAngle(vid)),
                round(conn.vehicle.getSpeed(vid) * 10),
            ]
        persons: list[int] = []
        for pid in conn.person.getIDList():
            x, y = conn.person.getPosition(pid)
            persons += [round(x * 10), round(y * 10), int(conn.person.getWaitingTime(pid) > 0)]
        self.frames.append(
            {
                "t": round(now - self.start),
                "v": vehicles,
                "p": persons,
                "s": [conn.trafficlight.getRedYellowGreenState(t) for t in self.signals],
            }
        )


def resolve_source(spec: str) -> dict[str, Any]:
    """A controller id, ``model:<name>[@vN]`` from the registry, or ``checkpoint:<path>``.

    ``checkpoint:`` is the free-hand form: any saved weights under ``results/`` (a
    selected run, a raw training checkpoint or a registry copy) can drive a side,
    whatever agent and hyperparameters produced it.
    """
    if spec.startswith("checkpoint:"):
        raw = spec.split(":", 1)[1].replace("\\", "/")
        path = Path(raw)
        if not path.is_absolute():
            path = ROOT / raw
        path = path.resolve()
        allowed = (
            (ROOT / "results" / "checkpoints").resolve(),
            (ROOT / "results" / "training").resolve(),
            (ROOT / "results" / "models").resolve(),
        )
        if not any(path.is_relative_to(root) for root in allowed):
            raise SystemExit("checkpoint must live under results/")
        if not path.is_file():
            raise SystemExit(f"checkpoint not found: {raw}")
        sidecar = path.with_suffix(".json")
        meta = json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.is_file() else {}
        config = meta.get("config") or {}
        method = str(config.get("name") or meta.get("agent") or path.parent.parent.name)
        return {
            "method": method,
            "label": str(config.get("label") or method),
            "checkpoint": path,
        }
    if not spec.startswith("model:"):
        return {"method": spec, "label": None, "checkpoint": None}
    raw = spec.split(":", 1)[1]
    name, _, version = raw.partition("@")
    registry: dict[str, Any] = {"models": {}}
    for path in (ROOT / "results" / "models.json", ROOT / "frontend" / "public" / "data" / "models.json"):
        if path.is_file():
            registry = json.loads(path.read_text(encoding="utf-8"))
            break
    versions = registry.get("models", {}).get(name) or []
    if not versions:
        known = ", ".join(sorted(registry.get("models", {}))) or "none"
        raise SystemExit(f"unknown model {name!r} (registered: {known})")
    if version:
        wanted = int(version.lstrip("v"))
        entry = next((v for v in versions if int(v.get("version", 0)) == wanted), None)
        if entry is None:
            raise SystemExit(f"{name} has no version {wanted}")
    else:
        entry = max(versions, key=lambda v: int(v.get("version", 0)))
    checkpoint = ROOT / str(entry.get("checkpoint", "")).replace("\\", "/")
    if not checkpoint.is_file():
        raise SystemExit(f"{name} v{entry.get('version')} has no saved checkpoint ({checkpoint})")
    return {
        "method": name,
        "label": f"{name} v{entry.get('version')}",
        "checkpoint": checkpoint,
    }


def record(source: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    method = source["method"]
    checkpoint = source["checkpoint"]
    if checkpoint is None and method in LEARNED:
        checkpoint = default_checkpoint(method, args.net)
    controller = make_controller(method, checkpoint)
    recorder = Recorder(args.window, args.every)
    hooks = controller.step_hooks
    controller.step_hooks = lambda: [*hooks(), recorder]  # type: ignore[method-assign]
    scratch = RESULTS_DIR / "tmp" / "replays"
    row = run_episode(
        method,
        args.net,
        args.demand,
        args.scenarios,
        args.seed,
        checkpoint=checkpoint,
        ssm=False,
        tag="replay",
        raw_dir=scratch / "raw",
        logs_dir=scratch / "logs",
        controller=controller,
    )
    print(f"  {source['label'] or method}: {len(recorder.frames)} frames, {len(recorder.ids)} vehicles")
    return {
        "method": method,
        "label": source["label"],
        "kpis": {k: row.get(k) for k in KPIS},
        "frames": recorder.frames,
        "events": recorder.events,
        "signals": recorder.signals,
        "start": recorder.start,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--net", default="grid3x3")
    parser.add_argument("--scenarios", nargs="*", default=["emergency"])
    parser.add_argument("--demand", default="peak")
    parser.add_argument("--seed", type=int, default=3)
    parser.add_argument(
        "--left", default="ft",
        help="controller id, model:<name>[@vN] or checkpoint:<path under results/>",
    )
    parser.add_argument(
        "--right", default="llm",
        help="controller id, model:<name>[@vN] or checkpoint:<path under results/>",
    )
    parser.add_argument("--window", type=float, default=480.0)
    parser.add_argument("--every", type=int, default=2)
    args = parser.parse_args()

    scen = "+".join(args.scenarios) or "normal"
    replay_id = f"{args.net}__{scen}__{args.demand}__s{args.seed}"
    left_source = resolve_source(args.left)
    right_source = resolve_source(args.right)

    def _tag(source: dict[str, Any]) -> str:
        name = str(source["label"] or source["method"])
        return "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in name).strip("-")

    if left_source["checkpoint"] or right_source["checkpoint"]:
        replay_id = f"{replay_id}__{_tag(left_source)}-vs-{_tag(right_source)}"
    print(f"recording {replay_id}: {args.left} | {args.right}")
    left = record(left_source, args)
    right = record(right_source, args)
    payload = {
        "id": replay_id,
        "network": args.net,
        "scenario": scen,
        "demand": args.demand,
        "seed": args.seed,
        "every": args.every,
        "window": args.window,
        "start": left["start"],
        "signals": left["signals"],
        "kinds": list(KIND),
        "sides": {"left": left, "right": right},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{replay_id}.json"
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"  {path}  {path.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
