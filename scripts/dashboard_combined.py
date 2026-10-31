"""Data of the dashboard pages on the combined study (frontend/public/data/combined/).

    python scripts/dashboard_combined.py

Every number those pages show is computed here from the result files, with the functions
of combined_analysis.py (frozen with the preregistration) and of combined_figures.py:

* ``study.json``: the protocol and the size of the final evaluation (the rigour banner);
* ``cells.json``: per situation, controller and measure, the mean and its 95 % interval
  (bootstrap over the training runs and the test seeds);
* ``tests.json``: every test of the frozen analysis (families hybrid, hybrid-sup,
  hybrid-ablation), with the means, the interval, the Holm p-value and the verdict;
* ``layers.json``: the ablation of the layers (COOP-FULL -> V1 -> H2 -> H3), no test;
* ``validation.json``: the ranking of the variants on the validation seeds 1000-1002,
  where the candidate was chosen (before any test seed);
* ``bilan.json``: the candidate against each reference (exploratory, without Holm);
* ``bigcity.json``: the stopped big-city attempts (docs/FAILURES.md, F-016), validation
  seed 1000 only, never evaluation results.

The pages only translate codes and format numbers; they write no number of their own.
"""

from __future__ import annotations

import json
import re
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import combined_analysis as ca  # noqa: E402
import combined_figures as cf  # noqa: E402

from cotraffic import config  # noqa: E402
from cotraffic.analysis.stats import crossed_bootstrap_ci  # noqa: E402
from cotraffic.paths import REPO_ROOT, RESULTS_DIR  # noqa: E402

OUT = REPO_ROOT / "frontend" / "public" / "data" / "combined"
FINAL = RESULTS_DIR / "combined"
VALIDATION = RESULTS_DIR / "exploration" / "combined"
BIGCITY = RESULTS_DIR / "bigcity"
PREREG = "2c0dd1d"  # docs/COMBINED_PREREGISTRATION.md, frozen; every final row carries it

# (dashboard code, method, parameter) of every controller of the final evaluation
CONTROLLERS = [
    ("hybrid_h2", "hybrid_h2", 4.0),
    ("mp", "mp", None),
    ("ev_rule_mp", "ev_rule_mp", None),
    ("coop_full", "coop_full", None),
    ("team_rules", "team_rules", None),  # our teammate's work (controllers/llm_team/PROVENANCE.md)
    ("ped_rule_mp", "ped_rule_mp", None),
    ("hybrid_h1", "hybrid_h1", 90.0),
    ("hybrid_h3", "hybrid_h3", 90.0),
    ("coop_full_evrule_switch", "coop_full_evrule_switch", None),
    ("coop_full_pedrule_switch", "coop_full_pedrule_switch", None),
]
METRICS = {
    "mean_travel_time": "travel",
    "mean_waiting_time": "waiting",
    "ev_delay": "ambulances",
    "ped_mean_waiting_time": "pedestrians",
}
VARIANTS = {label: code for (code, _), label in
            zip(ca.LABELS, ca.LABELS.values(), strict=True)}  # fmt: skip
VERDICTS = {
    "non inférieure (démontré)": "noninf",
    "vraie perte": "loss",
    "vraie perte (au-delà de −2 %)": "lossBeyond",
    "intervalle trop large pour conclure": "wide",
    "meilleure (démontré)": "best",
    "supériorité non démontrée": "notSup",
}


def write(name: str, data) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=1, ensure_ascii=False, allow_nan=False)
    (OUT / f"{name}.json").write_text(text + "\n", encoding="utf-8")
    print(OUT / f"{name}.json")


def split(case: str) -> dict:
    network, scenario, demand = case.split()
    return {"network": network, "scenario": scenario, "demand": demand}


def r(v, digits: int = 2):
    return None if v is None or not np.isfinite(v) else round(float(v), digits)


# ---------------------------------------------------------------- study
def study(df: pd.DataFrame, tests: pd.DataFrame) -> dict:
    protocol = config.load_protocol()
    commits = sorted(df.git_commit.astype(str).unique())
    ranks = [pd.read_csv(VALIDATION / f"rank_s{s}.csv") for s in (1000, 1001, 1002)]
    main = tests[tests.famille == "hybrid"]
    return {
        "source": f"results/combined/raw ({len(df)} rows), analysis_tests.csv, "
        "configs/protocol.yaml, results/exploration/combined/rank_s100*.csv",
        "prereg": PREREG,
        "commits": commits,
        "episodes": int(len(df)),
        "episodeMinutes": round(
            sum(protocol["evaluation"][k] for k in ("warmup_s", "measure_s", "cooldown_s")) / 60
        ),
        "testSeeds": sorted(int(s) for s in df.seed.unique()),
        "models": int(df.run.dropna().nunique()),
        "situations": int(df.groupby(["network", "scenario", "demand"]).ngroups),
        "tests": int(len(main)),
        "marginPct": ca.MARGIN,
        "alpha": ca.ALPHA,
        "bootstrapDraws": ca.N_BOOT,
        "validationSeeds": [1000, 1001, 1002],
        "variantsTried": int(max(len(t) for t in ranks)),
        "perturbations": perturbations(),
        "candidate": {
            "beta": ca.CANDIDATE[1],
            "decisionS": int(protocol["timing"]["delta_time"]),
            "evRangeM": int(protocol["baselines"]["ev_preemption_range_m"]),
            "minGreenS": int(protocol["timing"]["min_green"]),
            "maxRedS": int(protocol["timing"]["max_red"]),
        },
    }


def perturbations() -> dict:
    """The perturbations of the robustness cells and the generalisation network, read from
    their configs (the page describes them with these numbers)."""
    import combined_eval as ce

    noise = config.load("scenarios", "sensor_noise")["sensor_noise"]
    dropout = config.load("scenarios", "comm_dropout_30")["comm_dropout"]
    buses = config.load("scenarios", "buses")["buses"]

    def lights(network: str) -> int:
        grid = config.load("networks", network)["grid"]
        return int(grid["x"] * grid["y"])

    return {
        "sensorNoise": {
            "countStdVeh": float(noise["count_std_veh"]),
            "failedPct": round(100 * float(noise["failed_fraction"])),
        },
        "commDropout": {"lossPct": round(100 * float(dropout["p"])), "mode": dropout["mode"]},
        "buses": {"periodMin": round(float(buses["period_s"]) / 60)},
        "generalisation": {
            network: {"trainedOn": trained, "lights": lights(network),
                      "trainedLights": lights(trained)}
            for network, trained in ce.TRAINED_ON.items()
        },
    }  # fmt: skip


# ---------------------------------------------------------------- cells
def played(cell: pd.DataFrame, method: str, scenario: str) -> str | None:
    """None if the controller was played in the cell, else what it is by construction."""
    if (cell.method == method).any():
        return None
    same = ca.reduces_to(method, scenario)
    return same if same != method else "absent"


def cells(df: pd.DataFrame) -> list[dict]:
    out = []
    groups = {k: g for k, g in df.groupby(["network", "scenario", "demand"])}
    for case in cf.ORDER:
        key = tuple(case.split())
        cell = groups[key]
        scenario = key[1]
        metrics = ["mean_travel_time", "mean_waiting_time"]
        metrics += ["ev_delay"] if scenario == "emergency" else []
        metrics += ["ped_mean_waiting_time"] if scenario == "pedestrians" else []
        rows = []
        for code, method, param in CONTROLLERS:
            same = played(cell, method, scenario)
            if same == "absent":
                continue
            values = {}
            for metric in metrics:
                t = ca.table(cell, method, param, metric).to_numpy()
                if not t.size or np.isnan(t).all():
                    continue
                mean, lo, hi = crossed_bootstrap_ci(t)
                values[METRICS[metric]] = {"mean": r(mean), "low": r(lo), "high": r(hi),
                                           "n": int(np.isfinite(t).sum())}  # fmt: skip
            rows.append({"controller": code, "sameAs": same, "values": values})
        out.append({**split(case), "controllers": rows})
    return out


# ---------------------------------------------------------------- tests
def all_tests(tests: pd.DataFrame) -> list[dict]:
    sup = tests[tests.famille == "hybrid-sup"].set_index(["case", "métrique"])
    out = []
    for row in tests.to_dict("records"):
        verdict = VERDICTS[row["verdict"]]
        key = (row["case"], row["métrique"])
        item = {
            "family": row["famille"],
            "variant": VARIANTS[row["variante"]],
            **split(row["case"]),
            "metric": "travel" if row["métrique"] == "trajet" else "waiting",
            "reference": row["référence"],
            "referenceMean": r(row["moyenne référence"]),
            "variantMean": r(row["moyenne variante"]),
            "gain": r(row["gain (%)"]),
            "low": r(row["IC bas"]),
            "high": r(row["IC haut"]),
            "pHolm": r(row["p Holm"], 5),
            "cliff": r(row["Cliff"], 3),
            "n": row["n"],
            "verdict": verdict,
        }
        if row["famille"] == "hybrid":  # the verdict of the forest plot
            superior = VERDICTS[sup.loc[key, "verdict"]] == "best"
            item["pHolmSup"] = r(sup.loc[key, "p Holm"], 5)
            item["verdict"] = "best" if superior else verdict
        out.append(item)
    return out


# ---------------------------------------------------------------- layers
LAYERS = [("coop_full", "coop_full", None),
          ("coop_full_evrule_switch", "coop_full_evrule_switch", None),
          ("hybrid_h2", "hybrid_h2", 4.0), ("hybrid_h3", "hybrid_h3", 90.0)]  # fmt: skip


def layers(df: pd.DataFrame) -> list[dict]:
    """The same means as the section "Ablation des couches" of analysis.md."""
    groups = {k: g for k, g in df.groupby(["network", "scenario", "demand"])}
    out = []
    for case in cf.ORDER:
        cell = groups[tuple(case.split())]
        line = {**split(case), "layers": []}
        for code, method, param in LAYERS:
            values = {}
            for metric in ("mean_travel_time", "mean_waiting_time"):
                base = float(np.nanmean(ca.table(cell, "coop_full", None, metric).to_numpy()))
                t = ca.table(cell, method, param, metric).to_numpy()
                v = float(np.nanmean(t)) if t.size else np.nan
                gain = r(100 * (base - v) / base, 1)
                values[METRICS[metric]] = {"mean": r(v, 1), "gainVsCoopFull": gain}
            line["layers"].append({"layer": code, "values": values})
        out.append(line)
    return out


# ---------------------------------------------------------------- validation
CODE_PATTERNS = [
    (r"^H3 : H2 β = 4, MP partout si file d'entrée > quantile (\d+) %", "hybrid_h3", "q"),
    (r"^H2 : COOP-FULL \+ biais MP β = (\d+)", "hybrid_h2", "beta"),
    (r"^H1 : COOP-FULL / MP selon la congestion, quantile (\d+) %", "hybrid_h1", "q"),
    (r"^COOP-FULL \+ EV-RULE \+ PED-RULE", "coop_full_pedrule_switch", None),
    (r"^COOP-FULL \+ EV-RULE \+ ses règles piétons", "coop_full_teamped_switch", None),
    (r"^V1 : COOP-FULL \+ EV-RULE", "coop_full_evrule_switch", None),
    (r"^COOP-FULL seul", "coop_full", None),
]


def variant_code(label: str) -> dict:
    for pattern, code, param in CODE_PATTERNS:
        m = re.match(pattern, label)
        if m:
            value = float(m.group(1)) if param else None
            return {"variant": code, "param": param, "value": value}
    raise ValueError(f"unknown variant: {label}")


def validation() -> dict:
    seeds = []
    for seed in (1000, 1001, 1002):
        t = pd.read_csv(VALIDATION / f"rank_s{seed}.csv")
        seeds.append({
            "seed": seed,
            "rows": [{**variant_code(row["variant"]), "rank": int(row["rank"]),
                      "label": row["variant"], "cells": int(row["cells"]),
                      "betterOrEqual": int(row["better_or_equal"]),
                      "uncertain": int(row["uncertain"]), "worse": int(row["worse"]),
                      "evDelay": r(row["ev_delay"]), "pedWait": r(row["ped_wait"])}
                     for row in t.to_dict("records")],
        })  # fmt: skip
    return {"source": "results/exploration/combined/rank_s1000.csv, rank_s1001.csv, "
            "rank_s1002.csv (rules: docs/COMBINED_PREREGISTRATION.md, section 0)",
            "seeds": seeds}  # fmt: skip


# ---------------------------------------------------------------- bilan
BILAN = {"meilleure": "better", "pas d'écart démontré": "same",
         "moins bonne, de moins de 2 %": "worseSmall",
         "moins bonne, de 2 % ou plus": "worseLarge"}  # fmt: skip
REF_CODES = {"MP": "mp", "EV-RULE-MP": "ev_rule_mp", "COOP-FULL": "coop_full",
             "TEAM-RULES": "team_rules", "PED-RULE-MP": "ped_rule_mp"}  # fmt: skip
CRITERIA = {"trajet": "travel", "attente": "waiting", "ambulances": "ambulances",
            "piétons": "pedestrians"}  # fmt: skip


def bilan() -> dict:
    summary = pd.read_csv(FINAL / "bilan_references.csv")
    detail = pd.read_csv(FINAL / "bilan_detail.csv")
    return {
        "source": "results/combined/bilan_references.csv, bilan_detail.csv "
        "(scripts/combined_figures.py)",
        "references": [{"reference": REF_CODES[row["référence"]],
                        **{BILAN[k]: int(row[k]) for k in BILAN}, "criteria": int(row["critères"])}
                       for row in summary.to_dict("records")],
        "detail": [{"reference": REF_CODES[row["référence"]], **split(row["case"]),
                    "criterion": CRITERIA[row["critère"]], "gain": r(row["gain (%)"]),
                    "low": r(row["IC bas"]), "high": r(row["IC haut"]),
                    "verdict": BILAN[row["verdict (IC à 95 %)"]]}
                   for row in detail.to_dict("records")],
    }  # fmt: skip


# ---------------------------------------------------------------- big city (F-016)
def bigcity() -> dict:
    cities = []
    for name in ("barcelona", "paris"):
        lights = json.loads((BIGCITY / f"{name}_lights.json").read_text(encoding="utf-8"))
        cities.append({"network": name, "lights": lights["lights"], "driven": lights["driven"],
                       "drivenLightsPct": lights["driven_share_lights_pct"],
                       "drivenLanesPct": lights["driven_share_lanes_pct"],
                       "wideLights": lights["wide_lights"]})  # fmt: skip
    sweep = pd.read_csv(BIGCITY / "calibration" / "sweep.csv")
    method = sweep.run_id.str.extract(r"^(\w+?)(?:-x[\d.]+)?__", expand=False)
    return {
        "source": "results/bigcity/*_lights.json, results/bigcity/calibration/sweep.csv "
        "(scripts/bigcity.py; docs/FAILURES.md, F-016)",
        "status": "stopped",
        "seed": 1000,
        "cities": cities,
        "parisSweep": [{"controller": m, "vehPerH": int(row["veh_per_h"]),
                        "waiting": r(row["mean_waiting_time"], 1),
                        "travel": r(row["mean_travel_time"], 1),
                        "teleports": int(row["teleports_total"]),
                        "unfinished": int(row["unfinished"])}
                       for m, row in zip(method, sweep.to_dict("records"), strict=True)],
    }  # fmt: skip


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    warnings.filterwarnings("ignore", category=RuntimeWarning)  # means of empty tables
    every = ca.load(FINAL / "raw")
    df = every[every.method != "hybrid_h2_llm"]  # the LLM variant has its own page
    tests = pd.read_csv(FINAL / "analysis_tests.csv")
    src = "results/combined/raw (preregistration 2c0dd1d, test seeds 0-4)"
    write("study", study(every, tests))
    write("cells", {"source": src, "cells": cells(df)})
    frozen = "results/combined/analysis_tests.csv (scripts/combined_analysis.py, frozen)"
    write("tests", {"source": frozen, "tests": all_tests(tests)})
    write("layers", {"source": src, "cells": layers(df)})
    write("validation", validation())
    write("bilan", bilan())
    write("bigcity", bigcity())


if __name__ == "__main__":
    main()
