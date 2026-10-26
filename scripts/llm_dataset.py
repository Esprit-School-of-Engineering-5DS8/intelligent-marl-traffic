"""Oracle on validation, and the LoRA / prompt-tuning dataset from training seeds.

    python scripts/llm_situations.py --seed 100002 --out train2      # more training situations
    python scripts/llm_dataset.py --train few train2 train3 --val validation [--jobs 6]
    python scripts/llm_dataset.py --summary-only                      # tables from saved replays

Every situation is replayed for 300 s from its snapshot with each candidate advice: none,
the rule-based advice, the rules with every item at strength 2 and 3, and (validation
only) 3 placebo draws (RandomSource with the distributions of the LLM's validation advice).
All candidates apply after the same delay, the LLM's median validation latency (8.2 s),
as in the pre-registration. Gains: positive = better (less waiting, EV stops x 10).

Validation (seed 1000): PPO alone (0), rules, LLM (qwen2.5:3b zero, from v2_tech, its own
measured latency), placebo (mean of the draws), oracle (best candidate of each situation,
LLM included, chosen afterwards: an upper bound) -> results/exploration/llm_oracle/.

Dataset (results/exploration/llm_lora/): one chat example per situation, the zero-shot
prompt as input and, as the answer, the best structured candidate (rules family) if it
gains at least --min-gain %, else the empty advice (abstention). Training situations come
from training seeds only; validation situations (seed 1000) are only used for measuring.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from llm_benchmark import _score  # noqa: E402  (same replay as the benchmark)

from cotraffic.llm.advice import Advice, Item, parse, to_wire, weight_of  # noqa: E402
from cotraffic.llm.progress import Progress  # noqa: E402
from cotraffic.llm.prompts import load  # noqa: E402
from cotraffic.llm.rollout import Stored  # noqa: E402
from cotraffic.llm.settings import load_settings  # noqa: E402
from cotraffic.llm.sources import RandomSource, RuleSource  # noqa: E402
from cotraffic.paths import RESULTS_DIR  # noqa: E402
from cotraffic.seeds import TEST_SEEDS, TRAINING_SEED_BASE  # noqa: E402
from cotraffic.utils.io import git_commit  # noqa: E402

SITUATIONS = RESULTS_DIR / "tmp" / "llm" / "situations"
BENCH = RESULTS_DIR / "exploration" / "llm_benchmark"
ORACLE = RESULTS_DIR / "exploration" / "llm_oracle"
DATASET = RESULTS_DIR / "exploration" / "llm_lora"
STRUCTURED = ("rules", "rules_s2", "rules_s3")
LLM_LABEL = "qwen2.5:3b|zero"


def kind_of(stored: Stored) -> str:
    kinds = sorted(e["kind"] for e in stored.situation.events)
    return kinds[0] if kinds else "none"


def placebo() -> RandomSource:
    """Placebo with the amplitude of the LLM's validation advice (v2_tech, zero)."""
    calls = pd.read_csv(BENCH / "v2_tech_calls.csv", keep_default_na=False)
    calls = calls[(calls.model == "qwen2.5:3b") & (calls.technique == "zero")]
    counts, weights, validities = [], [], []
    for text in calls.advice:
        items = json.loads(text)["a"] if text else []
        counts.append(len(items))
        weights += [i["w"] for i in items]
        validities += [i["s"] for i in items]
    return RandomSource(counts, weights, validities)


def candidates(stored: Stored, with_placebo: bool, source: RandomSource) -> dict[str, Advice]:
    rules = RuleSource().advise(stored.situation).advice  # [Exigence 6] candidats rejoués
    out: dict[str, Advice] = {}
    if rules.a:
        out["rules"] = rules
        for strength in (2, 3):
            out[f"rules_s{strength}"] = Advice(
                a=[Item(j=i.j, p=i.p, w=weight_of(strength), s=i.s) for i in rules.a], r=""
            )
    if with_placebo:
        for k in range(1, 4):
            source.reset(int(stored.situation.time) * 10 + k)
            out[f"placebo_{k}"] = source.advise(stored.situation).advice
    return out


def replay(sets: dict[str, list[Path]], args, source: RandomSource) -> pd.DataFrame:
    tasks = []
    for split, paths in sets.items():
        for p in paths:
            s = Stored.load(p)
            tasks.append((str(p), "none", "", 0.0, args.horizon, args.beta))
            for label, adv in candidates(s, split == "val", source).items():
                if adv.a:
                    tasks.append(
                        (str(p), label, adv.model_dump_json(), args.delay, args.horizon, args.beta)
                    )
    progress = Progress("replays", len(tasks), every=10)
    rows = []
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        for row in pool.map(_score, tasks, chunksize=4):
            rows.append(row)
            progress.tick()
    df = pd.DataFrame(rows)
    df["commit"] = git_commit()
    return df


def gains(df: pd.DataFrame) -> pd.DataFrame:  # [Exigence 8] gain en %, positif = mieux
    """One row per situation, one column per candidate: gain in % (missing = 0)."""
    base = df[df.label == "none"].set_index("situation")
    out = pd.DataFrame(index=base.index)
    out["kind"] = base["kind"]
    for label, g in df[df.label != "none"].groupby("label"):
        g = g.set_index("situation")
        b = base.loc[g.index]
        gain = (
            100
            * ((b.waiting_veh_s - g.waiting_veh_s) + 10 * (b.ev_stopped_s - g.ev_stopped_s))
            / b.waiting_veh_s.clip(lower=1)
        )
        out[label] = gain.reindex(out.index).fillna(0.0)
    return out


def oracle_tables(val: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    llm = pd.read_csv(BENCH / "v2_tech_scores.csv")  # [Exigence 8] placebo, règles, LLM et oracle
    llm = gains(llm[llm.label.isin(["none", LLM_LABEL])])
    val = val.copy()
    val["llm"] = llm[LLM_LABEL].reindex(val.index).fillna(0.0)
    placebos = [c for c in val if c.startswith("placebo_")]
    cand = [c for c in (*STRUCTURED, *placebos, "llm") if c in val]
    val["placebo"] = val[placebos].mean(axis=1) if placebos else 0.0
    val["oracle"] = val[cand].clip(lower=0).max(axis=1)  # "none" (0) is a candidate
    val["oracle_choice"] = np.where(val[cand].max(axis=1) > 0, val[cand].idxmax(axis=1), "none")
    rows = []
    groups = [("all", val), ("any event", val[val.kind != "none"])]
    groups += list(val.groupby("kind"))
    for name, g in groups:
        rows.append(
            {
                "situations": name,
                "n": len(g),
                "ppo_alone_%": 0.0,
                "rules_%": round(g["rules"].mean(), 2) if "rules" in g else 0.0,
                "llm_%": round(g["llm"].mean(), 2),
                "placebo_%": round(g["placebo"].mean(), 2),
                "oracle_%": round(g["oracle"].mean(), 2),
            }
        )
    choice = val.oracle_choice.str.replace(r"placebo_\d", "placebo", regex=True)
    return pd.DataFrame(rows), choice.value_counts().rename_axis("best").reset_index()


def label_of(row: pd.Series, min_gain: float) -> str:  # [Exigence 6] l'étiquette apprise par LoRA
    cols = [c for c in STRUCTURED if c in row and row[c] >= min_gain]
    return max(cols, key=lambda c: row[c]) if cols else "abstain"


def write_dataset(name: str, paths: list[Path], g: pd.DataFrame, args) -> pd.DataFrame:
    prompt = load(args.prompt_version, "zero")  # [Exigence 6] jeu de données LoRA (JSONL)
    rows, lines = [], []
    for p in paths:
        s = Stored.load(p)
        row = g.loc[s.id]
        label = label_of(row, args.min_gain)
        advice = Advice(a=[], r="") if label == "abstain" else candidates(s, False, None)[label]
        answer = to_wire(advice)
        assert parse(answer) is not None
        messages = prompt.messages(s.situation.to_text())
        lines.append(
            json.dumps(
                {
                    "id": s.id,
                    "split": name,
                    "kind": kind_of(s),
                    "label": label,
                    "gain_%": round(float(row[label]) if label != "abstain" else 0.0, 3),
                    "messages": [*messages, {"role": "assistant", "content": answer}],
                },
                ensure_ascii=False,
            )
        )
        rows.append({"id": s.id, "kind": kind_of(s), "label": label})
    DATASET.mkdir(parents=True, exist_ok=True)
    (DATASET / f"llm_lora_{name}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return pd.DataFrame(rows)


def main() -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--train", nargs="+", default=["few"])
    parser.add_argument("--val", default="validation")
    parser.add_argument("--beta", type=float, default=settings.advisor.beta)
    parser.add_argument("--delay", type=float, default=8.2, help="s, same for all candidates")
    parser.add_argument("--horizon", type=float, default=300.0)
    parser.add_argument("--min-gain", type=float, default=0.25)
    parser.add_argument("--jobs", type=int, default=6)
    parser.add_argument("--prompt-version", default=settings.prompt_version)
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args()

    train = [p for name in args.train for p in sorted((SITUATIONS / name).glob("*.json"))]
    val = sorted((SITUATIONS / args.val).glob("*.json"))
    for p in train:
        seed = Stored.load(p).spec.seed
        if seed < TRAINING_SEED_BASE:
            raise SystemExit(f"{p.name}: training examples must come from training seeds")
    if any(Stored.load(p).spec.seed in TEST_SEEDS for p in val):
        raise SystemExit("test seeds are never used here")

    ORACLE.mkdir(parents=True, exist_ok=True)
    scores_csv = ORACLE / "replays.csv"
    if args.summary_only:
        df = pd.read_csv(scores_csv)
    else:
        df = replay({"train": train, "val": val}, args, placebo())
        df.to_csv(scores_csv, index=False)
    val_ids = {Stored.load(p).id for p in val}
    g = gains(df)
    table, choices = oracle_tables(g[g.index.isin(val_ids)])
    table.to_csv(ORACLE / "oracle_summary.csv", index=False)
    choices.to_csv(ORACLE / "oracle_choices.csv", index=False)
    print("Validation (seed 1000), mean gain on waiting, positive = better:")
    print(table.to_string(index=False))
    print(choices.to_string(index=False))

    train_labels = write_dataset("train", train, g, args)
    val_labels = write_dataset("val", val, g, args)
    for name, labels in (("train", train_labels), ("val", val_labels)):
        print(f"{name}: {len(labels)} examples, labels {labels.label.value_counts().to_dict()}")


if __name__ == "__main__":
    main()
