"""Save the situations where the advisor would be called, from COOP-FULL episodes.

    python scripts/llm_situations.py --seed 1000              # validation set (benchmark, tuning)
    python scripts/llm_situations.py --seed 100001 --out few  # training seed (few-shot examples)

Each situation (event or periodic call during the measured window) is stored as a SUMO
state, the environment's Python state and a JSON file with its text, under
results/tmp/llm/situations/<out>/. Test seeds (0-999) are refused.
"""

from __future__ import annotations

import argparse

from cotraffic.controllers.registry import make_controller
from cotraffic.llm.advised import AdvisorConfig
from cotraffic.llm.rollout import EpisodeSpec, record
from cotraffic.paths import CHECKPOINTS_DIR, RESULTS_DIR
from cotraffic.seeds import TEST_SEEDS

SCENARIOS = [
    ["incident"],
    ["emergency"],
    ["sensor_noise"],
    ["comm_dropout_30"],
    ["pedestrians"],
    [],
]
WARMUP = {"validation": 600.0, "evaluation": 900.0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument("--out", default="validation")
    parser.add_argument("--net", default="grid4x4")
    parser.add_argument("--demand", default="peak")
    parser.add_argument("--train", type=int, default=1, help="COOP-FULL training run")
    args = parser.parse_args()
    if args.seed in TEST_SEEDS:
        parser.error("test seeds are never used to build prompts or tune the advisor")

    base = make_controller(
        "coop_full", CHECKPOINTS_DIR / "coop_full" / args.net / f"seed{args.train}.zip"
    )
    folder = RESULTS_DIR / "tmp" / "llm" / "situations" / args.out
    cfg = AdvisorConfig()
    total = 0
    for scen in SCENARIOS:
        spec = EpisodeSpec(args.net, args.demand, scen, args.seed)
        stored = record(base, spec, folder, cfg, after_s=WARMUP[spec.mode])
        total += len(stored)
        print(f"{'+'.join(scen) or 'normal':16s} {len(stored):3d} situations")
    print(f"{total} situations in {folder}")


if __name__ == "__main__":
    main()
