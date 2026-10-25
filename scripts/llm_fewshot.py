"""Few-shot examples for the advisor prompt, from a training seed only.

    python scripts/llm_situations.py --seed 100001 --out few     # situations first
    python scripts/llm_fewshot.py [--set few] [--per-kind 1] [--beta 2] [--horizon 300]

For each situation with an event, a few candidate advices (rules, and the rules with every
item at strength 2 or 3) are replayed from its snapshot and scored against no advice; per
event kind, the situation where the best candidate gains the most becomes an example, with
that candidate as the answer. Written to configs/prompts/advisor-v2-examples.jsonl.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

from cotraffic.llm.advice import Advice, Item, to_wire, weight_of
from cotraffic.llm.prompts import examples_path
from cotraffic.llm.rollout import Stored
from cotraffic.llm.sources import RuleSource
from cotraffic.paths import CHECKPOINTS_DIR, RESULTS_DIR
from cotraffic.seeds import TRAINING_SEED_BASE

SITUATIONS = RESULTS_DIR / "tmp" / "llm" / "situations"
_WORKER: dict = {}


def candidates(stored: Stored) -> dict[str, Advice]:
    rules = RuleSource().advise(stored.situation).advice
    out = {"none": None, "rules": rules}
    for strength in (2, 3):
        out[f"rules_s{strength}"] = Advice(
            a=[Item(j=i.j, p=i.p, w=weight_of(strength), s=i.s) for i in rules.a], r=""
        )
    return out


def _score(task):
    from cotraffic.controllers.registry import make_controller
    from cotraffic.llm.rollout import make_env, score

    path, label, advice_json, horizon, beta = task
    stored = Stored.load(path)
    if "base" not in _WORKER:
        _WORKER["base"] = make_controller(
            "coop_full", CHECKPOINTS_DIR / "coop_full" / stored.spec.network / "seed1.zip"
        )
        _WORKER["envs"] = {}
    key = (stored.spec.network, tuple(stored.spec.scenarios), stored.spec.seed)
    if key not in _WORKER["envs"]:
        _WORKER["envs"][key] = make_env(stored.spec, _WORKER["base"].agent_cfg)
    advice = Advice.model_validate_json(advice_json) if advice_json else None
    s = score(_WORKER["envs"][key], _WORKER["base"], stored, advice, horizon, beta, 0.0)
    return stored.id, label, s.waiting_veh_s, s.ev_stopped_s


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--set", default="few")
    parser.add_argument("--per-kind", type=int, default=1)
    parser.add_argument("--beta", type=float, default=2.0)
    parser.add_argument("--horizon", type=float, default=300.0)
    parser.add_argument("--jobs", type=int, default=3)
    args = parser.parse_args()

    paths = sorted((SITUATIONS / args.set).glob("*.json"))
    items = {p: Stored.load(p) for p in paths}
    if any(s.spec.seed < TRAINING_SEED_BASE for s in items.values()):
        raise SystemExit("few-shot examples must come from training seeds only")
    tasks = []
    for p, s in items.items():
        if not s.situation.events:
            continue
        for label, advice in candidates(s).items():
            tasks.append(
                (p, label, advice.model_dump_json() if advice else "", args.horizon, args.beta)
            )
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(_score, tasks))

    scores: dict[str, dict[str, tuple[float, float]]] = defaultdict(dict)
    for sid, label, waiting, ev in results:
        scores[sid][label] = (waiting, ev)
    by_kind: dict[str, list[tuple[float, str, str]]] = defaultdict(list)
    for s in items.values():
        sc = scores.get(s.id)
        if not sc:
            continue
        base_wait, base_ev = sc["none"]
        kind = sorted(e["kind"] for e in s.situation.events)[0]
        for label, (waiting, ev) in sc.items():
            if label == "none":
                continue
            # gain: waiting of all vehicles, plus emergency-vehicle stops counted 10 times
            gain = (base_wait - waiting) + 10 * (base_ev - ev)
            by_kind[kind].append((gain, s.id, label))

    examples = []
    for kind, ranked in sorted(by_kind.items()):
        ranked.sort(reverse=True)
        for gain, sid, label in ranked[: args.per_kind]:
            if gain <= 0:
                continue
            stored = next(s for s in items.values() if s.id == sid)
            advice = candidates(stored)[label]
            examples.append(
                {
                    "kind": kind,
                    "situation": sid,
                    "gain": round(gain, 1),
                    "state": stored.situation.to_text(),
                    "advice": to_wire(advice),
                }
            )
            print(f"{kind:15s} {sid}  {label:9s} gain {gain:8.1f}")
    out = examples_path()
    out.write_text("\n".join(json.dumps(e) for e in examples) + "\n", encoding="utf-8")
    print(f"{len(examples)} examples -> {out}")


if __name__ == "__main__":
    main()
