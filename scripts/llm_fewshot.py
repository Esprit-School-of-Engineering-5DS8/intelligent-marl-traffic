"""Few-shot examples for the advisor prompt, from a training seed only.

    python scripts/llm_situations.py --seed 100001 --out few     # situations first
    python scripts/llm_fewshot.py [--set few] [--beta 4] [--horizon 300] [--min-gain 0.25]
    python scripts/llm_fewshot.py --from-scores      # choose again from the saved replays

For each situation, a few candidate advices (rules, and the rules with every item at
strength 2 or 3) are replayed from its snapshot and scored against no advice. Per kind of
situation (event kind, or "none"), the candidate with the best MEAN gain over all the
situations of that kind is retained (a situation where it has nothing to say counts as a
gain of 0): taking the best single situation would overstate the gain (winner's curse).
If that mean reaches ``--min-gain`` % of the waiting time, the example is the situation
where this candidate helps the most, with its advice as the answer; otherwise the example
teaches abstention: the situation where advice hurts the most, answered with an empty list.
Replays go to results/exploration/llm_fewshot/, examples to
configs/prompts/advisor-v2-examples.jsonl.
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

from cotraffic.llm.advice import Advice, Item, to_wire, weight_of
from cotraffic.llm.progress import Progress
from cotraffic.llm.prompts import examples_path
from cotraffic.llm.rollout import Stored
from cotraffic.llm.sources import RuleSource
from cotraffic.paths import CHECKPOINTS_DIR, RESULTS_DIR
from cotraffic.seeds import TRAINING_SEED_BASE
from cotraffic.utils.io import git_commit

SITUATIONS = RESULTS_DIR / "tmp" / "llm" / "situations"
OUT = RESULTS_DIR / "exploration" / "llm_fewshot"
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
    parser.add_argument("--beta", type=float, default=4.0)
    parser.add_argument("--min-gain", type=float, default=0.25, help="% of the waiting time")
    parser.add_argument("--horizon", type=float, default=300.0)
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--from-scores", action="store_true")
    args = parser.parse_args()

    paths = sorted((SITUATIONS / args.set).glob("*.json"))
    items = {p: Stored.load(p) for p in paths}
    if any(s.spec.seed < TRAINING_SEED_BASE for s in items.values()):
        raise SystemExit("few-shot examples must come from training seeds only")
    scores_csv = OUT / f"{args.set}_beta{args.beta:g}_scores.csv"
    if args.from_scores:
        df = pd.read_csv(scores_csv)
    else:
        df = replay(items, args)
        OUT.mkdir(parents=True, exist_ok=True)
        df.to_csv(scores_csv, index=False)
    choose(items, df, args)


def replay(items: dict, args) -> pd.DataFrame:
    tasks = []
    for p, s in items.items():
        for label, advice in candidates(s).items():
            if advice is not None and not advice.a and label != "none":
                continue  # the rules have nothing to say: same as no advice
            tasks.append(
                (p, label, advice.model_dump_json() if advice else "", args.horizon, args.beta)
            )
    progress = Progress("replays", len(tasks), every=10)
    results = []
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        for result in pool.map(_score, tasks):
            results.append(result)
            progress.tick()
    df = pd.DataFrame(results, columns=["situation", "label", "waiting_veh_s", "ev_stopped_s"])
    df["beta"] = args.beta
    df["horizon_s"] = args.horizon
    df["commit"] = git_commit()
    return df


def kind_of(stored: Stored) -> str:
    kinds = sorted(e["kind"] for e in stored.situation.events)
    return kinds[0] if kinds else "none"


def choose(items: dict, df: pd.DataFrame, args) -> None:
    by_id = {s.id: s for s in items.values()}
    base = df[df.label == "none"].set_index("situation")
    labels = sorted(set(df.label) - {"none"})
    # gain in % of the waiting time without advice; emergency-vehicle stops count 10 times;
    # a candidate with nothing to say in a situation leaves it as it is (gain 0)
    gains = pd.DataFrame(0.0, index=base.index, columns=labels)
    for row in df[df.label != "none"].itertuples():
        b = base.loc[row.situation]
        gains.loc[row.situation, row.label] = (
            100
            * ((b.waiting_veh_s - row.waiting_veh_s) + 10 * (b.ev_stopped_s - row.ev_stopped_s))
            / max(b.waiting_veh_s, 1)
        )
    gains["kind"] = [kind_of(by_id[sid]) for sid in gains.index]
    means = gains.groupby("kind")[labels].mean()
    means["n"] = gains.groupby("kind").size()
    print("mean gain (% of waiting) per kind and candidate:")
    print(means.round(2).to_string())
    means.round(3).to_csv(OUT / f"{args.set}_beta{args.beta:g}_kinds.csv")

    examples = []
    for kind, g in gains.groupby("kind"):
        best = means.loc[kind, labels].astype(float).idxmax()
        mean = float(means.loc[kind, best])
        if mean >= args.min_gain:
            sid, label, gain = g[best].idxmax(), best, float(g[best].max())
        else:  # nothing helps on average: teach abstention where advice hurts the most
            worst = g[labels].min(axis=1)
            sid, label, gain = worst.idxmin(), "abstain", float(worst.min())
        stored = by_id[sid]
        advice = Advice(a=[], r="") if label == "abstain" else candidates(stored)[label]
        examples.append(
            {
                "kind": kind,
                "situation": sid,
                "candidate": label,
                "mean_gain_%": round(mean, 2),
                "gain_%": round(gain, 2),
                "state": stored.situation.to_text(),
                "advice": to_wire(advice),
            }
        )
        print(f"{kind:15s} {label:9s} mean {mean:6.2f} %  example {sid} ({gain:+.2f} %)")
    out = examples_path()
    out.write_text("\n".join(json.dumps(e) for e in examples) + "\n", encoding="utf-8")
    print(f"{len(examples)} examples -> {out}")


if __name__ == "__main__":
    main()
