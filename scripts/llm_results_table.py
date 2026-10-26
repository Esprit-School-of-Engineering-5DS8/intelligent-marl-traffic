"""The validation results of the LLM work in one table, computed from the result files.

    python scripts/llm_results_table.py                 # final dataset (default)
    python scripts/llm_results_table.py --set prelim    # preliminary dataset

Seed 1000 (63 validation situations, 300 s replays from the same snapshot). Gain on
waiting: positive = better than PPO alone. Recall and false advice are measured against
the validation labels of the dataset the Kaggle notebook was run on:
* final (results/exploration/llm_lora/llm_lora_val.jsonl): 15 situations labelled with
  an advice, 48 with abstention; models trained on 169 examples (seeds 100001-100003);
* prelim (llm_lora/preliminary/): 8 with an advice, 55 with abstention; 69 examples.
Writes results/exploration/llm_summary/validation_table[_prelim].csv and prints a
Markdown table.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from llm_dataset import candidates, placebo  # noqa: E402

from cotraffic.llm.rollout import Stored  # noqa: E402
from cotraffic.llm.sources import RuleSource  # noqa: E402
from cotraffic.paths import RESULTS_DIR  # noqa: E402

EXPL = RESULTS_DIR / "exploration"
SETS = {
    "final": {
        "labels": EXPL / "llm_lora" / "llm_lora_val.jsonl",
        "kaggle": EXPL / "llm_lora" / "final_lora_comparison.csv",
        "replay": EXPL / "llm_benchmark" / "final_kaggle_val_summary.csv",
        "note": "préliminaire : 169 exemples d'entraînement ; latence sur GPU T4",
        "out": "validation_table.csv",
    },
    "prelim": {
        "labels": EXPL / "llm_lora" / "preliminary" / "llm_lora_val.jsonl",
        "kaggle": EXPL / "llm_benchmark" / "results" / "lora_comparison.csv",
        "replay": EXPL / "llm_benchmark" / "prelim_kaggle_val_summary.csv",
        "note": "préliminaire : 69 exemples d'entraînement ; latence sur GPU T4",
        "out": "validation_table_prelim.csv",
    },
}
SITUATIONS = RESULTS_DIR / "tmp" / "llm" / "situations" / "validation"
OUT = EXPL / "llm_summary"


def pairs_of_wire(text: str) -> set[tuple[str, int]]:
    return {(j, p) for j, p, *_ in json.loads(text)["a"]}


def pairs_of_advice(advice) -> set[tuple[str, int]]:
    items = advice["a"] if isinstance(advice, dict) else advice.a
    return {(i["j"], i["p"]) if isinstance(i, dict) else (i.j, i.p) for i in items}


def measures(preds: dict[str, set | None], gold: dict[str, set]) -> dict:
    """preds: situation -> advised (junction, phase) pairs, None for an invalid answer."""
    ids = list(gold)
    advice_ids = [s for s in ids if gold[s]]
    abstain_ids = [s for s in ids if not gold[s]]
    need = sum(len(gold[s]) for s in advice_ids)
    hit = sum(len((preds.get(s) or set()) & gold[s]) for s in advice_ids)
    return {
        "json_valid_%": round(100 * sum(preds.get(s) is not None for s in ids) / len(ids)),
        "abstention_%": round(100 * sum(preds.get(s) == set() for s in ids) / len(ids)),
        "advice_recall_%": round(100 * hit / need) if need else None,
        "false_advice_%": round(
            100 * sum(bool(preds.get(s)) for s in abstain_ids) / len(abstain_ids)
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--set", choices=list(SETS), default="final")
    conf = SETS[parser.parse_args().set]
    gold = {}  # [Exigence 8] tableau final de la validation (graine 1000)
    for line in conf["labels"].read_text(encoding="utf-8").splitlines():
        ex = json.loads(line)
        gold[ex["id"]] = pairs_of_wire(ex["messages"][-1]["content"])
    n_advice = sum(bool(g) for g in gold.values())
    oracle = pd.read_csv(EXPL / "llm_oracle" / "oracle_summary.csv").set_index("situations")
    allrow = oracle.loc["all"]
    stored = {p.stem: Stored.load(p) for p in sorted(SITUATIONS.glob("*.json"))}

    rows = []

    def add(name, gain, preds, latency, source, note=""):
        m = measures(preds, gold) if preds is not None else {}
        rows.append(
            {
                "controller": name,
                "gain_waiting_%": gain,
                **m,
                "latency_s": latency,
                "latency_where": "local" if latency else "",
                "source": source,
                "note": note,
            }
        )

    rows.append(
        {
            "controller": "PPO seul (COOP-FULL)",
            "gain_waiting_%": 0.0,
            "latency_s": None,
            "source": "référence",
            "note": "aucun conseil",
        }
    )
    add("Toujours s'abstenir", 0.0, {s: set() for s in gold}, None, "référence triviale")
    rules = {s: pairs_of_advice(RuleSource().advise(stored[s].situation).advice) for s in gold}
    add(
        "Règles",
        float(allrow["rules_%"]),
        rules,
        None,
        "llm_oracle/oracle_summary.csv",
        "étiquettes construites à partir des règles : rappel de 100 % par construction",
    )
    src = placebo()
    draws = [
        {s: pairs_of_advice(candidates(stored[s], True, src)[f"placebo_{k}"]) for s in gold}
        for k in (1, 2, 3)
    ]
    m = pd.DataFrame([measures(d, gold) for d in draws]).mean().round(0)
    rows.append(
        {
            "controller": "Placebo (moyenne de 3 tirages)",
            "gain_waiting_%": float(allrow["placebo_%"]),
            **m.to_dict(),
            "latency_s": None,
            "source": "llm_oracle/oracle_summary.csv",
            "note": "conseils au hasard, même amplitude que le LLM",
        }
    )
    calls = pd.read_csv(EXPL / "llm_benchmark" / "v2_tech_calls.csv", keep_default_na=False)
    calls = calls[(calls.model == "qwen2.5:3b") & (calls.technique == "zero")]
    llm = {
        r.situation: (pairs_of_advice(json.loads(r.advice)) if r.advice else None)
        for r in calls.itertuples()
    }
    add(
        "LLM zero-shot qwen2.5:3b",
        float(allrow["llm_%"]),
        llm,
        round(calls.latency_s.median(), 1),
        "llm_benchmark/v2_tech_calls.csv ; llm_oracle/oracle_summary.csv",
        "latence Ollama locale (p50)",
    )
    rows.append(
        {
            "controller": "Oracle (meilleur candidat, après coup)",
            "gain_waiting_%": float(allrow["oracle_%"]),
            "latency_s": None,
            "source": "llm_oracle/oracle_summary.csv",
            "note": "borne haute",
        }
    )
    kaggle = pd.read_csv(conf["kaggle"]).set_index("technique")
    replay = pd.read_csv(conf["replay"]).set_index("technique")
    for tech, name in (
        ("base", "Base 0,5B (sans entraînement)"),
        ("lora", "LoRA 0,5B"),
        ("prompt_tuning", "Prompt tuning 0,5B"),
    ):
        k = kaggle.loc[tech]
        gain = float(replay.loc[tech, "gain_waiting_%"]) if tech in replay.index else 0.0
        rows.append(
            {
                "controller": name,
                "gain_waiting_%": gain,
                "json_valid_%": int(k["json_valid_%"]),
                "abstention_%": int(k["abstention_%"]),
                "advice_recall_%": int(k["advice_recall_%"]),
                "false_advice_%": int(k["false_advice_%"]),
                "latency_s": float(k["t4_latency_s"]),
                "latency_where": "T4",
                "source": f"{conf['kaggle'].name} ; {conf['replay'].name}",
                "note": conf["note"],
            }
        )
    table = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT / conf["out"], index=False)
    print(f"{len(gold)} validation situations, {n_advice} labelled with an advice\n")

    def fmt(v, unit="%"):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return "–"
        if unit == "gain" and abs(v) < 0.005:
            return "0,00 %"
        return (
            f"{v:+.2f} %".replace(".", ",")
            if unit == "gain"
            else f"{int(v)} %"
            if unit == "%"
            else f"{v:.1f} s".replace(".", ",")
        )

    print(
        "| Contrôleur | Gain sur l'attente | JSON valide | Abstention "
        "| Rappel des conseils | Faux conseils | Latence |"
    )
    print("|---|---|---|---|---|---|---|")

    def where(r):
        w = r.get("latency_where")
        return f" ({w})" if isinstance(w, str) and w and r["latency_s"] is not None else ""

    for r in table.to_dict("records"):
        print(
            f"| {r['controller']} | {fmt(r['gain_waiting_%'], 'gain')} "
            f"| {fmt(r.get('json_valid_%'))} | {fmt(r.get('abstention_%'))} "
            f"| {fmt(r.get('advice_recall_%'))} | {fmt(r.get('false_advice_%'))} "
            f"| {fmt(r['latency_s'], 's')}{where(r)} |"
        )


if __name__ == "__main__":
    main()
