"""Run an experiment matrix (``configs/experiments/<name>.yaml``).

A matrix is a list of cells (network x methods x demands x scenarios) evaluated on the
same seeds. Every run writes its own CSV, so a matrix can be interrupted and resumed,
or split between machines and merged later (``scripts/merge_results.py``): runs whose
result file already exists are skipped unless ``force`` is set.

Learned methods are evaluated with every selected checkpoint found under
``results/checkpoints/<method>/<network>/seed<k>.zip`` (one per training seed), so
their spread includes the variability between training runs.
"""

from __future__ import annotations

import os
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from cotraffic import config
from cotraffic.controllers.registry import BASELINES
from cotraffic.paths import CHECKPOINTS_DIR, LOGS_DIR, RAW_DIR, RESULTS_DIR
from cotraffic.seeds import TEST_SEEDS, check_seeds


@dataclass(frozen=True)
class RunSpec:
    method: str
    network: str
    demand: str
    scenarios: tuple[str, ...]
    seed: int
    checkpoint: str = ""
    tag: str = ""
    quick: bool = False
    ssm: bool = True


def find_checkpoints(method: str, network: str) -> list[tuple[int, Path]]:
    """Selected checkpoints of a learned method, one per training seed."""
    folder = CHECKPOINTS_DIR / method / network
    found = []
    for path in sorted(folder.glob("seed*.zip")):
        try:
            found.append((int(path.stem.removeprefix("seed")), path))
        except ValueError:
            continue
    return found


def expand(exp: dict[str, Any]) -> tuple[list[RunSpec], list[str]]:
    """All runs of an experiment, and warnings for learned methods without checkpoints."""
    specs, warnings = [], []
    quick = bool(exp.get("quick", False))
    seeds = [int(s) for s in exp["seeds"]]
    check_seeds(seeds, TEST_SEEDS, "evaluation")
    for cell in exp["cells"]:
        network = cell["network"]
        trained_on = cell.get("checkpoint_network", network)
        for method in cell["methods"]:
            if method in BASELINES or method == "random":
                variants = [("", "")]
            else:
                ckpts = find_checkpoints(method, trained_on)
                if not ckpts:
                    warnings.append(f"no checkpoint for {method} trained on {trained_on}")
                    continue
                variants = [(str(p), f"t{k}") for k, p in ckpts]
            for demand in cell["demands"]:
                for scenario in cell["scenarios"]:
                    scen = tuple(s for s in scenario.split("+") if s != "normal")
                    for seed in seeds:
                        for ckpt, tag in variants:
                            specs.append(
                                RunSpec(
                                    method,
                                    network,
                                    demand,
                                    scen,
                                    seed,
                                    ckpt,
                                    tag,
                                    quick,
                                    bool(cell.get("ssm", True)),
                                )
                            )
    return specs, warnings


def _dirs(quick: bool) -> tuple[Path, Path]:
    if quick:
        return RESULTS_DIR / "tmp" / "quick_raw", RESULTS_DIR / "tmp" / "quick_logs"
    return RAW_DIR, LOGS_DIR


def _execute(spec_dict: dict[str, Any]) -> tuple[str, str]:
    os.environ.setdefault("LIBSUMO_AS_TRACI", "1")
    from cotraffic.evaluation.runner import run_episode

    spec = RunSpec(**spec_dict)
    raw_dir, logs_dir = _dirs(spec.quick)
    try:
        row = run_episode(
            spec.method,
            spec.network,
            spec.demand,
            list(spec.scenarios),
            spec.seed,
            checkpoint=Path(spec.checkpoint) if spec.checkpoint else None,
            quick=spec.quick,
            ssm=spec.ssm,
            tag=spec.tag,
            raw_dir=raw_dir,
            logs_dir=logs_dir,
        )
        return row["run_id"], ""
    except Exception:  # noqa: BLE001 - reported to the caller, the matrix goes on
        return spec_dict["method"], traceback.format_exc()


def run_matrix(
    name: str, jobs: int = 2, force: bool = False, methods: list[str] | None = None
) -> int:
    """Run (or complete) an experiment; returns the number of failed runs."""
    from cotraffic.evaluation.runner import run_id

    exp = config.load("experiments", name)
    specs, warnings = expand(exp)
    if methods:
        wanted = set(methods)
        if "baselines" in wanted:
            wanted |= set(BASELINES)
        specs = [s for s in specs if s.method in wanted]
    for w in warnings:
        print(f"warning: {w}")
    todo = []
    for spec in specs:
        raw_dir, _ = _dirs(spec.quick)
        rid = run_id(spec.method, spec.network, spec.scenarios, spec.demand, spec.seed, spec.tag)
        if force or not (raw_dir / f"{rid}.csv").is_file():
            todo.append(spec)
    print(f"{name}: {len(specs)} runs, {len(specs) - len(todo)} already done, {len(todo)} to run")
    failures = 0
    with ProcessPoolExecutor(max_workers=max(1, jobs)) as pool:
        futures = {pool.submit(_execute, asdict(s)): s for s in todo}
        for i, future in enumerate(as_completed(futures), 1):
            rid, error = future.result()
            if error:
                failures += 1
                print(f"[{i}/{len(todo)}] FAILED {futures[future]}\n{error}")
            else:
                print(f"[{i}/{len(todo)}] {rid}")
    print(f"{name}: {failures} failed run(s)")
    return failures
